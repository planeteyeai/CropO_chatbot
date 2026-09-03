"""Daily Comprehensive Agronomic Report Fetcher Module.

Fetches composite daily agronomic synthesis (`GET /daily-report?plot_name={plot_id}`)
including all 8 satellite intelligence layers:
  1. agro_stats   2. growth   3. soil_moisture   4. water_uptake
  5. pest_detection   6. npk_analysis   7. current_weather   8. forecast

Caches under `data:plot:{plot_id}:daily_report` in Redis.
"""

from typing import Any, Dict, Optional
import structlog
from app.cache.redis_client import redis_client
from app.config.settings import settings
from app.context.area_units import format_field_dose, format_share, plot_acres_from_payloads
from app.fetchers.base import async_fetch_with_retry
from app.fetchers.cropo_client import cropo_base, cropo_headers

logger = structlog.get_logger(__name__)

TTL_SECONDS = 1800  # 30 mins
DAILY_REPORT_TIMEOUT = 120.0  # Admin.py runs 11 Earth Engine jobs in parallel


def get_daily_report_cache_key(plot_id: str) -> str:
    """Generate Redis key for plot daily report."""
    return f"data:plot:{plot_id.strip()}:daily_report"


def _pct(value: Any, digits: int = 1) -> str:
    """Format a numeric value as percentage string."""
    try:
        return f"{float(value):.{digits}f}%"
    except (TypeError, ValueError):
        return "N/A"


def _pixel_summary(layer: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(layer, dict):
        return {}
    summary = layer.get("pixel_summary")
    return summary if isinstance(summary, dict) else {}


def _build_layer_summaries(layers: Dict[str, Any]) -> Dict[str, str]:
    """Derive short NL summaries from each satellite layer for legacy fields."""
    growth_px = _pixel_summary(layers.get("growth"))
    soil_px = _pixel_summary(layers.get("soil_moisture"))
    uptake_px = _pixel_summary(layers.get("water_uptake"))
    pest_px = _pixel_summary(layers.get("pest_detection"))
    agro = layers.get("agro_stats") if isinstance(layers.get("agro_stats"), dict) else {}
    npk = layers.get("npk_analysis") if isinstance(layers.get("npk_analysis"), dict) else {}
    acres = plot_acres_from_payloads(agro, {"layers": layers})

    crop_health = (
        f"Growth layer ({layers.get('growth', {}).get('data_source', 'Satellite')}): "
        f"healthy canopy {format_share(growth_px.get('healthy_pixel_percentage'), acres, growth_px)}, "
        f"moderate {format_share(growth_px.get('moderate_pixel_percentage'), acres, growth_px)}, "
        f"stress {format_share(growth_px.get('stress_pixel_percentage'), acres, growth_px)} "
        f"(latest image: {growth_px.get('latest_image_date', 'N/A')})."
        if growth_px
        else "Growth/canopy layer data unavailable."
    )

    soil_water = (
        f"Satellite soil moisture layer ({layers.get('soil_moisture', {}).get('sensor_used', 'S1')}): "
        f"excellent {format_share(soil_px.get('excellent_pixel_percentage'), acres, soil_px)}, "
        f"adequate {format_share(soil_px.get('adequate_pixel_percentage'), acres, soil_px)}, "
        f"excess {format_share(soil_px.get('excess_pixel_percentage'), acres, soil_px)}, "
        f"shallow water {format_share(soil_px.get('shallow_water_pixel_percentage'), acres, soil_px)} "
        f"(latest image: {soil_px.get('latest_image_date', 'N/A')})."
        if soil_px
        else "Satellite soil moisture layer data unavailable."
    )

    weather_parts = []
    current = layers.get("current_weather")
    forecast = layers.get("forecast")
    if current:
        weather_parts.append(f"Current weather snapshot available.")
    if forecast:
        weather_parts.append(f"Forecast data available.")
    weather = " ".join(weather_parts) if weather_parts else "Weather layer not returned in latest daily report."

    action_items = []
    if uptake_px:
        action_items.append(
            f"Water uptake layer: very healthy uptake "
            f"{format_share(uptake_px.get('very_healthy_pixel_percentage'), acres, uptake_px)}."
        )
    if pest_px:
        chewing = pest_px.get("chewing_affected_pixel_percentage", 0) or 0
        fungi = pest_px.get("fungi_affected_pixel_percentage", 0) or 0
        if chewing or fungi:
            action_items.append(
                f"Pest layer flags: chewing {format_share(chewing, acres, pest_px)}, "
                f"fungi {format_share(fungi, acres, pest_px)} — scout affected zones."
            )
        else:
            action_items.append("Pest detection layer: no significant pest-affected area detected.")
    if npk:
        fert = npk.get("fertilizer_require_perAcre") or {}
        if fert:
            action_items.append(
                "NPK layer for this field: "
                f"N={format_field_dose(fert.get('N'), acres)}, "
                f"P={format_field_dose(fert.get('P'), acres)}, "
                f"K={format_field_dose(fert.get('K'), acres)}."
            )
        elif npk.get("soilN") is not None:
            action_items.append(
                f"Soil NPK: N={npk.get('soilN')} mg/kg, P={npk.get('soilP')} mg/kg, "
                f"K={npk.get('soilK')} mg/kg (required_n_per_acre={npk.get('required_n_per_acre')})."
            )
    if agro.get("current_growth_stage"):
        action_items.append(f"Crop stage: {agro.get('current_growth_stage')} ({agro.get('days_to_harvest', 'N/A')} days to harvest).")
    if not action_items:
        action_items = ["Review all 8 satellite layers for field-level variability."]

    return {
        "crop_health_summary": crop_health,
        "soil_water_summary": soil_water,
        "weather_summary": weather,
        "primary_action_items": action_items,
    }


def _merge_npk(res: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Admin.py returns `npk` (soilN/soilP/soilK) and `npk_analysis` separately — keep both."""
    analysis = res.get("npk_analysis") if isinstance(res.get("npk_analysis"), dict) else {}
    required = res.get("npk") if isinstance(res.get("npk"), dict) else {}
    if not analysis and not required:
        return None
    merged: Dict[str, Any] = {}
    merged.update(required)
    merged.update(analysis)
    # Preserve Admin.py names even when only one payload is present
    for key in (
        "soilN", "soilP", "soilK", "gndvi", "required_n_per_acre",
        "days_since_plantation", "max_yield", "area_acres",
        "soil_statistics", "recommended_dose_perAcre",
        "estimated_npk_uptake_perAcre", "fertilizer_require_perAcre",
    ):
        if merged.get(key) is None:
            merged[key] = required.get(key) if key in required else analysis.get(key)
    return merged or None


def _normalize_daily_report(res: Dict[str, Any], clean_id: str) -> Dict[str, Any]:
    """Preserve Admin.py daily-report keys, including both npk and npk_analysis."""
    layers: Dict[str, Any] = {
        "agro_stats": res.get("agro_stats"),
        "growth": res.get("growth"),
        "soil_moisture": res.get("soil_moisture"),
        "water_uptake": res.get("water_uptake"),
        "pest_detection": res.get("pest_detection"),
        "npk_analysis": _merge_npk(res),
        "current_weather": res.get("current_weather"),
        "forecast": res.get("forecast"),
    }

    summaries = _build_layer_summaries(layers)

    return {
        "status": "success",
        "plot_name": str(res.get("plot_name", clean_id)),
        "report_date": res.get("report_date", res.get("date", "Today")),
        "generated_at": res.get("generated_at"),
        "plot_info": res.get("plot_info"),
        "npk": res.get("npk") if isinstance(res.get("npk"), dict) else None,
        "layers": layers,
        "layer_count": sum(1 for v in layers.values() if v),
        "errors": res.get("errors"),
        **summaries,
    }


def _generate_fallback_daily_report(plot_id: str) -> Dict[str, Any]:
    """Fallback when daily-report API is unreachable."""
    return {
        "status": "fallback",
        "plot_name": str(plot_id),
        "report_date": "Today",
        "layers": {},
        "layer_count": 0,
        "crop_health_summary": "8-layer daily report not available — API fetch failed or timed out.",
        "soil_water_summary": "Satellite layer data unavailable in cache.",
        "weather_summary": "Weather layer unavailable in cache.",
        "primary_action_items": ["Reload plot telemetry to refresh the 8 satellite layers."],
    }


async def fetch_daily_report_for_plot(plot_id: str) -> Dict[str, Any]:
    """Fetch Admin.py GET /daily-report, then fill missing layers from the same endpoints it uses internally."""
    from app.fetchers.cropo_client import (
        cropo_get,
        cropo_post,
        layer_from_geojson,
        satellite_end_date,
        today_iso,
    )
    from app.fetchers.plots_info import get_plot_info_cache_key
    from app.fetchers.soil_irrigation import get_soil_cache_key
    from app.fetchers.cropo_weather import get_weather_cache_key

    clean_id = str(plot_id).strip()
    cache_key = get_daily_report_cache_key(clean_id)
    report_date = today_iso()
    end_date = satellite_end_date(report_date)

    lat = settings.DEFAULT_FARM_LAT
    lon = settings.DEFAULT_FARM_LON
    soil_cached = await redis_client.get_json(get_soil_cache_key(clean_id))
    weather_cached = await redis_client.get_json(get_weather_cache_key(clean_id))
    if isinstance(soil_cached, dict):
        if soil_cached.get("latitude"):
            lat = soil_cached["latitude"]
        if soil_cached.get("longitude"):
            lon = soil_cached["longitude"]
    if isinstance(weather_cached, dict):
        loc = weather_cached.get("location") if isinstance(weather_cached.get("location"), dict) else {}
        if loc.get("lat") is not None:
            lat = loc["lat"]
        if loc.get("lon") is not None:
            lon = loc["lon"]

    logger.info("fetch_daily_report_for_plot_started", plot_id=clean_id, date=report_date, lat=lat, lon=lon)

    res = await async_fetch_with_retry(
        url=f"{cropo_base()}/daily-report",
        headers=cropo_headers(),
        params={"plot_name": clean_id, "date": report_date, "lat": lat, "lon": lon},
        timeout=DAILY_REPORT_TIMEOUT,
        max_retries=1,
        method="GET",
    )

    if not isinstance(res, dict) or not res:
        existing = await redis_client.get_json(cache_key)
        if existing:
            logger.warning("daily_report_fetch_failed_retaining_cache", plot_id=clean_id)
            return existing
        res = {}

    # Fill gaps with the same Admin.py layer endpoints (POST query params, empty body).
    plot_info_cached = await redis_client.get_json(get_plot_info_cache_key(clean_id))
    plantation = None
    if isinstance(plot_info_cached, dict):
        crop = plot_info_cached.get("crop_details") if isinstance(plot_info_cached.get("crop_details"), dict) else {}
        plantation = crop.get("plantation_date")

    if not res.get("growth"):
        raw = await cropo_post("/analyze_Growth", {"plot_name": clean_id, "end_date": end_date}, timeout=90.0)
        layer = layer_from_geojson(raw)
        if layer:
            res["growth"] = layer
    if not res.get("soil_moisture"):
        raw = await cropo_post(
            "/SoilMoisture",
            {"plot_name": clean_id, "end_date": end_date},
            timeout=90.0,
        )
        layer = layer_from_geojson(raw)
        if layer:
            res["soil_moisture"] = layer
    if not res.get("water_uptake"):
        raw = await cropo_get("/wateruptake", {"plot_name": clean_id, "end_date": end_date}, timeout=90.0)
        if not raw:
            raw = await cropo_post("/wateruptake", {"plot_name": clean_id, "end_date": end_date}, timeout=90.0)
        layer = layer_from_geojson(raw)
        if layer:
            res["water_uptake"] = layer
    if not res.get("pest_detection"):
        raw = await cropo_post(
            "/pest-detection",
            {"plot_name": clean_id, "end_date": end_date},
            timeout=150.0,
        )
        layer = layer_from_geojson(raw)
        if layer:
            res["pest_detection"] = layer
    if not res.get("npk"):
        npk_params: Dict[str, Any] = {"end_date": report_date}
        if plantation and plantation not in ("N/A", ""):
            npk_params["plantation_date"] = plantation
        raw = await cropo_post(f"/required-n/{clean_id}", npk_params, timeout=60.0)
        if isinstance(raw, dict):
            months = raw.get("months") if isinstance(raw.get("months"), list) else []
            latest = months[-1] if months else raw
            if isinstance(latest, dict) and (
                latest.get("soilN") is not None or raw.get("soilN") is not None
            ):
                res["npk"] = {
                    "plot_name": raw.get("plot_name", clean_id),
                    "plantation_date": raw.get("plantation_date") or plantation,
                    "days_since_plantation": latest.get("days_since_plantation"),
                    "required_n_per_acre": latest.get("required_n_per_acre"),
                    "gndvi": latest.get("gndvi"),
                    "soilN": latest.get("soilN", raw.get("soilN")),
                    "soilP": latest.get("soilP", raw.get("soilP")),
                    "soilK": latest.get("soilK", raw.get("soilK")),
                    "max_yield": latest.get("max_yield"),
                    "months": months,
                }
    if not res.get("npk_analysis"):
        an_params: Dict[str, Any] = {"date": report_date, "fe_days_back": 30}
        if plantation and plantation not in ("N/A", ""):
            an_params["plantation_date"] = plantation
        raw = await cropo_post(f"/analyze-npk/{clean_id}", an_params, timeout=120.0)
        if isinstance(raw, dict) and (raw.get("soil_statistics") or raw.get("npk_analysis") or raw.get("months")):
            res["npk_analysis"] = raw

    if not isinstance(res, dict) or not any(
        res.get(k) for k in ("growth", "soil_moisture", "water_uptake", "pest_detection", "npk", "npk_analysis", "agro_stats")
    ):
        existing = await redis_client.get_json(cache_key)
        if existing:
            return existing
        normalized = _generate_fallback_daily_report(clean_id)
    else:
        if not res.get("plot_name"):
            res["plot_name"] = clean_id
        if not res.get("report_date"):
            res["report_date"] = report_date
        normalized = _normalize_daily_report(res, clean_id)

    await redis_client.set_json(cache_key, normalized, ttl_seconds=TTL_SECONDS)
    from app.cache.history import record_plot_snapshot
    layers = normalized.get("layers") if isinstance(normalized.get("layers"), dict) else {}
    growth_px = (layers.get("growth") or {}).get("pixel_summary") if isinstance(layers.get("growth"), dict) else {}
    pest_px = (layers.get("pest_detection") or {}).get("pixel_summary") if isinstance(layers.get("pest_detection"), dict) else {}
    soil_px = (layers.get("soil_moisture") or {}).get("pixel_summary") if isinstance(layers.get("soil_moisture"), dict) else {}
    await record_plot_snapshot(
        clean_id,
        "daily_report",
        {
            "healthy_pixel_percentage": (growth_px or {}).get("healthy_pixel_percentage"),
            "stress_pixel_percentage": (growth_px or {}).get("stress_pixel_percentage"),
            "chewing_affected_pixel_percentage": (pest_px or {}).get("chewing_affected_pixel_percentage"),
            "less_pixel_percentage": (soil_px or {}).get("less_pixel_percentage"),
            "layer_count": normalized.get("layer_count"),
        },
    )
    logger.info(
        "fetch_daily_report_for_plot_completed",
        plot_id=clean_id,
        layer_count=normalized.get("layer_count", 0),
    )
    return normalized


async def fetch_daily_reports() -> bool:
    """Scheduled background refresh for all active monitored plots."""
    from app.fetchers import get_active_plot_ids

    active_plots = get_active_plot_ids()
    if not active_plots:
        logger.info("no_active_plots_to_refresh", domain="daily_report")
        return True

    for pid in active_plots:
        await fetch_daily_report_for_plot(pid.strip())
    return True

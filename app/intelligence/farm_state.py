"""Normalize selected cache payloads into a compact farm state dict."""

from typing import Any, Dict, List, Optional
from app.cache.cache_reader import CacheResult
from app.context.context_builder import select_upcoming_hourly_et


def _num(value: Any) -> Optional[float]:
    try:
        if value is None or value == "N/A":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_farm_state(
    plot_id: str,
    cache_results: Dict[str, CacheResult],
    selected_layers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Include only domains that were actually retrieved."""
    identity = _data(cache_results, "plots_info")
    soil = _data(cache_results, "soil_and_irrigation")
    weather = _data(cache_results, "cropo_weather")
    health = _data(cache_results, "field_scores")
    report = _data(cache_results, "daily_report")

    satellite: Dict[str, Any] = {}
    if isinstance(report, dict):
        layers = report.get("layers") if isinstance(report.get("layers"), dict) else {}
        wanted = selected_layers or list(layers.keys())
        for name in wanted:
            if name in layers and layers[name]:
                satellite[name] = _compact_layer(name, layers[name])

    freshness = {name: item.freshness for name, item in cache_results.items()}
    missing = [name for name, item in cache_results.items() if item.freshness == "MISSING" or not item.data]
    # Also note requested but empty satellite layers
    if selected_layers:
        for name in selected_layers:
            if name not in satellite:
                missing.append(f"layer:{name}")

    state: Dict[str, Any] = {
        "plot_id": str(plot_id),
        "identity": _compact_identity(identity),
        "soil": _compact_soil(soil),
        "weather": _compact_weather(weather),
        "field_health": _compact_health(health),
        "satellite": satellite,
        "freshness": freshness,
        "missing_data": missing,
    }
    return {k: v for k, v in state.items() if v or k in ("plot_id", "freshness", "missing_data")}


def _data(results: Dict[str, CacheResult], domain: str) -> Optional[dict]:
    item = results.get(domain)
    if item and isinstance(item.data, dict):
        return item.data
    return None


def _compact_identity(payload: Optional[dict]) -> Dict[str, Any]:
    if not payload:
        return {}
    crop = payload.get("crop_details") if isinstance(payload.get("crop_details"), dict) else {}
    return {
        "name": payload.get("name"),
        "area_acres": payload.get("area_acres"),
        "crop_details": {
            "crop_type": crop.get("crop_type"),
            "crop_variety": crop.get("crop_variety"),
            "plantation_date": crop.get("plantation_date"),
            "irrigation_type": crop.get("irrigation_type"),
        },
    }


def _hourly_et_compact(records: Any, hours: int = 4) -> List[Dict[str, Any]]:
    rows = []
    for dt, val in select_upcoming_hourly_et(records, hours=hours):
        rows.append({"time": dt.strftime("%H:%M"), "et0_mm": val})
    return rows


def _compact_soil(payload: Optional[dict]) -> Dict[str, Any]:
    if not payload:
        return {}
    return {
        "latest_moisture_pct": _num(payload.get("latest_moisture_pct")),
        "moisture_status": payload.get("moisture_status"),
        "yesterday_rainfall_mm": _num(payload.get("yesterday_rainfall_mm")),
        "et_mean_mm": _num(payload.get("et_mean_mm")),
        "advisory": payload.get("advisory"),
        "water_remain_liters": _num(payload.get("water_remain_liters") or payload.get("total_water_remain_liters")),
        "water_remain_kl": _num(payload.get("water_remain_kl")),
        "irrigation_needed_kl": _num(payload.get("irrigation_needed_kl")),
        "eto_sum_mm": _num(payload.get("eto_sum_mm")),
        "eto_loss_liters": _num(payload.get("eto_loss_liters")),
        "eto_loss_kl": _num(payload.get("eto_loss_kl")),
        "water_present_kl": _num(payload.get("water_present_kl")),
        "water_loss_kl": _num(payload.get("water_loss_kl")),
        "average_eto_mm": _num(payload.get("average_eto_mm")),
        "ndmi": _num(payload.get("ndmi")),
        "et_mean_mm_per_day": _num(payload.get("et_mean_mm_per_day")),
        "hourly_et_next_4h": _hourly_et_compact(payload.get("hourly_records_et"), 4),
        "hourly_steps": payload.get("hourly_steps") if isinstance(payload.get("hourly_steps"), list) else [],
        "water_remain_days": payload.get("water_remain_days") if isinstance(payload.get("water_remain_days"), list) else [],
        "latitude": _num(payload.get("latitude")),
        "longitude": _num(payload.get("longitude")),
        "history": payload.get("history") if isinstance(payload.get("history"), list) else [],
    }


def _compact_weather(payload: Optional[dict]) -> Dict[str, Any]:
    if not payload:
        return {}
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    forecast = payload.get("forecast") if isinstance(payload.get("forecast"), list) else []
    return {
        "current": {
            "temperature_celsius": _num(current.get("temperature_celsius")),
            "min_temp": _num(current.get("min_temp")),
            "max_temp": _num(current.get("max_temp")),
            "rain_status": current.get("rain_status"),
            "rainfall_probability_pct": _num(current.get("rainfall_probability_pct")),
        },
        "forecast": [
            {
                "date": d.get("date"),
                "avg_temp_celsius": _num(d.get("avg_temp_celsius")),
                "rain_prob_pct": _num(d.get("rain_prob_pct")),
                "will_rain": d.get("will_rain"),
                "rain_status": d.get("rain_status"),
            }
            for d in forecast[:4]
            if isinstance(d, dict)
        ],
        "location": payload.get("location") if isinstance(payload.get("location"), dict) else {},
    }


def _compact_health(payload: Optional[dict]) -> Dict[str, Any]:
    if not payload:
        return {}
    return {
        "field_score_pct": _num(payload.get("field_score_pct")),
        "health_status": payload.get("health_status"),
        "advisory": payload.get("advisory"),
    }


def _compact_layer(name: str, layer: Any) -> Dict[str, Any]:
    if not isinstance(layer, dict):
        return {"available": True, "raw_type": type(layer).__name__}
    px = layer.get("pixel_summary") if isinstance(layer.get("pixel_summary"), dict) else {}
    compact = {
        "sensor": layer.get("sensor_used") or layer.get("data_source") or layer.get("sensor"),
        "latest_image_date": layer.get("latest_image_date") or px.get("latest_image_date"),
    }
    if px:
        compact["pixel_summary"] = {k: v for k, v in px.items() if v is not None}
    if name == "agro_stats":
        compact["current_growth_stage"] = layer.get("current_growth_stage")
        compact["days_to_harvest"] = layer.get("days_to_harvest")
        soil = layer.get("soil") if isinstance(layer.get("soil"), dict) else {}
        compact["soil_ph"] = soil.get("phh2o")
        compact["area_acres"] = layer.get("area_acres") or soil.get("area_acres")
    if name == "npk_analysis":
        compact["soil_statistics"] = layer.get("soil_statistics")
        compact["recommended_dose_perAcre"] = layer.get("recommended_dose_perAcre")
        compact["fertilizer_require_perAcre"] = layer.get("fertilizer_require_perAcre")
        compact["soilN"] = layer.get("soilN")
        compact["soilP"] = layer.get("soilP")
        compact["soilK"] = layer.get("soilK")
        compact["gndvi"] = layer.get("gndvi")
        compact["required_n_per_acre"] = layer.get("required_n_per_acre")
        compact["max_yield"] = layer.get("max_yield")
    if name in ("current_weather", "forecast") and not px:
        compact["present"] = True
    return compact

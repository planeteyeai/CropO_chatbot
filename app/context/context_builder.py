"""Context Builder Layer (Per-Plot Scoped).

Retrieves cached plot telemetry from Redis and formats it into rich, natural-language
agronomic context (never raw JSON dumps) for LLM prompt injection.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import structlog
from app.cache.redis_client import redis_client
from app.context.area_units import (
    coerce_acres,
    format_acres,
    format_count_as_area,
    format_field_dose,
    format_share,
    plot_acres_from_payloads,
)
from app.fetchers import (
    get_plot_info_cache_key,
    get_soil_cache_key,
    get_score_cache_key,
    get_weather_cache_key,
    get_daily_report_cache_key,
)

logger = structlog.get_logger(__name__)


def _format_freshness(metadata: Optional[Dict[str, Any]]) -> str:
    """Produce human-readable cache freshness label."""
    if not metadata:
        return ""
    age = metadata.get("age_seconds")
    if age is not None:
        return f" (Updated {age}s ago)" if age < 60 else f" (Updated {age // 60}m ago)"
    return ""


def select_upcoming_hourly_et(
    records: Any,
    hours: int = 4,
    *,
    now: Optional[datetime] = None,
) -> List[Tuple[datetime, float]]:
    """Upcoming hourly FAO ET0 rows from compute-et `hourly_records_et`."""
    if not isinstance(records, list) or hours <= 0:
        return []
    clock = now or datetime.now()
    floor = clock.replace(minute=0, second=0, microsecond=0)
    upcoming: List[Tuple[datetime, float]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        t = rec.get("time")
        v = rec.get("et0_fao_evapotranspiration")
        if t is None or v is None:
            continue
        try:
            dt = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            val = float(v)
        except (TypeError, ValueError):
            continue
        if dt >= floor:
            upcoming.append((dt, val))
    upcoming.sort(key=lambda item: item[0])
    return upcoming[:hours]


def format_plot_info_snippet(payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
    """Format plot crop & agronomic metadata."""
    if not isinstance(payload, dict):
        return "Plot metadata is currently unavailable in cache."

    fresh = _format_freshness(metadata)
    name = payload.get("name", "Unknown")
    area = payload.get("area_acres", 1.0)
    crop = payload.get("crop_details", {})
    crop_type = crop.get("crop_type", "General Crop")
    variety = crop.get("crop_variety", "Standard Variety")
    planted = crop.get("plantation_date", "N/A")
    irrigation = crop.get("irrigation_type", "Drip Irrigation")
    geom = payload.get("geometry_type", "Polygon Boundary")

    return (
        f"[Plot #{name} Crop & Land Profile{fresh}]\n"
        f"- Cultivated Crop: {crop_type}\n"
        f"- Crop Variety: {variety}\n"
        f"- Land Area: {area} acres ({geom})\n"
        f"- Plantation Date: {planted}\n"
        f"- Installed Irrigation Infrastructure: {irrigation}"
    )


def format_plot_soil_snippet(
    payload: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
    *,
    include_hourly_et: bool = False,
    compact: bool = False,
) -> str:
    """Format plot soil moisture, evapotranspiration loss, and irrigation balance."""
    if not isinstance(payload, dict):
        return "Soil moisture telemetry is currently unavailable in cache."

    fresh = _format_freshness(metadata)
    name = payload.get("plot_name", "?")
    moisture = payload.get("latest_moisture_pct", "N/A")
    status = payload.get("moisture_status", "Normal")
    rain = payload.get("yesterday_rainfall_mm", 0.0)
    et = payload.get("et_mean_mm", 0.0)
    adv = payload.get("advisory", "Maintain standard irrigation schedule.")

    lines = [
        f"[Plot #{name} Soil Hydration & Irrigation Dynamics{fresh}]",
        f"- Current Root-Zone Soil Moisture: {moisture}% (Hydration Status: {status})",
        f"- Agronomic Water Management Advisory: {adv}",
    ]
    if compact:
        return "\n".join(lines)

    lines[2:2] = [
        f"- Recent Precipitation Influx: {rain} mm received yesterday",
        f"- Soil-layer yesterday ET (irrigation-and-soil-moisture): {et} mm/day",
    ]
    lines.extend(_format_water_balance_lines(payload))

    daily_et = payload.get("et_mean_mm_per_day")
    if include_hourly_et and daily_et is not None:
        lines.append(
            f"- compute-et ET_mean_mm_per_day (AskO hourly ET API, not the irrigation graph): {daily_et} mm/day"
        )

    if include_hourly_et:
        next4 = select_upcoming_hourly_et(payload.get("hourly_records_et"), hours=4)
        next12 = select_upcoming_hourly_et(payload.get("hourly_records_et"), hours=12)
        if next4:
            parts = [f"{dt.strftime('%H:%M')}={v} mm" for dt, v in next4]
            total4 = round(sum(v for _, v in next4), 2)
            lines.append(
                f"- Hourly ET0 next 4 hours (compute-et hourly_records_et / et0_fao_evapotranspiration): "
                f"{'; '.join(parts)}. Total next 4 hours: {total4} mm."
            )
        if next12:
            parts12 = [f"{dt.strftime('%H:%M')}={v}" for dt, v in next12]
            lines.append(
                f"- Hourly ET0 remaining hours (mm): {', '.join(parts12)}"
            )
        elif payload.get("hourly_records_et"):
            lines.append("- Hourly ET0 series is cached but all timestamps are in the past for this refresh window.")

    history = payload.get("history", [])
    if history and len(history) > 1:
        hist_strs = [
            f"{d.get('day', 'Day')}: {d.get('moisture')}% moisture (ET: {d.get('et_mm')}mm)"
            for d in history[-4:]
        ]
        lines.append(f"- Recent Multi-Day Moisture Progression: {' | '.join(hist_strs)}")

    return "\n".join(lines)


def _fmt_num(value: Any, digits: int) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _format_water_balance_lines(payload: Dict[str, Any]) -> List[str]:
    """Same labels and rounding as CropO Insights irrigation graph."""
    remain = payload.get("water_remain_liters")
    if remain is None:
        remain = payload.get("total_water_remain_liters")
    if remain is None and payload.get("eto_sum_mm") is None:
        return []

    try:
        remain_f = float(remain) if remain is not None else None
    except (TypeError, ValueError):
        remain_f = None
    needed = payload.get("irrigation_needed_kl")
    if needed is None and remain_f is not None:
        needed = round(abs(remain_f) / 1000.0, 1) if remain_f < 0 else 0.0
    remain_kl = payload.get("water_remain_kl")
    if remain_kl is None and remain_f is not None:
        remain_kl = round(remain_f / 1000.0, 1)
    eto_loss_kl = payload.get("eto_loss_kl")
    if eto_loss_kl is None and payload.get("eto_loss_liters") is not None:
        try:
            eto_loss_kl = round(float(payload["eto_loss_liters"]) / 1000.0, 1)
        except (TypeError, ValueError):
            eto_loss_kl = None
    date_str = payload.get("water_balance_date") or payload.get("end_date") or "latest day"
    lines = [
        f"[WATER BALANCE — CropO app irrigation graph, {date_str}]",
        "- Quote these exact numbers. Do not convert or round them differently.",
    ]
    if needed is not None:
        lines.append(f"- Irrigation needed: {_fmt_num(needed, 1)} kL")
    if remain_f is not None:
        lines.append(f"- Water remaining: {remain_f} L ({_fmt_num(remain_kl, 1)} kL remain)")
    if eto_loss_kl is not None:
        lines.append(f"- ETo loss: {_fmt_num(eto_loss_kl, 1)} kL")
    if payload.get("eto_sum_mm") is not None:
        lines.append(f"- ETo today: {_fmt_num(payload.get('eto_sum_mm'), 1)} mm/day (eto_sum_mm from water-remain-per-day)")
    if payload.get("ndmi") is not None:
        lines.append(f"- NDMI: {_fmt_num(payload.get('ndmi'), 3)}")
    if payload.get("water_loss_kl") is not None:
        lines.append(f"- Water Loss: {_fmt_num(payload.get('water_loss_kl'), 1)} kL")
    elif payload.get("total_water_evaporation") is not None:
        try:
            lines.append(
                f"- Water Loss: {_fmt_num(float(payload['total_water_evaporation']) / 1000.0, 1)} kL"
            )
        except (TypeError, ValueError):
            pass
    if payload.get("water_present_kl") is not None:
        lines.append(f"- Water Present: {_fmt_num(payload.get('water_present_kl'), 1)} kL")
    elif payload.get("total_water_remain_a_day") is not None:
        try:
            lines.append(
                f"- Water Present: {_fmt_num(float(payload['total_water_remain_a_day']) / 1000.0, 1)} kL"
            )
        except (TypeError, ValueError):
            pass
    if payload.get("average_eto_mm") is not None:
        lines.append(f"- Avg ETo Rate: {_fmt_num(payload.get('average_eto_mm'), 3)} mm/h")
    if payload.get("area_m2") is not None:
        lines.append(f"- Field area: {payload.get('area_m2')} m²")
    if payload.get("total_water_remain_liters") is not None:
        lines.append(f"- Period total remaining: {payload.get('total_water_remain_liters')} L")
    if payload.get("total_eto_loss_liters") is not None:
        lines.append(f"- Period total ETo loss: {payload.get('total_eto_loss_liters')} L")

    steps = payload.get("hourly_steps") if isinstance(payload.get("hourly_steps"), list) else []
    if steps:
        parts = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            hour = step.get("hour")
            eto = step.get("eto_mm")
            after_kl = step.get("water_volume_after_kl")
            if after_kl is None and step.get("water_volume_after_liters") is not None:
                try:
                    after_kl = round(float(step["water_volume_after_liters"]) / 1000.0, 1)
                except (TypeError, ValueError):
                    after_kl = None
            eto_s = _fmt_num(eto, 3) if eto is not None else "n/a"
            kl_s = _fmt_num(after_kl, 1) if after_kl is not None else "n/a"
            parts.append(f"H{hour} eto={eto_s} mm remain={kl_s} kL")
        if parts:
            lines.append(f"- Hourly water volume (graph): {'; '.join(parts)}")

    days = payload.get("water_remain_days") if isinstance(payload.get("water_remain_days"), list) else []
    if len(days) > 1:
        trend = []
        for day in days[-7:]:
            if not isinstance(day, dict):
                continue
            eto = day.get("eto_sum_mm")
            kl = day.get("water_remain_kl")
            trend.append(
                f"{day.get('date')}: remain={_fmt_num(kl, 1) if kl is not None else 'n/a'} kL, "
                f"ETo={_fmt_num(eto, 1) if eto is not None else 'n/a'} mm"
            )
        if trend:
            lines.append(f"- Daily ETo trend (last {len(trend)} days): {' | '.join(trend)}")
    return lines


def format_plot_score_snippet(payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
    """Format plot Sentinel-2 NDVI vegetative health score."""
    if not isinstance(payload, dict):
        return "Field health score is currently unavailable in cache."

    fresh = _format_freshness(metadata)
    name = payload.get("plot_name", "?")
    score = payload.get("field_score_pct", "N/A")
    health = payload.get("health_status", "Good")
    adv = payload.get("advisory", "Canopy developing normally.")

    return (
        f"[Plot #{name} Satellite Remote Sensing & Canopy Health{fresh}]\n"
        f"- Normalized Difference Vegetation Index (NDVI) Field Score: {score}% / 100.0%\n"
        f"- Canopy Biomass & Chlorophyll Activity Status: {health}\n"
        f"- Satellite Observation & Agronomic Inspection Note: {adv}"
    )


def format_plot_weather_snippet(
    payload: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
    *,
    include_forecast: bool = True,
) -> str:
    """Format farm weather, temperature range, and precipitation outlook."""
    if not isinstance(payload, dict):
        return "Weather telemetry is currently unavailable in cache."

    fresh = _format_freshness(metadata)
    current = payload.get("current", {})
    temp = current.get("temperature_celsius", "N/A")
    min_t = current.get("min_temp", "N/A")
    max_t = current.get("max_temp", "N/A")
    avg_t = current.get("avg_temp", "N/A")
    rain_st = current.get("rain_status", "No Rain")
    rain_prob = current.get("rainfall_probability_pct", 0)

    lines = [
        f"[Farm Atmospheric Weather & Microclimate{fresh}]",
        f"- Current Ambient Temperature: {temp}°C (Day Average: {avg_t}°C, Range: {min_t}°C to {max_t}°C)",
        f"- Precipitation Outlook Today: {rain_st} (Rain Probability: {rain_prob}%)",
    ]

    forecast = payload.get("forecast", [])
    if include_forecast and forecast:
        outlook_strs = [
            f"{d.get('date', 'Day')}: {d.get('avg_temp_celsius')}°C ({d.get('rain_prob_pct')}% rain, {d.get('rain_status', 'Clear')})"
            for d in forecast[:4]
        ]
        lines.append(f"- 4-Day Weather & Rainfall Trend: {' | '.join(outlook_strs)}")

    return "\n".join(lines)


def format_farm_location_for_market(
    plot_id: str,
    plots_info: Optional[Dict[str, Any]] = None,
    soil: Optional[Dict[str, Any]] = None,
    weather: Optional[Dict[str, Any]] = None,
) -> str:
    """Crop + coordinates so Gemini Search can look up the nearest mandi."""
    info = plots_info if isinstance(plots_info, dict) else {}
    soil = soil if isinstance(soil, dict) else {}
    weather = weather if isinstance(weather, dict) else {}
    crop = (info.get("crop_details") or {}) if isinstance(info.get("crop_details"), dict) else {}
    loc = weather.get("location") if isinstance(weather.get("location"), dict) else {}
    lat = soil.get("latitude") if soil.get("latitude") is not None else loc.get("lat")
    lon = soil.get("longitude") if soil.get("longitude") is not None else loc.get("lon")
    crop_type = crop.get("crop_type") or "the plot crop"
    variety = crop.get("crop_variety") or ""
    lines = [
        f"[Farm location for nearby mandi / APMC / eNAM search — Plot #{plot_id}]",
        f"- Crop to price: {crop_type}" + (f" (variety {variety})" if variety else ""),
    ]
    if lat is not None and lon is not None:
        lines.append(f"- Farm coordinates: {lat}, {lon} (use the nearest APMC/mandi to this point)")
        lines.append(
            f"- Search query hint: tentative {crop_type} mandi ₹/quintal near {lat},{lon} India and next-6-day price trend (no calendar dates)"
        )
    else:
        lines.append("- Farm coordinates: not in cache. Search the nearest mandi for this plot's crop in India.")
    lines.append(
        "- Prices are NOT in CropO satellite cache. Use Google Search. Always label rates as tentative/approximate. "
        "Do not cite an exact market date. Quality-adjust using NDVI/field score, healthy canopy acres, and pest-affected acres from cache."
    )
    return "\n".join(lines)


def _format_layer_pixels(
    title: str,
    layer: Optional[Dict[str, Any]],
    fields: List[tuple],
    plot_acres: Optional[float] = None,
) -> List[str]:
    """Format a satellite layer as acres of this plot. Never say pixels."""
    if not isinstance(layer, dict):
        return [f"- {title}: Data unavailable for this layer."]

    px = layer.get("pixel_summary") if isinstance(layer.get("pixel_summary"), dict) else {}
    sensor = layer.get("sensor_used") or layer.get("data_source") or layer.get("sensor") or "Satellite"
    latest = layer.get("latest_image_date") or px.get("latest_image_date") or "N/A"
    images = layer.get("image_count")

    lines = [f"- {title} ({sensor}, latest: {latest}, images: {images or 'N/A'}):"]
    if not px:
        lines.append("  * Area breakdown not available.")
        return lines

    for label, key in fields:
        val = px.get(key)
        if val is None:
            continue
        key_l = (key or "").lower()
        if "count" in key_l and "percentage" not in key_l:
            lines.append(f"  * {label}: {format_count_as_area(val)}")
        else:
            lines.append(f"  * {label}: {format_share(val, plot_acres, px)}")
    return lines


def _npk_kg_per_acre(npk: Dict[str, Any], recommended: Dict[str, Any], required: Dict[str, Any]):
    n = required.get("N") if required.get("N") is not None else recommended.get("N")
    if n is None:
        n = npk.get("required_n_per_acre")
    p = required.get("P") if required.get("P") is not None else recommended.get("P")
    k = required.get("K") if required.get("K") is not None else recommended.get("K")
    return n, p, k


def _format_npk_fertilizer_materials(
    npk: Dict[str, Any],
    recommended: Dict[str, Any],
    required: Dict[str, Any],
    plot_acres: Optional[float] = None,
) -> str:
    from app.knowledge.agriculture_knowledge import npk_to_common_fertilizers
    from app.context.area_units import format_acres, format_field_dose, format_organic_for_plot

    plan = npk_to_common_fertilizers(*_npk_kg_per_acre(npk, recommended, required))
    if not plan:
        return ""
    acres = coerce_acres(plot_acres)
    urea = format_field_dose(plan["urea_kg"], acres)
    dap = format_field_dose(plan["dap_kg"], acres)
    mop = format_field_dose(plan["mop_kg"], acres)
    area_note = f" for this {format_acres(acres)} field" if acres else ""
    organic = format_organic_for_plot(acres)
    lines = (
        f"  * THIS FIELD doses{area_note} — quote these first, not only kg/acre: "
        f"Urea (46% N) ≈ {urea}; "
        f"DAP (18-46-0) ≈ {dap}; "
        f"MOP (60% K2O) ≈ {mop}. "
        f"Split urea; subtract already-applied fertilizer; confirm with a soil test."
    )
    if organic:
        lines += f"\n  * {organic}"
    return lines


def format_daily_report_snippet(
    payload: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
    selected_layers: Optional[List[str]] = None,
    plot_acres: Optional[float] = None,
    include_fertilizer_materials: bool = True,
) -> str:
    """Format composite daily report. If selected_layers is set, only those layers."""
    if not isinstance(payload, dict):
        return "Daily agronomic report is currently unavailable in cache."

    fresh = _format_freshness(metadata)
    name = payload.get("plot_name", "?")
    date_str = payload.get("report_date", "Today")
    layers = payload.get("layers") if isinstance(payload.get("layers"), dict) else {}
    wanted = set(selected_layers or [])
    acres = coerce_acres(plot_acres) or plot_acres_from_payloads(payload, layers.get("agro_stats") if isinstance(layers.get("agro_stats"), dict) else None)

    def _want(layer_name: str) -> bool:
        return not wanted or layer_name in wanted

    if wanted:
        lines = [f"[Plot #{name} Selected satellite layers ({date_str}){fresh}]"]
    else:
        lines = [
            f"[Plot #{name} Daily Report — 8 Satellite Intelligence Layers ({date_str}){fresh}]",
            f"- Layers loaded: {payload.get('layer_count', len([v for v in layers.values() if v]))} / 8",
        ]

    # Layer 1: Agro stats
    if _want("agro_stats"):
        agro = layers.get("agro_stats") if isinstance(layers.get("agro_stats"), dict) else {}
        if agro:
            soil_stats = agro.get("soil") if isinstance(agro.get("soil"), dict) else {}
            biomass = agro.get("biomass") if isinstance(agro.get("biomass"), dict) else {}
            lines.append("- Layer 1 — Agro Stats:")
            lines.append(f"  * Growth stage: {agro.get('current_growth_stage', 'N/A')} | Days to harvest: {agro.get('days_to_harvest', 'N/A')}")
            area_val = coerce_acres(agro.get("area_acres", soil_stats.get("area_acres"))) or acres
            lines.append(f"  * Area: {format_acres(area_val) if area_val else 'N/A'}")
            lines.append(f"  * Soil pH: {soil_stats.get('phh2o', 'N/A')} | Organic carbon stock: {soil_stats.get('organic_carbon_stock', 'N/A')}")
            if biomass:
                lines.append(f"  * Biomass mean: {biomass.get('mean', 'N/A')} (min {biomass.get('min', 'N/A')}, max {biomass.get('max', 'N/A')})")
        elif not wanted:
            lines.append("- Layer 1 — Agro Stats: unavailable.")

    # Layer 2: Growth / canopy health
    if _want("growth"):
        lines.extend(_format_layer_pixels(
            "Layer 2 — Growth / Canopy Health (acres of this plot)",
            layers.get("growth"),
            [
                ("Healthy canopy", "healthy_pixel_percentage"),
                ("Moderate canopy", "moderate_pixel_percentage"),
                ("Weak canopy", "weak_pixel_percentage"),
                ("Stress canopy", "stress_pixel_percentage"),
            ],
            plot_acres=acres,
        ))

    # Layer 3: Satellite soil moisture map
    if _want("soil_moisture"):
        lines.extend(_format_layer_pixels(
            "Layer 3 — Satellite Soil Moisture (acres of this plot)",
            layers.get("soil_moisture"),
            [
                ("Less moisture area", "less_pixel_percentage"),
                ("Adequate moisture area", "adequate_pixel_percentage"),
                ("Excellent moisture area", "excellent_pixel_percentage"),
                ("Excess moisture area", "excess_pixel_percentage"),
                ("Shallow water area", "shallow_water_pixel_percentage"),
            ],
            plot_acres=acres,
        ))

    # Layer 4: Water uptake
    if _want("water_uptake"):
        lines.extend(_format_layer_pixels(
            "Layer 4 — Water Uptake (acres of this plot)",
            layers.get("water_uptake"),
            [
                ("Deficient uptake area", "deficient_pixel_percentage"),
                ("Less uptake area", "less_pixel_percentage"),
                ("Adequate uptake area", "adequat_pixel_percentage"),
                ("Excellent uptake area", "excellent_pixel_percentage"),
                ("Very healthy uptake area", "very_healthy_pixel_percentage"),
            ],
            plot_acres=acres,
        ))

    # Layer 5: Pest detection
    if _want("pest_detection"):
        lines.extend(_format_layer_pixels(
            "Layer 5 — Pest Detection (acres of this plot)",
            layers.get("pest_detection"),
            [
                ("Healthy canopy area", "healthy_pixel_count"),
                ("Chewing pest affected area", "chewing_affected_pixel_percentage"),
                ("Fungi affected area", "fungi_affected_pixel_percentage"),
                ("Sucking pest affected area", "sucking_affected_pixel_percentage"),
                ("Wilt affected area", "wilt_affected_pixel_percentage"),
                ("Soil-borne affected area", "SoilBorn_affected_pixel_percentage"),
            ],
            plot_acres=acres,
        ))

    # Layer 6: NPK analysis
    if _want("npk_analysis"):
        npk = layers.get("npk_analysis") if isinstance(layers.get("npk_analysis"), dict) else {}
        if npk:
            soil_npk = npk.get("soil_statistics") if isinstance(npk.get("soil_statistics"), dict) else {}
            recommended = npk.get("recommended_dose_perAcre") if isinstance(npk.get("recommended_dose_perAcre"), dict) else {}
            required = npk.get("fertilizer_require_perAcre") if isinstance(npk.get("fertilizer_require_perAcre"), dict) else {}
            if include_fertilizer_materials:
                lines.append("- Layer 6 — NPK / Soil Nutrition:")
                lines.append(f"  * Soil N: {soil_npk.get('total_nitrogen', 'N/A')} | P: {soil_npk.get('phosphorus', 'N/A')} | K: {soil_npk.get('potassium', 'N/A')}")
                lines.append(f"  * pH: {soil_npk.get('phh2o', 'N/A')} | Organic carbon: {soil_npk.get('soil_organic_carbon', 'N/A')}")
                if recommended:
                    n_f = format_field_dose(recommended.get("N"), acres) if recommended.get("N") is not None else "N/A"
                    p_f = format_field_dose(recommended.get("P"), acres) if recommended.get("P") is not None else "N/A"
                    k_f = format_field_dose(recommended.get("K"), acres) if recommended.get("K") is not None else "N/A"
                    lines.append(f"  * Recommended NPK for this field: N={n_f}, P={p_f}, K={k_f}")
                if required:
                    n_f = format_field_dose(required.get("N"), acres) if required.get("N") is not None else "N/A"
                    p_f = format_field_dose(required.get("P"), acres) if required.get("P") is not None else "N/A"
                    k_f = format_field_dose(required.get("K"), acres) if required.get("K") is not None else "N/A"
                    lines.append(f"  * Fertilizer required for this field: N={n_f}, P={p_f}, K={k_f}")
                if npk.get("soilN") is not None:
                    lines.append(
                        f"  * soilN={npk.get('soilN')} mg/kg | soilP={npk.get('soilP')} mg/kg | "
                        f"soilK={npk.get('soilK')} mg/kg | GNDVI={npk.get('gndvi')} | "
                        f"required_n_per_acre={npk.get('required_n_per_acre')}"
                    )
                materials = _format_npk_fertilizer_materials(npk, recommended, required, plot_acres=acres)
                if materials:
                    lines.append(materials)
            if npk.get("max_yield") is not None:
                from app.knowledge.yield_units import interpret_cached_yield

                crop_name = None
                info = payload.get("plot_info") if isinstance(payload.get("plot_info"), dict) else {}
                crop = info.get("crop_details") if isinstance(info.get("crop_details"), dict) else {}
                agro_layer = layers.get("agro_stats") if isinstance(layers.get("agro_stats"), dict) else {}
                crop_name = (
                    crop.get("crop_type")
                    or crop.get("crop_type_name")
                    or info.get("crop_type_name")
                    or agro_layer.get("crop_type")
                    or agro_layer.get("crop")
                )
                interpreted = interpret_cached_yield(npk.get("max_yield"), crop_name, acres)
                if interpreted and interpreted.get("line"):
                    lines.append(f"  * {interpreted['line']}")
                else:
                    lines.append(
                        f"  * Cached max_yield={npk.get('max_yield')} (unit unlabeled — "
                        "do NOT treat as tonnes/acre if the number is above ~120 for sugarcane)"
                    )
        elif not wanted:
            lines.append("- Layer 6 — NPK / Soil Nutrition: unavailable (may have timed out upstream).")

    # Layer 7: Current weather
    if _want("current_weather"):
        current = layers.get("current_weather")
        if current:
            lines.append(f"- Layer 7 — Current Weather: {current}")
        elif not wanted:
            lines.append("- Layer 7 — Current Weather: not included in latest report.")

    # Layer 8: Forecast
    if _want("forecast"):
        forecast = layers.get("forecast")
        if forecast:
            lines.append(f"- Layer 8 — Forecast: {forecast}")
        elif not wanted:
            lines.append("- Layer 8 — Forecast: not included in latest report.")

    if not wanted:
        lines.append(f"- Executive Summary — Crop Health: {payload.get('crop_health_summary', 'N/A')}")
        lines.append(f"- Executive Summary — Soil/Water: {payload.get('soil_water_summary', 'N/A')}")
        actions = payload.get("primary_action_items", [])
        if actions:
            lines.append("- Key Advisories:")
            for act in actions:
                lines.append(f"  * {act}")

    return "\n".join(lines)


DOMAIN_FORMATTERS = {
    "plots_info": format_plot_info_snippet,
    "soil_and_irrigation": format_plot_soil_snippet,
    "field_scores": format_plot_score_snippet,
    "cropo_weather": format_plot_weather_snippet,
    "daily_report": format_daily_report_snippet,
}

DOMAIN_KEY_GETTERS = {
    "plots_info": get_plot_info_cache_key,
    "soil_and_irrigation": get_soil_cache_key,
    "field_scores": get_score_cache_key,
    "cropo_weather": get_weather_cache_key,
    "daily_report": get_daily_report_cache_key,
}


async def build_context_for_plot(plot_id: str, domain_names: List[str]) -> str:
    """Pull cached domain data from Redis specifically for the given plot_id.
    
    Always includes crop profile and relevant environmental telemetry so the LLM
    can provide comprehensive, well-grounded agronomic explanations.
    """
    clean_id = str(plot_id).strip()

    # Determine domains to load: always include plot info so the crop type & variety is known,
    # plus the matched domains (or all domains if none matched specifically)
    if domain_names:
        target_domains = list(dict.fromkeys(["plots_info"] + domain_names))
    else:
        target_domains = ["plots_info", "soil_and_irrigation", "field_scores", "cropo_weather", "daily_report"]

    context_blocks = []

    for domain in target_domains:
        key_getter = DOMAIN_KEY_GETTERS.get(domain)
        formatter = DOMAIN_FORMATTERS.get(domain)
        if not key_getter or not formatter:
            continue

        cache_key = key_getter(clean_id)
        envelope = await redis_client.get_with_metadata(cache_key)

        if envelope and "data" in envelope:
            formatted_text = formatter(envelope["data"], envelope)
            context_blocks.append(formatted_text)

    if not context_blocks:
        return f"[No pre-fetched cached telemetry found for Plot #{clean_id}. Please load the plot data first.]"

    return f"--- COMPREHENSIVE TELEMETRY FEED FOR PLOT #{clean_id} ---\n" + "\n\n".join(context_blocks) + "\n--- END PLOT TELEMETRY ---"


def _offline_knowledge_block(analysis, language: str, plot_acres: Optional[float] = None) -> str:
    from app.knowledge.agriculture_knowledge import lookup_knowledge
    from app.context.area_units import format_organic_for_plot

    topics = list(analysis.topics or [])
    intent = getattr(analysis, "intent", "") or ""
    et_only = bool(getattr(analysis, "is_et_value_query", False))
    practice = bool(getattr(analysis, "is_practice_query", False))
    keys: List[str] = []
    if not et_only and intent not in {"OUT_OF_DOMAIN", "OFFLINE_FAQ"}:
        keys.append("fusion")
    if practice:
        keys.append("organic_ipm")
    elif (intent == "PEST" or "pest" in topics) and not (
        intent == "NUTRIENT" or "nutrient" in topics or getattr(analysis, "is_fertilizer_query", False)
    ):
        keys.append("organic_ipm")
        keys.append("pest_identity")
    if intent == "NUTRIENT" or "nutrient" in topics:
        keys.append("npk")
    if (intent == "NUTRIENT" or "nutrient" in topics) and ("pest" in topics or intent == "PEST"):
        keys.append("nutrition_and_pests")
        keys.append("organic_ipm")
    if getattr(analysis, "is_fertilizer_query", False) and "npk" not in keys:
        keys.append("npk")
    if getattr(analysis, "is_yield_query", False) or getattr(analysis, "is_yield_realism_query", False):
        keys.append("yield_sanity")
    if getattr(analysis, "is_yield_realism_query", False):
        pass
    elif getattr(analysis, "is_fertilizer_query", False) or getattr(analysis, "is_yield_improve_query", False) or (
        (intent == "NUTRIENT" or "nutrient" in topics) and not getattr(analysis, "is_yield_query", False)
    ):
        if "organic_fertilizer" not in keys:
            keys.append("organic_fertilizer")
        if "npk" not in keys:
            keys.append("npk")
    if not et_only and (intent in {"IRRIGATION", "SOIL"} or "irrigation" in topics or "soil" in topics):
        keys.append("soil_moisture")
    snippets = [lookup_knowledge(k, language) for k in keys]
    snippets = [s for s in snippets if s]
    organic_scaled = ""
    if plot_acres and "organic_fertilizer" in keys:
        organic_scaled = format_organic_for_plot(plot_acres)
        if organic_scaled:
            snippets.append(organic_scaled)
    if not snippets:
        return ""
    return "[AGRICULTURAL PRACTICE — not plot numbers]\n" + "\n".join(f"- {s}" for s in snippets)


async def build_intelligence_context(result, response_mode: str = "normal") -> str:
    """Prioritized grounded context from farm intelligence + existing domain formatters."""
    from app.context.context_budget import assemble_sections, budget_chars
    from app.context.evidence_formatter import (
        format_anomalies_block,
        format_conflicts_block,
        format_decision_block,
        format_farm_intelligence_marker,
        format_freshness_block,
        format_memories_block,
        format_trends_block,
    )

    plot_id = result.plot_id
    analysis = result.query_analysis
    language = getattr(analysis, "language", "en")
    limit = budget_chars(response_mode, analysis.intent)
    yield_only = bool(
        getattr(analysis, "is_yield_query", False)
        and not getattr(analysis, "is_fertilizer_query", False)
        and not getattr(analysis, "is_yield_improve_query", False)
        and not getattr(analysis, "is_yield_realism_query", False)
    )

    telemetry_blocks = []
    payloads = result.cache_payloads or {}
    selected = list(result.selected_layers or [])
    practice = bool(getattr(analysis, "is_practice_query", False))
    et_only = bool(getattr(analysis, "is_et_value_query", False))
    market = analysis.intent == "MARKET_PRICE" or bool(getattr(analysis, "is_market_price_query", False))
    soil_compact = analysis.intent in {"SOIL", "CURRENT_STATUS"} and not et_only
    for domain in result.matched_domains or []:
        payload = payloads.get(domain)
        if not isinstance(payload, dict):
            continue
        if market and domain in {"soil_and_irrigation", "cropo_weather"}:
            continue
        if domain == "daily_report":
            report_payload = payload
            info = payloads.get("plots_info")
            if isinstance(info, dict) and not payload.get("plot_info"):
                report_payload = dict(payload)
                report_payload["plot_info"] = info
            telemetry_blocks.append(
                format_daily_report_snippet(
                    report_payload,
                    None,
                    selected_layers=selected or None,
                    plot_acres=plot_acres_from_payloads(
                        payloads.get("plots_info"),
                        report_payload,
                        result.farm_state if isinstance(getattr(result, "farm_state", None), dict) else None,
                    ),
                    include_fertilizer_materials=not yield_only,
                )
            )
            continue
        if practice and domain in {"field_scores", "cropo_weather", "soil_and_irrigation"}:
            continue
        if domain == "soil_and_irrigation":
            telemetry_blocks.append(
                format_plot_soil_snippet(
                    payload,
                    None,
                    include_hourly_et=et_only,
                    compact=soil_compact,
                )
            )
            continue
        if domain == "cropo_weather":
            include_forecast = analysis.intent in {"FORECAST", "IRRIGATION", "PEST"} or "forecast" in (
                analysis.topics or []
            ) or "pest" in (analysis.topics or [])
            telemetry_blocks.append(
                format_plot_weather_snippet(payload, None, include_forecast=include_forecast)
            )
            continue
        formatter = DOMAIN_FORMATTERS.get(domain)
        if formatter:
            telemetry_blocks.append(formatter(payload, None))
    # Always include plot identity when present
    if "plots_info" not in (result.matched_domains or []) and isinstance(payloads.get("plots_info"), dict):
        telemetry_blocks.insert(0, format_plot_info_snippet(payloads["plots_info"], None))
    if market:
        telemetry_blocks.insert(
            0,
            format_farm_location_for_market(
                plot_id,
                payloads.get("plots_info"),
                payloads.get("soil_and_irrigation"),
                payloads.get("cropo_weather"),
            ),
        )

    farm_state_text = ""
    if telemetry_blocks:
        farm_state_text = (
            f"--- COMPREHENSIVE TELEMETRY FEED FOR PLOT #{plot_id} ---\n"
            + "\n\n".join(telemetry_blocks)
            + "\n--- END PLOT TELEMETRY ---"
        )
    elif analysis.intent != "OUT_OF_DOMAIN":
        farm_state_text = (
            f"[No pre-fetched cached telemetry found for Plot #{plot_id}. Please load the plot data first.]"
        )

    layer_notes = "\n".join((result.briefing or {}).get("notes") or [])
    layers_text = f"[SELECTED SATELLITE LAYERS]\n{layer_notes}" if layer_notes else ""
    if getattr(analysis, "is_et_value_query", False):
        layers_text = ""

    yield_only = bool(
        getattr(analysis, "is_yield_query", False)
        and not getattr(analysis, "is_fertilizer_query", False)
        and not getattr(analysis, "is_yield_improve_query", False)
        and not getattr(analysis, "is_yield_realism_query", False)
    )
    include_decision = (
        not bool(getattr(analysis, "is_et_value_query", False))
        and not yield_only
        and (bool(getattr(analysis, "is_yield_query", False)) or not practice)
        and (
            analysis.intent in {
                "IRRIGATION", "RECOMMENDATION", "PEST", "NUTRIENT", "WHY_DIAGNOSIS", "HARVEST",
            }
            or any(t in (analysis.topics or []) for t in ("irrigation", "pest", "nutrient", "harvest"))
            or bool(getattr(analysis, "is_yield_query", False))
        )
    )
    knowledge_text = _offline_knowledge_block(
        analysis,
        language,
        plot_acres=plot_acres_from_payloads(
            payloads.get("plots_info"),
            payloads.get("daily_report"),
            result.farm_state if isinstance(getattr(result, "farm_state", None), dict) else None,
        ),
    )
    yield_q = bool(getattr(analysis, "is_yield_query", False) or getattr(analysis, "is_fertilizer_query", False))
    yield_realism = bool(getattr(analysis, "is_yield_realism_query", False))
    yield_improve = bool(getattr(analysis, "is_yield_improve_query", False))
    pest_id = bool(
        getattr(analysis, "is_pest_identity_query", False)
        or analysis.intent == "PEST"
        or "pest" in (analysis.topics or [])
    )
    _FUSION = (
        "[GROUNDING] Short bullets. This question only. "
        "Never recap satellite. Never start with 'Based on the satellite'. "
        "Field-area quantities first (kg/acre in parentheses). "
        "Do not answer old off-topic questions from history. "
    )
    if yield_realism:
        grounding_note = (
            _FUSION
            + "3 bullets: realistic or not; INTERPRETED YIELD t/acre and total tonnes. No NPK/organic/pest."
        )
    elif yield_improve or (yield_q and getattr(analysis, "is_fertilizer_query", False)):
        grounding_note = (
            _FUSION
            + "MUST classify fertilizers: heading Chemical (Urea/DAP/MOP kg for this field) "
            "then heading Organic (FYM/vermicompost tonnes for this field). One yield line first. No carbon/pest."
        )
    elif getattr(analysis, "is_fertilizer_query", False):
        grounding_note = (
            _FUSION
            + "MUST classify: Chemical (Urea/DAP/MOP for this field) and Organic "
            "(ORGANIC FOR THIS FIELD tonnes). No carbon/pest essay."
        )
    elif getattr(analysis, "is_yield_query", False) and not getattr(analysis, "is_fertilizer_query", False):
        grounding_note = (
            _FUSION
            + "3–4 bullets: INTERPRETED YIELD tonnes for this plot (t/acre in parentheses). "
            "No NPK, organic, pest, or carbon."
        )
    elif pest_id and not et_only and not getattr(analysis, "is_fertilizer_query", False):
        grounding_note = (
            _FUSION
            + "Affected acres + 2–3 likely pest names. Scout to confirm. No NPK dump."
        )
    else:
        grounding_note = (
            _FUSION
            + "3–5 bullets for THIS question. Ignore unused telemetry."
        )
    sections = [
        (
            "system_note",
            grounding_note,
        ),
        (
            "resolved_question",
            f"Original question: {result.original_question}\nResolved question: {result.resolved_question}",
        ),
        ("decision", format_decision_block(result, language) if include_decision else ""),
        ("farm_state", farm_state_text),
        ("layers", layers_text),
        ("knowledge", knowledge_text),
        ("memories", format_memories_block(result.relevant_memories)),
        ("summary", f"[CONVERSATION SUMMARY]\n{result.conversation_summary}" if result.conversation_summary else ""),
        (
            "secondary",
            "\n\n".join(
                filter(
                    None,
                    [
                        format_trends_block(result.trends),
                        format_anomalies_block(result.anomalies),
                        format_conflicts_block(result.conflicts),
                        format_freshness_block(
                            result.freshness,
                            (result.farm_state or {}).get("missing_data") or [],
                        ),
                        format_farm_intelligence_marker(result),
                    ],
                )
            ),
        ),
    ]
    packed = assemble_sections(sections, limit)
    result.context = packed
    return packed


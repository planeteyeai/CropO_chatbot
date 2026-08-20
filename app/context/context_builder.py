"""Context Builder Layer (Per-Plot Scoped).

Retrieves cached plot telemetry from Redis and formats it into rich, natural-language
agronomic context (never raw JSON dumps) for LLM prompt injection.
"""

from typing import Any, Dict, List, Optional
import structlog
from app.cache.redis_client import redis_client
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


def format_plot_soil_snippet(payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
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
        f"- Recent Precipitation Influx: {rain} mm received yesterday",
        f"- Daily Crop Evapotranspiration (ET0) Water Loss: {et} mm/day",
        f"- Agronomic Water Management Advisory: {adv}",
    ]

    history = payload.get("history", [])
    if history and len(history) > 1:
        hist_strs = [
            f"{d.get('day', 'Day')}: {d.get('moisture')}% moisture (ET: {d.get('et_mm')}mm)"
            for d in history[-4:]
        ]
        lines.append(f"- Recent Multi-Day Moisture Progression: {' | '.join(hist_strs)}")

    return "\n".join(lines)


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


def format_plot_weather_snippet(payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
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
    if forecast:
        outlook_strs = [
            f"{d.get('date', 'Day')}: {d.get('avg_temp_celsius')}°C ({d.get('rain_prob_pct')}% rain, {d.get('rain_status', 'Clear')})"
            for d in forecast[:4]
        ]
        lines.append(f"- 4-Day Weather & Rainfall Trend: {' | '.join(outlook_strs)}")

    return "\n".join(lines)


def format_daily_report_snippet(payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
    """Format composite daily agronomic report."""
    if not isinstance(payload, dict):
        return "Daily agronomic report is currently unavailable in cache."

    fresh = _format_freshness(metadata)
    name = payload.get("plot_name", "?")
    date_str = payload.get("report_date", "Today")
    health = payload.get("crop_health_summary", "Canopy vigor optimal.")
    soil_water = payload.get("soil_water_summary", "Soil moisture adequate.")
    weather = payload.get("weather_summary", "Weather conditions stable.")
    actions = payload.get("primary_action_items", [])

    lines = [
        f"[Plot #{name} Daily Agronomic Executive Report ({date_str}){fresh}]",
        f"- Crop & Canopy Health Status: {health}",
        f"- Soil Hydration & Water Dynamics: {soil_water}",
        f"- Atmospheric Microclimate Summary: {weather}",
    ]

    if actions:
        lines.append("- Daily Agronomic Action Items & Advisories:")
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

"""Detect sudden agronomic changes using centralized thresholds."""

from typing import Any, Dict, List, Optional
from app.config.intelligence_rules import (
    FIELD_SCORE_DROP_ANOMALY,
    MOISTURE_DROP_ANOMALY_PCT,
    PEST_SPIKE_ANOMALY_PCT,
    TEMP_SWING_ANOMALY_C,
    GROWTH_STRESS_ALERT_PCT,
)
from app.context.area_units import acres_from_pct, format_acres, plot_acres_from_payloads


def _last_two(series: List[Dict[str, Any]], key: str) -> Optional[tuple]:
    vals = []
    for item in series:
        try:
            if item.get(key) is not None:
                vals.append(float(item[key]))
        except (TypeError, ValueError):
            continue
    if len(vals) < 2:
        return None
    return vals[-2], vals[-1]


def detect_anomalies(
    farm_state: Dict[str, Any],
    history_by_domain: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    anomalies: List[Dict[str, Any]] = []

    pair = _last_two(history_by_domain.get("field_scores") or [], "field_score_pct")
    if pair and pair[0] - pair[1] >= FIELD_SCORE_DROP_ANOMALY:
        anomalies.append({
            "type": "FIELD_SCORE_DROP",
            "severity": "HIGH",
            "detail": f"Field score dropped from {pair[0]:.1f} to {pair[1]:.1f}.",
        })

    pair = _last_two(history_by_domain.get("soil_and_irrigation") or [], "moisture_pct")
    if pair and pair[0] - pair[1] >= MOISTURE_DROP_ANOMALY_PCT:
        anomalies.append({
            "type": "SOIL_MOISTURE_DROP",
            "severity": "HIGH",
            "detail": f"Soil moisture fell from {pair[0]:.1f}% to {pair[1]:.1f}%.",
        })

    acres = plot_acres_from_payloads(farm_state)

    pair = _last_two(history_by_domain.get("daily_report") or [], "chewing_affected_pixel_percentage")
    if pair and pair[1] - pair[0] >= PEST_SPIKE_ANOMALY_PCT:
        a0 = acres_from_pct(pair[0], acres)
        a1 = acres_from_pct(pair[1], acres)
        if a0 is not None and a1 is not None:
            pest_detail = f"Chewing-pest affected area rose from {format_acres(a0)} to {format_acres(a1)}."
        else:
            pest_detail = "Chewing-pest affected area increased on this plot."
        anomalies.append({
            "type": "PEST_INCREASE",
            "severity": "MEDIUM",
            "detail": pest_detail,
        })

    pair = _last_two(history_by_domain.get("daily_report") or [], "stress_pixel_percentage")
    if pair and pair[1] >= GROWTH_STRESS_ALERT_PCT and pair[1] > pair[0]:
        stress_area = acres_from_pct(pair[1], acres)
        if stress_area is not None:
            stress_detail = f"Canopy stress area increased to {format_acres(stress_area)}."
        else:
            stress_detail = "Canopy stress area increased on this plot."
        anomalies.append({
            "type": "GROWTH_DECLINE",
            "severity": "MEDIUM",
            "detail": stress_detail,
        })

    pair = _last_two(history_by_domain.get("cropo_weather") or [], "temperature_celsius")
    if pair and abs(pair[1] - pair[0]) >= TEMP_SWING_ANOMALY_C:
        anomalies.append({
            "type": "WEATHER_SWING",
            "severity": "LOW",
            "detail": f"Temperature swung from {pair[0]:.1f}°C to {pair[1]:.1f}°C.",
        })

    return anomalies

"""Deterministic cross-layer conflict detection."""

from typing import Any, Dict, List, Optional
from app.config.intelligence_rules import (
    MOISTURE_DRY_PCT,
    MOISTURE_SATURATED_PCT,
    PEST_WATCH_PCT,
    RAIN_LIKELY_PCT,
)


def _moisture_pct(farm_state: Dict[str, Any]) -> Optional[float]:
    return (farm_state.get("soil") or {}).get("latest_moisture_pct")


def _rain_prob(farm_state: Dict[str, Any]) -> Optional[float]:
    current = (farm_state.get("weather") or {}).get("current") or {}
    prob = current.get("rainfall_probability_pct")
    if prob is not None:
        return prob
    forecast = (farm_state.get("weather") or {}).get("forecast") or []
    if forecast:
        return forecast[0].get("rain_prob_pct")
    return None


def _tomorrow_rain(farm_state: Dict[str, Any]) -> Optional[float]:
    forecast = (farm_state.get("weather") or {}).get("forecast") or []
    if len(forecast) >= 2:
        return forecast[1].get("rain_prob_pct")
    if forecast:
        return forecast[0].get("rain_prob_pct")
    return None


def detect_conflicts(farm_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    conflicts: List[Dict[str, Any]] = []
    moisture = _moisture_pct(farm_state)
    rain = _rain_prob(farm_state)
    rain_tmr = _tomorrow_rain(farm_state)
    pest = ((farm_state.get("satellite") or {}).get("pest_detection") or {}).get("pixel_summary") or {}
    chewing = pest.get("chewing_affected_pixel_percentage") or 0
    fungi = pest.get("fungi_affected_pixel_percentage") or 0

    if moisture is not None and moisture <= MOISTURE_DRY_PCT and rain is not None and rain >= RAIN_LIKELY_PCT:
        conflicts.append({
            "conflict_type": "IRRIGATION_VS_FORECAST",
            "severity": "MEDIUM",
            "recommended_resolution": "WAIT_AND_REASSESS",
            "detail": "Soil is dry but rainfall is likely — full irrigation may be unnecessary.",
        })

    if moisture is not None and moisture >= MOISTURE_SATURATED_PCT and rain_tmr is not None and rain_tmr >= RAIN_LIKELY_PCT:
        conflicts.append({
            "conflict_type": "SATURATION_VS_RAIN",
            "severity": "HIGH",
            "recommended_resolution": "PAUSE_IRRIGATION",
            "detail": "Soil is already wet and more rain is likely.",
        })

    try:
        fungi_n = float(fungi or 0)
        rain_n = float(rain or 0)
        if fungi_n >= PEST_WATCH_PCT and rain_n >= RAIN_LIKELY_PCT:
            conflicts.append({
                "conflict_type": "FUNGAL_VS_RAIN",
                "severity": "MEDIUM",
                "recommended_resolution": "INSPECT_AND_AVOID_OVERWATER",
                "detail": "Fungal-risk area plus likely rain increase disease pressure.",
            })
    except (TypeError, ValueError):
        pass

    score = (farm_state.get("field_health") or {}).get("field_score_pct")
    if score is not None and score >= 80 and moisture is not None and moisture <= MOISTURE_DRY_PCT:
        conflicts.append({
            "conflict_type": "HEALTH_VS_MOISTURE",
            "severity": "LOW",
            "recommended_resolution": "MONITOR_MOISTURE",
            "detail": "Canopy looks vigorous but root-zone moisture is low.",
        })

    return conflicts

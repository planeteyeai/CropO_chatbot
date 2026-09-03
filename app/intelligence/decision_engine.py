"""Evidence-based farm decisions. LLM must not invent these when evidence exists."""

from typing import Any, Dict, List, Optional
from app.config.intelligence_rules import (
    MOISTURE_CRITICAL_DRY_PCT,
    MOISTURE_DRY_PCT,
    MOISTURE_SATURATED_PCT,
    PEST_ALERT_PCT,
    PEST_WATCH_PCT,
    RAIN_HIGH_PCT,
    RAIN_LIKELY_PCT,
)
from app.context.area_units import format_share, plot_acres_from_payloads
from app.routing.query_classifier import QueryAnalysis

STALE_STATES = {"STALE", "VERY_STALE", "MISSING"}


def _moisture(farm_state: Dict[str, Any]) -> Optional[float]:
    return (farm_state.get("soil") or {}).get("latest_moisture_pct")


def _rain(farm_state: Dict[str, Any]) -> Optional[float]:
    current = (farm_state.get("weather") or {}).get("current") or {}
    return current.get("rainfall_probability_pct")


def _tomorrow_rain(farm_state: Dict[str, Any]) -> Optional[float]:
    forecast = (farm_state.get("weather") or {}).get("forecast") or []
    if not forecast:
        return None
    idx = 1 if len(forecast) > 1 else 0
    return forecast[idx].get("rain_prob_pct")


def _freshness_ok(farm_state: Dict[str, Any], domains: List[str]) -> bool:
    fresh = farm_state.get("freshness") or {}
    return not any(fresh.get(d) in STALE_STATES for d in domains)


def decide(
    analysis: QueryAnalysis,
    farm_state: Dict[str, Any],
    trends: Dict[str, str],
    anomalies: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not analysis.requires_decision and analysis.intent not in {
        "IRRIGATION", "RECOMMENDATION", "PEST", "NUTRIENT", "WHY_DIAGNOSIS",
    }:
        if analysis.intent in {"WEATHER", "FORECAST", "PLOT_INFO", "CROP_HEALTH", "CURRENT_STATUS", "SOIL"}:
            if analysis.intent in {"WEATHER", "FORECAST", "PLOT_INFO"}:
                return None
            return _status_decision(farm_state, conflicts)
        return None

    topics = set(analysis.topics)
    # Fertilizer questions (even with "pest") must not fall through to the pest MONITOR blurb.
    if getattr(analysis, "is_fertilizer_query", False) or analysis.intent == "NUTRIENT":
        return _nutrient_decision(farm_state)
    if analysis.intent == "PEST" or "pest" in topics:
        return _pest_decision(farm_state)
    if analysis.intent in {"IRRIGATION", "RECOMMENDATION"} or "irrigation" in topics or "soil" in topics:
        return _irrigation_decision(farm_state, trends, conflicts)
    if anomalies:
        return {
            "decision": "INSPECT_FIELD",
            "confidence": "MEDIUM",
            "evidence": [a.get("detail") for a in anomalies[:3]],
            "risks": ["Anomalous change detected in cached series."],
            "next_action": "Inspect the plot and reload telemetry if values look wrong.",
        }
    return _status_decision(farm_state, conflicts)


def _irrigation_decision(farm_state, trends, conflicts) -> Dict[str, Any]:
    moisture = _moisture(farm_state)
    rain = _rain(farm_state)
    rain_tmr = _tomorrow_rain(farm_state)
    soil_missing = not (farm_state.get("soil") or {})
    evidence: List[str] = []
    risks: List[str] = []

    if soil_missing or moisture is None:
        return {
            "decision": "INSUFFICIENT_DATA",
            "confidence": "LOW",
            "evidence": ["Soil moisture is not in cache for this plot."],
            "risks": ["Do not irrigate blindly without moisture data."],
            "next_action": "Reload plot telemetry, then re-ask whether to irrigate.",
        }

    evidence.append(f"Root-zone soil moisture is {moisture}% ({(farm_state.get('soil') or {}).get('moisture_status')}).")
    if rain is not None:
        evidence.append(f"Cached rain probability today is {rain}%.")
    if rain_tmr is not None:
        evidence.append(f"Cached rain probability (next forecast day) is {rain_tmr}%.")
    if trends.get("soil_moisture") and trends["soil_moisture"] != "INSUFFICIENT_DATA":
        evidence.append(f"Soil moisture trend: {trends['soil_moisture']}.")

    irrigation_conflict = any(c.get("conflict_type") == "IRRIGATION_VS_FORECAST" for c in conflicts)
    saturation_conflict = any(c.get("conflict_type") == "SATURATION_VS_RAIN" for c in conflicts)
    stale = not _freshness_ok(farm_state, ["soil_and_irrigation", "cropo_weather"])

    if moisture >= MOISTURE_SATURATED_PCT or saturation_conflict:
        decision = "MONITOR"
        next_action = "Pause drip until moisture recedes into the optimal band."
        risks.append("Over-irrigation risks poor root aeration.")
    elif irrigation_conflict or (
        moisture > MOISTURE_CRITICAL_DRY_PCT
        and rain_tmr is not None
        and rain_tmr >= RAIN_LIKELY_PCT
    ):
        decision = "WAIT_FOR_RAIN"
        next_action = "Hold a full irrigation cycle and reassess after the expected rain window."
        risks.append("Irrigating now plus rain could saturate the root zone.")
    elif moisture <= MOISTURE_CRITICAL_DRY_PCT and (rain_tmr is None or rain_tmr < RAIN_LIKELY_PCT):
        decision = "IRRIGATE_NOW" if not stale else "IRRIGATE_LIGHTLY"
        next_action = "Start a conservative irrigation cycle and recheck moisture."
        if stale:
            risks.append("Moisture/weather cache is not fresh — keep the cycle light.")
    elif moisture <= MOISTURE_DRY_PCT:
        if rain is not None and rain >= RAIN_HIGH_PCT:
            decision = "WAIT_FOR_RAIN"
            next_action = "Wait for likely rain; apply a light cycle only if rain misses."
        else:
            decision = "IRRIGATE_LIGHTLY"
            next_action = "Apply a light drip cycle rather than a full soaking."
    else:
        decision = "MONITOR"
        next_action = "Maintain the current schedule; no urgent irrigation change."

    if stale and decision == "IRRIGATE_NOW":
        decision = "IRRIGATE_LIGHTLY"
        risks.append("Stale cache reduced the recommendation to a light cycle.")

    return {
        "decision": decision,
        "confidence": "LOW" if stale else "MEDIUM",
        "evidence": evidence,
        "risks": risks,
        "next_action": next_action,
    }


def _pest_decision(farm_state) -> Dict[str, Any]:
    pest = ((farm_state.get("satellite") or {}).get("pest_detection") or {}).get("pixel_summary") or {}
    if not pest:
        return {
            "decision": "INSUFFICIENT_DATA",
            "confidence": "LOW",
            "evidence": ["Pest layer is not in the cached daily report."],
            "risks": ["Do not spray based on missing satellite pest data."],
            "next_action": "Reload the daily report, then scout the field if flags appear.",
        }
    chewing = float(pest.get("chewing_affected_pixel_percentage") or 0)
    fungi = float(pest.get("fungi_affected_pixel_percentage") or 0)
    worst = max(chewing, fungi)
    acres = plot_acres_from_payloads(farm_state)
    chewing_area = format_share(chewing, acres, pest)
    fungi_area = format_share(fungi, acres, pest)
    if worst >= PEST_ALERT_PCT:
        decision = "CHECK_PESTS"
        nxt = (
            f"Chewing {chewing_area} / fungi {fungi_area} — predict 2–3 likely pest names "
            "from crop/stage/weather, then walk flagged patches before any spray."
        )
    elif worst >= PEST_WATCH_PCT:
        decision = "INSPECT_FIELD"
        nxt = (
            f"Chewing {chewing_area} / fungi {fungi_area} — name likely pests from agronomy, "
            "then confirm damage in the field."
        )
    else:
        decision = "MONITOR"
        nxt = (
            f"Chewing {chewing_area} / fungi {fungi_area} (low). Still name likely pests; "
            "no blanket spray."
        )
    return {
        "decision": decision,
        "confidence": "MEDIUM",
        "evidence": [f"Chewing {chewing_area}; fungi {fungi_area} (cached pest layer)."],
        "risks": [],
        "next_action": nxt,
    }


def _nutrient_decision(farm_state) -> Dict[str, Any]:
    npk = (farm_state.get("satellite") or {}).get("npk_analysis") or {}
    if not npk:
        return {
            "decision": "INSUFFICIENT_DATA",
            "confidence": "LOW",
            "evidence": ["NPK layer is not in cache."],
            "risks": ["Do not apply fertilizer without nutrition data or a soil test."],
            "next_action": "Reload daily report / confirm with a soil test.",
        }
    req = npk.get("fertilizer_require_perAcre") or {}
    soil_n = npk.get("soilN")
    evidence = []
    if req:
        evidence.append(f"Cached fertilizer_require_perAcre: {req}")
    rec = npk.get("recommended_dose_perAcre") if isinstance(npk.get("recommended_dose_perAcre"), dict) else {}
    from app.knowledge.agriculture_knowledge import npk_to_common_fertilizers

    n = (req or {}).get("N") or rec.get("N") or npk.get("required_n_per_acre")
    p = (req or {}).get("P") or rec.get("P")
    k = (req or {}).get("K") or rec.get("K")
    plan = npk_to_common_fertilizers(n, p, k)
    acres = plot_acres_from_payloads(farm_state)
    if plan:
        from app.context.area_units import format_field_dose

        evidence.append(
            f"THIS FIELD fertilizers: Urea {format_field_dose(plan['urea_kg'], acres)}, "
            f"DAP {format_field_dose(plan['dap_kg'], acres)}, "
            f"MOP {format_field_dose(plan['mop_kg'], acres)}."
        )
    if soil_n is not None:
        evidence.append(
            f"soilN={npk.get('soilN')} mg/kg, soilP={npk.get('soilP')} mg/kg, "
            f"soilK={npk.get('soilK')} mg/kg, required_n_per_acre={npk.get('required_n_per_acre')}"
        )
    if not evidence:
        evidence.append("NPK layer present in cache.")
    return {
        "decision": "CHECK_NUTRIENTS",
        "confidence": "MEDIUM",
        "evidence": evidence,
        "risks": ["Satellite NPK is an estimate — verify before heavy application."],
        "next_action": (
            "Apply Urea, DAP, and MOP for THIS field's acres (see THIS FIELD fertilizers line); "
            "split nitrogen; compare with fertilizer already applied."
        ),
    }


def _status_decision(farm_state, conflicts) -> Dict[str, Any]:
    if conflicts:
        top = conflicts[0]
        return {
            "decision": "MONITOR",
            "confidence": "MEDIUM",
            "evidence": [top.get("detail")],
            "risks": [top.get("conflict_type")],
            "next_action": "Resolve the conflicting signals before a major input.",
        }
    return {
        "decision": "MONITOR",
        "confidence": "MEDIUM",
        "evidence": ["Cached plot telemetry is available for a status readout."],
        "risks": [],
        "next_action": "Ask a specific irrigation, pest, or health question for a recommendation.",
    }

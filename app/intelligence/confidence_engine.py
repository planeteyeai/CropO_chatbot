"""Farmer-facing confidence from freshness, completeness, and agreement."""

from typing import Any, Dict, List
from app.config.intelligence_rules import CRITICAL_DOMAINS_BY_TOPIC

HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"


def assess_confidence(
    topics: List[str],
    farm_state: Dict[str, Any],
    conflicts: List[Dict[str, Any]],
    trends: Dict[str, str],
    decision: Dict[str, Any] | None,
) -> str:
    if decision and decision.get("decision") == "INSUFFICIENT_DATA":
        return LOW

    freshness = farm_state.get("freshness") or {}
    missing = farm_state.get("missing_data") or []
    penalty = 0

    critical: List[str] = []
    for topic in topics or ["irrigation"]:
        critical.extend(CRITICAL_DOMAINS_BY_TOPIC.get(topic, []))
    critical = list(dict.fromkeys(critical)) or ["soil_and_irrigation", "cropo_weather"]

    for domain in critical:
        state = freshness.get(domain)
        if state == "MISSING" or domain in missing:
            penalty += 2
        elif state in {"VERY_STALE", "STALE"}:
            penalty += 1
        elif state == "AGING":
            penalty += 0  # still usable

    if conflicts:
        penalty += 1
    if any(c.get("severity") == "HIGH" for c in conflicts):
        penalty += 1

    usable_trends = [v for v in trends.values() if v not in {"INSUFFICIENT_DATA", None}]
    if topics and "irrigation" in topics and not usable_trends:
        penalty += 0  # optional

    if penalty >= 3:
        return LOW
    if penalty >= 1:
        return MEDIUM
    return HIGH


def confidence_badge(level: str) -> str:
    return {"HIGH": "🟢 Strong data support", "MEDIUM": "🟡 Moderate data support", "LOW": "🔴 Limited available data"}.get(
        level, "🟡 Moderate data support"
    )

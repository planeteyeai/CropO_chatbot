"""Format intelligence artifacts as concise natural-language blocks (never raw JSON dumps)."""

from typing import Any, Dict, List, Optional
from app.config.intelligence_rules import decision_label
from app.intelligence.orchestrator import IntelligenceResult


def format_decision_block(result: IntelligenceResult, language: str = "en") -> str:
    decision = result.decision or {}
    if not decision:
        return ""
    code = decision.get("decision") or ""
    lines = [
        "[INTERNAL DECISION — numbers only; do not paste this block as the farmer's answer]",
        f"Decision: {code} ({decision_label(code, language)})",
        f"Confidence: {result.confidence}",
    ]
    for ev in (decision.get("evidence") or [])[:4]:
        lines.append(f"- Evidence: {ev}")
    for risk in (decision.get("risks") or [])[:3]:
        lines.append(f"- Risk: {risk}")
    if decision.get("next_action"):
        lines.append(f"- Next step: {decision['next_action']}")
    return "\n".join(lines)


def format_freshness_block(freshness: Dict[str, str], missing: List[str]) -> str:
    if not freshness and not missing:
        return ""
    lines = ["[DATA FRESHNESS — never call this live]"]
    for domain, state in freshness.items():
        lines.append(f"- {domain}: {state}")
    if missing:
        lines.append(f"- Missing: {', '.join(missing[:8])}")
    return "\n".join(lines)


def format_trends_block(trends: Dict[str, str]) -> str:
    usable = {k: v for k, v in trends.items() if v and v != "INSUFFICIENT_DATA"}
    if not usable:
        return ""
    lines = ["[TRENDS FROM CACHED HISTORY]"]
    for name, label in usable.items():
        lines.append(f"- {name}: {label}")
    return "\n".join(lines)


def format_anomalies_block(anomalies: List[Dict[str, Any]]) -> str:
    if not anomalies:
        return ""
    lines = ["[ANOMALIES]"]
    for item in anomalies[:4]:
        lines.append(f"- {item.get('type')}: {item.get('detail')}")
    return "\n".join(lines)


def format_conflicts_block(conflicts: List[Dict[str, Any]]) -> str:
    if not conflicts:
        return ""
    lines = ["[CROSS-LAYER CONFLICTS]"]
    for item in conflicts[:3]:
        lines.append(
            f"- {item.get('conflict_type')} ({item.get('severity')}): "
            f"{item.get('detail')} → {item.get('recommended_resolution')}"
        )
    return "\n".join(lines)


def format_memories_block(memories: List[Dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines = ["[RELEVANT PRIOR TURNS — not the full chat log]"]
    for msg in memories[:5]:
        role = msg.get("role", "user")
        content = str(msg.get("content") or "").strip().replace("\n", " ")
        if len(content) > 220:
            content = content[:217] + "…"
        extra = ""
        if msg.get("recommendation"):
            extra = f" [prior rec: {msg['recommendation']}]"
        lines.append(f"- {role}: {content}{extra}")
    return "\n".join(lines)


def format_farm_intelligence_marker(result: IntelligenceResult) -> str:
    """Compact machine-readable block for Mock LLM / offline fallback."""
    decision = result.decision or {}
    soil = result.farm_state.get("soil") or {}
    weather = (result.farm_state.get("weather") or {}).get("current") or {}
    health = result.farm_state.get("field_health") or {}
    identity = result.farm_state.get("identity") or {}
    crop = (identity.get("crop_details") or {}).get("crop_type")
    return "\n".join(
        [
            "--- FARM INTELLIGENCE ---",
            f"intent: {result.query_analysis.intent}",
            f"topics: {', '.join(result.query_analysis.topics)}",
            f"decision: {decision.get('decision')}",
            f"confidence: {result.confidence}",
            f"crop: {crop}",
            f"moisture_pct: {soil.get('latest_moisture_pct')}",
            f"moisture_status: {soil.get('moisture_status')}",
            f"rain_prob: {weather.get('rainfall_probability_pct')}",
            f"temp_c: {weather.get('temperature_celsius')}",
            f"field_score: {health.get('field_score_pct')}",
            f"next_action: {decision.get('next_action')}",
            f"missing: {', '.join(result.farm_state.get('missing_data') or [])}",
            "--- END FARM INTELLIGENCE ---",
        ]
    )

"""Combine farm state, layer analyses, trends, and conflicts into a short briefing."""

from typing import Any, Dict, List


def reason_across_layers(
    farm_state: Dict[str, Any],
    layer_analyses: Dict[str, Any],
    trends: Dict[str, str],
    anomalies: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    notes: List[str] = []
    for name, analysis in layer_analyses.items():
        if not analysis.get("available"):
            continue
        if analysis.get("summary"):
            notes.append(f"{name}: {analysis['summary']}")
        notes.extend(analysis.get("alerts") or [])
    for trend_name, label in trends.items():
        if label not in {"INSUFFICIENT_DATA"}:
            notes.append(f"Trend {trend_name}: {label}.")
    for anomaly in anomalies:
        notes.append(anomaly.get("detail") or anomaly.get("type"))
    for conflict in conflicts:
        notes.append(conflict.get("detail") or conflict.get("conflict_type"))

    soil = farm_state.get("soil") or {}
    if (
        "soil_moisture" in layer_analyses
        and soil.get("latest_moisture_pct") is not None
    ):
        notes.insert(0, f"Root-zone moisture {soil.get('latest_moisture_pct')}% ({soil.get('moisture_status')}).")

    return {
        "notes": notes[:12],
        "layer_count_used": sum(1 for a in layer_analyses.values() if a.get("available")),
    }

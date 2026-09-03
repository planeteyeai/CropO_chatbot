"""Trend classification over bounded numeric series."""

from typing import Any, Dict, List, Optional
from app.config.intelligence_rules import (
    TREND_MIN_POINTS,
    TREND_STABLE_MAX_DELTA_RATIO,
    TREND_VOLATILE_REVERSAL_COUNT,
)

INCREASING = "INCREASING"
DECREASING = "DECREASING"
STABLE = "STABLE"
VOLATILE = "VOLATILE"
ANOMALOUS = "ANOMALOUS"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


def _to_floats(values: List[Any]) -> List[float]:
    out: List[float] = []
    for v in values:
        try:
            if v is None:
                continue
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def classify_series(values: List[Any], anomalous_jump: Optional[float] = None) -> str:
    nums = _to_floats(values)
    if len(nums) < TREND_MIN_POINTS:
        return INSUFFICIENT_DATA
    start, end = nums[0], nums[-1]
    span = max(abs(start), abs(end), 1.0)
    delta = end - start
    if anomalous_jump is not None and abs(delta) >= anomalous_jump:
        return ANOMALOUS
    if abs(delta) / span <= TREND_STABLE_MAX_DELTA_RATIO:
        return STABLE
    # Count meaningful direction reversals (ignore tiny noise)
    reversals = 0
    prev_dir = 0
    for a, b in zip(nums, nums[1:]):
        step = b - a
        direction = 1 if step > 0 else (-1 if step < 0 else 0)
        if direction and prev_dir and direction != prev_dir:
            reversals += 1
        if direction:
            prev_dir = direction
    if reversals >= TREND_VOLATILE_REVERSAL_COUNT:
        return VOLATILE
    if abs(delta) / span <= TREND_STABLE_MAX_DELTA_RATIO:
        return STABLE
    return INCREASING if delta > 0 else DECREASING


def analyze_trends(farm_state: Dict[str, Any], history_by_domain: Dict[str, List[Dict[str, Any]]]) -> Dict[str, str]:
    """Return metric → trend label for available series."""
    trends: Dict[str, str] = {}

    soil_hist = []
    if isinstance((farm_state.get("soil") or {}).get("history"), list):
        soil_hist = [(farm_state["soil"]["history"] or [])]
    snapshot_soil = history_by_domain.get("soil_and_irrigation") or []
    moisture_vals = [d.get("moisture") for series in soil_hist for d in series if isinstance(d, dict)]
    if not moisture_vals:
        moisture_vals = [s.get("moisture_pct") for s in snapshot_soil]
    trends["soil_moisture"] = classify_series(moisture_vals)

    score_snaps = history_by_domain.get("field_scores") or []
    trends["field_score"] = classify_series([s.get("field_score_pct") for s in score_snaps])

    weather_snaps = history_by_domain.get("cropo_weather") or []
    trends["temperature"] = classify_series([s.get("temperature_celsius") for s in weather_snaps])
    trends["rain_probability"] = classify_series([s.get("rainfall_probability_pct") for s in weather_snaps])

    report_snaps = history_by_domain.get("daily_report") or []
    trends["canopy_health"] = classify_series([s.get("healthy_pixel_percentage") for s in report_snaps])
    trends["pest_chewing"] = classify_series([s.get("chewing_affected_pixel_percentage") for s in report_snaps])

    return {k: v for k, v in trends.items() if v}

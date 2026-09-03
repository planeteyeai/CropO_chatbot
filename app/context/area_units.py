"""Convert satellite pixel shares/counts to plot acres for farmer-facing replies.

CropO Insights uses Sentinel-2 10 m pixels (100 m² each). Chat evidence usually
has percentages plus plot acreage, so affected acres = plot_acres × pct / 100.
"""

from __future__ import annotations

from typing import Any, Optional

# Same constants as GithubPush020726 insights_screen.dart (_areaLabelForPixelCount).
PIXEL_AREA_M2 = 100.0
M2_PER_ACRE = 4046.8564224


def coerce_acres(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        acres = float(value)
    except (TypeError, ValueError):
        return None
    if acres <= 0:
        return None
    return acres


def acres_from_pct(pct: Any, plot_acres: Any) -> Optional[float]:
    plot = coerce_acres(plot_acres)
    if plot is None or pct is None or pct == "":
        return None
    try:
        return plot * (float(pct) / 100.0)
    except (TypeError, ValueError):
        return None


def acres_from_pixel_count(count: Any) -> Optional[float]:
    if count is None or count == "":
        return None
    try:
        n = float(count)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return (n * PIXEL_AREA_M2) / M2_PER_ACRE


def format_acres(acres: Any) -> str:
    value = coerce_acres(acres)
    if value is None:
        try:
            if acres is not None and float(acres) == 0:
                return "0 acres"
        except (TypeError, ValueError):
            return "area not in cache"
        return "area not in cache"
    if value < 0.01:
        return "<0.01 acres"
    if value < 0.1:
        return f"{value:.3f} acres"
    return f"{value:.2f} acres"


def format_share(pct: Any, plot_acres: Any = None, pixel_summary: Any = None) -> str:
    """Farmer-facing area for a satellite class. Never says 'pixel'."""
    acres_plot = coerce_acres(plot_acres)
    px = pixel_summary if isinstance(pixel_summary, dict) else {}
    if acres_plot is None:
        acres_plot = acres_from_pixel_count(px.get("total_pixel_count"))
    acres = acres_from_pct(pct, acres_plot)
    if acres is None:
        return "area not in cache"
    if acres_plot:
        return f"{format_acres(acres)} of the {format_acres(acres_plot)} plot"
    return format_acres(acres)


def format_count_as_area(count: Any) -> str:
    acres = acres_from_pixel_count(count)
    if acres is None:
        return "area not in cache"
    return format_acres(acres)


def plot_acres_from_payloads(*sources: Any) -> Optional[float]:
    for src in sources:
        if not isinstance(src, dict):
            continue
        acres = coerce_acres(src.get("area_acres"))
        if acres:
            return acres
        crop = src.get("crop_details") if isinstance(src.get("crop_details"), dict) else {}
        acres = coerce_acres(crop.get("area_acres"))
        if acres:
            return acres
        identity = src.get("identity") if isinstance(src.get("identity"), dict) else {}
        acres = coerce_acres(identity.get("area_acres"))
        if acres:
            return acres
        layers = src.get("layers") if isinstance(src.get("layers"), dict) else {}
        agro = layers.get("agro_stats") if isinstance(layers.get("agro_stats"), dict) else src.get("agro_stats")
        if isinstance(agro, dict):
            acres = coerce_acres(agro.get("area_acres"))
            if acres:
                return acres
            soil = agro.get("soil") if isinstance(agro.get("soil"), dict) else {}
            acres = coerce_acres(soil.get("area_acres"))
            if acres:
                return acres
        satellite = src.get("satellite") if isinstance(src.get("satellite"), dict) else {}
        agro = satellite.get("agro_stats") if isinstance(satellite.get("agro_stats"), dict) else {}
        acres = coerce_acres(agro.get("area_acres")) if agro else None
        if acres:
            return acres
    return None


def scale_per_acre_amount(per_acre: Any, plot_acres: Any, digits: int = 1) -> Optional[float]:
    """kg/acre (or t/acre) × plot acres → amount for this field."""
    acres = coerce_acres(plot_acres)
    if acres is None or per_acre is None or per_acre == "":
        return None
    try:
        return round(float(per_acre) * acres, digits)
    except (TypeError, ValueError):
        return None


def format_field_dose(per_acre: Any, plot_acres: Any, unit: str = "kg") -> str:
    """Lead with this field's total; keep per-acre in parentheses."""
    acres = coerce_acres(plot_acres)
    total = scale_per_acre_amount(per_acre, acres)
    try:
        rate_s = f"{float(per_acre):.1f}"
    except (TypeError, ValueError):
        return str(per_acre)
    if total is None or acres is None:
        return f"{rate_s} {unit}/acre"
    return f"{total} {unit} for this {format_acres(acres)} field ({rate_s} {unit}/acre)"


def format_organic_for_plot(plot_acres: Any) -> str:
    acres = coerce_acres(plot_acres)
    if acres is None:
        return ""
    fym_lo = scale_per_acre_amount(2, acres)
    fym_hi = scale_per_acre_amount(5, acres)
    verm_lo = scale_per_acre_amount(1, acres)
    verm_hi = scale_per_acre_amount(1.5, acres)
    return (
        f"ORGANIC FOR THIS {format_acres(acres)} FIELD: "
        f"FYM/compost {fym_lo}–{fym_hi} tonnes "
        f"(2–5 t/acre); vermicompost {verm_lo}–{verm_hi} tonnes "
        f"(1–1.5 t/acre). Scale every other dose the same way."
    )

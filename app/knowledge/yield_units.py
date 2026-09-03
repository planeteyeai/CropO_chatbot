"""Interpret cached required-n max_yield into realistic tonnes/acre.

The CropO required-n field is unlabeled. Quoting it as tonnes/acre made
Plot 22 sugarcane look like 443 t/acre — that is not possible. Maharashtra
cane is typically ~28–40 t/acre; good fields 40–60; exceptional 80–100.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

HA_PER_ACRE = 0.40468564224

_CANE = ("sugarcane", "sugar cane", "cane", "ऊस", "गन्ना", "ಕಬ್ಬು")


def _crop_name(crop: Any) -> str:
    if isinstance(crop, dict):
        crop = crop.get("crop_type") or crop.get("crop_type_name") or ""
    return str(crop or "").strip()


def is_sugarcane(crop: Any) -> bool:
    name = _crop_name(crop).lower()
    return any(tok in name for tok in _CANE)


def interpret_cached_yield(
    raw: Any,
    crop: Any = None,
    plot_acres: Any = None,
) -> Optional[Dict[str, Any]]:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None

    acres = None
    try:
        acres = float(plot_acres) if plot_acres not in (None, "") else None
        if acres is not None and acres <= 0:
            acres = None
    except (TypeError, ValueError):
        acres = None

    cane = is_sugarcane(crop)
    unknown_crop = not _crop_name(crop)
    assumed = "tonnes/acre"
    t_acre = value

    if cane or (unknown_crop and value > 150):
        if 8 <= value <= 120:
            assumed = "tonnes/acre"
            t_acre = value
        elif 121 <= value <= 300:
            assumed = "tonnes/hectare"
            t_acre = value * HA_PER_ACRE
        elif 301 <= value <= 1200:
            assumed = "quintals/acre"
            t_acre = value / 10.0
        else:
            assumed = "unknown"
            t_acre = None
    elif value > 150:
        assumed = "not tonnes/acre"
        t_acre = None

    if t_acre is None:
        return {
            "raw": value,
            "tonnes_per_acre": None,
            "tonnes_plot": None,
            "unit_assumed": assumed,
            "realistic": False,
            "line": (
                f"INTERPRETED YIELD: cached max_yield={value} is NOT tonnes/acre "
                f"for this crop. Do not quote {value} t/acre. Say the unit is unclear "
                "and give a typical range instead (sugarcane Maharashtra ~28–40 t/acre)."
            ),
        }

    t_acre = round(t_acre, 1)
    realistic = 12 <= t_acre <= 100 if (cane or unknown_crop) else True
    t_plot = round(t_acre * acres, 1) if acres else None
    plot_bit = (
        f" For this {acres:.2f}-acre plot that is about {t_plot} tonnes total."
        if acres and t_plot is not None
        else ""
    )
    range_bit = (
        " Typical irrigated sugarcane in Maharashtra is ~28–40 t/acre; "
        "good fields 40–60; exceptional 80–100. Values above ~120 t/acre are not realistic."
        if cane
        else ""
    )
    return {
        "raw": value,
        "tonnes_per_acre": t_acre,
        "tonnes_plot": t_plot,
        "unit_assumed": assumed,
        "realistic": realistic,
        "line": (
            f"INTERPRETED YIELD (use this, not the raw max_yield as tonnes/acre): "
            f"tentative {t_acre} tonnes/acre"
            + (f" ({t_plot} tonnes on this plot)" if t_plot is not None else "")
            + f". Cached max_yield={value} treated as {assumed}."
            + plot_bit
            + range_bit
            + " Always say tentative — not a harvest weighment."
        ),
    }

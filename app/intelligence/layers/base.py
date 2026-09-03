"""Layer analysis helpers for daily-report satellite layers."""

from typing import Any, Dict, List, Optional

from app.context.area_units import format_field_dose, format_share

LAYER_ANALYZERS = (
    "agro_stats",
    "growth",
    "soil_moisture",
    "water_uptake",
    "pest_detection",
    "npk_analysis",
    "current_weather",
    "forecast",
)


def _px(layer: Any) -> Dict[str, Any]:
    if not isinstance(layer, dict):
        return {}
    px = layer.get("pixel_summary")
    return px if isinstance(px, dict) else {}


def analyze_layer(name: str, layer: Any, plot_acres: Optional[float] = None) -> Dict[str, Any]:
    if layer is None:
        return {"name": name, "available": False, "summary": f"{name} layer not in cache.", "alerts": []}
    analyzer = {
        "agro_stats": _agro,
        "growth": _growth,
        "soil_moisture": _soil,
        "water_uptake": _uptake,
        "pest_detection": _pest,
        "npk_analysis": _npk,
        "current_weather": _weather,
        "forecast": _forecast,
    }.get(name)
    if not analyzer:
        return {"name": name, "available": True, "summary": f"{name} present.", "alerts": []}
    return analyzer(layer, plot_acres)


def analyze_selected_layers(
    layers: Dict[str, Any],
    selected: List[str],
    plot_acres: Optional[float] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in selected:
        out[name] = analyze_layer(
            name,
            layers.get(name) if isinstance(layers, dict) else None,
            plot_acres=plot_acres,
        )
    return out


def _agro(layer: Dict[str, Any], plot_acres: Optional[float] = None) -> Dict[str, Any]:
    stage = layer.get("current_growth_stage")
    days = layer.get("days_to_harvest")
    return {
        "name": "agro_stats",
        "available": True,
        "summary": f"Growth stage {stage or 'n/a'}; days to harvest {days if days is not None else 'n/a'}.",
        "metrics": {"current_growth_stage": stage, "days_to_harvest": days},
        "alerts": [],
    }


def _growth(layer: Dict[str, Any], plot_acres: Optional[float] = None) -> Dict[str, Any]:
    px = _px(layer)
    healthy = px.get("healthy_pixel_percentage")
    stress = px.get("stress_pixel_percentage")
    alerts = []
    try:
        if float(stress or 0) >= 30:
            alerts.append("High canopy stress area.")
    except (TypeError, ValueError):
        pass
    return {
        "name": "growth",
        "available": bool(px or layer),
        "summary": (
            f"Healthy canopy {format_share(healthy, plot_acres, px)}; "
            f"stress {format_share(stress, plot_acres, px)}."
        ),
        "metrics": {"healthy": healthy, "stress": stress},
        "alerts": alerts,
    }


def _soil(layer: Dict[str, Any], plot_acres: Optional[float] = None) -> Dict[str, Any]:
    px = _px(layer)
    less = px.get("less_pixel_percentage")
    excess = px.get("excess_pixel_percentage")
    return {
        "name": "soil_moisture",
        "available": bool(px),
        "summary": (
            f"Less-moisture area {format_share(less, plot_acres, px)}; "
            f"excess {format_share(excess, plot_acres, px)}."
        ),
        "metrics": {"less": less, "excess": excess},
        "alerts": [],
    }


def _uptake(layer: Dict[str, Any], plot_acres: Optional[float] = None) -> Dict[str, Any]:
    px = _px(layer)
    return {
        "name": "water_uptake",
        "available": bool(px),
        "summary": (
            f"Very healthy uptake {format_share(px.get('very_healthy_pixel_percentage'), plot_acres, px)}; "
            f"deficient {format_share(px.get('deficient_pixel_percentage'), plot_acres, px)}."
        ),
        "metrics": px,
        "alerts": [],
    }


def _pest(layer: Dict[str, Any], plot_acres: Optional[float] = None) -> Dict[str, Any]:
    px = _px(layer)
    chewing = px.get("chewing_affected_pixel_percentage")
    fungi = px.get("fungi_affected_pixel_percentage")
    alerts = []
    try:
        if float(chewing or 0) >= 8 or float(fungi or 0) >= 8:
            alerts.append("Pest-affected area above watch threshold.")
    except (TypeError, ValueError):
        pass
    return {
        "name": "pest_detection",
        "available": bool(px),
        "summary": (
            f"Chewing {format_share(chewing, plot_acres, px)}; "
            f"fungi {format_share(fungi, plot_acres, px)}."
        ),
        "metrics": {"chewing": chewing, "fungi": fungi},
        "alerts": alerts,
    }


def _npk(layer: Dict[str, Any], plot_acres: Optional[float] = None) -> Dict[str, Any]:
    from app.knowledge.agriculture_knowledge import npk_to_common_fertilizers

    soil = layer.get("soil_statistics") if isinstance(layer.get("soil_statistics"), dict) else {}
    req = layer.get("fertilizer_require_perAcre") if isinstance(layer.get("fertilizer_require_perAcre"), dict) else {}
    rec = layer.get("recommended_dose_perAcre") if isinstance(layer.get("recommended_dose_perAcre"), dict) else {}
    n = layer.get("soilN") if layer.get("soilN") is not None else soil.get("total_nitrogen")
    p = layer.get("soilP") if layer.get("soilP") is not None else soil.get("phosphorus")
    k = layer.get("soilK") if layer.get("soilK") is not None else soil.get("potassium")
    n_kg = req.get("N") if req.get("N") is not None else rec.get("N")
    p_kg = req.get("P") if req.get("P") is not None else rec.get("P")
    k_kg = req.get("K") if req.get("K") is not None else rec.get("K")
    plan = npk_to_common_fertilizers(n_kg, p_kg, k_kg)
    fert_bit = ""
    if plan:
        fert_bit = (
            f" THIS FIELD: Urea {format_field_dose(plan['urea_kg'], plot_acres)}; "
            f"DAP {format_field_dose(plan['dap_kg'], plot_acres)}; "
            f"MOP {format_field_dose(plan['mop_kg'], plot_acres)}."
        )
    return {
        "name": "npk_analysis",
        "available": True,
        "summary": f"soilN/soilP/soilK {n}/{p}/{k}; require/acre {req}.{fert_bit}",
        "metrics": {
            "soilN": n,
            "soilP": p,
            "soilK": k,
            "gndvi": layer.get("gndvi"),
            "required_n_per_acre": layer.get("required_n_per_acre"),
            "soil_statistics": soil,
            "fertilizer_require_perAcre": req,
        },
        "alerts": [],
    }


def _weather(layer: Any, plot_acres: Optional[float] = None) -> Dict[str, Any]:
    return {
        "name": "current_weather",
        "available": bool(layer),
        "summary": "Current weather snapshot present in daily report." if layer else "Current weather layer missing.",
        "metrics": {},
        "alerts": [],
    }


def _forecast(layer: Any, plot_acres: Optional[float] = None) -> Dict[str, Any]:
    return {
        "name": "forecast",
        "available": bool(layer),
        "summary": "Forecast snapshot present in daily report." if layer else "Forecast layer missing.",
        "metrics": {},
        "alerts": [],
    }

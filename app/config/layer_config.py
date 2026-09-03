"""Daily-report layer relevance by agronomic topic.

Weights: HIGH | MEDIUM | LOW | IGNORE
Only HIGH/MEDIUM layers are analyzed for a given question.
"""

from typing import Dict, List

LAYER_NAMES = (
    "agro_stats",
    "growth",
    "soil_moisture",
    "water_uptake",
    "pest_detection",
    "npk_analysis",
    "current_weather",
    "forecast",
)

# topic -> {layer: weight}
TOPIC_LAYER_RELEVANCE: Dict[str, Dict[str, str]] = {
    "irrigation": {
        "soil_moisture": "HIGH",
        "water_uptake": "HIGH",
        "current_weather": "HIGH",
        "forecast": "HIGH",
        "growth": "MEDIUM",
        "agro_stats": "LOW",
        "pest_detection": "LOW",
        "npk_analysis": "LOW",
    },
    "uptake": {
        "water_uptake": "HIGH",
        "soil_moisture": "LOW",
        "growth": "LOW",
        "agro_stats": "IGNORE",
        "pest_detection": "IGNORE",
        "npk_analysis": "IGNORE",
        "current_weather": "IGNORE",
        "forecast": "IGNORE",
    },
    "soil": {
        "soil_moisture": "HIGH",
        "water_uptake": "HIGH",
        "npk_analysis": "MEDIUM",
        "agro_stats": "MEDIUM",
        "forecast": "MEDIUM",
        "current_weather": "LOW",
        "growth": "LOW",
        "pest_detection": "IGNORE",
    },
    "weather": {
        "current_weather": "HIGH",
        "forecast": "HIGH",
        "soil_moisture": "MEDIUM",
        "water_uptake": "LOW",
        "growth": "LOW",
        "agro_stats": "IGNORE",
        "pest_detection": "LOW",
        "npk_analysis": "IGNORE",
    },
    "forecast": {
        "forecast": "HIGH",
        "current_weather": "HIGH",
        "soil_moisture": "MEDIUM",
        "water_uptake": "MEDIUM",
        "pest_detection": "LOW",
        "growth": "LOW",
        "agro_stats": "IGNORE",
        "npk_analysis": "IGNORE",
    },
    "pest": {
        "pest_detection": "HIGH",
        "growth": "HIGH",
        "current_weather": "MEDIUM",
        "forecast": "MEDIUM",
        "soil_moisture": "LOW",
        "agro_stats": "LOW",
        "water_uptake": "LOW",
        "npk_analysis": "IGNORE",
    },
    "nutrient": {
        "npk_analysis": "HIGH",
        "agro_stats": "HIGH",
        "growth": "MEDIUM",
        "soil_moisture": "MEDIUM",
        "water_uptake": "LOW",
        "pest_detection": "LOW",
        "current_weather": "IGNORE",
        "forecast": "IGNORE",
    },
    "crop_health": {
        "growth": "HIGH",
        "agro_stats": "HIGH",
        "pest_detection": "MEDIUM",
        "npk_analysis": "MEDIUM",
        "soil_moisture": "MEDIUM",
        "water_uptake": "MEDIUM",
        "current_weather": "LOW",
        "forecast": "LOW",
    },
    "harvest": {
        "agro_stats": "HIGH",
        "growth": "HIGH",
        "npk_analysis": "MEDIUM",
        "forecast": "MEDIUM",
        "current_weather": "LOW",
        "pest_detection": "MEDIUM",
        "soil_moisture": "LOW",
        "water_uptake": "LOW",
    },
    "plot_info": {
        "agro_stats": "MEDIUM",
        "growth": "LOW",
        "soil_moisture": "IGNORE",
        "water_uptake": "IGNORE",
        "pest_detection": "IGNORE",
        "npk_analysis": "LOW",
        "current_weather": "IGNORE",
        "forecast": "IGNORE",
    },
}

WEIGHT_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "IGNORE": 0}


def layers_for_topics(topics: List[str], min_weight: str = "MEDIUM") -> List[str]:
    """Union of layers meeting min_weight across the given topics, HIGH first."""
    min_rank = WEIGHT_RANK.get(min_weight, 2)
    scores: Dict[str, int] = {}
    for topic in topics:
        mapping = TOPIC_LAYER_RELEVANCE.get(topic.lower(), {})
        for layer, weight in mapping.items():
            rank = WEIGHT_RANK.get(weight, 0)
            if rank >= min_rank:
                scores[layer] = max(scores.get(layer, 0), rank)
    return sorted(scores.keys(), key=lambda name: (-scores[name], name))

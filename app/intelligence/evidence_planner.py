"""Decide which Redis domains and daily-report layers to read for a query."""

from dataclasses import dataclass, field
from typing import List
from app.config.layer_config import layers_for_topics
from app.routing.query_classifier import QueryAnalysis

TOPIC_DOMAINS = {
    "irrigation": ["soil_and_irrigation", "cropo_weather", "daily_report"],
    "uptake": ["daily_report"],
    "soil": ["soil_and_irrigation", "daily_report"],
    "weather": ["cropo_weather", "daily_report"],
    "forecast": ["cropo_weather", "daily_report"],
    "pest": ["daily_report", "field_scores"],
    "nutrient": ["daily_report", "plots_info"],
    "crop_health": ["field_scores", "daily_report", "plots_info"],
    "harvest": ["daily_report", "plots_info"],
    "plot_info": ["plots_info", "daily_report"],
    "market": ["plots_info", "soil_and_irrigation", "cropo_weather", "field_scores", "daily_report"],
}

INTENT_DOMAINS = {
    "IRRIGATION": ["soil_and_irrigation", "cropo_weather", "daily_report"],
    "SOIL": ["soil_and_irrigation", "daily_report"],
    "WEATHER": ["cropo_weather"],
    "FORECAST": ["cropo_weather", "daily_report"],
    "CROP_HEALTH": ["field_scores", "daily_report"],
    "PEST": ["daily_report", "field_scores"],
    "NUTRIENT": ["daily_report"],
    "HARVEST": ["daily_report", "plots_info"],
    "PLOT_INFO": ["plots_info", "daily_report"],
    "RECOMMENDATION": ["soil_and_irrigation", "cropo_weather", "field_scores", "daily_report"],
    "WHY_DIAGNOSIS": ["soil_and_irrigation", "field_scores", "daily_report", "cropo_weather"],
    "TREND": ["soil_and_irrigation", "field_scores", "cropo_weather"],
    "CURRENT_STATUS": ["plots_info", "field_scores", "daily_report"],
    "MARKET_PRICE": ["plots_info", "soil_and_irrigation", "cropo_weather", "field_scores", "daily_report"],
}


@dataclass
class EvidencePlan:
    domains: List[str] = field(default_factory=list)
    layers: List[str] = field(default_factory=list)
    requires_trend: bool = False
    requires_decision: bool = False
    requires_history: bool = False


def plan_evidence(analysis: QueryAnalysis, active_topic: str | None = None) -> EvidencePlan:
    if analysis.intent == "OUT_OF_DOMAIN":
        return EvidencePlan(domains=[], layers=[], requires_trend=False, requires_decision=False)

    domains: List[str] = []
    topics = list(analysis.topics)
    # Only inherit the previous topic for elliptical follow-ups with no topic of their own.
    if (
        active_topic
        and active_topic not in topics
        and getattr(analysis, "is_follow_up", False)
        and not topics
    ):
        topics.append(active_topic)

    for topic in topics:
        domains.extend(TOPIC_DOMAINS.get(topic, []))
    domains.extend(INTENT_DOMAINS.get(analysis.intent, []))
    domains.extend(analysis.matched_domains)

    if analysis.requires_plot_data:
        domains.insert(0, "plots_info")

    # Deduplicate, preserve order
    unique_domains = list(dict.fromkeys(d for d in domains if d))

    if analysis.requires_plot_data and not unique_domains:
        unique_domains = ["plots_info", "field_scores", "daily_report"]

    # Hourly/daily ET0 number questions: soil compute-et cache only — skip weather essays.
    if getattr(analysis, "is_et_value_query", False):
        unique_domains = [d for d in unique_domains if d in {"plots_info", "soil_and_irrigation"}]
        if "soil_and_irrigation" not in unique_domains:
            unique_domains.append("soil_and_irrigation")
        if analysis.requires_plot_data and "plots_info" not in unique_domains:
            unique_domains.insert(0, "plots_info")

    # Practice / organic-IPM questions: pest layer + crop identity only.
    fert = getattr(analysis, "is_fertilizer_query", False)
    practice = getattr(analysis, "is_practice_query", False)
    yield_q = getattr(analysis, "is_yield_query", False)
    if practice and not fert and not yield_q:
        unique_domains = [d for d in unique_domains if d in {"plots_info", "daily_report"}]
        if analysis.requires_plot_data and "plots_info" not in unique_domains:
            unique_domains.insert(0, "plots_info")
        if "daily_report" not in unique_domains:
            unique_domains.append("daily_report")
        if "nutrient" in topics or analysis.intent == "NUTRIENT":
            layers = ["npk_analysis"]
        else:
            layers = ["pest_detection"]
    elif fert or yield_q:
        keep = {"plots_info", "daily_report"}
        if fert or getattr(analysis, "is_yield_improve_query", False):
            keep.add("field_scores")
        unique_domains = [d for d in unique_domains if d in keep]
        if analysis.requires_plot_data and "plots_info" not in unique_domains:
            unique_domains.insert(0, "plots_info")
        if "daily_report" not in unique_domains:
            unique_domains.append("daily_report")
        layers = ["npk_analysis"]
        if yield_q and "agro_stats" not in layers:
            layers.insert(0, "agro_stats")
        if "pest" in topics:
            layers.append("pest_detection")
    elif getattr(analysis, "is_et_value_query", False):
        layers = []
    else:
        layers = layers_for_topics(topics or _topics_from_intent(analysis.intent), min_weight="MEDIUM")
        if "daily_report" in unique_domains and not layers:
            layers = layers_for_topics(["crop_health"], min_weight="HIGH")
        unique_domains, layers = _focus_evidence(analysis, topics, unique_domains, layers)

    skip_decision = bool(
        getattr(analysis, "is_et_value_query", False)
        or (getattr(analysis, "is_practice_query", False) and not getattr(analysis, "is_yield_query", False))
        or analysis.intent in {
            "WEATHER", "FORECAST", "PLOT_INFO", "SOIL", "CROP_HEALTH",
            "CURRENT_STATUS", "MARKET_PRICE",
        }
    )

    return EvidencePlan(
        domains=unique_domains,
        layers=layers,
        requires_trend=(
            False
            if skip_decision
            else (analysis.requires_trend or analysis.intent in {"IRRIGATION", "RECOMMENDATION", "TREND"})
        ),
        requires_decision=(
            False
            if skip_decision
            else (analysis.requires_decision or analysis.intent in {"IRRIGATION", "RECOMMENDATION", "PEST"})
        ),
        requires_history=analysis.requires_history or analysis.requires_trend,
    )


def _focus_evidence(
    analysis: QueryAnalysis,
    topics: List[str],
    domains: List[str],
    layers: List[str],
) -> tuple:
    """Keep one question on one evidence slice so Gemini cannot dump extra layers."""
    intent = analysis.intent
    topic_set = set(topics)
    keep_plots = "plots_info" if "plots_info" in domains or analysis.requires_plot_data else None

    def _pack(wanted_domains: List[str], wanted_layers: List[str]) -> tuple:
        ordered = []
        if keep_plots:
            ordered.append("plots_info")
        for domain in wanted_domains:
            if domain not in ordered:
                ordered.append(domain)
        return ordered, wanted_layers

    if "uptake" in topic_set and "irrigation" not in topic_set:
        return _pack(["daily_report"], ["water_uptake"])
    if intent == "PEST" or topic_set == {"pest"}:
        return _pack(
            ["plots_info", "cropo_weather", "daily_report"],
            ["pest_detection", "agro_stats"],
        )
    if intent == "SOIL" or topic_set == {"soil"}:
        return _pack(["soil_and_irrigation"], ["soil_moisture"])
    if intent == "IRRIGATION" or topic_set == {"irrigation"}:
        return _pack(["soil_and_irrigation", "cropo_weather"], [])
    if intent == "WEATHER" and "forecast" not in topic_set:
        return _pack(["cropo_weather"], ["current_weather"])
    if intent == "FORECAST" or "forecast" in topic_set:
        return _pack(["cropo_weather"], ["forecast", "current_weather"])
    if getattr(analysis, "is_yield_query", False):
        wanted = ["agro_stats", "npk_analysis"]
        if "pest" in topic_set:
            wanted.append("pest_detection")
        return _pack(
            ["plots_info", "daily_report"],
            wanted,
        )
    if intent in {"PLOT_INFO", "HARVEST"}:
        return _pack(["daily_report"], ["agro_stats"])
    if intent == "CROP_HEALTH":
        return _pack(["field_scores", "daily_report"], ["growth", "agro_stats"])
    if intent == "CURRENT_STATUS" and not topic_set:
        return _pack(["field_scores", "daily_report"], ["agro_stats", "growth"])
    if intent == "NUTRIENT":
        return _pack(["daily_report"], ["npk_analysis"] + (["pest_detection"] if "pest" in topic_set else []))
    if intent == "MARKET_PRICE" or "market" in topic_set:
        return _pack(
            ["plots_info", "soil_and_irrigation", "cropo_weather", "field_scores", "daily_report"],
            ["growth", "pest_detection", "agro_stats"],
        )
    return domains, layers


def _topics_from_intent(intent: str) -> List[str]:
    mapping = {
        "IRRIGATION": ["irrigation"],
        "SOIL": ["soil"],
        "WEATHER": ["weather"],
        "FORECAST": ["forecast"],
        "CROP_HEALTH": ["crop_health"],
        "PEST": ["pest"],
        "NUTRIENT": ["nutrient"],
        "HARVEST": ["harvest"],
        "PLOT_INFO": ["plot_info"],
        "RECOMMENDATION": ["irrigation"],
        "CURRENT_STATUS": ["plot_info", "crop_health"],
        "MARKET_PRICE": ["market"],
    }
    return mapping.get(intent, [])

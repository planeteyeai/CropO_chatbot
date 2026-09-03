"""Fast deterministic query classification.

Preserves the existing keyword domain router and adds intent/topic/action flags.
Typical runtime target: < 30ms with zero network/LLM calls.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence
import structlog
from app.routing.intent_router import route_query
from app.routing.language_router import detect_language, expand_for_routing

logger = structlog.get_logger(__name__)

INTENTS = (
    "CURRENT_STATUS",
    "RECOMMENDATION",
    "WHY_DIAGNOSIS",
    "TREND",
    "COMPARISON",
    "FORECAST",
    "IRRIGATION",
    "SOIL",
    "WEATHER",
    "CROP_HEALTH",
    "PEST",
    "NUTRIENT",
    "HARVEST",
    "PLOT_INFO",
    "MARKET_PRICE",
    "GENERAL_AGRICULTURE",
    "OFFLINE_FAQ",
    "OUT_OF_DOMAIN",
)

_FARM_MARKERS = (
    "my ", "our ", "this plot", "this field", "this farm", "should i", "do i",
    "plot #", "plot 1", "plot 2", "my ndvi", "my crop", "for this plot",
    "for my plot", "on my plot",
    "मेरा", "मेरी", "मेरे", "क्या करूँ",
    "माझा", "माझी", "माझे", "करू",
    "ನನ್ನ",
)

_AGRI_TOKENS = (
    "soil", "moisture", "irrigat", "drip", "weather", "rain", "forecast", "temp",
    "ndvi", "ndwi", "ndmi", "crop", "farm", "plot", "field", "pest", "npk",
    "fertiliz", "fertiliser", "manure", "urea", "harvest", "canopy", "satellite",
    "et0", "eto", "uptake", "health", "score", "acre", "mango", "grape", "wheat",
    "tomato", "spray", "scout", "precaution", "organic", "ipm", "neem",
    "outside", "drinking", "attacking", "infest", "mandi", "apmc", "msp",
    "yield", "yeild", "production", "quintal", "tonne",
    "नमी", "सिंचाई", "मिट्टी", "फसल", "खेत", "मौसम", "बारिश", "खाद",
    "उपज", "उत्पादन", "उत्पन्न",
    "ओलावा", "सिंचन", "पीक", "शेत", "हवामान", "पाऊस",
    "ತೇವಾಂಶ", "ನೀರಾವರಿ", "ಬೆಳೆ", "ಹವಾಮಾನ", "ಮಳೆ",
)

_OUT_OF_DOMAIN = (
    "stock", "tesla", "bitcoin", "poem", "bake", "basketball", "football",
    "celebrity", "movie", "crypto",
)

_ET_TOKEN_RE = re.compile(r"\b(et0|eto|evapotranspir\w*)\b", re.I)
_ET_BARE_RE = re.compile(r"\bet\b", re.I)
_ET_DEFINITION_QUESTIONS = {
    "what is et",
    "what is eto",
    "what is et0",
    "what is evapotranspiration",
    "what does et mean",
    "what does eto mean",
}

_INTENT_PATTERNS = (
    ("RECOMMENDATION", ("should i", "do i need", "what should", "recommend", "advice", "सल्ला", "ಶಿಫಾರಸು", "करूँ", "करू")),
    ("WHY_DIAGNOSIS", ("why", "reason", "caused", "क्यों", "का?", "ಏಕೆ")),
    ("TREND", ("trend", "increasing", "decreasing", "over time", "last week", "compared")),
    ("COMPARISON", ("compare", "versus", "vs ", "difference between")),
    ("FORECAST", ("forecast", "tomorrow", "will it rain", "rain coming", "going to rain", "outlook", "उद्या", "कल", "ನಾಳೆ")),
    ("IRRIGATION", ("irrigat", "drip", "water the", "water remain", "water remaining", "water available", "irrigation needed", "eto loss", "eto", "et0", "evapotranspir", "सिंचन", "सिंचाई", "ನೀರಾವರಿ")),
    ("SOIL", ("soil", "moisture", "field dry", "too dry", "too wet", "नमी", "ओलावा", "ತೇವಾಂಶ", "मिट्टी")),
    ("WEATHER", ("weather", "temperature", "rain", "humidity", "outside", "how's it outside", "how is it outside", "हवामान", "मौसम", "ಹವಾಮಾನ")),
    ("CROP_HEALTH", ("ndvi", "field score", "crop health", "canopy", "vigor", "looking okay", "looking good", "looking healthy", "looking fine", "looking well", "आरोग्य", "स्वास्थ्य")),
    ("PEST", ("pest", "fungi", "insect", "spray", "scout", "organic", "ipm", "biocontrol", "neem", "pheromone", "attacking", "eating my", "infest", "bothering", "chewing", "pest name", "which pest", "कीड", "कीट", "ಕೀಟ")),
    ("NUTRIENT", ("npk", "nitrogen", "phosphorus", "potassium", "fertiliz", "fertiliser", "manure", "put in the soil", "put in soil", "खत", "उर्वरक", "खाद")),
    ("HARVEST", ("harvest", "days to harvest", "growth stage", "yield", "yeild", "expected yield", "better yield", "increase yield", "improve yield", "production")),
    ("PLOT_INFO", ("variety", "plantation", "acres", "crop type", "what crop", "about my crop", "tell me about my", "what am i growing", "what's growing")),
    ("CURRENT_STATUS", ("what is my", "current", "status", "how is", "how's my", "show me")),
)

_TOPIC_KEYWORDS = {
    "irrigation": ("irrigat", "drip", "water remain", "water remaining", "water available", "irrigation needed", "eto loss", "eto", "et0", "evapotranspir", "सिंचन", "सिंचाई", "ನೀರಾವರಿ"),
    "uptake": ("uptake", "drinking", "taking water", "water reaching", "absorbing water"),
    "soil": ("soil", "moisture", "field dry", "too dry", "too wet", "is it dry", "नमी", "ओलावा", "ತೇವಾಂಶ", "मिट्टी"),
    "weather": ("weather", "temperature", "temp", "humidity", "outside", "हवामान", "मौसम", "ಹವಾಮಾನ"),
    "forecast": ("forecast", "tomorrow", "will it rain", "rain coming", "going to rain", "उद्या", "कल", "ನಾಳೆ"),
    "pest": ("pest", "fungi", "insect", "spray", "scout", "organic", "ipm", "biocontrol", "neem", "pheromone", "attacking", "eating my", "infest", "bothering", "chewing", "pest name", "which pest", "कीड", "कीट", "ಕೀಟ"),
    "nutrient": ("npk", "fertiliz", "fertiliser", "manure", "nitrogen", "phosphorus", "potassium", "put in the soil", "put in soil", "खत", "खाद"),
    "crop_health": ("ndvi", "ndwi", "field score", "crop health", "canopy", "vigor", "looking okay", "looking good", "looking healthy", "looking fine", "looking well"),
    "harvest": ("harvest", "growth stage", "days to harvest", "yield", "yeild", "expected yield", "better yield", "increase yield", "improve yield", "production", "उपज", "उत्पादन"),
    "plot_info": ("variety", "plantation", "acres", "crop type", "plot info", "about my crop", "tell me about my", "what am i growing"),
    "market": ("mandi", "market price", "crop price", "selling price", "market rate", "msp", "e-nam", "enam", "apmc", "मंडी", "भाव"),
}


@dataclass
class QueryAnalysis:
    intent: str
    topics: List[str] = field(default_factory=list)
    matched_domains: List[str] = field(default_factory=list)
    requires_plot_data: bool = False
    requires_decision: bool = False
    requires_trend: bool = False
    requires_history: bool = False
    is_follow_up: bool = False
    is_offline_faq_candidate: bool = False
    is_et_value_query: bool = False
    is_practice_query: bool = False
    is_fertilizer_query: bool = False
    is_market_price_query: bool = False
    is_yield_query: bool = False
    is_yield_realism_query: bool = False
    is_yield_improve_query: bool = False
    is_pest_identity_query: bool = False
    language: str = "en"
    routing_ms: float = 0.0


def _contains_any(text: str, needles: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(n.lower() in lowered or n in text for n in needles)


def _is_farm_specific(text: str) -> bool:
    lowered = text.lower()
    if any(m in lowered or m in text for m in _FARM_MARKERS):
        return True
    if re.search(r"\bplot\s*\d+\b", lowered):
        return True
    return False


def _is_agri(text: str) -> bool:
    lowered = text.lower()
    return any(tok in lowered or tok in text for tok in _AGRI_TOKENS)


def is_et_value_query(text: str) -> bool:
    """True when the farmer wants ET0/ETO numbers from cache, not irrigation advice or an ET definition."""
    q = (text or "").lower().strip()
    if not q:
        return False
    if any(k in q for k in ("irrigat", "should i", "drip", "water the")):
        return False
    compact = re.sub(r"[^\w\s]", " ", q)
    compact = re.sub(r"\s+", " ", compact).strip()
    if compact in _ET_DEFINITION_QUESTIONS:
        return False
    has_named_et = bool(_ET_TOKEN_RE.search(q))
    has_hourly_window = any(k in q for k in ("hour", "hours", "next"))
    has_hourly_et = bool(_ET_BARE_RE.search(q) and has_hourly_window)
    return (has_named_et and has_hourly_window) or has_hourly_et


def is_practice_query(text: str) -> bool:
    """Farmer is asking which methods/practices to follow, not for a status dump."""
    q = (text or "").lower()
    if not q or "organic carbon" in q:
        return False
    return any(
        k in q
        for k in (
            "organic",
            "ipm",
            "biocontrol",
            "bio-control",
            "bio control",
            "practices",
            "practice",
            "neem",
            "pheromone",
            "trichogramma",
            "have to refer",
            "what to refer",
            "which method",
        )
    )


def is_fertilizer_query(text: str) -> bool:
    """Farmer is asking which fertilizer / NPK materials to apply."""
    q = (text or "").lower()
    return any(
        k in q
        for k in (
            "fertiliz",
            "fertiliser",
            "urea",
            "dap",
            "mop",
            "potash",
            "put in the soil",
            "put in soil",
            "apply to the soil",
            "खत",
            "उर्वरक",
            "ಗೊಬ್ಬರ",
        )
    )


def _detect_topics(text: str) -> List[str]:
    found: List[str] = []
    lowered = text.lower()
    for topic, keys in _TOPIC_KEYWORDS.items():
        if any(k in lowered or k in text for k in keys):
            found.append(topic)
    return found


def _intent_from_topics(topics: List[str]) -> str:
    mapping = {
        "irrigation": "IRRIGATION",
        "soil": "SOIL",
        "uptake": "SOIL",
        "weather": "WEATHER",
        "forecast": "FORECAST",
        "pest": "PEST",
        "nutrient": "NUTRIENT",
        "crop_health": "CROP_HEALTH",
        "harvest": "HARVEST",
        "plot_info": "PLOT_INFO",
        "market": "MARKET_PRICE",
    }
    for topic in topics:
        intent = mapping.get(topic)
        if intent:
            return intent
    return "CURRENT_STATUS"


def _detect_intent(text: str, topics: List[str], farm_specific: bool, agri: bool) -> str:
    lowered = text.lower()
    for intent, keys in _INTENT_PATTERNS:
        if any(k in lowered or k in text for k in keys):
            return intent
    if farm_specific and "irrigation" in topics:
        return "IRRIGATION"
    if farm_specific:
        return "CURRENT_STATUS"
    if agri:
        return "GENERAL_AGRICULTURE"
    return "OUT_OF_DOMAIN"


_ACK_PHRASES = {
    "ok", "okay", "k", "okey",
    "thanks", "thank you", "thank u", "thx", "thankyou",
    "ok thanks", "okay thanks", "thanks ok", "thank you so much",
    "got it", "alright", "all right", "noted", "understood",
    "cool", "great", "done", "sure", "fine",
    "ok sir", "okay sir",
    "ठीक", "ठीक है", "अच्छा", "धन्यवाद", "ओके", "ओके है",
    "ठीक आहे", "आभार", "ओके आहे",
    "ಸರಿ", "ಧನ್ಯವಾದ", "ಧನ್ಯವಾದಗಳು", "ಓಕೆ",
}


def is_market_price_query(text: str) -> bool:
    """Farmer wants nearby mandi / APMC / crop selling rate — not Tesla stocks."""
    q = (text or "").lower()
    if not q:
        return False
    if any(k in q for k in ("stock", "tesla", "bitcoin", "crypto")):
        return False
    if any(
        k in q
        for k in (
            "mandi",
            "market price",
            "crop price",
            "selling price",
            "market rate",
            "msp",
            "e-nam",
            "enam",
            "apmc",
            "मंडी",
            "भाव",
            "किंमत",
            "ಬೆಲೆ",
            "how much will i get",
            "sell my crop",
        )
    ):
        return True
    if "price" in q and any(k in q for k in ("crop", "sugarcane", "wheat", "rice", "cotton", "mango", "grape", "my ")):
        return True
    return False


def is_yield_query(text: str) -> bool:
    """Farmer wants expected yield or how to improve yield (chemical + organic)."""
    q = (text or "").lower()
    if not q:
        return False
    return any(
        k in q
        for k in (
            "yield",
            "yeild",
            "production",
            "how much crop",
            "quintal per",
            "tons per",
            "tonne per",
            "better harvest",
            "increase harvest",
            "उपज",
            "उत्पादन",
            "उत्पन्न",
            "पैदावार",
            "ಇಳುವರಿ",
        )
    )


def is_yield_improve_query(text: str) -> bool:
    """Farmer wants practices to raise yield — not only the expected number."""
    q = (text or "").lower()
    if not is_yield_query(q):
        return False
    return any(
        k in q
        for k in (
            "better",
            "increase",
            "improve",
            "higher",
            "boost",
            "how to get",
            "how can i",
            "more production",
        )
    )


def is_yield_realism_query(text: str) -> bool:
    """Farmer is checking whether a yield figure is believable."""
    q = (text or "").lower()
    if not q:
        return False
    yieldish = any(k in q for k in ("yield", "yeild", "production", "उपज", "उत्पादन", "tonne", "ton"))
    if not yieldish:
        return False
    return any(
        k in q
        for k in (
            "realistic",
            "possible",
            "too high",
            "too much",
            "make sense",
            "correct",
            "true",
            "actual",
            "can it be",
            "is that",
        )
    )


def is_pest_identity_query(text: str) -> bool:
    """Farmer wants a likely pest name, not only the satellite chewing/fungi class."""
    q = (text or "").lower()
    if not q:
        return False
    pestish = any(
        k in q
        for k in ("pest", "insect", "borer", "chewing", "caterpillar", "कीड", "कीट", "ಕೀಟ")
    )
    if not pestish:
        return False
    return any(
        k in q
        for k in (
            "which",
            "what type",
            "what kind",
            "name",
            "predict",
            "identify",
            "species",
            "which one",
            "chewing pest",
        )
    )


def is_farmer_acknowledgment(text: str) -> bool:
    """Bare 'okay' / thanks — not a farm question like 'is it looking okay?'."""
    compact = re.sub(r"[^\w\s\u0900-\u097F\u0C80-\u0CFF]+", " ", (text or "").lower())
    compact = re.sub(r"\s+", " ", compact).strip()
    if not compact or len(compact.split()) > 5:
        return False
    return compact in _ACK_PHRASES


def is_clearly_out_of_domain(text: str) -> bool:
    """True only for clearly non-farm topics (stocks, poems, sports, etc.)."""
    return _contains_any(text, _OUT_OF_DOMAIN) and not _is_agri(text)


def classify_query(
    question: str,
    *,
    language: Optional[str] = None,
    is_follow_up: bool = False,
    is_faq_candidate: bool = False,
) -> QueryAnalysis:
    start = time.perf_counter()
    lang = language or detect_language(question)
    expanded = expand_for_routing(question)
    routing_query = expanded
    matched = route_query(routing_query)

    farm_specific = _is_farm_specific(question) or _is_farm_specific(expanded)
    agri = _is_agri(question) or _is_agri(expanded) or bool(matched)
    topics = _detect_topics(question) or _detect_topics(expanded)

    if is_faq_candidate and not farm_specific:
        intent = "OFFLINE_FAQ"
    elif is_clearly_out_of_domain(question):
        intent = "OUT_OF_DOMAIN"
        matched = []
        topics = []
        farm_specific = False
    else:
        intent = _detect_intent(question + " " + expanded, topics, farm_specific, agri)
        if topics and intent in {"GENERAL_AGRICULTURE", "OUT_OF_DOMAIN", "CURRENT_STATUS"}:
            topic_intent = _intent_from_topics(topics)
            if topic_intent and topic_intent != "CURRENT_STATUS":
                intent = topic_intent

    if intent == "OUT_OF_DOMAIN" and not agri:
        matched = []

    et_value = is_et_value_query(question) or is_et_value_query(expanded)
    practice = is_practice_query(question) or is_practice_query(expanded)
    q_low = question.lower()
    if practice and any(k in q_low for k in ("fertiliz", "manure", "compost", "npk")):
        intent = "NUTRIENT"
        if "nutrient" not in topics:
            topics.append("nutrient")
    elif practice and intent not in {"NUTRIENT", "IRRIGATION", "OUT_OF_DOMAIN"}:
        intent = "PEST"
        if "pest" not in topics:
            topics.append("pest")
    elif practice and intent in {"GENERAL_AGRICULTURE", "CURRENT_STATUS", "OFFLINE_FAQ"}:
        intent = "PEST"
        if "pest" not in topics:
            topics.append("pest")

    fertilizer = is_fertilizer_query(question) or is_fertilizer_query(expanded)
    if fertilizer and intent != "OUT_OF_DOMAIN":
        intent = "NUTRIENT"
        if "nutrient" not in topics:
            topics.append("nutrient")
        if any(k in q_low for k in ("pest", "insect", "borer", "कीड", "कीट", "ಕೀಟ")) and "pest" not in topics:
            topics.append("pest")

    market = is_market_price_query(question) or is_market_price_query(expanded)
    if market and not fertilizer and intent != "OUT_OF_DOMAIN":
        intent = "MARKET_PRICE"
        if "market" not in topics:
            topics.append("market")

    yield_q = is_yield_query(question) or is_yield_query(expanded)
    realism = is_yield_realism_query(question) or is_yield_realism_query(expanded)
    improve = is_yield_improve_query(question) or is_yield_improve_query(expanded)
    if realism:
        yield_q = True
        improve = False
    if yield_q:
        if not fertilizer:
            intent = "HARVEST"
        if "harvest" not in topics:
            topics.append("harvest")
        if not realism and (fertilizer or improve) and "nutrient" not in topics:
            topics.append("nutrient")

    pest_id = is_pest_identity_query(question) or is_pest_identity_query(expanded)
    if pest_id and not fertilizer and not yield_q:
        intent = "PEST"
        if "pest" not in topics:
            topics.append("pest")

    requires_decision = (
        not et_value
        and (yield_q or not practice)
        and not (yield_q and not fertilizer and not improve)
        and (
            yield_q
            or intent in {"RECOMMENDATION", "IRRIGATION", "PEST", "NUTRIENT", "HARVEST"}
            or any(k in q_low for k in ("should i", "what should", "do i need"))
        )
    )
    requires_trend = intent == "TREND" or any(
        k in q_low for k in ("trend", "increasing", "decreasing", "over time")
    )
    requires_history = requires_trend or any(
        k in q_low for k in ("last time", "previously", "yesterday", "last week")
    )
    requires_plot = et_value or practice or fertilizer or yield_q or farm_specific or bool(topics) or intent not in {
        "GENERAL_AGRICULTURE", "OFFLINE_FAQ", "OUT_OF_DOMAIN",
    }

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    analysis = QueryAnalysis(
        intent=intent,
        topics=topics,
        matched_domains=matched,
        requires_plot_data=bool(requires_plot and intent != "OUT_OF_DOMAIN"),
        requires_decision=requires_decision,
        requires_trend=requires_trend,
        requires_history=requires_history,
        is_follow_up=is_follow_up,
        is_offline_faq_candidate=bool(is_faq_candidate and not farm_specific and not yield_q),
        is_et_value_query=et_value,
        is_practice_query=practice,
        is_fertilizer_query=fertilizer,
        is_market_price_query=market,
        is_yield_query=yield_q,
        is_yield_realism_query=realism,
        is_yield_improve_query=bool(improve and not realism),
        is_pest_identity_query=pest_id,
        language=lang,
        routing_ms=round(elapsed_ms, 3),
    )
    logger.debug(
        "query_classified",
        intent=analysis.intent,
        topics=analysis.topics,
        domains=analysis.matched_domains,
        duration_ms=analysis.routing_ms,
    )
    return analysis

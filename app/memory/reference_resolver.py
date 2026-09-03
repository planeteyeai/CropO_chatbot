"""Resolve short multilingual follow-ups against the active conversation topic.

Never mutates the original user question stored in history.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional
from app.routing.language_router import detect_language, expand_for_routing
from app.routing.query_classifier import is_farmer_acknowledgment

FOLLOW_UP_MARKERS = (
    "what about",
    "how much",
    "then what",
    "and then",
    "is it good",
    "is it ok",
    "is it okay",
    "why",
    "tomorrow",
    "today",
    "and now",
    "next",
    "same for",
    "precaution",
    "precautions",
    "what should i",
    "what do i",
    "what to do",
    "any advice",
    "next step",
    "what else",
    "tell me more",
    "practices",
    "practice",
    "have to refer",
    "what to refer",
    # Hindi
    "फिर क्या",
    "कल क्या",
    "क्यों",
    "कितना",
    "कितनी",
    "आज क्या",
    "सावधानी",
    # Marathi
    "मग काय",
    "उद्या काय",
    "का?",
    "किती",
    "आज काय",
    # Kannada
    "ನಾಳೆ ಏನು",
    "ಏಕೆ",
    "ಎಷ್ಟು",
    "ಆಮೇಲೆ",
)


@dataclass
class ResolvedReference:
    original_question: str
    resolved_question: str
    is_follow_up: bool
    language: str


NEW_TOPIC_TOKENS = (
    "weather", "temperature", "temp", "humidity", "forecast", "rain",
    "ndvi", "pest", "npk", "score", "moisture", "soil", "irrigat", "drip",
    "eto", "et0", "evapotranspir",
    "fertiliz", "fertiliser", "manure",
    "organic", "ipm",
    "outside", "attacking", "drinking", "looking", "harvest",
    "yield", "yeild", "production", "chewing", "borer",
    "dry", "uptake", "mandi", "apmc", "msp",
    "हवामान", "मौसम", "ಹವಾಮಾನ", "बारिश", "पाऊस", "ಮಳೆ",
    "ओलावा", "नमी", "ತೇವಾಂಶ", "सिंचन", "सिंचाई", "ನೀರಾವರಿ",
)


def _names_own_topic(question: str) -> bool:
    lowered = question.lower()
    return any(tok in lowered or tok in question for tok in NEW_TOPIC_TOKENS)


def _is_follow_up(question: str, expanded: str) -> bool:
    q = question.strip()
    words = q.split()
    lowered = q.lower()
    # Bare "okay" / thanks is a close, not a follow-up on the last pest/soil topic.
    if is_farmer_acknowledgment(q):
        return False
    # A question that already names a topic is complete, even if short/typo-filled.
    if _names_own_topic(q):
        return False
    # Short elliptical turns are follow-ups ("why", "how much").
    if len(words) <= 3:
        return True
    if any(marker in q or marker in lowered for marker in FOLLOW_UP_MARKERS):
        return True
    return False


def _topic_phrase(state: Dict[str, Any]) -> str:
    topic = state.get("active_topic") or "this plot"
    return str(topic).replace("_", " ")


def resolve_reference(
    question: str,
    state: Optional[Dict[str, Any]] = None,
    language: Optional[str] = None,
) -> ResolvedReference:
    """Expand elliptical follow-ups using active topic / last recommendation."""
    state = state or {}
    lang = language or detect_language(question, fallback="en")
    expanded = expand_for_routing(question)
    original = question
    if not _is_follow_up(question, expanded):
        return ResolvedReference(
            original_question=original,
            resolved_question=original,
            is_follow_up=False,
            language=lang,
        )

    topic = _topic_phrase(state)
    last_rec = state.get("last_recommendation")
    q_l = question.lower()
    expanded_l = expanded.lower()

    if any(tok in q_l or tok in question for tok in ("tomorrow", "उद्या", "कल", "ನಾಳೆ")):
        resolved = f"What should the farmer do regarding {topic} tomorrow for this plot?"
    elif any(tok in q_l or tok in question for tok in ("today", "आज", "ಇಂದು")):
        resolved = f"What should the farmer do regarding {topic} today for this plot?"
    elif any(tok in q_l or tok in question for tok in ("why", "का", "का?", "क्यों", "ಏಕೆ")):
        if last_rec:
            resolved = f"Why was the previous {topic} recommendation ({last_rec}) given for this plot?"
        else:
            resolved = f"Why is the current {topic} situation on this plot the way it is?"
    elif any(
        tok in q_l or tok in question
        for tok in (
            "precaution", "precautions", "what to do", "what should i", "any advice", "सावधानी",
            "practices", "have to refer", "what to refer",
        )
    ):
        resolved = (
            f"What practical precautions and next field actions should the farmer take "
            f"regarding {topic} on this plot, using cached evidence and standard agricultural practice?"
        )
    elif any(tok in q_l or tok in question for tok in ("how much", "कितना", "कितनी", "किती", "ಎಷ್ಟು")):
        resolved = f"How much {topic} value or quantity applies to this plot right now?"
    elif "is it good" in q_l or "is it ok" in q_l:
        resolved = f"Is the current {topic} situation on this plot acceptable, and should the farmer change anything?"
    elif any(tok in question for tok in ("मग काय", "फिर क्या", "ಆಮೇಲೆ")) or "then what" in q_l:
        resolved = f"What should the farmer do next regarding {topic} for this plot?"
    else:
        resolved = f"Regarding {topic} on this plot: {question}"

    return ResolvedReference(
        original_question=original,
        resolved_question=resolved,
        is_follow_up=True,
        language=lang,
    )

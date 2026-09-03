"""Language detection and multilingual keyword expansion for fast routing.

Intelligence stays language-independent; answers are rendered in the user language.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

LANG_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi", "kn": "Kannada"}

# Distinctive tokens for Hindi vs Marathi (both Devanagari).
_MARATHI_MARKERS = (
    "काय", "आहे", "मी", "मग", "उद्या", "किती", "ओलावा", "सिंचन", "पीक",
    "शेत", "जमिनीतील", "करा", "पाऊस", "हवामान",
)
_HINDI_MARKERS = (
    "क्या", "है", "मैं", "फिर", "कल", "कितना", "कितनी", "मिट्टी", "सिंचाई",
    "फसल", "खेत", "नमी", "बारिश", "मौसम",
)

# Agri term aliases → English routing keywords (do not alter original question).
TERM_ALIASES: List[Tuple[str, str]] = [
    # Marathi
    ("ओलावा", "soil moisture irrigation"),
    ("सिंचन", "irrigation irrigate drip"),
    ("जमिनीतील", "soil"),
    ("हवामान", "weather temperature rain forecast"),
    ("पाऊस", "rain rainfall forecast"),
    ("पीक", "crop health"),
    ("आरोग्य", "crop health ndvi field score"),
    ("कीड", "pest detection"),
    ("खत", "npk fertilizer nutrient"),
    ("उद्या", "tomorrow forecast"),
    ("आज", "today"),
    # Hindi
    ("नमी", "soil moisture irrigation"),
    ("सिंचाई", "irrigation irrigate drip"),
    ("मिट्टी", "soil"),
    ("मौसम", "weather temperature rain forecast"),
    ("बारिश", "rain rainfall forecast"),
    ("फसल", "crop health"),
    ("स्वास्थ्य", "crop health ndvi field score"),
    ("कीट", "pest detection"),
    ("उर्वरक", "npk fertilizer nutrient"),
    ("क्यों", "why"),
    ("कितना", "how much"),
    ("कल", "tomorrow forecast"),
    # Kannada
    ("ತೇವಾಂಶ", "soil moisture irrigation"),
    ("ನೀರಾವರಿ", "irrigation irrigate drip"),
    ("ಮಣ್ಣಿನ", "soil"),
    ("ಹವಾಮಾನ", "weather temperature rain forecast"),
    ("ಮಳೆ", "rain rainfall forecast"),
    ("ಬೆಳೆ", "crop health"),
    ("ಆರೋಗ್ಯ", "crop health ndvi field score"),
    ("ಕೀಟ", "pest detection"),
    ("ಗೊಬ್ಬರ", "npk fertilizer nutrient"),
    ("ನಾಳೆ", "tomorrow forecast"),
    ("ಏಕೆ", "why"),
    ("ಎಷ್ಟು", "how much"),
]


def detect_language(text: str, fallback: str = "en") -> str:
    """Detect en / hi / mr / kn from script and distinctive tokens."""
    if not text:
        return fallback or "en"
    if re.search(r"[\u0C80-\u0CFF]", text):
        return "kn"
    if re.search(r"[\u0900-\u097F]", text):
        mr_hits = sum(1 for m in _MARATHI_MARKERS if m in text)
        hi_hits = sum(1 for m in _HINDI_MARKERS if m in text)
        if mr_hits > hi_hits:
            return "mr"
        if hi_hits > mr_hits:
            return "hi"
        # Default Devanagari with no strong signal → respect fallback if hi/mr
        if fallback in ("hi", "mr"):
            return fallback
        return "hi"
    return fallback if fallback in LANG_NAMES else "en"


def expand_for_routing(text: str) -> str:
    """Append English agri aliases so the existing keyword router can match."""
    extra: List[str] = []
    for native, english in TERM_ALIASES:
        if native in text:
            extra.append(english)
    if not extra:
        return text
    return f"{text} {' '.join(extra)}"


def language_name(code: str) -> str:
    return LANG_NAMES.get((code or "en").lower(), "English")

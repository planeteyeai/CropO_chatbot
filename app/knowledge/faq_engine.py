"""Offline FAQ engine. Exact matches skip Gemini entirely (target < 10ms)."""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional
from app.knowledge.faq_data import FAQ_ENTRIES
from app.routing.query_classifier import (
    _is_farm_specific,
    is_et_value_query,
    is_pest_identity_query,
    is_yield_query,
)

_PUNCT_RE = re.compile(r"[^\w\s\u0900-\u097F\u0C80-\u0CFF]+", re.UNICODE)
_PLOT_VALUE_RE = re.compile(
    r"\b(today|tomorrow|this plot|this field|will it rain|rain coming)\b",
    re.I,
)


def normalize_question(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.strip().lower()
    text = _PUNCT_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class FAQMatch:
    entry_id: str
    answer: str
    language: str
    method: str
    score: float
    latency_ms: float


def _is_plot_value_question(text: str) -> bool:
    """True when the farmer wants plot rain/weather numbers, not a definition FAQ."""
    q = normalize_question(text)
    if "will it rain" in q or "rain coming" in q:
        return True
    if _PLOT_VALUE_RE.search(q) and any(
        k in q for k in ("rain", "forecast", "weather", "temp", "temperature", "moisture")
    ):
        return True
    return False


class FAQEngine:
    def __init__(self, entries: Optional[List[Dict[str, Any]]] = None):
        self.entries = entries or FAQ_ENTRIES
        self._exact: Dict[str, Dict[str, Any]] = {}
        self._keyword_index: List[tuple] = []
        for entry in self.entries:
            for lang, questions in entry.get("questions", {}).items():
                for q in questions:
                    self._exact[normalize_question(q)] = {"entry": entry, "lang": lang}
            for kw in entry.get("keywords", []):
                self._keyword_index.append((normalize_question(kw), entry))

    def match(self, question: str, language: str = "en", allow_farm_specific: bool = False) -> Optional[FAQMatch]:
        start = time.perf_counter()
        if not allow_farm_specific and _is_farm_specific(question):
            return None
        if is_et_value_query(question):
            return None
        if is_yield_query(question):
            return None
        if is_pest_identity_query(question):
            return None
        if _is_plot_value_question(question):
            return None
        norm = normalize_question(question)
        lang = (language or "en").lower()
        if lang not in ("en", "hi", "mr", "kn"):
            lang = "en"

        # 1. Exact normalized question
        hit = self._exact.get(norm)
        if hit:
            return self._result(hit["entry"], lang, "exact", 1.0, start)

        words = [w for w in norm.split() if w]
        if len(words) <= 4 and not hit:
            # Elliptical follow-ups ("why", "how much") must use farm intelligence, not FAQ.
            return None

        # 2. Exact keyword contained as whole phrase
        for kw, entry in self._keyword_index:
            if kw and re.search(r"\b" + re.escape(kw) + r"\b", norm):
                # Prefer definitional phrasing for keyword hits
                if any(norm.startswith(p) for p in ("what is", "what does", "explain", "how does", "how to")):
                    return self._result(entry, lang, "keyword", 0.9, start)

        # 3. Phrase match: the stored FAQ question appears inside the user question.
        # Never match the reverse (that made "why" hit "why is data unavailable").
        for key, payload in self._exact.items():
            if len(key) < 12:
                continue
            if key in norm and len(norm) >= max(12, int(len(key) * 0.75)):
                return self._result(payload["entry"], lang, "phrase", 0.85, start)

        # 4. Fuzzy match
        best_ratio = 0.0
        best_entry = None
        for key, payload in self._exact.items():
            ratio = SequenceMatcher(None, norm, key).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_entry = payload["entry"]
        if best_entry and best_ratio >= 0.88:
            return self._result(best_entry, lang, "fuzzy", best_ratio, start)

        return None

    def _result(self, entry: Dict[str, Any], language: str, method: str, score: float, start: float) -> FAQMatch:
        answers = entry.get("answers") or {}
        answer = answers.get(language) or answers.get("en") or ""
        return FAQMatch(
            entry_id=str(entry.get("id")),
            answer=answer,
            language=language,
            method=method,
            score=score,
            latency_ms=round((time.perf_counter() - start) * 1000.0, 3),
        )


faq_engine = FAQEngine()

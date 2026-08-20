"""Ultra-Fast (<50ms) Intent Router.

Routes user query to one or more registered data domains based on in-memory keyword matching.
No external network or LLM calls are made during routing.
"""

import re
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Set
import structlog
from app.config.api_registry import API_REGISTRY
from app.config.settings import settings

logger = structlog.get_logger(__name__)


class IntentRouter(ABC):
    """Abstract interface for query routing."""

    @abstractmethod
    def route(self, query: str) -> List[str]:
        """Map user query string to a list of matched domain names."""
        pass


class KeywordIntentRouter(IntentRouter):
    """Deterministic, sub-millisecond keyword-based intent router."""

    def __init__(self, registry: List[Dict] = API_REGISTRY):
        self.registry = registry
        # Precompile single-token keywords and multi-word phrase keywords
        self._domain_single_tokens: Dict[str, Set[str]] = {}
        self._domain_phrases: Dict[str, List[str]] = {}

        for api in self.registry:
            name = api["name"]
            single_tokens = set()
            phrases = []

            all_keywords = list(api.get("keywords", [])) + [name, name.replace("_", " ")]
            for kw in all_keywords:
                clean_kw = kw.strip().lower()
                if " " in clean_kw:
                    phrases.append(clean_kw)
                else:
                    single_tokens.add(clean_kw)

            self._domain_single_tokens[name] = single_tokens
            self._domain_phrases[name] = phrases

    def route(self, query: str) -> List[str]:
        start_time = time.perf_counter()
        normalized_query = query.lower()

        # Tokenize query into alphanumeric words
        tokens = set(re.findall(r"\b[a-z0-9_-]+\b", normalized_query))

        matched_domains = []

        for domain in self._domain_single_tokens:
            # 1. Exact token matching
            if tokens.intersection(self._domain_single_tokens[domain]):
                matched_domains.append(domain)
                continue

            # 2. Multi-word phrase matching with word boundaries
            matched_phrase = False
            for phrase in self._domain_phrases[domain]:
                pattern = r"\b" + re.escape(phrase) + r"\b"
                if re.search(pattern, normalized_query):
                    matched_domains.append(domain)
                    matched_phrase = True
                    break

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.debug(
            "intent_routing_completed",
            query=query,
            matched=matched_domains,
            duration_ms=round(duration_ms, 3),
        )
        return matched_domains


class SentenceTransformerRouter(IntentRouter):
    """Optional embedding-based intent router (activated if ENABLE_EMBEDDING_ROUTING=True)."""

    def __init__(self, registry: List[Dict] = API_REGISTRY):
        self.registry = registry
        self.keyword_fallback = KeywordIntentRouter(registry)
        self._model = None
        self._domain_embeddings = {}

        try:
            from sentence_transformers import SentenceTransformer, util
            self._st_util = util
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            for api in self.registry:
                desc = f"{api['name']}: {api.get('description', '')} {' '.join(api.get('keywords', []))}"
                self._domain_embeddings[api["name"]] = self._model.encode(desc, convert_to_tensor=True)
            logger.info("sentence_transformer_router_initialized")
        except Exception as exc:
            logger.warning(
                "failed_to_load_sentence_transformers_falling_back_to_keywords",
                error=str(exc),
            )
            self._model = None

    def route(self, query: str) -> List[str]:
        if not self._model:
            return self.keyword_fallback.route(query)

        start_time = time.perf_counter()
        try:
            query_emb = self._model.encode(query, convert_to_tensor=True)
            matched = []
            for name, emb in self._domain_embeddings.items():
                score = float(self._st_util.cos_sim(query_emb, emb)[0][0])
                if score >= 0.38:  # Similarity threshold
                    matched.append(name)

            if not matched:
                matched = self.keyword_fallback.route(query)

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.debug(
                "embedding_routing_completed",
                query=query,
                matched=matched,
                duration_ms=round(duration_ms, 3),
            )
            return matched
        except Exception as exc:
            logger.warning("embedding_routing_error_fallback", error=str(exc))
            return self.keyword_fallback.route(query)


def get_router() -> IntentRouter:
    """Factory to instantiate configured router."""
    if settings.ENABLE_EMBEDDING_ROUTING:
        return SentenceTransformerRouter(API_REGISTRY)
    return KeywordIntentRouter(API_REGISTRY)


# Singleton instance for high performance
_default_router: IntentRouter = get_router()


def route_query(query: str) -> List[str]:
    """Top-level helper function to route a query string."""
    return _default_router.route(query)

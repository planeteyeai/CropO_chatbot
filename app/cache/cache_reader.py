"""Parallel plot-scoped cache reader with standardized freshness.

Uses the existing Redis client. Never opens new connections or calls CropO APIs.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import structlog
from app.cache.cache_keys import DOMAIN_KEY_GETTERS, plot_domain_key
from app.cache.redis_client import redis_client
from app.config.api_registry import get_api_by_name
from app.config.intelligence_rules import (
    FRESHNESS_AGING_MAX_RATIO,
    FRESHNESS_FRESH_MAX_RATIO,
    FRESHNESS_STALE_MAX_RATIO,
)

logger = structlog.get_logger(__name__)

FRESH = "FRESH"
AGING = "AGING"
STALE = "STALE"
VERY_STALE = "VERY_STALE"
MISSING = "MISSING"


@dataclass
class CacheResult:
    key: str
    domain: str
    data: Optional[dict]
    freshness: str
    cached_at: Optional[str]
    age_seconds: Optional[float]
    source: Optional[str]
    ttl_remaining: Optional[int] = None
    interval_seconds: Optional[int] = None


def classify_freshness(
    age_seconds: Optional[float],
    interval_seconds: Optional[int],
    ttl_remaining: Optional[int] = None,
) -> str:
    """Map cache age onto FRESH / AGING / STALE / VERY_STALE / MISSING."""
    if age_seconds is None:
        return MISSING
    interval = interval_seconds or 900
    ratio = float(age_seconds) / max(float(interval), 1.0)
    if ratio <= FRESHNESS_FRESH_MAX_RATIO:
        return FRESH
    if ratio <= FRESHNESS_AGING_MAX_RATIO:
        return AGING
    if ratio <= FRESHNESS_STALE_MAX_RATIO:
        return STALE
    return VERY_STALE


def _interval_for_domain(domain: str) -> Optional[int]:
    api = get_api_by_name(domain)
    if api:
        return int(api.get("interval_seconds") or 900)
    return None


async def read_domain(plot_id: str, domain: str) -> CacheResult:
    """Read one plot-scoped domain envelope from Redis / in-memory fallback."""
    key = plot_domain_key(plot_id, domain) or ""
    interval = _interval_for_domain(domain)
    if not key:
        return CacheResult(
            key="",
            domain=domain,
            data=None,
            freshness=MISSING,
            cached_at=None,
            age_seconds=None,
            source=None,
            interval_seconds=interval,
        )

    envelope = await redis_client.get_with_metadata(key)
    if not envelope:
        return CacheResult(
            key=key,
            domain=domain,
            data=None,
            freshness=MISSING,
            cached_at=None,
            age_seconds=None,
            source="missing",
            interval_seconds=interval,
        )

    age = envelope.get("age_seconds")
    freshness = classify_freshness(age, interval, envelope.get("ttl_remaining"))
    live = await redis_client.is_connected()
    return CacheResult(
        key=key,
        domain=domain,
        data=envelope.get("data") if isinstance(envelope.get("data"), dict) else envelope.get("data"),
        freshness=freshness,
        cached_at=envelope.get("cached_at_iso"),
        age_seconds=float(age) if age is not None else None,
        source="redis" if live else "memory",
        ttl_remaining=envelope.get("ttl_remaining"),
        interval_seconds=interval,
    )


async def read_domains(plot_id: str, domains: List[str]) -> Dict[str, CacheResult]:
    """Read independent domains in parallel."""
    unique = [d for d in dict.fromkeys(domains) if d in DOMAIN_KEY_GETTERS]
    if not unique:
        return {}
    results = await asyncio.gather(*(read_domain(plot_id, d) for d in unique))
    return {item.domain: item for item in results}


def freshness_map(results: Dict[str, CacheResult]) -> Dict[str, str]:
    return {name: item.freshness for name, item in results.items()}

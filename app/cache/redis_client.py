"""Async Redis Client for Hot Cache Storage."""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
from redis import asyncio as aioredis
from app.config.settings import settings

logger = structlog.get_logger(__name__)


class RedisCacheClient:
    """Async Redis hot cache manager with JSON serialization and metadata tracking."""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._client: Optional[aioredis.Redis] = None
        # In-memory fallback dictionary if Redis server is unavailable (for testing/offline resilience)
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._is_redis_available: bool = False

    async def connect(self) -> None:
        """Establish async connection to Redis with fallback."""
        try:
            self._client = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=3.0,
                socket_connect_timeout=3.0,
            )
            await self._client.ping()
            self._is_redis_available = True
            logger.info("redis_connected", url=self.redis_url)
        except Exception as exc:
            self._is_redis_available = False
            logger.warning(
                "redis_connection_failed_using_memory_cache",
                error=str(exc),
                url=self.redis_url,
            )

    async def close(self) -> None:
        """Close connection to Redis."""
        if self._client and self._is_redis_available:
            try:
                await self._client.aclose()
                logger.info("redis_connection_closed")
            except Exception as exc:
                logger.warning("redis_close_error", error=str(exc))

    async def is_connected(self) -> bool:
        """Check if Redis connection is active."""
        if not self._is_redis_available or not self._client:
            return False
        try:
            await self._client.ping()
            return True
        except Exception:
            return False

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> bool:
        """Store a JSON-serializable value with TTL and metadata envelope."""
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        envelope = {
            "data": value,
            "cached_at_timestamp": now,
            "cached_at_iso": now_iso,
            "ttl_seconds": ttl_seconds,
        }
        raw_json = json.dumps(envelope)

        if self._is_redis_available and self._client:
            try:
                await self._client.set(key, raw_json, ex=ttl_seconds)
                logger.debug("redis_set_success", key=key, ttl=ttl_seconds)
                return True
            except Exception as exc:
                logger.warning("redis_set_failed_fallback_memory", key=key, error=str(exc))

        # Fallback in-memory cache
        self._memory_cache[key] = {
            "raw": raw_json,
            "expires_at": now + ttl_seconds,
        }
        return True

    async def get_json(self, key: str) -> Optional[Any]:
        """Retrieve raw payload data from cache."""
        meta = await self.get_with_metadata(key)
        if meta and "data" in meta:
            return meta["data"]
        return None

    async def get_with_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached envelope containing data and freshness timestamps."""
        raw_json: Optional[str] = None

        if self._is_redis_available and self._client:
            try:
                raw_json = await self._client.get(key)
            except Exception as exc:
                logger.warning("redis_get_failed_trying_memory", key=key, error=str(exc))

        if raw_json is None and key in self._memory_cache:
            entry = self._memory_cache[key]
            if time.time() <= entry["expires_at"]:
                raw_json = entry["raw"]
            else:
                del self._memory_cache[key]

        if not raw_json:
            return None

        try:
            envelope = json.loads(raw_json)
            now = time.time()
            cached_at = envelope.get("cached_at_timestamp", now)
            ttl = envelope.get("ttl_seconds", 900)
            envelope["age_seconds"] = max(0, int(now - cached_at))
            envelope["ttl_remaining"] = max(0, int((cached_at + ttl) - now))
            return envelope
        except Exception as exc:
            logger.error("cache_json_decode_error", key=key, error=str(exc))
            return None

    async def get_all_keys_status(self, domain_keys: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Inspect status of all configured domain keys for diagnostics."""
        results = []
        for item in domain_keys:
            key = item.get("cache_key", "")
            meta = await self.get_with_metadata(key)
            status_item = {
                "name": item.get("name"),
                "cache_key": key,
                "interval_seconds": item.get("interval_seconds"),
                "is_cached": meta is not None,
                "cached_at_iso": meta.get("cached_at_iso") if meta else None,
                "age_seconds": meta.get("age_seconds") if meta else None,
                "ttl_remaining": meta.get("ttl_remaining") if meta else None,
                "sample_data": meta.get("data") if meta else None,
            }
            results.append(status_item)
        return results

    async def delete_key(self, key: str) -> bool:
        """Remove a single cache entry from Redis and in-memory fallback."""
        deleted = False
        if key in self._memory_cache:
            del self._memory_cache[key]
            deleted = True

        if self._is_redis_available and self._client:
            try:
                removed = await self._client.delete(key)
                deleted = deleted or bool(removed)
            except Exception as exc:
                logger.warning("redis_delete_failed", key=key, error=str(exc))

        return deleted

    async def clear_all_cache(self) -> Dict[str, int]:
        """Clear all plot/domain cache keys (Redis + in-memory)."""
        memory_cleared = len(self._memory_cache)
        self._memory_cache.clear()
        redis_deleted = 0

        if self._is_redis_available and self._client:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self._client.scan(cursor, match="data:*", count=200)
                    if keys:
                        redis_deleted += await self._client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as exc:
                logger.warning("redis_clear_all_failed", error=str(exc))

        logger.info("cache_cleared", memory_entries=memory_cleared, redis_keys=redis_deleted)
        return {"memory_entries_cleared": memory_cleared, "redis_keys_deleted": redis_deleted}

    async def clear_plot_cache(self, plot_id: str) -> int:
        """Delete all cached telemetry keys for a specific plot."""
        from app.fetchers.plots_info import get_plot_info_cache_key
        from app.fetchers.soil_irrigation import get_soil_cache_key
        from app.fetchers.field_score import get_score_cache_key
        from app.fetchers.cropo_weather import get_weather_cache_key
        from app.fetchers.daily_report import get_daily_report_cache_key

        clean_id = str(plot_id).strip()
        keys = [
            get_plot_info_cache_key(clean_id),
            get_soil_cache_key(clean_id),
            get_score_cache_key(clean_id),
            get_weather_cache_key(clean_id),
            get_daily_report_cache_key(clean_id),
        ]

        deleted = 0
        for key in keys:
            if await self.delete_key(key):
                deleted += 1

        logger.info("plot_cache_cleared", plot_id=clean_id, keys_deleted=deleted)
        return deleted

    async def append_snapshot(
        self,
        key: str,
        snapshot: Dict[str, Any],
        max_items: int,
        ttl_seconds: int,
    ) -> bool:
        """Append a compact item onto a bounded JSON list (Redis or memory fallback)."""
        existing = await self.get_json(key)
        items: List[Any] = existing if isinstance(existing, list) else []
        items.append(snapshot)
        if max_items > 0:
            items = items[-int(max_items) :]
        return await self.set_json(key, items, ttl_seconds=ttl_seconds)


redis_client = RedisCacheClient()

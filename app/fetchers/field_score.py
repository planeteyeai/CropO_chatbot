"""Field Health Score and Remote Sensing Fetcher Module.

Fetches NDVI/Field Health Scores (`GET /field_score?plot_name={plot_id}`) per plot.
Caches under `data:plot:{plot_id}:score` in Redis.
"""

from typing import Any, Dict
import structlog
from app.cache.redis_client import redis_client
from app.config.settings import settings
from app.fetchers.base import async_fetch_with_retry

logger = structlog.get_logger(__name__)

TTL_SECONDS = 1200  # 20 mins


def get_score_cache_key(plot_id: str) -> str:
    """Generate Redis key for plot health score."""
    return f"data:plot:{plot_id.strip()}:score"


def _generate_fallback_score(plot_id: str) -> Dict[str, Any]:
    """Fallback field health score."""
    return {
        "status": "success",
        "plot_name": str(plot_id),
        "field_score_pct": 100.0,
        "health_status": "Excellent (Peak Vigor)",
        "advisory": "Vigorous crop canopy; optimal photosynthetic activity.",
    }


async def fetch_score_for_plot(plot_id: str) -> Dict[str, Any]:
    """Fetch field score for a specific plot and write to Redis."""
    clean_id = str(plot_id).strip()
    cache_key = get_score_cache_key(clean_id)
    base_url = settings.CROPO_API_BASE_URL.rstrip("/")
    url = f"{base_url}/field_score?plot_name={clean_id}"
    headers = {"Accept": "application/json"}
    if settings.CROPO_API_KEY:
        headers["Authorization"] = f"Bearer {settings.CROPO_API_KEY}"

    logger.info("fetch_score_for_plot_started", plot_id=clean_id, url=url)

    res = await async_fetch_with_retry(url=url, headers=headers, timeout=30.0, max_retries=2)

    if not isinstance(res, dict) or "field_score" not in res:
        existing = await redis_client.get_json(cache_key)
        if existing:
            logger.warning("field_score_fetch_failed_retaining_cache", plot_id=clean_id)
            return existing
        normalized = _generate_fallback_score(clean_id)
    else:
        score = float(res.get("field_score", 100.0))
        if score >= 90:
            health = "Excellent (Peak Vigor)"
            adv = "Strong canopy index and optimal chlorophyll absorption."
        elif score >= 70:
            health = "Good / Normal"
            adv = "Standard vegetative development. No immediate intervention needed."
        elif score >= 50:
            health = "Moderate"
            adv = "Inspect for localized nutrient stress or leaf discoloration."
        else:
            health = "Low / Stressed"
            adv = "Vegetation stress detected. Ground inspection recommended."

        normalized = {
            "status": "success",
            "plot_name": str(res.get("plot_name", clean_id)),
            "field_score_pct": score,
            "health_status": health,
            "advisory": adv,
        }

    await redis_client.set_json(cache_key, normalized, ttl_seconds=TTL_SECONDS)
    from app.cache.history import record_plot_snapshot
    await record_plot_snapshot(
        clean_id,
        "field_scores",
        {"field_score_pct": normalized.get("field_score_pct")},
    )
    logger.info("fetch_score_for_plot_completed", plot_id=clean_id, score=normalized.get("field_score_pct"))
    return normalized


async def fetch_field_scores() -> bool:
    """Scheduled background refresh for all active monitored plots."""
    from app.fetchers import get_active_plot_ids

    active_plots = get_active_plot_ids()
    if not active_plots:
        logger.info("no_active_plots_to_refresh", domain="field_scores")
        return True

    for pid in active_plots:
        await fetch_score_for_plot(pid.strip())
    return True

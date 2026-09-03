"""Bounded historical snapshots for trend analysis.

Written only after a successful cache write. Never called from /chat.
Compact metrics only — not raw API payloads.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
from app.cache.cache_keys import history_key
from app.cache.redis_client import redis_client
from app.config.settings import settings

logger = structlog.get_logger(__name__)


async def record_plot_snapshot(
    plot_id: Optional[str],
    domain: str,
    metrics: Dict[str, Any],
) -> None:
    """Append a compact timestamped snapshot for a plot/domain."""
    if not plot_id or not str(plot_id).strip():
        return
    compact = {k: v for k, v in metrics.items() if v is not None}
    if not compact:
        return
    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **compact,
    }
    key = history_key(str(plot_id).strip(), domain)
    try:
        await redis_client.append_snapshot(
            key,
            snapshot,
            max_items=settings.HISTORY_MAX_ITEMS,
            ttl_seconds=settings.HISTORY_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning("history_snapshot_failed", plot_id=plot_id, domain=domain, error=str(exc))


async def load_plot_history(plot_id: str, domain: str) -> List[Dict[str, Any]]:
    """Read compact snapshots. Safe for the online chat pipeline (Redis only)."""
    raw = await redis_client.get_json(history_key(str(plot_id).strip(), domain))
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []

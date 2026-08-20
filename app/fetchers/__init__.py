import asyncio
from typing import Any, Dict, List, Set
import structlog
from app.config.settings import settings
from app.fetchers.base import async_fetch_with_retry
from app.fetchers.plots_info import (
    fetch_plots_info,
    fetch_plot_info_for_id,
    get_available_plots_list,
    get_plot_info_cache_key,
)
from app.fetchers.cropo_weather import (
    fetch_cropo_weather,
    fetch_weather_for_plot,
    get_weather_cache_key,
)
from app.fetchers.soil_irrigation import (
    fetch_soil_and_irrigation,
    fetch_soil_for_plot,
    get_soil_cache_key,
)
from app.fetchers.field_score import (
    fetch_field_scores,
    fetch_score_for_plot,
    get_score_cache_key,
)
from app.fetchers.daily_report import (
    fetch_daily_reports,
    fetch_daily_report_for_plot,
    get_daily_report_cache_key,
)

logger = structlog.get_logger(__name__)

# Active Plot Monitoring Pool - only contains plots that users have actually loaded/connected to
ACTIVE_PLOT_IDS: Set[str] = set()


def register_active_plot(plot_id: str) -> None:
    """Add a plot ID to the background scheduler's recurring refresh pool."""
    clean_id = str(plot_id).strip()
    if clean_id:
        ACTIVE_PLOT_IDS.add(clean_id)


def get_active_plot_ids() -> List[str]:
    """Return all active plots currently monitored by the background scheduler."""
    return list(ACTIVE_PLOT_IDS)


async def load_all_data_for_plot(plot_id: str) -> Dict[str, Any]:
    """Concurrently pre-fetch all telemetry domains for a specific farmer/plot and hot-cache in Redis."""
    clean_id = str(plot_id).strip()
    logger.info("loading_all_telemetry_for_plot", plot_id=clean_id)

    # Register plot in active monitoring pool so background scheduler keeps it fresh
    register_active_plot(clean_id)

    # 1. Fetch plot info first to get coordinates if available
    plot_info = await fetch_plot_info_for_id(clean_id)

    # 2. Concurrently fetch remaining domains in parallel
    results = await asyncio.gather(
        fetch_soil_for_plot(clean_id),
        fetch_score_for_plot(clean_id),
        fetch_weather_for_plot(clean_id),
        fetch_daily_report_for_plot(clean_id),
        return_exceptions=True,
    )

    soil_data = results[0] if not isinstance(results[0], Exception) else {}
    score_data = results[1] if not isinstance(results[1], Exception) else {}
    weather_data = results[2] if not isinstance(results[2], Exception) else {}
    daily_report_data = results[3] if not isinstance(results[3], Exception) else {}

    return {
        "status": "success",
        "plot_id": clean_id,
        "info": plot_info,
        "soil": soil_data,
        "score": score_data,
        "weather": weather_data,
        "daily_report": daily_report_data,
    }


__all__ = [
    "async_fetch_with_retry",
    "fetch_plots_info",
    "fetch_plot_info_for_id",
    "get_available_plots_list",
    "get_plot_info_cache_key",
    "fetch_cropo_weather",
    "fetch_weather_for_plot",
    "get_weather_cache_key",
    "fetch_soil_and_irrigation",
    "fetch_soil_for_plot",
    "get_soil_cache_key",
    "fetch_field_scores",
    "fetch_score_for_plot",
    "get_score_cache_key",
    "fetch_daily_reports",
    "fetch_daily_report_for_plot",
    "get_daily_report_cache_key",
    "load_all_data_for_plot",
    "register_active_plot",
    "get_active_plot_ids",
]

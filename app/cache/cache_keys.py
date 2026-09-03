"""Canonical cache-key helpers.

Preserves the existing plot-scoped Redis key contract used by fetchers:
  data:plot:{plot_id}:info|soil|score|weather|daily_report
"""

from typing import Callable, Dict, Optional
from app.fetchers.plots_info import get_plot_info_cache_key
from app.fetchers.soil_irrigation import get_soil_cache_key
from app.fetchers.field_score import get_score_cache_key
from app.fetchers.cropo_weather import get_weather_cache_key
from app.fetchers.daily_report import get_daily_report_cache_key

DOMAIN_KEY_GETTERS: Dict[str, Callable[[str], str]] = {
    "plots_info": get_plot_info_cache_key,
    "soil_and_irrigation": get_soil_cache_key,
    "field_scores": get_score_cache_key,
    "cropo_weather": get_weather_cache_key,
    "daily_report": get_daily_report_cache_key,
}

KNOWN_DOMAINS = tuple(DOMAIN_KEY_GETTERS.keys())


def plot_domain_key(plot_id: str, domain: str) -> Optional[str]:
    """Return the existing Redis key for a plot-scoped domain, or None if unknown."""
    getter = DOMAIN_KEY_GETTERS.get(domain)
    if not getter:
        return None
    return getter(str(plot_id).strip())


def history_key(plot_id: str, domain: str) -> str:
    """Bounded trend snapshots — separate from live cache keys."""
    return f"history:plot:{str(plot_id).strip()}:{domain}"


def conversation_messages_key(session_id: str) -> str:
    return f"conversation:{session_id}:messages"


def conversation_summary_key(session_id: str) -> str:
    return f"conversation:{session_id}:summary"


def conversation_state_key(session_id: str) -> str:
    return f"conversation:{session_id}:state"


def conversation_facts_key(session_id: str) -> str:
    return f"conversation:{session_id}:facts"


def session_id_for_plot(plot_id: str, explicit: Optional[str] = None) -> str:
    """Backward-compatible session id: client-supplied, else plot-scoped default."""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    return f"plot-{str(plot_id).strip()}"

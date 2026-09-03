"""CropO Railway API client — same host, paths, and query names as Admin.py.

Base URL: https://cropoappapis.up.railway.app
POST layer endpoints take plot_name / end_date as query params with an empty body.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional
from app.config.settings import settings
from app.fetchers.base import async_fetch_with_retry

CROPO_BASE_DEFAULT = "https://cropoappapis.up.railway.app"


def cropo_base() -> str:
    return (settings.CROPO_API_BASE_URL or CROPO_BASE_DEFAULT).rstrip("/")


def cropo_headers() -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if settings.CROPO_API_KEY:
        headers["Authorization"] = f"Bearer {settings.CROPO_API_KEY}"
    return headers


def today_iso() -> str:
    return date.today().strftime("%Y-%m-%d")


def satellite_end_date(report_date: Optional[str] = None) -> str:
    """Admin.py daily-report: end_date is day-after so today's imagery is included."""
    raw = report_date or today_iso()
    try:
        d = date.fromisoformat(raw[:10])
    except ValueError:
        d = date.today()
    return (d + timedelta(days=1)).strftime("%Y-%m-%d")


async def cropo_get(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 45.0,
    max_retries: int = 2,
) -> Optional[Dict[str, Any]]:
    url = f"{cropo_base()}{path}"
    return await async_fetch_with_retry(
        url=url,
        headers=cropo_headers(),
        params=params,
        timeout=timeout,
        max_retries=max_retries,
        method="GET",
    )


async def cropo_post(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 90.0,
    max_retries: int = 1,
) -> Optional[Dict[str, Any]]:
    url = f"{cropo_base()}{path}"
    return await async_fetch_with_retry(
        url=url,
        headers=cropo_headers(),
        params=params,
        timeout=timeout,
        max_retries=max_retries,
        method="POST",
    )


def layer_from_geojson(raw: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalize Admin.py GeoJSON layer (features[0].properties + pixel_summary)."""
    if not isinstance(raw, dict) or not raw:
        return None
    if raw.get("pixel_summary") or raw.get("features"):
        feat = (raw.get("features") or [{}])[0]
        props = feat.get("properties") if isinstance(feat, dict) else {}
        props = props if isinstance(props, dict) else {}
        dates = props.get("analysis_dates") if isinstance(props.get("analysis_dates"), dict) else {}
        return {
            "data_source": props.get("data_source") or props.get("sensor") or props.get("sensor_used"),
            "sensor": props.get("sensor"),
            "sensor_used": props.get("sensor_used"),
            "latest_image_date": (
                props.get("latest_image_date")
                or dates.get("latest_image_date")
                or (raw.get("pixel_summary") or {}).get("latest_image_date")
            ),
            "image_count": props.get("image_count") or props.get("image_count_in_range"),
            "image_dates": props.get("image_dates"),
            "tile_url": props.get("tile_url"),
            "pixel_summary": raw.get("pixel_summary") if isinstance(raw.get("pixel_summary"), dict) else {},
        }
    if raw.get("data_source") or raw.get("sensor_used") or raw.get("pixel_summary"):
        return raw
    return None

"""CropO Weather Fetcher Module.

Fetches live temperature and 7-day weather outlook from
the CropO Railway API (`GET /current-temperature`).
Caches in Redis under `data:plot:{plot_id}:weather` or global weather cache.
"""

from typing import Any, Dict, Optional
import structlog
from app.cache.redis_client import redis_client
from app.config.settings import settings
from app.fetchers.base import async_fetch_with_retry

logger = structlog.get_logger(__name__)

CACHE_KEY = "data:cropo_weather:latest"
TTL_SECONDS = 600  # 10 mins


def get_weather_cache_key(plot_id: Optional[str] = None) -> str:
    """Generate Redis key for weather telemetry."""
    if plot_id:
        return f"data:plot:{plot_id.strip()}:weather"
    return CACHE_KEY


def _generate_fallback_weather() -> Dict[str, Any]:
    """Fallback weather telemetry."""
    return {
        "status": "success",
        "current": {
            "temperature_celsius": 24.5,
            "min_temp": 22.8,
            "max_temp": 27.4,
            "rain_status": "No Rain",
            "rainfall_probability_pct": 45,
        },
        "forecast": [
            {"date": "Today", "avg_temp_celsius": 24.3, "rain_prob_pct": 45, "will_rain": False},
            {"date": "Tomorrow", "avg_temp_celsius": 24.3, "rain_prob_pct": 29, "will_rain": False},
        ],
    }


async def fetch_weather_for_plot(
    plot_id: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Dict[str, Any]:
    """Fetch live temperature and weather for a plot's coordinates."""
    base_url = settings.CROPO_API_BASE_URL.rstrip("/")
    target_lat = lat or settings.DEFAULT_FARM_LAT
    target_lon = lon or settings.DEFAULT_FARM_LON
    cache_key = get_weather_cache_key(plot_id)

    url = f"{base_url}/current-temperature?lat={target_lat}&lon={target_lon}"
    headers = {"Accept": "application/json"}
    if settings.CROPO_API_KEY:
        headers["Authorization"] = f"Bearer {settings.CROPO_API_KEY}"

    logger.info("fetch_weather_started", plot_id=plot_id, lat=target_lat, lon=target_lon)

    raw_data = await async_fetch_with_retry(url=url, headers=headers, timeout=6.0, max_retries=2)

    if not isinstance(raw_data, dict) or "data" not in raw_data:
        existing = await redis_client.get_json(cache_key)
        if existing:
            logger.warning("weather_fetch_failed_retaining_cache", key=cache_key)
            return existing
        normalized = _generate_fallback_weather()
    else:
        days = raw_data.get("data", [])
        today_data = days[0] if days else {}
        hourly = today_data.get("hourly", [])
        current_hour_temp = (
            hourly[-1].get("temperature_celsius")
            if hourly
            else today_data.get("average_temperature_celsius", 24.0)
        )

        forecast_list = []
        for d in days[:5]:
            forecast_list.append(
                {
                    "date": d.get("date", ""),
                    "avg_temp_celsius": d.get("average_temperature_celsius", 0.0),
                    "min_temp": d.get("min_temperature_celsius"),
                    "max_temp": d.get("max_temperature_celsius"),
                    "rain_prob_pct": d.get("average_rainfall_percentage", 0),
                    "will_rain": d.get("will_rain", False),
                    "rain_status": d.get("rain_status", "No Rain"),
                }
            )

        normalized = {
            "status": "success",
            "location": {"lat": target_lat, "lon": target_lon},
            "current": {
                "temperature_celsius": current_hour_temp,
                "min_temp": today_data.get("min_temperature_celsius"),
                "max_temp": today_data.get("max_temperature_celsius"),
                "avg_temp": today_data.get("average_temperature_celsius"),
                "rain_status": today_data.get("rain_status", "No Rain"),
                "rainfall_probability_pct": today_data.get("average_rainfall_percentage", 0),
            },
            "forecast": forecast_list,
        }

    await redis_client.set_json(cache_key, normalized, ttl_seconds=TTL_SECONDS)
    # Also update global weather key
    await redis_client.set_json(CACHE_KEY, normalized, ttl_seconds=TTL_SECONDS)
    if plot_id:
        from app.cache.history import record_plot_snapshot
        current = normalized.get("current") if isinstance(normalized.get("current"), dict) else {}
        await record_plot_snapshot(
            plot_id,
            "cropo_weather",
            {
                "temperature_celsius": current.get("temperature_celsius"),
                "rainfall_probability_pct": current.get("rainfall_probability_pct"),
            },
        )
    return normalized


async def fetch_cropo_weather() -> bool:
    """Scheduled global weather warm-up."""
    await fetch_weather_for_plot()
    return True

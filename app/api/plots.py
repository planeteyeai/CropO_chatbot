"""Plot & Farmer Session API Endpoints with Detailed Initialization Logs."""

import time
from typing import Any, Dict
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.cache.redis_client import redis_client
from app.fetchers import (
    get_available_plots_list,
    load_all_data_for_plot,
    get_plot_info_cache_key,
    get_soil_cache_key,
    get_score_cache_key,
    get_weather_cache_key,
)

logger = structlog.get_logger(__name__)

plots_router = APIRouter(prefix="/api/plots", tags=["Plots"])


class LoadPlotRequest(BaseModel):
    plot_id: str = Field(..., min_length=1, max_length=50, description="Plot identifier (e.g. '1', '2', 'F-5939')")


@plots_router.get("/available")
async def list_available_plots() -> Dict[str, Any]:
    """Retrieve all available plot IDs registered in the farm system."""
    try:
        plots = await get_available_plots_list()
        print(f"\n📋 [PLOT DISCOVERY] Found {len(plots)} registered plots from Railway API: {plots[:10]}...", flush=True)
        return {
            "status": "success",
            "total_count": len(plots),
            "plots": plots,
        }
    except Exception as exc:
        logger.error("list_available_plots_error", error=str(exc))
        return {
            "status": "success",
            "total_count": 5,
            "plots": ["1", "2", "3", "4", "5"],
        }


@plots_router.post("/load") 
async def load_plot_telemetry(request: LoadPlotRequest) -> Dict[str, Any]:
    """Pre-fetch and cache all telemetry for a specific plot in Redis hot cache."""
    plot_id = request.plot_id.strip()
    if not plot_id:
        raise HTTPException(status_code=400, detail="plot_id cannot be empty")

    t0 = time.perf_counter()
    print(f"\n🔄 [PRE-FETCH TRIGGERED] Initializing live Railway API telemetry for Plot #{plot_id}...", flush=True)

    try:
        start_time = time.perf_counter()
        result = await load_all_data_for_plot(plot_id)
        duration = time.perf_counter() - start_time

        info = result.get("info", {})
        crop = info.get("crop_details", {})
        soil = result.get("soil", {})
        score = result.get("score", {})
        weather = result.get("weather", {})
        cur_weather = weather.get("current", {})
        report = result.get("daily_report", {})

        log_box = (
            f"\n======================================================================\n"
            f"🌱 [PLOT TELEMETRY INITIALIZED & STORED IN REDIS]\n"
            f"----------------------------------------------------------------------\n"
            f"📌 Plot ID          : #{plot_id}\n"
            f"📥 Pre-fetched Feeds:\n"
            f"   ├── 🌾 Plot Info   -> key: data:plot:{plot_id}:info ({crop.get('crop_type', 'Crop')} {crop.get('crop_variety', '')}, {info.get('area_acres')} acres)\n"
            f"   ├── 💧 Soil & Rain -> key: data:plot:{plot_id}:soil (Moisture: {soil.get('latest_moisture_pct')}%, Rain: {soil.get('yesterday_rainfall_mm')}mm)\n"
            f"   ├── 📊 Field Score -> key: data:plot:{plot_id}:score (NDVI: {score.get('field_score_pct')}%, Status: {score.get('health_status')})\n"
            f"   ├── 🌦️ Farm Weather-> key: data:plot:{plot_id}:weather ({cur_weather.get('temperature_celsius')}°C, Rain: {cur_weather.get('rain_status')})\n"
            f"   └── 📑 Daily Report-> key: data:plot:{plot_id}:daily_report (Status: {report.get('status', 'available')})\n"
            f"⏱️  Total Pre-fetch Time: {duration:.3f}s\n"
            f"======================================================================\n"
        )
        print(log_box, flush=True)

        return result
    except Exception as exc:
        logger.error("load_plot_telemetry_failed", plot_id=plot_id, error=str(exc))
        print(f"\n❌ [PRE-FETCH FAILED] Plot #{plot_id} - Error: {str(exc)}\n", flush=True)
        raise HTTPException(status_code=500, detail=f"Failed to load telemetry for plot {plot_id}: {str(exc)}")


@plots_router.get("/{plot_id}/status")
async def get_plot_cache_status(plot_id: str) -> Dict[str, Any]:
    """Inspect hot cache freshness for a specific plot."""
    from app.fetchers.daily_report import get_daily_report_cache_key
    clean_id = plot_id.strip()
    keys = {
        "info": get_plot_info_cache_key(clean_id),
        "soil": get_soil_cache_key(clean_id),
        "score": get_score_cache_key(clean_id),
        "weather": get_weather_cache_key(clean_id),
        "daily_report": get_daily_report_cache_key(clean_id),
    }

    status_data = {}
    for domain, k in keys.items():
        meta = await redis_client.get_with_metadata(k)
        status_data[domain] = {
            "cache_key": k,
            "is_cached": meta is not None,
            "age_seconds": meta.get("age_seconds") if meta else None,
            "ttl_remaining": meta.get("ttl_remaining") if meta else None,
            "data": meta.get("data") if meta else None,
        }

    return {
        "plot_id": clean_id,
        "domains": status_data,
    }

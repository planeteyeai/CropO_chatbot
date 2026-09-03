"""Debug & Diagnostics Endpoints.

Provides endpoints to inspect Redis cache status, trigger manual background refreshes,
and host a built-in mock data source for the custom Crop Index API.
"""

from typing import Any, Dict
import structlog
from fastapi import APIRouter, HTTPException
from app.cache.redis_client import redis_client
from app.config.api_registry import API_REGISTRY, get_api_by_name
from app.config.settings import settings
from app.llm.client import (
    get_gemini_verification_status,
    init_gemini_verification,
    _resolve_gemini_api_key,
)
from app.scheduler.scheduler import _resolve_fetcher_callable

logger = structlog.get_logger(__name__)

debug_router = APIRouter(tags=["Debug"])


@debug_router.post("/debug/cache/clear")
async def clear_all_cache() -> Dict[str, Any]:
    """Clear entire hot cache (Redis + in-memory) and reset active plot pool."""
    from app.fetchers import ACTIVE_PLOT_IDS

    stats = await redis_client.clear_all_cache()
    ACTIVE_PLOT_IDS.clear()
    return {
        "status": "success",
        "message": "All cache cleared. Reload a plot to fetch fresh live telemetry.",
        **stats,
    }


@debug_router.get("/debug/gemini-key")
async def check_gemini_key(refresh: bool = False) -> Dict[str, Any]:
    """Test whether GEMINI_API_KEY works by sending a live 'hi, are you working?' request."""
    if refresh:
        working, message = await init_gemini_verification()
    else:
        cached_working, cached_message = get_gemini_verification_status()
        if cached_working is not None:
            working, message = cached_working, cached_message
        else:
            working, message = await init_gemini_verification()

    api_key = _resolve_gemini_api_key(settings)
    return {
        "working": working,
        "message": message,
        "provider": settings.LLM_PROVIDER,
        "model": settings.GEMINI_MODEL,
        "key_configured": bool(api_key),
        "key_preview": f"{api_key[:8]}..." if len(api_key) > 8 else ("(empty)" if not api_key else "(short key)"),
    }


@debug_router.get("/debug/cache")
async def get_cache_status() -> Dict[str, Any]:
    """Inspect hot cache state across all registered domains."""
    status_list = await redis_client.get_all_keys_status(API_REGISTRY)
    is_redis_live = await redis_client.is_connected()

    return {
        "redis_connected": is_redis_live,
        "total_registered_domains": len(API_REGISTRY),
        "domains": status_list,
    }


@debug_router.post("/debug/refresh/{domain_name}")
async def trigger_domain_refresh(domain_name: str) -> Dict[str, Any]:
    """Trigger an immediate background refresh of a specific data domain."""
    api_config = get_api_by_name(domain_name)
    if not api_config:
        raise HTTPException(
            status_code=404,
            detail=f"Domain '{domain_name}' not found in API_REGISTRY.",
        )

    try:
        fetcher_func = _resolve_fetcher_callable(api_config)
        success = await fetcher_func()
        return {
            "status": "success" if success else "failed",
            "domain": domain_name,
            "cache_key": api_config.get("cache_key"),
        }
    except Exception as exc:
        logger.error("manual_refresh_failed", domain=domain_name, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@debug_router.get("/api/v1/crops/index")
async def mock_crop_index_source() -> Dict[str, Any]:
    """Self-contained simulated source API endpoint for crop data.

    Allows the offline fetcher to run end-to-end out of the box locally.
    """
    return {
        "status": "success",
        "market_summary": {
            "overall_index": 131.2,
            "trend": "+2.4% week-over-week",
            "global_market_sentiment": "Strong export demand and stable global logistics",
        },
        "crops": [
            {
                "crop": "Wheat",
                "price_per_metric_ton_usd": 248.00,
                "daily_change_pct": "+1.1%",
                "yield_forecast": "High (3.6 tons/hectare)",
                "soil_moisture_level": "Optimal (68%)",
                "pest_risk": "Low",
                "advisory": "Favorable soil conditions; proceed with scheduled nitrogen application.",
            },
            {
                "crop": "Corn",
                "price_per_metric_ton_usd": 185.50,
                "daily_change_pct": "-0.2%",
                "yield_forecast": "Stable (9.9 tons/hectare)",
                "soil_moisture_level": "Moderate (55%)",
                "pest_risk": "Low",
                "advisory": "Maintain normal irrigation intervals; monitor soil aeration.",
            },
            {
                "crop": "Rice",
                "price_per_metric_ton_usd": 420.00,
                "daily_change_pct": "+1.5%",
                "yield_forecast": "High (4.8 tons/hectare)",
                "soil_moisture_level": "Saturated (82%)",
                "pest_risk": "Low",
                "advisory": "Water levels optimal for tillering stage.",
            },
            {
                "crop": "Soybean",
                "price_per_metric_ton_usd": 456.00,
                "daily_change_pct": "+1.8%",
                "yield_forecast": "Above average (3.0 tons/hectare)",
                "soil_moisture_level": "Optimal (64%)",
                "pest_risk": "Low",
                "advisory": "Pod filling phase progressing well.",
            },
            {
                "crop": "Cotton",
                "price_per_metric_ton_usd": 1835.00,
                "daily_change_pct": "+0.7%",
                "yield_forecast": "Normal (780 kg/hectare)",
                "soil_moisture_level": "Moderate (45%)",
                "pest_risk": "Low",
                "advisory": "Boll formation under favorable dry warmth.",
            },
        ],
        "environmental_indicators": {
            "average_soil_moisture_pct": 62.8,
            "drought_severity_index": "None",
            "irrigation_recommendation": "Standard cycles for cereal crops",
        },
    }

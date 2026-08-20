"""Tests for API fetchers, per-plot caching, and stale-on-failure guarantees."""

import pytest
from unittest.mock import patch, AsyncMock
from app.cache.redis_client import redis_client
from app.fetchers.plots_info import fetch_plots_info, fetch_plot_info_for_id, get_plot_info_cache_key
from app.fetchers.cropo_weather import fetch_cropo_weather, fetch_weather_for_plot, get_weather_cache_key
from app.fetchers.soil_irrigation import fetch_soil_and_irrigation, fetch_soil_for_plot, get_soil_cache_key
from app.fetchers.field_score import fetch_field_scores, fetch_score_for_plot, get_score_cache_key


@pytest.mark.asyncio
async def test_fetch_plot_info_writes_to_cache():
    """Verify fetch_plot_info_for_id normalizes metadata and stores in Redis."""
    mock_plot_1_info = {
        "name": "1",
        "geometry_type": "Polygon",
        "area_acres": 0.94,
        "crop_details": {
            "crop_type": "Mango",
            "crop_variety": "Alpha",
            "plantation_date": "2026-06-02",
            "irrigation_type": "Drip Irrigation",
        },
    }

    with patch("app.fetchers.plots_info.async_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_plot_1_info
        result = await fetch_plot_info_for_id("1")
        assert result["crop_details"]["crop_type"] == "Mango"

        cached = await redis_client.get_with_metadata(get_plot_info_cache_key("1"))
        assert cached is not None
        assert "data" in cached
        assert cached["data"]["name"] == "1"


@pytest.mark.asyncio
async def test_fetch_soil_for_plot_writes_to_cache():
    """Verify fetch_soil_for_plot captures soil moisture stack for the plot."""
    mock_soil_raw = {
        "plot_name": "1",
        "soil_moisture_stack": [
            {
                "day": "2026-08-17",
                "soil_moisture": 81.37,
                "rainfall_mm_yesterday": 1.4,
                "et_mean_mm_yesterday": 1.54,
            }
        ],
    }

    with patch("app.fetchers.soil_irrigation.async_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_soil_raw
        result = await fetch_soil_for_plot("1")
        assert result["latest_moisture_pct"] == 81.37

        cached = await redis_client.get_with_metadata(get_soil_cache_key("1"))
        assert cached is not None
        assert cached["data"]["latest_moisture_pct"] == 81.37


@pytest.mark.asyncio
async def test_fetch_score_for_plot_writes_to_cache():
    """Verify field score evaluation per plot."""
    mock_score_raw = {"plot_name": "1", "field_score": 100.0}

    with patch("app.fetchers.field_score.async_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_score_raw
        result = await fetch_score_for_plot("1")
        assert result["field_score_pct"] == 100.0

        cached = await redis_client.get_with_metadata(get_score_cache_key("1"))
        assert cached is not None
        assert cached["data"]["field_score_pct"] == 100.0


@pytest.mark.asyncio
async def test_soil_fetch_stale_on_failure():
    """Verify that failed soil moisture fetch retains existing cache."""
    cache_key = get_soil_cache_key("1")
    initial_data = {
        "status": "success",
        "plot_name": "1",
        "latest_moisture_pct": 81.4,
    }
    await redis_client.set_json(cache_key, initial_data, ttl_seconds=900)

    with patch("app.fetchers.soil_irrigation.async_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None
        result = await fetch_soil_for_plot("1")
        assert result["latest_moisture_pct"] == 81.4

        retained = await redis_client.get_with_metadata(cache_key)
        assert retained is not None
        assert retained["data"]["latest_moisture_pct"] == 81.4


@pytest.mark.asyncio
async def test_fetch_daily_report_for_plot_writes_to_cache():
    """Verify daily report is fetched, normalized and written to Redis."""
    from app.fetchers.daily_report import fetch_daily_report_for_plot, get_daily_report_cache_key

    mock_report = {
        "plot_name": "1",
        "date": "2026-08-19",
        "crop_health_summary": "Optimal canopy vigor",
        "soil_water_summary": "Soil root-zone moisture 81.37%",
        "weather_summary": "Overcast 24.5°C",
        "primary_action_items": ["Hold drip irrigation"],
    }

    with patch("app.fetchers.daily_report.async_fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_report
        result = await fetch_daily_report_for_plot("1")
        assert result["crop_health_summary"] == "Optimal canopy vigor"

        cached = await redis_client.get_with_metadata(get_daily_report_cache_key("1"))
        assert cached is not None
        assert cached["data"]["crop_health_summary"] == "Optimal canopy vigor"


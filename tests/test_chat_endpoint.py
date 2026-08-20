"""Tests for Plot Session Discovery, Pre-fetching, and the /chat SSE endpoint."""

import json
from unittest.mock import patch
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.cache.redis_client import redis_client
from app.fetchers.plots_info import get_plot_info_cache_key
from app.fetchers.cropo_weather import get_weather_cache_key
from app.fetchers.soil_irrigation import get_soil_cache_key
from app.fetchers.field_score import get_score_cache_key
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def seed_test_plot_cache():
    """Ensure Redis has cached telemetry for Plot 1 before each test."""
    plot_1_info = {
        "status": "success",
        "name": "1",
        "area_acres": 0.94,
        "geometry_type": "Polygon",
        "crop_details": {
            "crop_type": "Mango",
            "crop_variety": "Alpha",
            "plantation_date": "2026-06-02",
            "irrigation_type": "Drip Irrigation",
        },
    }
    plot_1_soil = {
        "status": "success",
        "plot_name": "1",
        "latest_moisture_pct": 81.4,
        "moisture_status": "High",
        "yesterday_rainfall_mm": 1.4,
        "et_mean_mm": 1.54,
        "advisory": "Defer irrigation cycles.",
    }
    plot_1_score = {
        "status": "success",
        "plot_name": "1",
        "field_score_pct": 100.0,
        "health_status": "Excellent (Peak Vigor)",
        "advisory": "Optimal photosynthetic activity.",
    }
    plot_1_weather = {
        "status": "success",
        "current": {
            "temperature_celsius": 24.5,
            "min_temp": 22.8,
            "max_temp": 27.4,
            "rain_status": "No Rain",
            "rainfall_probability_pct": 45,
        },
    }

    await redis_client.set_json(get_plot_info_cache_key("1"), plot_1_info, ttl_seconds=1800)
    await redis_client.set_json(get_soil_cache_key("1"), plot_1_soil, ttl_seconds=900)
    await redis_client.set_json(get_score_cache_key("1"), plot_1_score, ttl_seconds=1200)
    await redis_client.set_json(get_weather_cache_key("1"), plot_1_weather, ttl_seconds=600)


@pytest.mark.asyncio
async def test_available_plots_endpoint():
    """Verify GET /api/plots/available lists registered plots."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/plots/available")
        assert response.status_code == 200
        data = response.json()
        assert "plots" in data
        assert len(data["plots"]) > 0


@pytest.mark.asyncio
async def test_load_plot_telemetry_endpoint():
    """Verify POST /api/plots/load pre-fetches and returns plot telemetry."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/plots/load", json={"plot_id": "1"})
        assert response.status_code == 200
        data = response.json()
        assert data["plot_id"] == "1"
        assert "info" in data
        assert "soil" in data
        assert "score" in data


@pytest.mark.asyncio
async def test_chat_endpoint_streams_plot_grounded_sse():
    """Verify POST /chat streams plot-grounded tokens via Server-Sent Events."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={"plot_id": "1", "message": "What is the crop variety and plantation details for this plot?"},
            headers={"Accept": "text/event-stream"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        lines = response.text.split("\n\n")
        received_tokens = []
        is_done = False

        for line in lines:
            trimmed = line.strip()
            if not trimmed.startswith("data:"):
                continue
            data_json = json.loads(trimmed[5:].strip())
            if "token" in data_json and data_json["token"]:
                received_tokens.append(data_json["token"])
            if data_json.get("done") is True:
                is_done = True

        assert is_done is True
        full_text = "".join(received_tokens)
        assert len(full_text) > 0
        assert "Plot 1" in full_text or "plot 1" in full_text.lower() or "mango" in full_text.lower()


@pytest.mark.asyncio
async def test_multi_turn_chat_memory():
    """Verify POST /chat correctly processes multi-turn follow-up queries with history."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Turn 2: Follow-up question referring to previous soil moisture turn
        history = [
            {"role": "user", "content": "What is my soil moisture level?"},
            {"role": "assistant", "content": "Your soil moisture for Plot #1 is 81.4% (High / Saturated)."},
        ]
        response = await client.post(
            "/chat",
            json={
                "plot_id": "1",
                "message": "Is it good or should I pause drip irrigation?",
                "history": history,
            },
            headers={"Accept": "text/event-stream"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        lines = response.text.split("\n\n")
        received_tokens = []
        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith("data:"):
                data_json = json.loads(trimmed[5:].strip())
                if "token" in data_json and data_json["token"]:
                    received_tokens.append(data_json["token"])

        full_text = "".join(received_tokens).lower()
        assert len(full_text) > 0
        assert "moisture" in full_text or "irrigation" in full_text or "81" in full_text


@pytest.mark.asyncio
async def test_zero_external_api_calls_during_chat():
    """CRITICAL ARCHITECTURAL TEST: Verify /chat NEVER makes external API fetcher calls."""
    transport = ASGITransport(app=app)

    with patch("app.fetchers.base.async_fetch_with_retry") as mock_fetch_retry:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/chat",
                json={"plot_id": "1", "message": "What is my soil moisture and irrigation guide?"},
            )
            assert response.status_code == 200

        # Assert no external fetcher calls occurred during chat
        mock_fetch_retry.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,expected_substring", [
    ("hi", "मिट्टी की नमी"),
    ("mr", "जमिनीतील ओलावा"),
    ("kn", "ಮಣ್ಣಿನ ತೇವಾಂಶ"),
])
async def test_multilingual_chat_responses(lang: str, expected_substring: str):
    """Verify /chat returns appropriate localized response when language is specified."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={
                "plot_id": "1",
                "message": "What is my soil moisture?",
                "language": lang,
            },
            headers={"Accept": "text/event-stream"},
        )
        assert response.status_code == 200

        lines = response.text.split("\n\n")
        received_tokens = []
        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith("data:"):
                data_json = json.loads(trimmed[5:].strip())
                if "token" in data_json and data_json["token"]:
                    received_tokens.append(data_json["token"])

        full_text = "".join(received_tokens)
        assert len(full_text) > 0
        assert expected_substring in full_text



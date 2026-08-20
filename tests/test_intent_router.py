"""Tests for Intent Routing speed and multi-domain matching accuracy."""

import time
import pytest
from app.routing.intent_router import KeywordIntentRouter, route_query


@pytest.fixture
def keyword_router():
    return KeywordIntentRouter()


def test_keyword_router_matches_all_cropo_domains(keyword_router):
    """Verify that domain queries accurately map to their respective registered domains."""
    # Domain 1: plots_info
    assert "plots_info" in keyword_router.route("What crops are planted in Plot 1?")
    assert "plots_info" in keyword_router.route("How many acres is the mango orchard?")
    assert "plots_info" in keyword_router.route("Tell me the plantation date and irrigation type for plot 2")

    # Domain 2: cropo_weather
    assert "cropo_weather" in keyword_router.route("What is the current temperature and weather forecast?")
    assert "cropo_weather" in keyword_router.route("Will it rain today on the farm?")

    # Domain 3: soil_and_irrigation
    assert "soil_and_irrigation" in keyword_router.route("What is the soil moisture level for plot 1?")
    assert "soil_and_irrigation" in keyword_router.route("Do I need to irrigate my fields today?")

    # Domain 4: field_scores
    assert "field_scores" in keyword_router.route("What is the field score and health score for plot 1?")
    assert "field_scores" in keyword_router.route("Show me the NDVI vegetation vigor status")

    # Domain 5: daily_report
    assert "daily_report" in keyword_router.route("Give me the full daily report for my farm")
    assert "daily_report" in keyword_router.route("What is the overall daily summary report for plot 1?")



def test_keyword_router_ignores_out_of_domain_queries(keyword_router):
    """Verify that queries outside registered domains return an empty list."""
    out_of_domain_queries = [
        "What is the stock price of Tesla?",
        "Write a poem about space exploration",
        "How do I bake sourdough bread?",
        "Who won the basketball championship?",
    ]

    for q in out_of_domain_queries:
        matched = keyword_router.route(q)
        assert matched == [], f"Expected empty match for query: {q}"


def test_routing_latency_under_50ms():
    """Verify that intent routing executes in well under 50ms with zero network calls."""
    query = "Tell me about the soil moisture and weather forecast for plot 1"

    start = time.perf_counter()
    for _ in range(50):
        _ = route_query(query)
    total_duration_ms = (time.perf_counter() - start) * 1000.0
    avg_latency_ms = total_duration_ms / 50.0

    # Must resolve far below 50ms threshold
    assert avg_latency_ms < 10.0, f"Routing took {avg_latency_ms}ms, which exceeds budget"

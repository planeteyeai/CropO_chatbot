"""Central farm-intelligence coordinator. Cache-first, no CropO HTTP."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import structlog
from app.cache.cache_reader import CacheResult, freshness_map, read_domains
from app.cache.history import load_plot_history
from app.intelligence.anomaly_engine import detect_anomalies
from app.intelligence.confidence_engine import assess_confidence
from app.intelligence.conflict_detector import detect_conflicts
from app.intelligence.decision_engine import decide
from app.intelligence.evidence_planner import EvidencePlan, plan_evidence
from app.intelligence.farm_state import build_farm_state
from app.intelligence.layers.base import analyze_selected_layers
from app.context.area_units import plot_acres_from_payloads
from app.intelligence.cross_layer_reasoner import reason_across_layers
from app.intelligence.trend_engine import analyze_trends
from app.memory.memory_retriever import retrieve_relevant_memories
from app.routing.query_classifier import QueryAnalysis

logger = structlog.get_logger(__name__)


@dataclass
class IntelligenceResult:
    plot_id: str
    original_question: str
    resolved_question: str
    query_analysis: QueryAnalysis
    relevant_memories: List[Dict[str, Any]]
    farm_state: Dict[str, Any]
    trends: Dict[str, str]
    anomalies: List[Dict[str, Any]]
    conflicts: List[Dict[str, Any]]
    decision: Optional[Dict[str, Any]]
    confidence: str
    freshness: Dict[str, str]
    context: str
    selected_layers: List[str] = field(default_factory=list)
    matched_domains: List[str] = field(default_factory=list)
    evidence_plan: Optional[EvidencePlan] = None
    timings_ms: Dict[str, float] = field(default_factory=dict)
    response_source: str = "farm_intelligence"
    conversation_summary: str = ""
    briefing: Dict[str, Any] = field(default_factory=dict)
    cache_payloads: Dict[str, Any] = field(default_factory=dict)


async def run_intelligence(
    *,
    plot_id: str,
    original_question: str,
    resolved_question: str,
    language: str,
    session_state: Dict[str, Any],
    query_analysis: QueryAnalysis,
    messages: List[Dict[str, Any]],
    conversation_summary: str = "",
) -> IntelligenceResult:
    t0 = time.perf_counter()
    plan = plan_evidence(query_analysis, active_topic=session_state.get("active_topic"))

    t_mem = time.perf_counter()
    memories = retrieve_relevant_memories(
        messages,
        query=resolved_question,
        topics=query_analysis.topics,
        plot_id=plot_id,
        active_topic=session_state.get("active_topic"),
        is_follow_up=query_analysis.is_follow_up,
    )
    memory_ms = (time.perf_counter() - t_mem) * 1000.0

    t_cache = time.perf_counter()
    cache_results: Dict[str, CacheResult] = {}
    if plan.domains:
        cache_results = await read_domains(plot_id, plan.domains)
    cache_ms = (time.perf_counter() - t_cache) * 1000.0

    t_intel = time.perf_counter()
    farm_state = build_farm_state(plot_id, cache_results, selected_layers=plan.layers)

    history_by_domain: Dict[str, List[Dict[str, Any]]] = {}
    if plan.requires_trend or plan.requires_history:
        for domain in plan.domains:
            history_by_domain[domain] = await load_plot_history(plot_id, domain)

    trends = analyze_trends(farm_state, history_by_domain) if (plan.requires_trend or history_by_domain) else {}
    anomalies = detect_anomalies(farm_state, history_by_domain)
    conflicts = detect_conflicts(farm_state)

    report = (cache_results.get("daily_report").data if cache_results.get("daily_report") else None) or {}
    raw_layers = report.get("layers") if isinstance(report, dict) else {}
    plot_acres = plot_acres_from_payloads(
        farm_state,
        cache_results.get("plots_info").data if cache_results.get("plots_info") else None,
        report,
        raw_layers.get("agro_stats") if isinstance(raw_layers, dict) else None,
    )
    layer_analyses = analyze_selected_layers(
        raw_layers if isinstance(raw_layers, dict) else {},
        plan.layers,
        plot_acres=plot_acres,
    )
    briefing = reason_across_layers(farm_state, layer_analyses, trends, anomalies, conflicts)

    decision = decide(query_analysis, farm_state, trends, anomalies, conflicts)
    confidence = assess_confidence(
        query_analysis.topics,
        farm_state,
        conflicts,
        trends,
        decision,
    )
    if decision is not None:
        decision["confidence"] = confidence

    intel_ms = (time.perf_counter() - t_intel) * 1000.0
    freshness = freshness_map(cache_results)

    result = IntelligenceResult(
        plot_id=str(plot_id),
        original_question=original_question,
        resolved_question=resolved_question,
        query_analysis=query_analysis,
        relevant_memories=memories,
        farm_state=farm_state,
        trends=trends,
        anomalies=anomalies,
        conflicts=conflicts,
        decision=decision,
        confidence=confidence,
        freshness=freshness,
        context="",  # filled by context builder
        selected_layers=plan.layers,
        matched_domains=plan.domains,
        evidence_plan=plan,
        timings_ms={
            "memory_ms": round(memory_ms, 3),
            "cache_ms": round(cache_ms, 3),
            "intelligence_ms": round(intel_ms, 3),
            "total_pre_llm_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        },
        conversation_summary=conversation_summary,
        briefing=briefing,
        cache_payloads={name: item.data for name, item in cache_results.items() if item.data},
    )
    logger.info(
        "intelligence_completed",
        plot_id=plot_id,
        intent=query_analysis.intent,
        domains=plan.domains,
        layers=plan.layers,
        confidence=confidence,
        **result.timings_ms,
    )
    return result

"""Chat Endpoint — thin orchestration over FAQ, memory, and farm intelligence.

POST /chat never calls CropO external APIs. Farm data comes only from Redis / memory fallback.
"""

import json
import time
from typing import Any, AsyncIterator, Dict, List, Literal, Optional
import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.cache.cache_keys import session_id_for_plot
from app.context.context_builder import build_intelligence_context
from app.intelligence.orchestrator import IntelligenceResult, run_intelligence
from app.knowledge.faq_engine import faq_engine
from app.knowledge.offline_responder import farmer_ack_greeting, render_farmer_response
from app.llm.client import get_llm_client, get_provider_label
from app.llm.prompts import SYSTEM_GROUNDING_PROMPT, build_intelligence_user_prompt
from app.memory.conversation_memory import ConversationMemory, hydrate_from_client_history
from app.memory.reference_resolver import ResolvedReference, resolve_reference
from app.memory.topic_state import update_topic_state
from app.routing.language_router import detect_language
from app.routing.query_classifier import classify_query, is_clearly_out_of_domain, is_farmer_acknowledgment

logger = structlog.get_logger(__name__)

chat_router = APIRouter(tags=["Chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "model"] = Field(..., description="Message author role")
    content: str = Field(..., description="Message text content")


class ChatRequest(BaseModel):
    plot_id: str = Field(default="1", description="Selected Plot / Farmer identifier")
    message: str = Field(..., min_length=1, max_length=2000, description="User's query string")
    history: List[ChatMessage] = Field(default=[], description="Previous conversation turns for context memory")
    language: str = Field(default="en", description="Target response language ('en', 'hi', 'mr', 'kn')")
    session_id: Optional[str] = Field(default=None, description="Optional session id; defaults to plot-scoped id")
    response_mode: str = Field(default="normal", description="short | normal | detailed")


def _sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_text(text: str, chunk_size: int = 24) -> AsyncIterator[str]:
    if not text:
        return
    for i in range(0, len(text), chunk_size):
        yield text[i : i + chunk_size]


def _history_dicts(history: List[ChatMessage]) -> List[Dict[str, str]]:
    return [{"role": h.role, "content": h.content} for h in history]


_CANNED_PEST_MARKERS = (
    "satellite pixel signatures",
    "not a confirmed lab identification",
    "leaf undersides and growing tips",
    "blanket insecticide",
)
_SATELLITE_RECITE_OPENERS = (
    "based on the satellite",
    "based on satellite imagery",
    "based on the current satellite",
    "the satellite imagery shows",
    "the satellite imagery indicates",
    "the satellite imagery can only",
)
_PEST_REFUSAL_MARKERS = (
    "cannot identify the specific",
    "cannot identify the pest",
    "cannot identify the specific type",
    "cannot identify the specific name",
    "satellite cannot identify",
    "satellite imagery can only classify",
    "satellite imagery cannot identify",
)


def _is_canned_pest_disclaimer(text: str) -> bool:
    lowered = (text or "").lower()
    hits = sum(1 for m in _CANNED_PEST_MARKERS if m in lowered)
    if hits >= 2:
        return True
    if any(m in lowered for m in _PEST_REFUSAL_MARKERS):
        return True
    return any(m in lowered for m in _SATELLITE_RECITE_OPENERS)


def _sanitize_llm_history(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Drop prior assistant turns that are only the satellite-pest disclaimer."""
    cleaned: List[Dict[str, str]] = []
    for msg in history:
        role = msg.get("role") or ""
        content = msg.get("content") or ""
        if role in ("assistant", "model", "bot") and _is_canned_pest_disclaimer(content):
            continue
        cleaned.append(msg)
    return cleaned


async def generate_chat_events(
    plot_id: str,
    user_message: str,
    history: List[ChatMessage] = [],
    language: str = "en",
    session_id: Optional[str] = None,
    response_mode: str = "normal",
) -> AsyncIterator[str]:
    """Online pipeline: FAQ → memory → intelligence → grounded LLM SSE. Zero CropO HTTP."""
    t_start = time.perf_counter()
    lang = (language or "en").lower().strip() or "en"
    if lang not in ("en", "hi", "mr", "kn"):
        lang = detect_language(user_message, fallback="en")
    sid = session_id_for_plot(plot_id, session_id)
    memory = ConversationMemory(sid)

    await hydrate_from_client_history(memory, [h.model_dump() for h in history], plot_id)
    messages = await memory.get_messages()
    state = await memory.get_state()
    summary = await memory.get_summary()

    # Bare "okay" / thanks: greet the farmer. Do not continue the last pest/soil essay.
    if is_farmer_acknowledgment(user_message):
        greeting = farmer_ack_greeting(lang, plot_id)
        await memory.append_message({
            "role": "user",
            "content": user_message,
            "plot_id": plot_id,
            "topics": [],
            "intent": "ACKNOWLEDGMENT",
        })
        full = []
        async for chunk in _stream_text(greeting):
            full.append(chunk)
            yield _sse({"token": chunk, "done": False})
        await memory.append_message({
            "role": "assistant",
            "content": "".join(full),
            "plot_id": plot_id,
            "topics": [],
            "intent": "ACKNOWLEDGMENT",
            "confidence": "HIGH",
        })
        logger.info(
            "chat_completed",
            plot_id=plot_id,
            intent="ACKNOWLEDGMENT",
            response_source="greeting",
            total_ms=round((time.perf_counter() - t_start) * 1000.0, 3),
        )
        yield _sse({
            "token": "",
            "done": True,
            "plot_id": plot_id,
            "matched_domains": [],
            "selected_layers": [],
            "confidence": "HIGH",
            "freshness": {},
            "response_source": "greeting",
        })
        return

    # --- FAQ fast path (exact/keyword) before LLM ---
    t_faq_0 = time.perf_counter()
    faq_hit = faq_engine.match(user_message, language=lang)
    faq_ms = (time.perf_counter() - t_faq_0) * 1000.0

    if faq_hit and faq_hit.method in {"exact", "keyword", "phrase"}:
        await memory.append_message({
            "role": "user",
            "content": user_message,
            "timestamp": None,
            "plot_id": plot_id,
            "topics": [],
            "intent": "OFFLINE_FAQ",
        })
        full = []
        async for chunk in _stream_text(faq_hit.answer):
            full.append(chunk)
            yield _sse({"token": chunk, "done": False})
        answer = "".join(full)
        await memory.append_message({
            "role": "assistant",
            "content": answer,
            "plot_id": plot_id,
            "topics": [],
            "intent": "OFFLINE_FAQ",
            "confidence": "HIGH",
        })
        logger.info(
            "chat_completed",
            plot_id=plot_id,
            intent="OFFLINE_FAQ",
            faq_ms=round(faq_ms, 3),
            response_source="faq",
            total_ms=round((time.perf_counter() - t_start) * 1000.0, 3),
        )
        yield _sse({
            "token": "",
            "done": True,
            "plot_id": plot_id,
            "matched_domains": [],
            "selected_layers": [],
            "confidence": "HIGH",
            "freshness": {},
            "response_source": "faq",
        })
        return

    # --- Reference resolution + classification ---
    t_route_0 = time.perf_counter()
    resolved = resolve_reference(user_message, state=state, language=lang)
    analysis = classify_query(
        user_message,
        language=lang,
        is_follow_up=resolved.is_follow_up,
        is_faq_candidate=bool(faq_hit),
    )
    # Farm follow-ups without topic words ("precautions", "what next") must use the active topic,
    # not empty OUT_OF_DOMAIN context — that made Gemini refuse instead of advising.
    if (
        analysis.intent == "OUT_OF_DOMAIN"
        and state.get("active_topic")
        and not is_clearly_out_of_domain(user_message)
        and not is_farmer_acknowledgment(user_message)
    ):
        if not resolved.is_follow_up:
            resolved = resolve_reference(user_message, state=state, language=lang)
            if not resolved.is_follow_up:
                topic = str(state.get("active_topic") or "this plot").replace("_", " ")
                resolved = ResolvedReference(
                    original_question=user_message,
                    resolved_question=f"Regarding {topic} on this plot: {user_message}",
                    is_follow_up=True,
                    language=lang,
                )
        analysis = classify_query(
            resolved.resolved_question,
            language=lang,
            is_follow_up=True,
            is_faq_candidate=bool(faq_hit),
        )
    elif resolved.is_follow_up and not analysis.topics:
        # Follow-ups keep the prior topic; named questions (weather, pest, etc.) keep their own intent.
        analysis = classify_query(
            resolved.resolved_question,
            language=lang,
            is_follow_up=True,
            is_faq_candidate=bool(faq_hit),
        )
    analysis.is_follow_up = resolved.is_follow_up
    t_route_ms = (time.perf_counter() - t_route_0) * 1000.0

    intel: IntelligenceResult = await run_intelligence(
        plot_id=plot_id,
        original_question=user_message,
        resolved_question=resolved.resolved_question,
        language=lang,
        session_state=state,
        query_analysis=analysis,
        messages=messages,
        conversation_summary=summary,
    )

    t_ctx_0 = time.perf_counter()
    context_text = await build_intelligence_context(intel, response_mode=response_mode)
    t_ctx_ms = (time.perf_counter() - t_ctx_0) * 1000.0

    user_prompt = build_intelligence_user_prompt(
        original_question=user_message,
        resolved_question=resolved.resolved_question,
        context_text=context_text,
        language=lang,
        response_mode=response_mode,
    )

    await memory.append_message({
        "role": "user",
        "content": user_message,
        "plot_id": plot_id,
        "topics": analysis.topics,
        "intent": analysis.intent,
    })

    llm_client = get_llm_client()
    provider_name = get_provider_label(llm_client)
    history_dicts = _history_dicts(history) or [
        {"role": m["role"], "content": m["content"]} for m in messages[-8:]
        if m.get("role") in ("user", "assistant", "model")
    ]
    use_history = _sanitize_llm_history(history_dicts[-8:])
    mode = (response_mode or "normal").lower()
    token_budget = {"short": 180, "normal": 380, "detailed": 700}.get(mode, 380)
    if analysis.intent == "MARKET_PRICE" or getattr(analysis, "is_market_price_query", False):
        token_budget = max(token_budget, 640)
    elif getattr(analysis, "is_fertilizer_query", False) or getattr(analysis, "is_yield_improve_query", False):
        token_budget = max(token_budget, 520)

    t_llm_0 = time.perf_counter()
    t_first_token: float | None = None
    token_count = 0
    collected: List[str] = []

    try:
        async for token in llm_client.stream_chat(
            SYSTEM_GROUNDING_PROMPT,
            user_prompt,
            history=use_history,
            max_output_tokens=token_budget,
            enable_google_search=bool(
                analysis.intent == "MARKET_PRICE" or getattr(analysis, "is_market_price_query", False)
            ),
        ):
            if t_first_token is None:
                t_first_token = time.perf_counter() - t_llm_0
            token_count += 1
            collected.append(token)
            yield _sse({"token": token, "done": False})

        t_llm_total = time.perf_counter() - t_llm_0
        t_total = time.perf_counter() - t_start
        answer = "".join(collected)

        rec = (intel.decision or {}).get("decision")
        await memory.append_message({
            "role": "assistant",
            "content": answer,
            "plot_id": plot_id,
            "topics": analysis.topics,
            "recommendation": rec,
            "domains_used": intel.matched_domains,
            "confidence": intel.confidence,
        })
        await update_topic_state(
            memory,
            plot_id=plot_id,
            topics=analysis.topics,
            intent=analysis.intent,
            recommendation=rec,
        )

        timings = intel.timings_ms or {}
        print(
            (
                f"\n"
                f"======================================================================\n"
                f"[CROPO CHAT PIPELINE EXECUTION METRICS]\n"
                f"----------------------------------------------------------------------\n"
                f"Active Plot ID        : #{plot_id}\n"
                f"User Query            : \"{user_message}\" (History Turns: {len(history)})\n"
                f"Detected Intent       : {analysis.intent} topics={analysis.topics}\n"
                f"Matched Domains       : {intel.matched_domains if intel.matched_domains else ['none']}\n"
                f"FAQ Time              : {faq_ms:.2f} ms\n"
                f"Intent Routing Time   : {t_route_ms:.2f} ms\n"
                f"Memory Retrieval Time : {timings.get('memory_ms', 0):.2f} ms\n"
                f"Redis Cache Read Time : {timings.get('cache_ms', t_ctx_ms):.2f} ms [ZERO external APIs]\n"
                f"Intelligence Time     : {timings.get('intelligence_ms', 0):.2f} ms\n"
                f"LLM Provider Backend  : {provider_name}\n"
                f"Time to 1st Token     : {f'{t_first_token:.3f}s' if t_first_token is not None else 'N/A'}\n"
                f"LLM Generation Time   : {t_llm_total:.3f}s ({token_count} chunks streamed)\n"
                f"TOTAL PIPELINE LATENCY: {t_total:.3f}s\n"
                f"======================================================================\n"
            ),
            flush=True,
        )
        logger.info(
            "chat_completed",
            plot_id=plot_id,
            intent=analysis.intent,
            topics=analysis.topics,
            memory_count=len(intel.relevant_memories),
            matched_domains=intel.matched_domains,
            selected_layers=intel.selected_layers,
            faq_ms=round(faq_ms, 3),
            routing_ms=round(t_route_ms, 3),
            memory_ms=timings.get("memory_ms"),
            cache_ms=timings.get("cache_ms"),
            intelligence_ms=timings.get("intelligence_ms"),
            ttft_ms=round((t_first_token or 0) * 1000.0, 3) if t_first_token is not None else 0,
            total_ms=round(t_total * 1000.0, 3),
            response_source="farm_intelligence",
        )
        yield _sse({
            "token": "",
            "done": True,
            "plot_id": plot_id,
            "matched_domains": intel.matched_domains,
            "selected_layers": intel.selected_layers,
            "confidence": intel.confidence,
            "freshness": intel.freshness,
            "response_source": "farm_intelligence",
        })
    except Exception as exc:
        t_total = time.perf_counter() - t_start
        logger.error("chat_streaming_error", plot_id=plot_id, error=str(exc))
        fallback = render_farmer_response(
            language=lang,
            intent=analysis.intent,
            decision=intel.decision,
            confidence=intel.confidence,
            farm_state=intel.farm_state,
            anomalies=intel.anomalies,
            conflicts=intel.conflicts,
            freshness=intel.freshness,
            missing=(intel.farm_state or {}).get("missing_data") or [],
        )
        async for chunk in _stream_text(fallback or f"\n\n[Error generating response: {str(exc)}]"):
            yield _sse({"token": chunk, "done": False})
        print(f"\n[CHAT PIPELINE ERROR] Plot #{plot_id} - Error: {str(exc)} (Failed after {t_total:.3f}s)\n", flush=True)
        yield _sse({"token": "", "done": True, "error": True, "plot_id": plot_id, "response_source": "offline"})


@chat_router.post("/chat")
async def chat_endpoint(request: ChatRequest) -> StreamingResponse:
    """Chat endpoint strictly serving from pre-fetched Redis cache with SSE token streaming and multi-turn history."""
    plot_id = request.plot_id.strip() if request.plot_id else "1"
    user_query = request.message.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    mode = (request.response_mode or "normal").lower()
    if mode not in ("short", "normal", "detailed"):
        mode = "normal"

    return StreamingResponse(
        generate_chat_events(
            plot_id,
            user_query,
            request.history,
            language=request.language,
            session_id=request.session_id,
            response_mode=mode,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

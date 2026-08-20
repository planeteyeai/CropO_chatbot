"""Chat Endpoint (Plot-Scoped) with Multi-Turn Memory & Diagnostic Metrics.

Receives user queries alongside plot_id and conversation history, routes intent in <50ms,
builds context exclusively from Redis cache for that specific plot (ZERO external API calls),
and streams SSE response tokens.
"""

import json
import time
from typing import AsyncIterator, List, Literal
import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.config.settings import settings
from app.context.context_builder import build_context_for_plot
from app.llm.client import get_llm_client
from app.llm.prompts import SYSTEM_GROUNDING_PROMPT, build_user_prompt
from app.routing.intent_router import route_query

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


async def generate_chat_events(
    plot_id: str,
    user_message: str,
    history: List[ChatMessage] = [],
    language: str = "en",
) -> AsyncIterator[str]:
    """Execute online pipeline for a specific plot with multi-turn history and language support, stream SSE tokens."""
    t_start = time.perf_counter()

    # 1. Multi-turn Intent Detection Benchmark
    t_route_0 = time.perf_counter()
    
    # If the user asks a short follow-up (e.g. "is it good?", "why?", "how to fix it?"),
    # combine the latest user query from history to ensure accurate domain routing
    routing_query = user_message
    if len(user_message.split()) <= 4 and history:
        prev_user_queries = [h.content for h in history if h.role == "user"]
        if prev_user_queries:
            routing_query = f"{prev_user_queries[-1]} {user_message}"

    matched_domains = route_query(routing_query)
    t_route_sec = time.perf_counter() - t_route_0

    # 2. Redis Cache Context Benchmark (Zero External APIs)
    t_ctx_0 = time.perf_counter()
    context_text = await build_context_for_plot(plot_id, matched_domains)
    t_ctx_sec = time.perf_counter() - t_ctx_0

    # 3. Assemble Grounded Prompt with Target Language Directive
    user_prompt = build_user_prompt(user_message, context_text, language=language)

    # 4. LLM Multi-turn Streaming Benchmark
    llm_client = get_llm_client()
    provider_name = (
        f"Google Gemini ({settings.GEMINI_MODEL})"
        if settings.LLM_PROVIDER == "gemini"
        else settings.LLM_PROVIDER.upper()
    )

    history_dicts = [{"role": h.role, "content": h.content} for h in history]

    t_llm_0 = time.perf_counter()
    t_first_token: float | None = None
    token_count = 0

    try:
        async for token in llm_client.stream_chat(SYSTEM_GROUNDING_PROMPT, user_prompt, history=history_dicts):
            if t_first_token is None:
                t_first_token = time.perf_counter() - t_llm_0
            token_count += 1
            event_payload = {
                "token": token,
                "done": False,
            }
            yield f"data: {json.dumps(event_payload)}\n\n"

        t_llm_total = time.perf_counter() - t_llm_0
        t_total = time.perf_counter() - t_start

        # Print Terminal Diagnostic Summary Box
        ttft_str = f"{t_first_token:.3f}s" if t_first_token is not None else "N/A"
        summary_log = (
            f"\n"
            f"======================================================================\n"
            f"🌾 [CROPO CHAT PIPELINE EXECUTION METRICS]\n"
            f"----------------------------------------------------------------------\n"
            f"📌 Active Plot ID        : #{plot_id}\n"
            f"💬 User Query            : \"{user_message}\" (History Turns: {len(history)})\n"
            f"🎯 Detected Intent       : {matched_domains if matched_domains else ['all_plot_telemetry']}\n"
            f"⏱️  Intent Routing Time   : {t_route_sec:.4f}s ({t_route_sec * 1000:.2f} ms)\n"
            f"📦 Redis Cache Read Time : {t_ctx_sec:.4f}s ({t_ctx_sec * 1000:.2f} ms) [ZERO external APIs]\n"
            f"🤖 LLM Provider Backend  : {provider_name}\n"
            f"⚡ Time to 1st Token     : {ttft_str}\n"
            f"⏳ LLM Generation Time   : {t_llm_total:.3f}s ({token_count} chunks streamed)\n"
            f"🏁 TOTAL PIPELINE LATENCY: {t_total:.3f}s\n"
            f"======================================================================\n"
        )
        print(summary_log, flush=True)

        # Final completion event frame
        final_payload = {
            "token": "",
            "done": True,
            "plot_id": plot_id,
            "matched_domains": matched_domains,
        }
        yield f"data: {json.dumps(final_payload)}\n\n"

    except Exception as exc:
        t_total = time.perf_counter() - t_start
        logger.error("chat_streaming_error", plot_id=plot_id, error=str(exc))
        print(
            f"\n❌ [CHAT PIPELINE ERROR] Plot #{plot_id} - Error: {str(exc)} (Failed after {t_total:.3f}s)\n",
            flush=True,
        )
        error_payload = {
            "token": f"\n\n[Error generating response: {str(exc)}]",
            "done": True,
            "error": True,
        }
        yield f"data: {json.dumps(error_payload)}\n\n"


@chat_router.post("/chat")
async def chat_endpoint(request: ChatRequest) -> StreamingResponse:
    """Chat endpoint strictly serving from pre-fetched Redis cache with SSE token streaming and multi-turn history."""
    plot_id = request.plot_id.strip() if request.plot_id else "1"
    user_query = request.message.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    return StreamingResponse(
        generate_chat_events(plot_id, user_query, request.history, language=request.language),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

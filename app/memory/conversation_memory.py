"""Session conversation memory — latest 20 messages plus summary/state/facts.

Uses the existing Redis client and in-memory fallback. Never calls CropO APIs.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
from app.cache.cache_keys import (
    conversation_facts_key,
    conversation_messages_key,
    conversation_state_key,
    conversation_summary_key,
)
from app.cache.redis_client import redis_client
from app.config.settings import settings

logger = structlog.get_logger(__name__)

DEFAULT_STATE = {
    "active_topic": None,
    "active_intent": None,
    "last_recommendation": None,
    "last_plot_id": None,
    "unresolved_questions": [],
    "topics": [],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationMemory:
    """Per-session rolling memory stored as JSON envelopes."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._ttl = settings.CONVERSATION_TTL_SECONDS
        self._max = settings.CONVERSATION_MAX_MESSAGES

    async def get_messages(self) -> List[Dict[str, Any]]:
        raw = await redis_client.get_json(conversation_messages_key(self.session_id))
        if isinstance(raw, list):
            return [m for m in raw if isinstance(m, dict)]
        return []

    async def replace_messages(self, messages: List[Dict[str, Any]]) -> None:
        trimmed = messages[-self._max :]
        await redis_client.set_json(
            conversation_messages_key(self.session_id),
            trimmed,
            ttl_seconds=self._ttl,
        )

    async def append_message(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        messages = await self.get_messages()
        payload = dict(message)
        payload.setdefault("timestamp", _now_iso())
        messages.append(payload)
        trimmed = messages[-self._max :]
        await self.replace_messages(trimmed)
        return trimmed

    async def get_state(self) -> Dict[str, Any]:
        raw = await redis_client.get_json(conversation_state_key(self.session_id))
        if isinstance(raw, dict):
            merged = dict(DEFAULT_STATE)
            merged.update(raw)
            return merged
        return dict(DEFAULT_STATE)

    async def set_state(self, state: Dict[str, Any]) -> None:
        await redis_client.set_json(
            conversation_state_key(self.session_id),
            state,
            ttl_seconds=self._ttl,
        )

    async def get_summary(self) -> str:
        raw = await redis_client.get_json(conversation_summary_key(self.session_id))
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            return str(raw.get("text") or "")
        return ""

    async def set_summary(self, text: str) -> None:
        await redis_client.set_json(
            conversation_summary_key(self.session_id),
            {"text": text, "updated_at": _now_iso()},
            ttl_seconds=self._ttl,
        )

    async def get_facts(self) -> List[Dict[str, Any]]:
        raw = await redis_client.get_json(conversation_facts_key(self.session_id))
        if isinstance(raw, list):
            return [f for f in raw if isinstance(f, dict)]
        return []

    async def add_fact(self, fact: Dict[str, Any]) -> None:
        facts = await self.get_facts()
        facts.append({**fact, "timestamp": fact.get("timestamp") or _now_iso()})
        await redis_client.set_json(
            conversation_facts_key(self.session_id),
            facts[-12:],
            ttl_seconds=self._ttl,
        )


async def hydrate_from_client_history(
    memory: ConversationMemory,
    history: List[Dict[str, Any]],
    plot_id: str,
) -> None:
    """If the server has no messages yet, seed from the client-supplied history buffer."""
    existing = await memory.get_messages()
    if existing or not history:
        return
    seeded: List[Dict[str, Any]] = []
    for item in history:
        role = item.get("role") if isinstance(item, dict) else getattr(item, "role", None)
        content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
        if not content:
            continue
        seeded.append(
            {
                "role": "assistant" if role in ("assistant", "model", "bot") else "user",
                "content": str(content),
                "timestamp": _now_iso(),
                "plot_id": plot_id,
                "source": "client_history",
            }
        )
    if seeded:
        await memory.replace_messages(seeded)

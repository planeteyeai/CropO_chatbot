"""Active topic / recommendation state helpers."""

from typing import Any, Dict, List, Optional
from app.memory.conversation_memory import ConversationMemory


def derive_active_topic(topics: List[str], previous: Optional[str] = None) -> Optional[str]:
    if topics:
        return topics[0]
    return previous


async def update_topic_state(
    memory: ConversationMemory,
    *,
    plot_id: str,
    topics: List[str],
    intent: str,
    recommendation: Optional[str] = None,
    unresolved: Optional[str] = None,
) -> Dict[str, Any]:
    state = await memory.get_state()
    active = derive_active_topic(topics, state.get("active_topic"))
    if active:
        state["active_topic"] = active
    state["active_intent"] = intent
    state["last_plot_id"] = plot_id
    if topics:
        merged = list(dict.fromkeys(list(state.get("topics") or []) + topics))
        state["topics"] = merged[-8:]
    if recommendation:
        state["last_recommendation"] = recommendation
    pending = list(state.get("unresolved_questions") or [])
    if unresolved:
        pending.append(unresolved)
        state["unresolved_questions"] = pending[-5:]
    elif recommendation:
        state["unresolved_questions"] = []
    await memory.set_state(state)

    if len((await memory.get_messages()) or []) >= 6:
        rec = state.get("last_recommendation") or "none"
        topic = state.get("active_topic") or "general"
        await memory.set_summary(
            f"Active topic: {topic}. Last recommendation: {rec}. Plot: {plot_id}."
        )
    return state

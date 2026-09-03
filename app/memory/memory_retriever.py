"""Fast scoring retrieval over the last 20 conversation messages.

Default scoring is keyword/topic/plot/recency — no embeddings unless enabled.
"""

from typing import Any, Dict, List, Set
from app.config.settings import settings


def _tokens(text: str) -> Set[str]:
    return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(t) > 2}


def score_message(
    message: Dict[str, Any],
    *,
    topics: List[str],
    query: str,
    plot_id: str,
    active_topic: str | None,
    is_follow_up: bool,
    index_from_end: int,
) -> float:
    content = str(message.get("content") or "")
    msg_topics = [str(t).lower() for t in (message.get("topics") or [])]
    query_tokens = _tokens(query)
    content_tokens = _tokens(content)

    score = 0.0
    topic_set = {t.lower() for t in topics}
    if topic_set and topic_set.intersection(msg_topics):
        score += 4.0
    if query_tokens and content_tokens:
        overlap = query_tokens.intersection(content_tokens)
        score += min(3.0, 0.6 * len(overlap))
    if plot_id and str(message.get("plot_id") or "") == str(plot_id):
        score += 1.5
    # Recency: newest messages score higher
    score += max(0.0, 2.0 - (0.15 * index_from_end))
    if active_topic and (active_topic.lower() in msg_topics or active_topic.lower() in content.lower()):
        score += 2.0
    if is_follow_up and index_from_end <= 3:
        score += 1.5
    if message.get("recommendation"):
        score += 0.5
    return score


def retrieve_relevant_memories(
    messages: List[Dict[str, Any]],
    *,
    query: str,
    topics: List[str],
    plot_id: str,
    active_topic: str | None = None,
    is_follow_up: bool = False,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """Return top 3–6 relevant memories. Never dumps the full 20 by default."""
    if not messages:
        return []
    ranked = []
    total = len(messages)
    for idx, msg in enumerate(messages):
        index_from_end = total - 1 - idx
        ranked.append(
            (
                score_message(
                    msg,
                    topics=topics,
                    query=query,
                    plot_id=plot_id,
                    active_topic=active_topic,
                    is_follow_up=is_follow_up,
                    index_from_end=index_from_end,
                ),
                msg,
            )
        )
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = [msg for score, msg in ranked if score > 0][: max(3, min(limit, 6))]
    if not selected and messages:
        selected = messages[-3:]
    return selected


def retrieve_for_llm(*args, **kwargs) -> List[Dict[str, Any]]:
    """Alias kept for callers; embeddings remain opt-in via ENABLE_EMBEDDING_ROUTING."""
    _ = settings.ENABLE_EMBEDDING_ROUTING  # reserved; keyword scoring is the default fast path
    return retrieve_relevant_memories(*args, **kwargs)

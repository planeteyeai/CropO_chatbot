"""Keep LLM context small and prioritized."""

from typing import List, Tuple

MODE_LIMITS = {
    "short": 2200,
    "normal": 6500,
    "detailed": 9000,
}

# Lower number = higher priority (matches the prompt order)
SECTION_PRIORITY = {
    "system_note": 1,
    "resolved_question": 2,
    "knowledge": 3,
    "decision": 4,
    "farm_state": 5,
    "layers": 6,
    "memories": 7,
    "summary": 8,
    "secondary": 9,
}


def budget_chars(response_mode: str, intent: str) -> int:
    mode = (response_mode or "normal").lower()
    limit = MODE_LIMITS.get(mode, MODE_LIMITS["normal"])
    if intent in {"CURRENT_STATUS", "PLOT_INFO", "WEATHER"} and mode == "normal":
        return min(limit, 4500)
    if intent in {"WHY_DIAGNOSIS", "RECOMMENDATION", "TREND", "PEST", "NUTRIENT"}:
        return max(limit, MODE_LIMITS["normal"])
    if intent == "HARVEST" and mode == "normal":
        return min(limit, 3800)
    return limit


def assemble_sections(sections: List[Tuple[str, str]], max_chars: int) -> str:
    """Pack sections by priority until the character budget is exhausted."""
    ranked = sorted(sections, key=lambda item: SECTION_PRIORITY.get(item[0], 9))
    parts: List[str] = []
    used = 0
    for _name, text in ranked:
        block = (text or "").strip()
        if not block:
            continue
        if used + len(block) + 2 > max_chars:
            remaining = max_chars - used - 2
            if remaining < 80:
                break
            block = block[:remaining].rstrip() + "…"
        parts.append(block)
        used += len(block) + 2
        if used >= max_chars:
            break
    return "\n\n".join(parts)

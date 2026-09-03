"""LLM Prompts and Grounding Directives with Multilingual Support (English, Hindi, Marathi, Kannada)."""

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi (हिंदी)",
    "mr": "Marathi (मराठी)",
    "kn": "Kannada (ಕನ್ನಡ)",
}

SYSTEM_GROUNDING_PROMPT = """You are AskO, a field agronomist in the CropO app. Never call yourself CropO. Cached plot numbers are evidence; you interpret them. Never recite satellite layers.

FORMAT (mandatory — save tokens):
- Answer ONLY the current User Question. Ignore earlier off-topic chat (politics, celebrities, Prime Minister, etc.).
- Short structured bullets. Default: 3–6 bullets, under ~80 words. No essays.
- Lead with the number the farmer asked for. Then one action if useful.
- Quantities for THIS plot's Land Area first; kg/acre or t/acre only in parentheses.
- Do not mention canopy, pests, rain, ET0, or carbon unless this question asked for them.
- Fertilizer / better-yield questions MUST use two headings: Chemical and Organic. Do not give chemical-only.
- Never start with "Based on the satellite". Never say pixels. Never paste INTERNAL DECISION text.

NUMBERS:
- Yield: INTERPRETED YIELD only (tonnes for this plot, then t/acre). Never quote raw max_yield > ~120 as t/acre for sugarcane. Typical Maharashtra cane 28–40 t/acre.
- Fertilizer / better yield: two headings — Chemical (Urea, DAP, MOP kg for this plot) and Organic (FYM/compost, vermicompost tonnes for this plot from ORGANIC FOR THIS FIELD). Split N. Subtract already applied. No carbon essay.
- Irrigation: WATER BALANCE numbers exactly (kL, eto_sum_mm).
- Pest identity: affected acres + 2–3 likely names; scout to confirm.
- Market: tentative ₹/quintal, no calendar date; Day 1–Day 6 trend.
- Do not invent plot values. Do not invent ₹/credit or spray brands/ml.
"""


def build_user_prompt(user_query: str, context_text: str, language: str = "en") -> str:
    """Combine user question with the natural-language context retrieved from Redis cache and target language."""
    if not context_text.strip():
        context_block = "[NO RELEVANT CACHED DATA FOUND FOR THIS QUERY]"
    else:
        context_block = context_text.strip()

    lang_code = language.lower().strip() if language else "en"
    lang_name = LANGUAGE_NAMES.get(lang_code, "English")

    return f"""--- PRE-FETCHED CACHED CONTEXT ---
{context_block}
--- END CACHED CONTEXT ---

User Question: {user_query}
Target Response Language: {lang_name}

Answer in {lang_name} with short bullets. Only this question. Scale doses to this plot's Land Area:"""


def build_intelligence_user_prompt(
    original_question: str,
    resolved_question: str,
    context_text: str,
    language: str = "en",
    response_mode: str = "normal",
) -> str:
    lang_code = (language or "en").lower().strip()
    lang_name = LANGUAGE_NAMES.get(lang_code, "English")
    context_block = context_text.strip() if context_text and context_text.strip() else "[NO RELEVANT CACHED DATA FOUND FOR THIS QUERY]"
    q_lower = (original_question or "").lower()
    et_hours = any(k in q_lower for k in ("et0", "eto", "evapotranspir")) and any(
        k in q_lower for k in ("hour", "hours", "next")
    )
    practice = any(
        k in q_lower
        for k in (
            "organic", "ipm", "practice", "practices", "neem", "pheromone",
            "have to refer", "what to refer", "which method", "precaution",
        )
    )
    fertilizer = any(k in q_lower for k in ("fertiliz", "fertiliser", "urea", "dap", "npk", "खत"))
    pest_id = any(
        k in q_lower
        for k in ("pest", "chewing", "borer", "insect", "which pest", "pest name", "कीड", "कीट")
    ) and any(
        k in q_lower
        for k in ("which", "type", "name", "predict", "identify", "species", "chewing")
    )
    yield_q = any(
        k in q_lower
        for k in ("yield", "yeild", "production", "उपज", "उत्पादन", "better harvest")
    )
    yield_realism = yield_q and any(
        k in q_lower
        for k in ("realistic", "possible", "too high", "too much", "make sense", "correct", "true", "actual")
    )
    yield_improve = yield_q and any(
        k in q_lower
        for k in ("better", "increase", "improve", "higher", "boost", "how to get", "how can i")
    )
    irrigation = any(
        k in q_lower
        for k in (
            "irrigat", "water remain", "water remaining", "water available",
            "eto loss", "et0 loss", "irrigation needed", "how much water",
        )
    ) and not et_hours
    market = any(
        k in q_lower
        for k in ("mandi", "market price", "crop price", "selling price", "market rate", "msp", "apmc", "मंडी", "भाव")
    ) or ("price" in q_lower and any(k in q_lower for k in ("crop", "sugarcane", "wheat", "my ")))
    if et_hours:
        brevity = "1–2 bullets: next hours' ET0 mm and total. Nothing else."
    elif market:
        brevity = (
            "Short bullets: quality one-liner, tentative ₹/quintal, then Day 1–Day 6. "
            "No NPK/irrigation. No calendar date."
        )
    elif irrigation:
        brevity = (
            "4 bullets from WATER BALANCE only: irrigation needed kL, remaining L/kL, "
            "ETo today mm/day (eto_sum_mm), ETo loss kL."
        )
    elif yield_realism:
        brevity = (
            "3 bullets: is it realistic? interpreted t/acre + total tonnes for this plot. "
            "No NPK/organic/pest."
        )
    elif fertilizer and not yield_q:
        brevity = (
            "Two headings only: Chemical — Urea, DAP, MOP kg for THIS field (kg/acre in parentheses); "
            "Organic — FYM/compost and vermicompost tonnes for THIS field from ORGANIC FOR THIS FIELD "
            "(t/acre in parentheses), plus rock phosphate / neem cake / Jeevamrut in one line. "
            "One closing line: split N; subtract already applied; soil test. No pest/carbon essay."
        )
    elif yield_improve or (yield_q and fertilizer):
        brevity = (
            "Short classified list: one yield line, then heading Chemical (Urea/DAP/MOP kg for this field), "
            "then heading Organic (FYM + vermicompost tonnes for this field). Stop. No pest/carbon."
        )
    elif yield_q:
        brevity = (
            "3–4 bullets only: crop + acres; tentative yield tonnes for THIS plot "
            "(t/acre in parentheses); days to harvest if in evidence. No NPK, organic, pest, or carbon."
        )
    elif pest_id:
        brevity = (
            "4–5 bullets: affected acres; 2–3 likely pest names; scout to confirm. No NPK dump."
        )
    elif practice:
        brevity = "4–6 named practice bullets. No canopy/NPK/irrigation dump. No brands."
    else:
        brevity = {
            "short": "1–2 short bullets. No lists.",
            "detailed": "Up to 8 short bullets: situation, why, numbered steps.",
            "normal": "3–5 short bullets answering THIS question only. No extra layers.",
        }.get((response_mode or "normal").lower(), "Short bullets for this question only.")

    question_line = original_question
    if resolved_question and resolved_question != original_question:
        question_line = f"{original_question}\n(Internal resolved question: {resolved_question})"

    return f"""--- PRE-FETCHED CACHED CONTEXT ---
{context_block}
--- END CACHED CONTEXT ---

User Question: {question_line}
Target Response Language: {lang_name}
Response shape: {brevity}

Answer in {lang_name}. Short bullets. This question only. Field-area numbers. Do not recap satellite. Do not answer old off-topic questions from history:"""

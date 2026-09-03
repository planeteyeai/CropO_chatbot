"""Short farmer-facing replies when Gemini is unavailable or for Mock LLM."""

from typing import Any, Dict, List, Optional
from app.config.intelligence_rules import farmer_term
from app.knowledge.agriculture_knowledge import lookup_knowledge


def _lang(language: str) -> str:
    return language if language in ("en", "hi", "mr", "kn") else "en"


def render_farmer_response(
    *,
    language: str,
    intent: str,
    decision: Optional[Dict[str, Any]],
    confidence: str,
    farm_state: Dict[str, Any],
    anomalies: List[Any],
    conflicts: List[Any],
    freshness: Dict[str, str],
    missing: List[str],
) -> str:
    """One-sentence answer grounded in intelligence output."""
    lang = _lang(language)
    soil = farm_state.get("soil") or {}
    health = farm_state.get("field_health") or {}
    identity = farm_state.get("identity") or {}
    dec = (decision or {}).get("decision")
    moisture = soil.get("latest_moisture_pct")
    moisture_status = soil.get("moisture_status")
    score = health.get("field_score_pct")
    crop = (identity.get("crop_details") or {}).get("crop_type")
    weather = (farm_state.get("weather") or {}).get("current") or {}
    temp = weather.get("temperature_celsius")
    rain_prob = weather.get("rainfall_probability_pct")
    rain_status = weather.get("rain_status")
    soil_term = farmer_term("soil_moisture", lang)

    action_intents = {"RECOMMENDATION", "IRRIGATION", "PEST", "NUTRIENT"}
    if intent in {"WEATHER", "FORECAST"}:
        return _one_sentence_weather(lang, temp, rain_prob, rain_status)
    if dec and intent in action_intents:
        return _one_sentence_action(lang, dec, moisture, moisture_status, soil_term)
    if intent == "WHY_DIAGNOSIS":
        return _one_sentence_why(lang, moisture, moisture_status, soil_term)
    return _one_sentence_status(lang, crop, moisture, moisture_status, score, soil_term)


def _one_sentence_weather(lang, temp, rain_prob, rain_status):
    t = f"{temp}°C" if temp is not None else "n/a"
    r = f"{rain_prob}%" if rain_prob is not None else "n/a"
    rs = rain_status or ""
    if lang == "hi":
        return f"आज तापमान {t} है और बारिश की संभावना {r} है।"
    if lang == "mr":
        return f"आज तापमान {t} आहे आणि पावसाची शक्यता {r} आहे."
    if lang == "kn":
        return f"ಇಂದು ತಾಪಮಾನ {t} ಮತ್ತು ಮಳೆ ಸಾಧ್ಯತೆ {r}."
    extra = f" ({rs})" if rs else ""
    return f"Today is {t} with a {r} chance of rain{extra}."


def _one_sentence_action(lang, dec, moisture, moisture_status, soil_term):
    m = f"{moisture}%" if moisture is not None else None
    status = moisture_status or ""
    hold_water = dec in {"MONITOR", "WAIT_FOR_RAIN"}
    if lang == "hi":
        action = "अभी सिंचाई न करें" if hold_water else "अभी सिंचाई करें" if dec == "IRRIGATE_NOW" else "हल्की सिंचाई करें" if dec == "IRRIGATE_LIGHTLY" else "खेत की जाँच करें"
        return f"{action} — {soil_term} {m} ({status}) है।" if m else f"{action}।"
    if lang == "mr":
        action = "आता पाणी देऊ नका" if hold_water else "आता सिंचन करा" if dec == "IRRIGATE_NOW" else "हलके सिंचन करा" if dec == "IRRIGATE_LIGHTLY" else "शेत तपासा"
        return f"{action} — {soil_term} {m} ({status}) आहे." if m else f"{action}."
    if lang == "kn":
        action = "ಈಗ ನೀರು ಕೊಡಬೇಡಿ" if hold_water else "ಈಗ ನೀರಾವರಿ ಮಾಡಿ" if dec == "IRRIGATE_NOW" else "ಹಗುರ ನೀರಾವರಿ ಮಾಡಿ" if dec == "IRRIGATE_LIGHTLY" else "ಜಮೀನು ಪರಿಶೀಲಿಸಿ"
        return f"{action} — {soil_term} {m} ({status})." if m else f"{action}."
    action = "Don't irrigate now" if hold_water else "Irrigate now" if dec == "IRRIGATE_NOW" else "Give a light irrigation" if dec == "IRRIGATE_LIGHTLY" else "Inspect the field"
    return f"{action} — {soil_term} is {m} ({status})." if m else f"{action}."


def _one_sentence_status(lang, crop, moisture, moisture_status, score, soil_term):
    m = f"{moisture}%" if moisture is not None else "n/a"
    if lang == "hi":
        return f"{soil_term} {m} ({moisture_status or 'n/a'}) है।"
    if lang == "mr":
        return f"{soil_term} {m} ({moisture_status or 'n/a'}) आहे."
    if lang == "kn":
        return f"{soil_term} {m} ({moisture_status or 'n/a'})."
    prefix = f"{crop}: " if crop else ""
    extra = f", field score {score}%" if score is not None else ""
    return f"{prefix}{soil_term} is {m} ({moisture_status or 'n/a'}){extra}."


def _one_sentence_why(lang, moisture, moisture_status, soil_term):
    m = f"{moisture}%" if moisture is not None else "n/a"
    if lang == "hi":
        return f"क्योंकि {soil_term} {m} ({moisture_status or 'n/a'}) है।"
    if lang == "mr":
        return f"कारण {soil_term} {m} ({moisture_status or 'n/a'}) आहे."
    if lang == "kn":
        return f"ಕಾರಣ {soil_term} {m} ({moisture_status or 'n/a'})."
    return f"Because {soil_term} is {m} ({moisture_status or 'n/a'})."


def farmer_ack_greeting(language: str = "en", plot_id: str = "") -> str:
    """Short close + greeting after the farmer says okay / thanks."""
    lang = _lang(language)
    pid = (plot_id or "").strip()
    if lang == "hi":
        where = f"प्लॉट {pid} के बारे में" if pid else "आपकी फसल के बारे में"
        return f"नमस्ते। {where} और कुछ पूछना हो तो बताइए।"
    if lang == "mr":
        where = f"प्लॉट {pid} बद्दल" if pid else "तुमच्या पिकाबद्दल"
        return f"नमस्कार. {where} आणखी काही विचारायचे असेल तर सांगा."
    if lang == "kn":
        where = f"ಪ್ಲಾಟ್ {pid} ಬಗ್ಗೆ" if pid else "ನಿಮ್ಮ ಬೆಳೆ ಬಗ್ಗೆ"
        return f"ನಮಸ್ಕಾರ. {where} ಇನ್ನೇನಾದರೂ ಕೇಳಬೇಕಾದರೆ ಹೇಳಿ."
    where = f"plot {pid}" if pid else "your crop"
    return f"Hello. I'm here if you need anything else about {where}."

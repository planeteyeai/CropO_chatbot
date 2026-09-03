"""LLM Client Layer (Google Gemini & Mock Fallback) with Multi-Turn Conversation Support.

Provides streaming token generation using:
- GeminiLLMClient: Multi-turn SSE streaming from Google Gemini official REST endpoint.
- MockLLMClient: Deterministic grounded simulator used for automated tests and offline fallback.
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx
import structlog
from dotenv import dotenv_values
from app.config.settings import Settings, settings

logger = structlog.get_logger(__name__)

INVALID_GEMINI_KEYS = {"", "your_gemini_api_key_here", "changeme", "xxx", "replace_me"}

_gemini_key_working: Optional[bool] = None
_gemini_verify_message: str = ""
_active_gemini_client: Optional["GeminiLLMClient"] = None


def set_active_gemini_client(client: Optional["GeminiLLMClient"]) -> None:
    """Pin the Gemini client that passed startup verification for all chat requests."""
    global _active_gemini_client
    _active_gemini_client = client


def _is_placeholder_gemini_key(key: str) -> bool:
    """True when the key is empty or an obvious placeholder."""
    cleaned = (key or "").strip()
    return not cleaned or cleaned.lower() in INVALID_GEMINI_KEYS


def _resolve_gemini_api_key(cfg: Settings) -> str:
    """Resolve Gemini key from project .env, OS env, or parent workspace .env."""
    candidates: List[str] = [
        (cfg.GEMINI_API_KEY or "").strip(),
        (os.environ.get("GEMINI_API_KEY") or "").strip(),
    ]

    parent_env = Path(__file__).resolve().parents[3] / ".env"
    if parent_env.exists():
        parent_key = (dotenv_values(parent_env).get("GEMINI_API_KEY") or "").strip()
        candidates.append(parent_key)

    for key in candidates:
        if not _is_placeholder_gemini_key(key):
            return key
    return ""


def set_gemini_verification_result(working: bool, message: str) -> None:
    """Cache the result of a live Gemini API key probe."""
    global _gemini_key_working, _gemini_verify_message
    _gemini_key_working = working
    _gemini_verify_message = message


def get_gemini_verification_status() -> tuple[Optional[bool], str]:
    """Return cached probe result: (working | None if not probed yet, message)."""
    return _gemini_key_working, _gemini_verify_message


async def verify_gemini_api_key(
    api_key: str,
    model: str = "gemini-2.5-flash",
) -> tuple[bool, str]:
    """Verify a Gemini key by sending a minimal live API request."""
    if _is_placeholder_gemini_key(api_key):
        return False, "No API key set"

    clean_model = (model or "gemini-2.5-flash").replace("models/", "")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{clean_model}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {"parts": [{"text": "Hi, are you working? Reply with one short sentence."}]}
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                try:
                    err = response.json().get("error", {}).get("message", response.text[:200])
                except Exception:
                    err = response.text[:200]
                return False, err or f"HTTP {response.status_code}"

            data = response.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            if (text or "").strip():
                return True, "Gemini responded OK"
            return False, "Empty response from Gemini"
    except Exception as exc:
        logger.error("gemini_key_probe_failed", error=str(exc))
        return False, str(exc)


async def init_gemini_verification(cfg: Optional[Settings] = None) -> tuple[bool, str]:
    """Probe Gemini once at startup and cache whether the configured key works."""
    cfg = cfg or settings
    if cfg.LLM_PROVIDER.lower() != "gemini":
        set_gemini_verification_result(True, "LLM provider is not gemini")
        return True, "LLM provider is not gemini"

    api_key = _resolve_gemini_api_key(cfg)
    if not api_key:
        set_gemini_verification_result(False, "GEMINI_API_KEY is missing or a placeholder")
        return False, "GEMINI_API_KEY is missing or a placeholder"

    ok, msg = await verify_gemini_api_key(api_key, cfg.GEMINI_MODEL or "gemini-2.5-flash")
    set_gemini_verification_result(ok, msg)
    if ok:
        set_active_gemini_client(
            GeminiLLMClient(
                api_key=api_key,
                model=cfg.GEMINI_MODEL or "gemini-2.5-flash",
            )
        )
        logger.info("gemini_key_verified", detail=msg)
    else:
        set_active_gemini_client(None)
        logger.warning("gemini_key_verification_failed", detail=msg)
    return ok, msg


GEMINI_KEY_HELP = (
    "**Gemini is not connected** — chat cannot use the LLM until you fix `GEMINI_API_KEY`.\n\n"
    "The server tested your key with a live Gemini request and it did not work.\n\n"
    "**Fix:**\n"
    "1. Get a key from https://aistudio.google.com/apikey\n"
    "2. In `CropO_chatbot/.env` set `GEMINI_API_KEY=your_key`\n"
    "3. Restart the server (or call `GET /debug/gemini-key` to re-test)\n\n"
    "After that, Gemini will answer using your live plot data."
)


def _extract_cached_context(user_prompt: str) -> str:
    """Pull the Redis context block injected into the user prompt."""
    lower = user_prompt.lower()
    start_marker = "--- pre-fetched cached context ---"
    end_marker = "--- end cached context ---"
    if start_marker not in lower:
        return ""
    start = lower.index(start_marker) + len(start_marker)
    end = lower.index(end_marker) if end_marker in lower else len(user_prompt)
    return user_prompt[start:end].strip()


def _parse_farm_intelligence_marker(user_prompt: str) -> Optional[Dict[str, str]]:
    start = user_prompt.find("--- FARM INTELLIGENCE ---")
    end = user_prompt.find("--- END FARM INTELLIGENCE ---")
    if start < 0 or end < 0:
        return None
    block = user_prompt[start:end]
    parsed: Dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed or None


def _mock_from_intelligence(user_prompt: str, language: str) -> Optional[str]:
    marker = _parse_farm_intelligence_marker(user_prompt)
    if not marker:
        return None
    from app.knowledge.offline_responder import render_farmer_response

    def _maybe_float(raw: str):
        try:
            if raw in {"", "None", "n/a"}:
                return None
            return float(raw)
        except (TypeError, ValueError):
            return None

    farm_state = {
        "identity": {"crop_details": {"crop_type": marker.get("crop")}},
        "soil": {
            "latest_moisture_pct": _maybe_float(marker.get("moisture_pct", "")),
            "moisture_status": marker.get("moisture_status") or None,
        },
        "weather": {
            "current": {
                "rainfall_probability_pct": _maybe_float(marker.get("rain_prob", "")),
                "temperature_celsius": _maybe_float(marker.get("temp_c", "")),
            }
        },
        "field_health": {"field_score_pct": _maybe_float(marker.get("field_score", ""))},
        "missing_data": [p for p in (marker.get("missing") or "").split(",") if p.strip()],
    }
    missing = [p.strip() for p in (marker.get("missing") or "").split(",") if p.strip()]
    topics = [t.strip() for t in (marker.get("topics") or "").split(",") if t.strip()]
    return render_farmer_response(
        language=language,
        intent=marker.get("intent") or "CURRENT_STATUS",
        decision={
            "decision": marker.get("decision") or None,
            "evidence": [],
            "risks": [],
            "next_action": marker.get("next_action") or "",
        },
        confidence=marker.get("confidence") or "MEDIUM",
        farm_state=farm_state,
        anomalies=[],
        conflicts=[],
        freshness={},
        missing=missing,
    )



def _build_mock_response_from_context(user_prompt: str, question_lower: str) -> Optional[str]:
    """Answer from cached telemetry instead of hardcoded mock templates."""
    context = _extract_cached_context(user_prompt)
    if not context:
        return None

    ctx_lower = context.lower()
    if "[no pre-fetched cached telemetry found" in ctx_lower or "[no relevant cached data found" in ctx_lower:
        return None

    layer_query = any(
        k in question_lower
        for k in [
            "layer", "layers", "satellite", "npk", "pest", "water uptake",
            "daily report", "8 layer", "pixel", "biomass", "growth stage",
        ]
    )

    if layer_query and ("layer 1" in ctx_lower or "8 satellite" in ctx_lower):
        lines: List[str] = []
        capture = False
        for line in context.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if "daily report" in stripped.lower() and "layer" in stripped.lower():
                capture = True
            if capture:
                lines.append(stripped)
        if lines:
            return (
                "**8 Satellite Intelligence Layers (read directly from pre-fetched Redis cache):**\n\n"
                + "\n".join(lines)
            )

    # For any other query, summarize matching telemetry lines from cache
    if "comprehensive telemetry feed" in ctx_lower or "--- end plot telemetry ---" in ctx_lower:
        relevant: List[str] = []
        for line in context.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("---"):
                continue
            line_lower = stripped.lower()
            if any(k in question_lower for k in line_lower.split()) or any(
                k in line_lower for k in ["moisture", "score", "weather", "crop", "plot", "ndvi", "layer"]
            ):
                relevant.append(stripped)
        if relevant:
            return (
                "**Answer from pre-fetched CropO cache (not LLM-generated):**\n\n"
                + "\n".join(relevant[:25])
            )

    return None


class BaseLLMClient(ABC):
    """Abstract Base Class for LLM providers."""

    @abstractmethod
    async def stream_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        max_output_tokens: int = 120,
        enable_google_search: bool = False,
    ) -> AsyncIterator[str]:
        """Stream tokens asynchronously one by one."""
        pass


class GeminiLLMClient(BaseLLMClient):
    """Google Gemini streaming client with multi-turn conversation support."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        clean_model = model.replace("models/", "")
        self.model = clean_model

    async def stream_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        max_output_tokens: int = 120,
        enable_google_search: bool = False,
    ) -> AsyncIterator[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:streamGenerateContent?key={self.api_key}&alt=sse"
        headers = {"Content-Type": "application/json"}

        # Construct multi-turn contents array
        contents: List[Dict[str, Any]] = []

        # 1. Add previous conversation turns (sliding window of last 6 turns)
        if history:
            for msg in history[-6:]:
                role = "model" if msg.get("role") in ["assistant", "model", "bot"] else "user"
                content_text = msg.get("content", "").strip()
                if content_text:
                    contents.append({
                        "role": role,
                        "parts": [{"text": content_text}],
                    })

        # 2. Add current turn with grounded context snippet
        contents.append({
            "role": "user",
            "parts": [{"text": user_prompt}],
        })

        payload: Dict[str, Any] = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.55,
                "maxOutputTokens": max(128, int(max_output_tokens or 400)),
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        if enable_google_search:
            payload["tools"] = [{"google_search": {}}]

        timeout = 70.0 if enable_google_search else 45.0
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200 and enable_google_search:
                        error_body = await response.aread()
                        logger.warning(
                            "gemini_google_search_unavailable_retrying_without_tool",
                            status_code=response.status_code,
                            error=error_body.decode("utf-8", errors="ignore")[:300],
                        )
                        payload.pop("tools", None)
                        async with client.stream("POST", url, headers=headers, json=payload) as retry:
                            async for token in self._iter_sse_tokens(retry):
                                yield token
                        return
                    if response.status_code != 200:
                        error_body = await response.aread()
                        error_text = error_body.decode("utf-8", errors="ignore")
                        logger.error(
                            "gemini_api_error",
                            status_code=response.status_code,
                            error=error_text,
                        )
                        if response.status_code in (400, 401, 403):
                            set_gemini_verification_result(False, error_text[:200])
                            yield (
                                "**Gemini API key error.** Your `GEMINI_API_KEY` in `CropO_chatbot/.env` "
                                "was rejected by Google.\n\n"
                                "1. Get a key from https://aistudio.google.com/apikey\n"
                                "2. Put it in `CropO_chatbot/.env` as `GEMINI_API_KEY=your_key`\n"
                                "3. Restart the server or call `GET /debug/gemini-key` to re-test"
                            )
                            return
                        async for token in MockLLMClient(mode="gemini_unavailable").stream_chat(
                            system_prompt, user_prompt, history
                        ):
                            yield token
                        return

                    async for token in self._iter_sse_tokens(response):
                        yield token
        except Exception as exc:
            logger.error("gemini_streaming_failed_fallback", error=str(exc))
            async for token in MockLLMClient(mode="gemini_unavailable").stream_chat(
                system_prompt, user_prompt, history
            ):
                yield token

    async def _iter_sse_tokens(self, response: httpx.Response) -> AsyncIterator[str]:
        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            try:
                chunk = json.loads(data_str)
                candidates = chunk.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for p in parts:
                        text = p.get("text", "")
                        if text:
                            yield text
            except Exception:
                continue


class MockLLMClient(BaseLLMClient):
    """Offline mock LLM for tests, or fallback when Gemini is unavailable."""

    def __init__(self, mode: str = "offline"):
        # offline = test/demo templates; gemini_unavailable = show key setup help only
        self.mode = mode

    async def stream_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        max_output_tokens: int = 120,
        enable_google_search: bool = False,
    ) -> AsyncIterator[str]:
        if self.mode == "gemini_unavailable":
            lang = "en"
            pl = user_prompt.lower()
            if "marathi" in pl or "मराठी" in user_prompt:
                lang = "mr"
            elif "hindi" in pl or "हिंदी" in user_prompt:
                lang = "hi"
            elif "kannada" in pl or "ಕನ್ನಡ" in user_prompt:
                lang = "kn"
            intel_text = _mock_from_intelligence(user_prompt, lang)
            if intel_text:
                words = intel_text.split(" ")
                for i, word in enumerate(words):
                    yield word if i == len(words) - 1 else word + " "
                    await asyncio.sleep(0.01)
                return
            words = GEMINI_KEY_HELP.split(" ")
            for i, word in enumerate(words):
                yield word if i == len(words) - 1 else word + " "
                await asyncio.sleep(0.01)
            return

        prompt_lower = user_prompt.lower()
        # Combine history queries if follow-up
        if history:
            for h in history:
                prompt_lower += " " + h.get("content", "").lower()

        is_marathi = "marathi" in prompt_lower or "मराठी" in prompt_lower
        is_hindi = "hindi" in prompt_lower or "हिंदी" in prompt_lower
        is_kannada = "kannada" in prompt_lower or "ಕನ್ನಡ" in prompt_lower
        lang = "mr" if is_marathi else "hi" if is_hindi else "kn" if is_kannada else "en"

        intel_text = _mock_from_intelligence(user_prompt, lang)
        if intel_text:
            words = intel_text.split(" ")
            for i, word in enumerate(words):
                token = word if i == len(words) - 1 else word + " "
                yield token
                await asyncio.sleep(0.015)
            return

        if "user question:" in prompt_lower:
            question_lower = prompt_lower.split("user question:")[-1].split("answer strictly")[0].strip()
        else:
            question_lower = prompt_lower

        context_response = _build_mock_response_from_context(user_prompt, question_lower)
        if context_response:
            words = context_response.split(" ")
            for i, word in enumerate(words):
                token = word if i == len(words) - 1 else word + " "
                yield token
                await asyncio.sleep(0.015)
            return

        is_marathi = "marathi" in prompt_lower or "मराठी" in prompt_lower
        is_hindi = "hindi" in prompt_lower or "हिंदी" in prompt_lower
        is_kannada = "kannada" in prompt_lower or "ಕನ್ನಡ" in prompt_lower

        if "[no pre-fetched cached telemetry found" in prompt_lower or "[no relevant cached data found" in prompt_lower:
            if is_marathi:
                response_text = "माझ्याकडे सध्याच्या प्री-फेच केलेल्या कॅशमध्ये या विषयाची माहिती उपलब्ध नाही. मी फक्त सक्रिय फार्म डेटा (प्लॉट तपशील, हवामान, जमिनीतील ओलावा, आणि पीक आरोग्य स्कोअर) वरूनच उत्तर देऊ शकतो."
            elif is_hindi:
                response_text = "मेरे पास वर्तमान प्री-फेच किए गए कैश में इस विषय की जानकारी उपलब्ध नहीं है। मैं केवल हमारे सक्रिय फार्म डेटा (जैसे प्लॉट विवरण, मौसम, मिट्टी की नमी और फसल स्वास्थ्य स्कोर) के आधार पर ही उत्तर दे सकता हूँ।"
            elif is_kannada:
                response_text = "ನನ್ನ ಬಳಿ ಪ್ರಸ್ತುತ ಸಂಗ್ರಹಿಸಲಾದ ಡೇಟಾದಲ್ಲಿ ಈ ವಿಷಯದ ಬಗ್ಗೆ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ. ನಾನು ಕೇವಲ ನಮ್ಮ ಜಮೀನಿನ ಸಕ್ರಿಯ ಡೇಟಾ (ಪ್ಲಾಟ್ ವಿವರ, ಹವಾಮಾನ, ಮಣ್ಣಿನ ತೇವಾಂಶ ಮತ್ತು ಬೆಳೆ ಆರೋಗ್ಯ ಸ್ಕೋರ್) ಆಧಾರದ ಮೇಲೆ ಮಾತ್ರ ಉತ್ತರಿಸಬಲ್ಲೆ."
            else:
                response_text = (
                    "I do not have information about that topic in my current pre-fetched cache. "
                    "I am strictly configured to answer only from our active farm data feeds (such as Plots Metadata, Farm Weather, Soil Moisture, and Field Health Scores)."
                )
        elif any(k in question_lower for k in ["moisture", "soil", "water", "irrigation", "irrigate", "drip", "is it good", "ओलावा", "नमी", "पाणी", "तೇವಾಂಶ", "ನೀರಾವರಿ"]):
            if is_marathi:
                response_text = (
                    "**जमिनीतील ओलावा आणि सिंचन व्यवस्थापन सल्ला:**\n\n"
                    "- **मुळांच्या भागातील ओलावा:** 81.37% (जास्त / संतृप्त)\n"
                    "- **कृषी मूल्यांकन:** नुकत्याच झालेल्या पावसामुळे (1.4 मिमी) जमिनीतील ओलावा प्रमाणापेक्षा जास्त आहे. जास्त ओलाव्यामुळे मुळांना हवा मिळण्यात अडथळा येऊ शकतो.\n"
                    "- **सल्ला:** जोपर्यंत ओलावा 55% ते 70% च्या योग्य पातळीवर येत नाही, तोपर्यंत ठिबक सिंचन थांबवावे."
                )
            elif is_hindi:
                response_text = (
                    "**मिट्टी की नमी और सिंचाई प्रबंधन सलाह:**\n\n"
                    "- **रूट-ज़ोन मिट्टी की नमी:** 81.37% (उच्च / संतृप्त)\n"
                    "- **कृषि मूल्यांकन:** हाल ही में हुई बारिश (1.4 मिमी) के कारण मिट्टी में नमी पर्याप्त से अधिक है। अत्यधिक नमी से जड़ों में फंगल समस्या हो सकती है।\n"
                    "- **सलाह:** जब तक नमी का स्तर 55% - 70% के इष्टतम स्तर पर न आ जाए, तब तक ड्रिप सिंचाई रोक कर रखें।"
                )
            elif is_kannada:
                response_text = (
                    "**ಮಣ್ಣಿನ ತೇವಾಂಶ ಮತ್ತು ನೀರಾವರಿ ನಿರ್ವಹಣಾ ಸಲಹೆ:**\n\n"
                    "- **ಮಣ್ಣಿನ ತೇವಾಂಶ ಮಟ್ಟ:** 81.37% (ಹೆಚ್ಚು / ಸ್ಯಾಚುರೇಟೆಡ್)\n"
                    "- **ಕೃಷಿ ಮೌಲ್ಯಮಾಪನ:** ಇತ್ತೀಚಿನ ಮಳೆಯಿಂದಾಗಿ (1.4 ಮಿಮೀ) ಮಣ್ಣಿನಲ್ಲಿ ಸಾಕಷ್ಟು ತೇವಾಂಶವಿದೆ. ಅತಿಯಾದ ತೇವಾಂಶವು ಬೇರುಗಳಿಗೆ ಗಾಳಿಯಾಡದಂತೆ ಮಾಡಬಹುದು.\n"
                    "- **ಸಲಹೆ:** ತೇವಾಂಶವು 55% - 70% ವ್ಯಾಪ್ತಿಗೆ ಬರುವವರೆಗೆ ಹನಿ ನೀರಾವರಿಯನ್ನು ನಿಲ್ಲಿಸಿ."
                )
            else:
                response_text = (
                    "**Soil Moisture & Irrigation Assessment:**\n\n"
                    "- **Root-zone Soil Moisture:** 81.37% (Saturated / High Hydration)\n"
                    "- **Agronomic Evaluation:** This is well above standard field capacity due to recent rainfall (1.4 mm - 2.1 mm). While soil hydration is adequate, prolonged saturation risks poor root aeration.\n"
                    "- **Actionable Advisory:** Defer active drip irrigation until moisture levels recede into the 55% - 70% optimal band."
                )
        elif any(k in question_lower for k in ["score", "health", "ndvi", "vigor", "remote sensing", "आरोग्य", "स्वास्थ्य", "ಸ್ಕೋರ್", "ಆರೋಗ್ಯ"]):
            if is_marathi:
                response_text = (
                    "**सॅटेलाइट रिमोट सेन्सिंग व पीक आरोग्य स्कोअर:**\n\n"
                    "- **प्लॉट पीक आरोग्य स्कोअर:** 100.0% (उत्कृष्ट जोम / Peak Vigor)\n"
                    "- **कॅनोपी स्थिती:** उत्तम प्रकाशसंश्लेषण क्रिया आणि पिकावर कोणताही तणाव आढळलेला नाही."
                )
            elif is_hindi:
                response_text = (
                    "**सैटेलाइट रिमोट सेंसिंग और फसल स्वास्थ्य स्कोर:**\n\n"
                    "- **प्लॉट फसल स्वास्थ्य स्कोर:** 100.0% (उत्कृष्ट / Peak Vigor)\n"
                    "- **कैनोपी स्थिति:** उच्च प्रकाश संश्लेषण और कोई तनाव नहीं देखा गया है।"
                )
            elif is_kannada:
                response_text = (
                    "**ಉಪಗ್ರಹ ರಿಮೋಟ್ ಸೆನ್ಸಿಂಗ್ ಮತ್ತು ಬೆಳೆ ಆರೋಗ್ಯ ಸ್ಕೋರ್:**\n\n"
                    "- **ಪ್ಲಾಟ್ ಆರೋಗ್ಯ ಸ್ಕೋರ್:** 100.0% (ಅತ್ಯುತ್ತಮ / Peak Vigor)\n"
                    "- **ಬೆಳೆಯ ಸ್ಥಿತಿ:** ಅತ್ಯುತ್ತಮ ದ್ಯುತಿಸಂಶ್ಲೇಷಣೆ ಮತ್ತು ಯಾವುದೇ ಒತ್ತಡವಿಲ್ಲ."
                )
            else:
                response_text = (
                    "**Field Health & Remote Sensing Scores:**\n\n"
                    "- **Plot Field Health Score:** 100.0% (Peak Vigor)\n"
                    "- **Canopy Status:** Dense vegetative index with optimal chlorophyll absorption and zero detected stress."
                )
        elif any(k in question_lower for k in ["weather", "temp", "temperature", "rain", "rainfall", "forecast", "climate", "हवामान", "तापमान", "हವಾಮಾನ", "ತಾಪಮಾನ"]):
            if is_marathi:
                response_text = (
                    "**थेट शेताचे हवामान आणि अंदाज:**\n\n"
                    "- **सध्याचे तापमान:** 24.5°C (दिवसाचे तापमान: 22.8°C - 27.4°C)\n"
                    "- **पावसाची शक्यता:** ~45% (हलक्या पावसाचा अंदाज)\n"
                    "- **पुढील अंदाज:** तापमान 23.8°C - 24.6°C दरम्यान स्थिर राहील."
                )
            elif is_hindi:
                response_text = (
                    "**खेत का मौसम और वर्षा पूर्वानुमान:**\n\n"
                    "- **वर्तमान तापमान:** 24.5°C (दिन का तापमान: 22.8°C - 27.4°C)\n"
                    "- **बारिश की संभावना:** ~45% (हल्की बारिश का अनुमान)\n"
                    "- **पूर्वानुमान:** तापमान 23.8°C - 24.6°C के बीच रहेगा।"
                )
            elif is_kannada:
                response_text = (
                    "**ಜಮೀನಿನ ನೇರ ಹವಾಮಾನ ಮತ್ತು ಮಳೆಯ ಮುನ್ಸೂಚನೆ:**\n\n"
                    "- **ಪ್ರಸ್ತುತ ತಾಪಮಾನ:** 24.5°C (ದಿನದ ಶ್ರೇಣಿ: 22.8°C - 27.4°C)\n"
                    "- **ಮಳೆಯ ಸಂಭವನೀಯತೆ:** ~45% (ಸ್ವಲ್ಪ ಮಳೆಯ ನಿರೀಕ್ಷೆ)\n"
                    "- **ಮುನ್ಸೂಚನೆ:** ತಾಪಮಾನವು 23.8°C - 24.6°C ನಡುವೆ ಸ್ಥಿರವಾಗಿರುತ್ತದೆ."
                )
            else:
                response_text = (
                    "**Live Farm Weather & Atmospheric Telemetry:**\n\n"
                    "- **Current Temperature:** 24.5°C (Day Range: 22.8°C - 27.4°C)\n"
                    "- **Precipitation Probability:** ~45% (Rain Status: Light showers / Rain expected)\n"
                    "- **Outlook:** Stable temperatures around 23.8°C - 24.6°C."
                )
        elif any(k in question_lower for k in ["plot", "mango", "grape", "tomato", "acres", "variety", "crop", "पीक", "फसल", "ಬೆಳೆ", "ಆಂಬಾ"]):
            if is_marathi:
                response_text = (
                    "**शेताचा प्लॉट तपशील आणि पीक माहिती:**\n\n"
                    "- **पीक प्रकार:** आंबा (अल्फा व्हरायटी)\n"
                    "- **क्षेत्रफळ:** 0.94 एकर | सिंचन: ठिबक सिंचन\n"
                    "- **लागवड तारीख:** 2 जून 2026"
                )
            elif is_hindi:
                response_text = (
                    "**खेत का प्लॉट विवरण और फसल जानकारी:**\n\n"
                    "- **फसल:** आम (अल्फा किस्म)\n"
                    "- **क्षेत्रफल:** 0.94 एकड़ | सिंचाई: ड्रिप सिंचाई\n"
                    "- **बुवाई की तारीख:** 2 जून 2026"
                )
            elif is_kannada:
                response_text = (
                    "**ಪ್ಲಾಟ್ ವಿವರ ಮತ್ತು ಬೆಳೆ ಮಾಹಿತಿ:**\n\n"
                    "- **ಬೆಳೆ:** ಮಾವು (ಆಲ್ಫಾ ತಳಿ)\n"
                    "- **ವಿಸ್ತೀರ್ಣ:** 0.94 ಎಕರೆ | ನೀರಾವರಿ: ಹನಿ ನೀರಾವರಿ\n"
                    "- **ನಾಟಿ ದಿನಾಂಕ:** 2 ಜೂನ್ 2026"
                )
            else:
                response_text = (
                    "**Farm Plot Profile & Crop Telemetry:**\n\n"
                    "- **Cultivation:** Mango (Alpha variety)\n"
                    "- **Area:** 0.94 acres | Irrigation: Drip Irrigation\n"
                    "- **Plantation Date:** June 2, 2026"
                )
        else:
            if is_marathi:
                response_text = (
                    "प्री-फेच केलेल्या **CropO हॉट कॅश** वरून माहिती:\n\n"
                    "- **सक्रिय प्लॉट:** आंबा अल्फा (0.94 एकर)\n"
                    "- **जमिनीतील ओलावा:** 81.37% (संतृप्त)\n"
                    "- **आरोग्य स्कोअर:** 100.0% (उत्कृष्ट जोम)\n"
                    "- **हवामान:** 24.5°C आणि ~45% पावसाची शक्यता.\n\n"
                    "मी आपल्या शेतीसाठी आणखी काय मदत करू शकतो?"
                )
            elif is_hindi:
                response_text = (
                    "प्री-फेच किए गए **CropO हॉट कैश** के आधार पर जानकारी:\n\n"
                    "- **सक्रिय प्लॉट:** आम अल्फा (0.94 एकड़)\n"
                    "- **मिट्टी की नमी:** 81.37% (संतृप्त)\n"
                    "- **स्वास्थ्य स्कोर:** 100.0% (उत्कृष्ट)\n"
                    "- **मौसम:** 24.5°C और ~45% बारिश की संभावना।\n\n"
                    "मैं आपके खेत के लिए और क्या सहायता कर सकता हूँ?"
                )
            elif is_kannada:
                response_text = (
                    "ಸಂಗ್ರಹಿಸಲಾದ **CropO ಡೇಟಾ** ಆಧಾರದ ಮೇಲೆ:\n\n"
                    "- **ಸಕ್ರಿಯ ಪ್ಲಾಟ್ ವಿವರ:** ಮಾವು ಆಲ್ಫಾ (0.94 ಎಕರೆ)\n"
                    "- **ಮಣ್ಣಿನ ತೇವಾಂಶ:** 81.37% (ಸ್ಯಾಚುರೇಟೆಡ್)\n"
                    "- **ಆರೋಗ್ಯ ಸ್ಕೋರ್:** 100.0% (ಅತ್ಯುತ್ತಮ)\n"
                    "- **ಹವಾಮಾನ:** 24.5°C ಮತ್ತು ~45% ಮಳೆಯ ಸಂಭವನೀಯತೆ.\n\n"
                    "ನಿಮ್ಮ ಜಮೀನಿನ ನಿರ್ವಹಣೆಗೆ ನಾನು ಇನ್ನೇನು ಸಹಾಯ ಮಾಡಬಹುದು?"
                )
            else:
                response_text = (
                    "Based on the pre-fetched **CropO Live Cache**:\n\n"
                    "- **Active Plot Details:** Mango Alpha (0.94 acres)\n"
                    "- **Soil Moisture:** 81.37% (Saturated)\n"
                    "- **Field Score:** 100.0% (Peak Vigor)\n"
                    "- **Weather:** 24.5°C with ~45% rain chance.\n\n"
                    "How else can I assist with your plot management?"
                )

        words = response_text.split(" ")
        for i, word in enumerate(words):
            token = word if i == len(words) - 1 else word + " "
            yield token
            await asyncio.sleep(0.015)


def get_provider_label(client: BaseLLMClient) -> str:
    """Human-readable label for whichever LLM backend is actually active."""
    if isinstance(client, GeminiLLMClient):
        return f"Google Gemini ({settings.GEMINI_MODEL})"
    if isinstance(client, MockLLMClient) and client.mode == "gemini_unavailable":
        _, verify_msg = get_gemini_verification_status()
        detail = verify_msg[:80] if verify_msg else "live probe failed"
        return f"Mock (Gemini key not working — {detail})"
    return "Mock (offline test mode)"


def get_llm_client(app_settings: Optional[Settings] = None) -> BaseLLMClient:
    """Factory creating LLM client: Google Gemini in production, Mock for tests/fallback."""
    cfg = app_settings or settings
    provider = cfg.LLM_PROVIDER.lower()

    if provider == "gemini":
        if _active_gemini_client is not None:
            return _active_gemini_client

        api_key = _resolve_gemini_api_key(cfg)
        if not api_key:
            logger.warning(
                "gemini_api_key_missing_or_placeholder_using_mock",
                hint="Set GEMINI_API_KEY in CropO_chatbot/.env",
            )
            return MockLLMClient(mode="gemini_unavailable")
        if _gemini_key_working is False:
            logger.warning(
                "gemini_api_key_probe_failed_using_mock",
                detail=_gemini_verify_message,
            )
            return MockLLMClient(mode="gemini_unavailable")
        return GeminiLLMClient(
            api_key=api_key,
            model=cfg.GEMINI_MODEL or "gemini-2.5-flash",
        )
    return MockLLMClient()

"""
LLM Extractor — IEP-1
======================
Replaces the rule-based StructuredExtractor for multilingual complaints.

Routing:
  - Arabizi  → GPT-4o  (best Arabizi comprehension, via OpenAI API)
  - Arabic / French / English → Qwen2.5-7B-Instruct (self-hosted via Ollama)

Both backends return the same JSON schema so the caller is backend-agnostic.
Falls back to the rule-based StructuredExtractor if both LLMs are unavailable.
"""

import json
import logging
import os
import re
import time
from typing import Optional

from openai import AsyncOpenAI

from cedarfix_shared.schemas import (
    ComplaintType,
    LocationJSON,
    SignalsJSON,
    SeverityLevel,
    TextUnderstandingResult,
)
from .extractor import StructuredExtractor

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (injected via environment variables)
# ---------------------------------------------------------------------------

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# RunPod Qwen endpoint — OpenAI-compatible (/v1/chat/completions)
# Base URL must NOT include /chat/completions; the SDK appends it automatically.
QWEN_BASE_URL: str = os.getenv(
    "QWEN_BASE_URL",
    "https://plp5oqfqe81tdm-8000.proxy.runpod.net/v1",
)
QWEN_MODEL: str = os.getenv("QWEN_MODEL", "qwen2.5-1.5b-instruct")
QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "none")  # RunPod doesn't require a real key
# Set QWEN_ENABLED=true to route ar/fr/en to Qwen on RunPod.
# When false, GPT-4o handles ALL languages.
QWEN_ENABLED: bool = os.getenv("QWEN_ENABLED", "true").lower() == "true"

# Arabizi is translated to English by GPT-4o first, then Qwen classifies.
# GPT-4o is never used for full classification anymore — translation only.
_TRANSLATE_ONLY_LANGUAGES = {"arabizi"}

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

# Translation-only prompt — used by GPT-4o for Arabizi input
_TRANSLATE_PROMPT = """\
You are a Lebanese dialect translator.
Translate the Arabizi text (Arabic written with Latin letters and numbers like 3, 7, 2, 5) into natural English.
Return ONLY a JSON object with a single field:
{"translation": "<English text>"}
No explanation, no markdown.
"""

# Full classification prompt — used by Qwen for all languages
_SYSTEM_PROMPT = """\
You are an AI assistant for CedarFix, a Lebanese public infrastructure complaint platform.
Analyze the complaint text and return ONLY a valid JSON object — no explanation, no markdown.

JSON schema (all fields required):
{
  "english_translation": "<complaint translated to English, or same text if already English>",
  "issue_type": "<best matching label — use known types when applicable: pothole, road_damage, flooding, waste_accumulation, electricity_outage, telecom_outage, traffic_light, water_pipe, sidewalk_damage, streetlight — or suggest a specific label if none fit>",
  "category": "<one of: roads | drainage | electricity | water | sanitation | telecom | public_health | environment | other>",
  "subcategory": "<short specific label, e.g. pothole, pipe_leak, wifi_outage>",
  "severity": "<one of: LOW | MEDIUM | HIGH | CRITICAL>",
  "location_mentions": ["<place name>"],
  "keywords": ["<key term>"],
  "summary": "<one-sentence English summary>",
  "signals": {
    "public_safety_risk": <true|false>,
    "traffic_impact": <true|false>,
    "emergency_signal": <true|false>
  },
  "confidence": <0.0–1.0>
}

Rules:
- severity=CRITICAL only for imminent danger or total blockage.
- confidence reflects how certain you are of issue_type.
- Ogero handles internet/wifi/telecom outages; EDL handles electricity.
"""


def _user_prompt(text: str, language: str) -> str:
    lang_hint = {
        "ar": "Arabic",
        "fr": "French",
        "en": "English",
        "arabizi": "Arabizi (Arabic written with Latin letters and numbers)",
        "unknown": "unknown language",
    }.get(language, language)
    return f"Language hint: {lang_hint}\n\nComplaint:\n{text}"


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

def _parse_llm_json(raw: str) -> dict:
    """
    Robustly extract a JSON object from an LLM response that may contain
    markdown fences or leading/trailing prose.
    """
    # Strip markdown code fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    # Find first { … } block
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(raw[start:end])


# ---------------------------------------------------------------------------
# Backend callers
# ---------------------------------------------------------------------------

async def _call_gpt4o_translate(text: str) -> str:
    """Translate Arabizi to English using GPT-4o. Returns the English string only."""
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _TRANSLATE_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    result = json.loads(response.choices[0].message.content)
    return result.get("translation", text)


async def _call_qwen(text: str, language: str) -> dict:
    """Call the self-hosted Qwen on RunPod via its OpenAI-compatible endpoint."""
    client = AsyncOpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    response = await client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(text, language)},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    return _parse_llm_json(response.choices[0].message.content)


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------

_ISSUE_TO_CATEGORY = {
    "pothole": "roads",           "road_damage": "roads",
    "flooding": "drainage",       "waste_accumulation": "sanitation",
    "electricity_outage": "electricity", "traffic_light": "roads",
    "water_pipe": "water",        "sidewalk_damage": "roads",
    "streetlight": "electricity", "telecom_outage": "telecom",
    "other": "other",
}


def _build_result(complaint_id: str, original_text: str, language: str,
                  data: dict, processing_ms: int) -> TextUnderstandingResult:
    issue_raw = data.get("issue_type", "other")
    try:
        issue_type = ComplaintType(issue_raw)
    except ValueError:
        issue_type = ComplaintType.OTHER

    severity_raw = data.get("severity", "LOW")
    try:
        severity = SeverityLevel(severity_raw)
    except ValueError:
        severity = SeverityLevel.LOW

    category = data.get("category") or _ISSUE_TO_CATEGORY.get(issue_raw, "other")
    subcategory = data.get("subcategory", issue_raw)
    translation = data.get("english_translation", original_text)

    signals_raw = data.get("signals", {})
    signals = SignalsJSON(
        public_safety_risk=bool(signals_raw.get("public_safety_risk", False)),
        traffic_impact=bool(signals_raw.get("traffic_impact", False)),
        emergency_signal=bool(signals_raw.get("emergency_signal", False)),
    )

    location_mentions: list = data.get("location_mentions", [])
    location = LocationJSON(
        raw=", ".join(location_mentions),
        normalized=location_mentions[0] if location_mentions else "",
        confidence=0.75 if location_mentions else 0.0,
    )

    # normalized_text is the English translation — downstream IEP-1 embeds this
    normalized_text = translation if translation else original_text

    return TextUnderstandingResult(
        complaint_id=complaint_id,
        original_text=original_text,
        normalized_text=normalized_text,
        language=language,
        english_translation=translation if language != "en" else None,
        summary=data.get("summary", ""),
        category=category,
        subcategory=subcategory,
        issue_type=issue_type,
        location=location,
        severity=severity,
        signals=signals,
        urgency_keywords=data.get("keywords", []),
        confidence=float(data.get("confidence", 0.7)),
        processing_ms=processing_ms,
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class LLMExtractor:
    """
    Drop-in replacement for StructuredExtractor that uses LLMs.
    Falls back to StructuredExtractor if both LLMs are unavailable.
    """

    def __init__(self):
        self._fallback = StructuredExtractor()

    async def extract(
        self, complaint_id: str, text: str, language: str
    ) -> TextUnderstandingResult:
        t0 = time.time()
        data: Optional[dict] = None
        english_text = text  # may be replaced by translation

        # Step 1: Translate Arabizi → English via GPT-4o (translation only)
        if language in _TRANSLATE_ONLY_LANGUAGES and OPENAI_API_KEY:
            try:
                english_text = await _call_gpt4o_translate(text)
                log.info("[IEP-1] GPT-4o translated Arabizi → English: %s", english_text[:80])
            except Exception as e:
                log.warning("[IEP-1] GPT-4o translation failed (%s), classifying raw text", e)
                english_text = text

        # Step 2: Classify with Qwen (always, for all languages)
        if QWEN_ENABLED:
            try:
                classify_lang = "en" if language in _TRANSLATE_ONLY_LANGUAGES else language
                data = await _call_qwen(english_text, classify_lang)
                log.info("[IEP-1] Qwen classified language=%s", language)
            except Exception as e:
                log.warning("[IEP-1] Qwen failed (%s), falling back to rule-based", e)

        processing_ms = int((time.time() - t0) * 1000)

        if data is None:
            log.warning("[IEP-1] Qwen unavailable — falling back to rule-based extractor")
            result = self._fallback.extract(complaint_id, english_text)
            result.language = language
            result.english_translation = english_text if language != "en" else None
            result.processing_ms = processing_ms
            return result

        # Inject translation into data so _build_result can store it
        if language in _TRANSLATE_ONLY_LANGUAGES:
            data["english_translation"] = english_text

        return _build_result(complaint_id, text, language, data, processing_ms)

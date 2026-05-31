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
from typing import List, Literal, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from cedarfix_shared.schemas import (
    ComplaintType,
    LocationJSON,
    SignalsJSON,
    SeverityLevel,
    TextUnderstandingResult,
)
from cedarfix_shared.location import lookup_text
from .extractor import StructuredExtractor

# ---------------------------------------------------------------------------
# Structured output schema — keys are fixed by us; LLM only fills values.
# When the endpoint supports guided_json (vLLM), this schema is enforced at
# the token level so the model cannot invent keys, wrong enum values, or
# refuse to answer by outputting something like {"error": "not a complaint"}.
# ---------------------------------------------------------------------------

class _SignalsOutput(BaseModel):
    public_safety_risk: bool = False
    traffic_impact: bool = False
    emergency_signal: bool = False


class _LLMOutput(BaseModel):
    is_complaint: bool = True
    english_translation: str = ""
    issue_type: Literal[
        "pothole", "road_damage", "flooding", "waste_accumulation",
        "electricity_outage", "water_outage", "telecom_outage",
        "traffic_light", "water_pipe", "sidewalk_damage", "streetlight",
        "traffic_incident", "public_safety", "other",
    ] = "other"
    category: str = "other"         # free-form — LLM can use new values
    subcategory: str = "other"      # free-form — LLM should be specific
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"
    location_mentions: List[str] = []
    keywords: List[str] = []
    summary: str = ""
    signals: _SignalsOutput = Field(default_factory=_SignalsOutput)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    semantic_domain: Literal[
        "transportation", "utilities", "environment", "safety", "other",
    ] = "other"
    physical_component: str = "other"   # free-form — be specific
    failure_mode: Literal[
        "damage", "outage", "overflow", "accumulation", "blockage",
        "contamination", "other",
    ] = "other"


# JSON schema passed to vLLM's guided_json parameter.
# This locks the output structure so the LLM only generates values.
_LLM_OUTPUT_SCHEMA: dict = _LLMOutput.model_json_schema()

# Whether to use guided_json constrained decoding.
# Falls back to plain json_object mode if the endpoint rejects the parameter.
QWEN_GUIDED: bool = os.getenv("QWEN_GUIDED", "true").lower() == "true"


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

# Full classification prompt — used by Qwen for all languages.
# With guided_json the model only fills values — no need to describe JSON format.
_SYSTEM_PROMPT = """\
You are a Lebanese public infrastructure complaint classifier for CedarFix.
Analyze the text and fill in the output fields.

is_complaint: true if the text describes ANY real public infrastructure or public-space problem
(potholes, floods, garbage, power outage, water leak, streetlights, broken benches, fallen trees,
construction rubble, stray animals causing danger, river pollution, sewage smell, missing manholes, etc.).
Set false ONLY for pure personal emotion, spam, or text 100% unrelated to public space.

For issue_type - pick the closest match from the allowed values, or "other" if nothing fits.
For category and subcategory - use the most accurate specific label even if it is new (e.g. broken_bench, fallen_tree, chemical_pollution).
For semantic_domain, physical_component, failure_mode - describe what you actually observe in the text.
For confidence - how certain you are of issue_type (0.0 = no complaint, 1.0 = certain).

Rules:
- severity=CRITICAL only for imminent danger or total blockage.
- confidence=0.0 when is_complaint=false.
- Ogero handles telecom outages; EDL handles electricity.
- "water waste" or "wasted water" = pipe leak: issue_type water_pipe, category water.
- "waste" or "garbage" alone = solid trash: issue_type waste_accumulation, category sanitation.
- If no issue_type fits, use "other" but set subcategory and category to something specific (e.g. subcategory: broken_bench, category: street_furniture).
- semantic_domain, physical_component, failure_mode: free-form, use the most accurate label.
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
    """Call the self-hosted Qwen on RunPod via its OpenAI-compatible endpoint.

    When QWEN_GUIDED=true (default), passes the JSON schema as guided_json so
    vLLM constrains token generation — the LLM only fills values, never invents
    keys, wrong enum values, or malformed JSON.
    Falls back to plain json_object mode if the endpoint rejects guided_json.
    """
    client = AsyncOpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL, max_retries=0, timeout=20.0)

    kwargs: dict = dict(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(text, language)},
        ],
        temperature=0.0,
    )

    if QWEN_GUIDED:
        # Guided decoding: vLLM enforces the schema at token level.
        # The model cannot output a wrong enum value or miss a required key.
        kwargs["extra_body"] = {"guided_json": _LLM_OUTPUT_SCHEMA}
    else:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = await client.chat.completions.create(**kwargs)
        raw = response.choices[0].message.content
        data = _parse_llm_json(raw)
        # Validate through Pydantic — coerces types and fills missing fields with defaults.
        validated = _LLMOutput.model_validate(data)
        return validated.model_dump()
    except Exception as e:
        if QWEN_GUIDED and ("guided" in str(e).lower() or "extra_body" in str(e).lower() or "422" in str(e)):
            # Endpoint doesn't support guided_json — retry without it.
            log.warning("[IEP-1] guided_json not supported (%s), retrying without", e)
            kwargs.pop("extra_body", None)
            kwargs["response_format"] = {"type": "json_object"}
            response = await client.chat.completions.create(**kwargs)
            data = _parse_llm_json(response.choices[0].message.content)
            validated = _LLMOutput.model_validate(data)
            return validated.model_dump()
        raise


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------

_ISSUE_TO_CATEGORY = {
    "pothole": "roads",           "road_damage": "roads",
    "flooding": "drainage",       "waste_accumulation": "sanitation",
    "electricity_outage": "electricity", "traffic_light": "roads",
    "water_pipe": "water",        "water_outage": "water",
    "sidewalk_damage": "roads",
    "streetlight": "electricity", "telecom_outage": "telecom",
    "traffic_incident": "roads",  "public_safety": "other",
    "other": "other",
}

def _build_result(complaint_id: str, original_text: str, language: str,
                  data: dict, processing_ms: int) -> TextUnderstandingResult:
    # --- Non-complaint early exit ---
    # LLM explicitly said this is not an infrastructure complaint.
    # Force type=OTHER + near-zero confidence so the media-validation gate
    # catches it as invalid_no_complaint (or needs_clarification if image disagrees).
    if not data.get("is_complaint", True):
        log.info("[IEP-1] LLM flagged as non-complaint for complaint_id=%s", complaint_id)
        translation = data.get("english_translation", original_text)
        return TextUnderstandingResult(
            complaint_id=complaint_id,
            original_text=original_text,
            normalized_text=translation or original_text,
            language=language,
            english_translation=translation if language != "en" else None,
            summary=data.get("summary", "Not a complaint"),
            category="other",
            subcategory="not_a_complaint",
            issue_type=ComplaintType.OTHER,
            location=LocationJSON(raw="", normalized="", confidence=0.0, source="none"),
            severity=SeverityLevel.LOW,
            signals=SignalsJSON(public_safety_risk=False, traffic_impact=False, emergency_signal=False),
            urgency_keywords=[],
            confidence=0.0,
            processing_ms=processing_ms,
        )

    # issue_type is already validated by _LLMOutput Pydantic model \u2014 guaranteed to be a
    # known ComplaintType value (guided_json enforces this at the token level; Pydantic
    # coerces any remaining edge cases to "other").
    issue_raw = data.get("issue_type", "other")
    issue_type = ComplaintType(issue_raw) if issue_raw in {ct.value for ct in ComplaintType} else ComplaintType.OTHER
    unknown_type = (issue_raw not in {ct.value for ct in ComplaintType})
    severity_raw = data.get("severity", "LOW")
    try:
        severity = SeverityLevel(severity_raw)
    except ValueError:
        log.warning("[IEP-1] LLM returned unknown severity=%r \u2014 using MEDIUM", severity_raw)
        severity = SeverityLevel.MEDIUM

    llm_cat = data.get("category", "")
    # Use whatever category the LLM returns \u2014 don't restrict to a hardcoded list.
    # Only fall back to the static type\u2192category map when the LLM returned nothing.
    category = llm_cat if llm_cat else _ISSUE_TO_CATEGORY.get(issue_raw, issue_raw or "other")
    subcategory = data.get("subcategory", issue_raw)
    translation = data.get("english_translation", original_text)

    signals_raw = data.get("signals", {})
    signals = SignalsJSON(
        public_safety_risk=bool(signals_raw.get("public_safety_risk", False)),
        traffic_impact=bool(signals_raw.get("traffic_impact", False)),
        emergency_signal=bool(signals_raw.get("emergency_signal", False)),
    )

    # Build LocationJSON and enrich with seed lookup if possible
    location_mentions: list = data.get("location_mentions", [])
    raw_loc = ", ".join(location_mentions)
    resolved_loc = lookup_text(raw_loc) if raw_loc else None
    location = LocationJSON(
        raw=raw_loc,
        normalized=resolved_loc["name"] if resolved_loc else (location_mentions[0] if location_mentions else ""),
        municipality=resolved_loc["municipality"] if resolved_loc else None,
        district=resolved_loc["district"] if resolved_loc else None,
        governorate=resolved_loc["governorate"] if resolved_loc else None,
        latitude=resolved_loc["lat"] if resolved_loc else None,
        longitude=resolved_loc["lng"] if resolved_loc else None,
        confidence=0.80 if resolved_loc else (0.60 if location_mentions else 0.0),
        source="text_lookup" if resolved_loc else ("llm_extracted" if location_mentions else "none"),
    )

    # normalized_text is the English translation — downstream IEP-1 embeds this
    normalized_text = translation if translation else original_text

    raw_confidence = float(data.get("confidence", 0.7))
    # Penalise confidence when the type was not in the allowed taxonomy
    effective_confidence = round(raw_confidence * 0.40, 3) if unknown_type else raw_confidence

    result = TextUnderstandingResult(
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
        confidence=effective_confidence,
        semantic_domain=data.get("semantic_domain"),
        physical_component=data.get("physical_component"),
        failure_mode=data.get("failure_mode"),
        processing_ms=processing_ms,
    )

    if unknown_type:
        # The LLM returned an issue_type outside the taxonomy enum.
        # Surface it in subcategory so it is visible in the JSON — do NOT lose it.
        # subcategory already holds the LLM's own subcategory value; prepend the
        # raw issue_type so both are preserved, e.g. "broken_fence (damaged_railing)".
        llm_sub = data.get("subcategory", "")
        result.subcategory = f"{issue_raw} ({llm_sub})" if llm_sub and llm_sub != issue_raw else issue_raw

    return result


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

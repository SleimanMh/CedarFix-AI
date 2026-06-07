"""LLM Extractor - IEP-1 (fact extraction only)."""

import json
import logging
import os
import re
import time
from typing import List, Literal, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from cedarfix_shared.schemas import (
    AlignmentFeaturesJSON,
    ExtractionEvidenceJSON,
    LocationJSON,
    RoutingFeaturesJSON,
    SignalsJSON,
    SeverityLevel,
    TextUnderstandingResult,
)
from cedarfix_shared.location import lookup_text
from cedarfix_shared.metrics import TEXT_EXTRACTION_FAILURE_TOTAL, TEXT_EXTRACTION_SOURCE_TOTAL
from .extractor import StructuredExtractor


class _SignalsOutput(BaseModel):
    public_safety_risk: bool = False
    traffic_impact: bool = False
    corruption_signal: bool = False
    emergency_signal: bool = False


class _LLMOutput(BaseModel):
    is_complaint: bool = True
    english_translation: str = ""
    issue_type: str = "unknown"
    category: str = "unknown"
    subcategory: str = "unknown"
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"
    location_mentions: List[str] = []
    keywords: List[str] = []
    summary: str = ""
    signals: _SignalsOutput = Field(default_factory=_SignalsOutput)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    semantic_domain: str = "unknown"
    physical_component: str = "unknown"
    failure_mode: str = "unknown"


_LLM_OUTPUT_SCHEMA: dict = _LLMOutput.model_json_schema()
QWEN_GUIDED: bool = os.getenv("QWEN_GUIDED", "false").lower() == "true"

log = logging.getLogger(__name__)

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "http://host.docker.internal:8000/v1")
QWEN_MODEL: str = os.getenv("QWEN_MODEL", "cedarfix")
QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "none")
QWEN_ENABLED: bool = os.getenv("QWEN_ENABLED", "true").lower() == "true"
QWEN_TIMEOUT: float = float(os.getenv("QWEN_TIMEOUT", "50"))
QWEN_MAX_ATTEMPTS: int = max(1, int(os.getenv("QWEN_MAX_ATTEMPTS", "1")))
QWEN_MAX_TOKENS: int = max(128, int(os.getenv("QWEN_MAX_TOKENS", "1536")))
_TRANSLATE_ONLY_LANGUAGES: set[str] = set()


def _error_type(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timeout" in text:
        return "timeout"
    if "connection" in name or "connect" in text:
        return "connection"
    if "json" in name or "json" in text:
        return "json_parse"
    return name or "unknown"

_TRANSLATE_PROMPT = """\
You are a Lebanese dialect translator.
Translate the Arabizi text (Arabic written with Latin letters and numbers like 3, 7, 2, 5) into natural English.
Return ONLY a JSON object with a single field:
{"translation": "<English text>"}
No explanation, no markdown.
"""

_SYSTEM_PROMPT = """\
You are a Lebanese public infrastructure complaint fact extractor for CedarFix.
Extract structured facts only.
Return only a valid JSON object matching the requested fields. No markdown, no prose.
Do not decide the responsible public entity. Do not perform routing.
Never output routing decisions or review decisions.
When the input is not English, fill english_translation with a natural English translation.
Return these top-level keys only: is_complaint, english_translation, issue_type, category,
subcategory, severity, location_mentions, keywords, summary, signals, confidence,
semantic_domain, physical_component, failure_mode.
Do not include routing_features, evidence, alignment_features, responsible_entity,
routing_decision, or other nested enrichment fields; the backend derives them.

is_complaint: true if the text describes ANY real public infrastructure or public-space problem
in streets, sidewalks, public buildings, parks, utilities, public transport stops, drainage, sanitation,
water, electricity, telecom, public safety, or other public/shared spaces.
Set false ONLY for pure personal emotion, spam, or text 100% unrelated to public space.

Do not classify by choosing the nearest item from examples. There is no fixed taxonomy.
Use free-form snake_case labels based on the object and failure actually described in the text.

issue_type:
- Use a specific free-form label for the problem as written, e.g. cracked_bus_stop_shelter, sewage_overflow,
  missing_manhole_cover, loose_pedestrian_bridge_railing, unspecified_sidewalk_hazard.
- Do not normalize plural/singular words if the user's wording naturally suggests a different label.
- If the complaint directly names the issue or object, base issue_type on that named issue/object instead of
  replacing it with a broader surface, material, or nearby failure description.
- Do not use issue_type='other' to hide a new issue. Use a precise new label instead.
- Use issue_type='unknown' only when the text clearly gives no object or problem.
- Use issue_type='unspecified_*' only when the object is genuinely unnamed. If the text names a specific object
  such as pothole, road hole, crater, sewer, drain, bus stop shelter, railing, step, cable, pipe, or manhole,
  preserve that object in issue_type instead of replacing it with a vague surface/component label.

category:
- Use a broad free-form group such as road_surface, sidewalk, sewer_network, drainage, street_furniture,
  public_transport_stop, electrical_grid, telecom_network, water_network, waste_management, public_space,
  structural_hazard, environmental_hazard, animal_hazard, or another accurate group.

subcategory:
- Use the most specific visible/reported object or failure, such as cracked_shelter_roof, exploded_sewer,
  loose_railing, broken_step, exposed_wire, chemical_spill, fallen_tree, or ambiguous_sidewalk_obstacle.

For vague descriptions, preserve uncertainty instead of inventing an object:
- "big broken thing on the sidewalk" -> issue_type=unspecified_sidewalk_hazard, category=sidewalk,
  subcategory=ambiguous_broken_object, physical_component=sidewalk.
- "bus stop shelter roof is cracked" -> issue_type=cracked_bus_stop_shelter, category=public_transport_stop,
  subcategory=cracked_shelter_roof. Do NOT call this streetlight.
- "fi majrour mfajjar w ri7a ktir 2awye bl tari2" -> issue_type=sewage_overflow or burst_sewer,
  category=sewer_network, subcategory=sewage_smell_or_overflow. Do NOT call this streetlight.

For confidence - how certain you are of issue_type (0.0 = no complaint, 1.0 = certain).
semantic_domain:
- Use a broad domain from the facts: transportation for roads, sidewalks, traffic, public transport stops,
  pedestrian paths, and street mobility; utilities for water, electricity, telecom, sewer, and service networks;
  environment for waste, pollution, flooding, sewage discharge, smells, animals, or green-space hazards;
  safety for structural/public danger when the component is not otherwise clear; other only as a last resort.
- Do not use semantic_domain='unknown' when the text names a public component or public-space hazard.
- If a road, sidewalk, pedestrian path, bridge used by pedestrians, stairway, or public transport stop is named,
  use transportation unless the complaint is mainly pollution, waste, sewage, animals, or vegetation.
- Safety risk belongs in signals and severity; do not change the domain to safety when the component domain is clear.

physical_component:
- Name the actual component from the text, e.g. sidewalk, sewer_network, bus_stop_shelter, shelter_roof,
  pedestrian_bridge_railing, public_staircase, electrical_box, telecom_cable, road_surface.

failure_mode:
- Name the actual failure/action, e.g. damage, cracked, broken, missing, overflow, sewage_smell,
  exposed, falling_pieces, blockage, contamination, low_hanging, obstruction.

summary:
- Always provide one short factual sentence. Do not leave it empty for complaint text.

If unsure, use the closest factual component from the text and lower confidence; do not guess a specific object.

Other rules:
- severity=CRITICAL only for imminent danger or total blockage.
- confidence=0.0 when is_complaint=false.
"""


def _user_prompt(text: str, language: str) -> str:
    lang_hint = {
        "ar": "Arabic",
        "fr": "French",
        "en": "English",
        "arabizi": "Arabizi (Arabic written with Latin letters and numbers)",
        "unknown": "unknown language",
    }.get(language, language)
    extra = ""
    if language == "arabizi":
        extra = (
            "\nLebanese Arabizi hints: fi=there is, majrour/sewer=sewer or drain, "
            "mfajjar=burst/exploded, ri7a=smell, ktir/kter=very, 2awye=strong, "
            "bl/b=on/in, tari2=road, may/maye=water, kahraba=electricity.\n"
        )
    return f"Language hint: {lang_hint}{extra}\nComplaint:\n{text}"


def _parse_llm_json(raw: str) -> dict:
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(raw[start:end])


def _string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    if value is None:
        return default
    return bool(value)


def _scalar_text(value, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return default
    return str(value)


def _coerce_llm_output(data: dict) -> dict:
    """
    Qwen sometimes returns a valid JSON object with loose shapes for nested
    fields. Preserve the extracted facts and repair those shapes before
    Pydantic validation instead of discarding the whole LLM response.
    """
    clean = dict(data or {})

    clean["is_complaint"] = _bool(clean.get("is_complaint"), True)
    for key in (
        "english_translation",
        "issue_type",
        "category",
        "subcategory",
        "summary",
        "semantic_domain",
        "physical_component",
        "failure_mode",
    ):
        clean[key] = _scalar_text(clean.get(key), _LLMOutput.model_fields[key].default)

    clean["location_mentions"] = _string_list(clean.get("location_mentions"))
    clean["keywords"] = _string_list(clean.get("keywords"))

    signals = _as_dict(clean.get("signals"))
    clean["signals"] = {
        "public_safety_risk": _bool(signals.get("public_safety_risk")),
        "traffic_impact": _bool(signals.get("traffic_impact")),
        "corruption_signal": _bool(signals.get("corruption_signal")),
        "emergency_signal": _bool(signals.get("emergency_signal")),
    }

    severity = str(clean.get("severity", "LOW")).upper()
    clean["severity"] = severity if severity in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else "LOW"

    try:
        clean["confidence"] = max(0.0, min(1.0, float(clean.get("confidence", 0.5))))
    except (TypeError, ValueError):
        clean["confidence"] = 0.5

    return clean


async def _call_gpt4o_translate(text: str) -> str:
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


async def _call_gpt4o_extract(text: str, language: str) -> dict:
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, max_retries=0, timeout=35.0)
    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(text, language)},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    data = _parse_llm_json(response.choices[0].message.content)
    return _LLMOutput.model_validate(_coerce_llm_output(data)).model_dump()


async def _call_qwen(text: str, language: str) -> dict:
    client = AsyncOpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL, max_retries=0, timeout=QWEN_TIMEOUT)

    kwargs: dict = dict(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(text, language)},
        ],
        temperature=0.0,
        max_tokens=QWEN_MAX_TOKENS,
    )

    if QWEN_GUIDED:
        kwargs["extra_body"] = {"guided_json": _LLM_OUTPUT_SCHEMA}
    else:
        kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(QWEN_MAX_ATTEMPTS):
        try:
            response = await client.chat.completions.create(**kwargs)
            data = _parse_llm_json(response.choices[0].message.content)
            return _LLMOutput.model_validate(_coerce_llm_output(data)).model_dump()
        except Exception as e:
            if QWEN_GUIDED and ("guided" in str(e).lower() or "extra_body" in str(e).lower() or "422" in str(e)):
                log.warning("[IEP-1] guided_json not supported (%s), retrying without", e)
                kwargs.pop("extra_body", None)
                kwargs["response_format"] = {"type": "json_object"}
                response = await client.chat.completions.create(**kwargs)
                data = _parse_llm_json(response.choices[0].message.content)
                return _LLMOutput.model_validate(_coerce_llm_output(data)).model_dump()
            if attempt + 1 < QWEN_MAX_ATTEMPTS and "timed out" in str(e).lower():
                log.warning("[IEP-1] Qwen timeout on attempt %s, retrying (%s)", attempt + 1, e)
                continue
            raise


def _snake(value: str | None, default: str = "unknown") -> str:
    s = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    s = re.sub(r"[^a-z0-9_]", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or default


def _snake_or_default(value: str | None, default: str) -> str:
    normalized = _snake(value, "unknown")
    return default if normalized in {"", "unknown"} and default else normalized


def _dynamic_descriptor_fallback(
    issue_type: str,
    category: str,
    subcategory: str,
    semantic_domain: str,
    physical_component: str,
    failure_mode: str,
) -> tuple[str, str, str]:
    labels = [x for x in (category, subcategory, issue_type) if x and x != "unknown"]
    joined = "_".join(labels)

    if semantic_domain in {"", "unknown", "other"} and labels:
        semantic_domain = category if category != "unknown" else labels[0]

    if physical_component in {"", "unknown", "other"} and labels:
        physical_component = category if category != "unknown" else labels[0]

    if failure_mode in {"", "unknown", "other"}:
        for token in reversed(joined.split("_")):
            if token and token not in {"unspecified", "ambiguous", "public", "space"}:
                failure_mode = token
                break

    return semantic_domain, physical_component, failure_mode


def _build_result(complaint_id: str, original_text: str, language: str, data: dict, processing_ms: int) -> TextUnderstandingResult:
    if not data.get("is_complaint", True):
        translation = data.get("english_translation", original_text)
        return TextUnderstandingResult(
            complaint_id=complaint_id,
            original_text=original_text,
            normalized_text=translation or original_text,
            language=language,
            english_translation=translation if language != "en" else None,
            summary=data.get("summary", "Not a complaint"),
            category="unknown",
            subcategory="unknown",
            issue_type="unknown",
            location=LocationJSON(raw="", normalized="", confidence=0.0, source="none"),
            severity=SeverityLevel.LOW,
            signals=SignalsJSON(public_safety_risk=False, traffic_impact=False, corruption_signal=False, emergency_signal=False),
            routing_features=RoutingFeaturesJSON(),
            evidence=ExtractionEvidenceJSON(missing_information=["complaint_not_detected_in_text"]),
            alignment_features=AlignmentFeaturesJSON(),
            urgency_keywords=[],
            confidence=0.0,
            processing_ms=processing_ms,
        )

    issue_type = _snake(data.get("issue_type"), "unknown")
    category = _snake_or_default(data.get("category"), "unknown")
    subcategory = _snake_or_default(data.get("subcategory"), issue_type)
    semantic_domain = _snake_or_default(data.get("semantic_domain"), "unknown")
    physical_component = _snake_or_default(data.get("physical_component"), "unknown")
    failure_mode = _snake_or_default(data.get("failure_mode"), "unknown")
    semantic_domain, physical_component, failure_mode = _dynamic_descriptor_fallback(
        issue_type, category, subcategory, semantic_domain, physical_component, failure_mode
    )

    severity_raw = data.get("severity", "LOW")
    try:
        severity = SeverityLevel(severity_raw)
    except ValueError:
        severity = SeverityLevel.MEDIUM

    translation = data.get("english_translation", original_text)

    signals_raw = data.get("signals", {})
    signals = SignalsJSON(
        public_safety_risk=bool(signals_raw.get("public_safety_risk", False)),
        traffic_impact=bool(signals_raw.get("traffic_impact", False)),
        corruption_signal=bool(signals_raw.get("corruption_signal", False)),
        emergency_signal=bool(signals_raw.get("emergency_signal", False)),
    )

    rf_raw = data.get("routing_features", {})
    routing_features = RoutingFeaturesJSON(
        domain=_snake_or_default(rf_raw.get("domain"), semantic_domain),
        physical_component=_snake_or_default(rf_raw.get("physical_component"), physical_component),
        failure_mode=_snake_or_default(rf_raw.get("failure_mode"), failure_mode),
        hazard_type=_snake(rf_raw.get("hazard_type", "none"), "none"),
        affected_public_space=bool(rf_raw.get("affected_public_space", True)),
        requires_emergency_attention=bool(rf_raw.get("requires_emergency_attention", signals.emergency_signal)),
    )

    ev_raw = data.get("evidence", {})
    text_evidence = [str(x) for x in ev_raw.get("text_evidence", []) if str(x).strip()]
    if not text_evidence and original_text.strip():
        text_evidence = [original_text.strip()]
    evidence = ExtractionEvidenceJSON(
        text_evidence=text_evidence,
        image_evidence=[str(x) for x in ev_raw.get("image_evidence", []) if str(x).strip()],
        missing_information=[str(x) for x in ev_raw.get("missing_information", []) if str(x).strip()],
    )

    af_raw = data.get("alignment_features", {})
    alignment_features = AlignmentFeaturesJSON(
        domain=_snake_or_default(af_raw.get("domain"), routing_features.domain),
        physical_component=_snake_or_default(af_raw.get("physical_component"), routing_features.physical_component),
        failure_mode=_snake_or_default(af_raw.get("failure_mode"), routing_features.failure_mode),
        visible_hazard=bool(af_raw.get("visible_hazard", False)),
        objects=[_snake(x) for x in af_raw.get("objects", []) if str(x).strip()],
        actions=[_snake(x) for x in af_raw.get("actions", []) if str(x).strip()],
        location_context=[str(x).strip() for x in af_raw.get("location_context", []) if str(x).strip()],
    )

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

    normalized_text = translation if translation else original_text
    summary = str(data.get("summary") or "").strip()
    if not summary:
        summary = f"{issue_type.replace('_', ' ').capitalize()} reported."
    return TextUnderstandingResult(
        complaint_id=complaint_id,
        original_text=original_text,
        normalized_text=normalized_text,
        language=language,
        english_translation=translation if language != "en" else None,
        summary=summary,
        category=category,
        subcategory=subcategory,
        issue_type=issue_type,
        location=location,
        location_mentions=[str(x).strip() for x in location_mentions if str(x).strip()],
        severity=severity,
        signals=signals,
        urgency_keywords=data.get("keywords", []),
        confidence=float(data.get("confidence", 0.7)),
        semantic_domain=semantic_domain,
        physical_component=physical_component,
        failure_mode=failure_mode,
        routing_features=routing_features,
        evidence=evidence,
        alignment_features=alignment_features,
        processing_ms=processing_ms,
    )


class LLMExtractor:
    def __init__(self):
        self._fallback = StructuredExtractor()

    async def extract(self, complaint_id: str, text: str, language: str) -> TextUnderstandingResult:
        t0 = time.time()
        data: Optional[dict] = None
        english_text = text

        if OPENAI_API_KEY:
            try:
                data = await _call_gpt4o_extract(text, language)
                english_text = data.get("english_translation") or text
                TEXT_EXTRACTION_SOURCE_TOTAL.labels(source="gpt4o").inc()
            except Exception as e:
                TEXT_EXTRACTION_FAILURE_TOTAL.labels(source="gpt4o", error_type=_error_type(e)).inc()
                log.warning("[IEP-1] GPT-4o extraction failed (%s), using fallback path", e)
                english_text = text

        if QWEN_ENABLED and data is None and language not in _TRANSLATE_ONLY_LANGUAGES:
            try:
                data = await _call_qwen(english_text, language)
                TEXT_EXTRACTION_SOURCE_TOTAL.labels(source="qwen").inc()
            except Exception as e:
                TEXT_EXTRACTION_FAILURE_TOTAL.labels(source="qwen", error_type=_error_type(e)).inc()
                log.warning("[IEP-1] Qwen failed (%s), falling back to rule-based", e)
        elif QWEN_ENABLED and data is None and language in _TRANSLATE_ONLY_LANGUAGES:
            log.warning("[IEP-1] Skipping Qwen: Arabizi is handled by GPT-4o only")

        processing_ms = int((time.time() - t0) * 1000)

        if data is None:
            TEXT_EXTRACTION_SOURCE_TOTAL.labels(source="rule_based_fallback").inc()
            result = self._fallback.extract(complaint_id, english_text)
            result.language = language
            result.english_translation = english_text if language != "en" and english_text != text else None
            result.issue_type = _snake(getattr(result, "issue_type", "unknown"), "unknown")
            result.category = _snake(getattr(result, "category", "unknown"), "unknown")
            result.subcategory = _snake(getattr(result, "subcategory", result.issue_type), result.issue_type)
            result.routing_features = RoutingFeaturesJSON(
                domain=_snake(getattr(result, "semantic_domain", getattr(result, "category", "unknown")), "unknown"),
                physical_component=_snake(getattr(result, "physical_component", "unknown"), "unknown"),
                failure_mode=_snake(getattr(result, "failure_mode", "unknown"), "unknown"),
                hazard_type="none",
                affected_public_space=True,
                requires_emergency_attention=bool(getattr(result, "signals", SignalsJSON()).emergency_signal),
            )
            result.evidence = ExtractionEvidenceJSON(text_evidence=[text.strip()] if text.strip() else [])
            result.alignment_features = AlignmentFeaturesJSON(
                domain=result.routing_features.domain,
                physical_component=result.routing_features.physical_component,
                failure_mode=result.routing_features.failure_mode,
            )
            result.processing_ms = processing_ms
            return result

        if language in _TRANSLATE_ONLY_LANGUAGES:
            data["english_translation"] = english_text

        return _build_result(complaint_id, text, language, data, processing_ms)

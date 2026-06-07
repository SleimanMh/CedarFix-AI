"""Multi-complaint splitter for gateway submissions."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from pydantic import BaseModel, Field

from cedarfix_shared.metrics import MULTI_COMPLAINT_CHILD_COUNT, MULTI_COMPLAINT_SPLIT_TOTAL
from cedarfix_shared.schemas import ComplaintSplitItem, ComplaintSplitResult


SPLITTER_ENABLED = os.getenv("MULTI_COMPLAINT_SPLITTER_ENABLED", "true").lower() == "true"
SPLITTER_LLM_ENABLED = os.getenv("MULTI_COMPLAINT_SPLITTER_LLM_ENABLED", "true").lower() == "true"
SPLITTER_MAX_CHILDREN = int(os.getenv("MULTI_COMPLAINT_SPLITTER_MAX_CHILDREN", "5"))
SPLITTER_TIMEOUT = float(os.getenv("MULTI_COMPLAINT_SPLITTER_TIMEOUT", "12"))

QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "")
QWEN_MODEL = os.getenv("QWEN_MODEL", "cedarfix")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "none")


class _LLMSplitOutput(BaseModel):
    is_multi: bool = False
    complaints: list[ComplaintSplitItem] = Field(default_factory=list)
    confidence: float = Field(0.75, ge=0.0, le=1.0)
    reason: str = ""


_SPLIT_SCHEMA = _LLMSplitOutput.model_json_schema()

_SYSTEM_PROMPT = """You split citizen infrastructure reports into independent complaints.
Return JSON only. Do not route, classify authorities, or invent details.
If the text describes one issue, return is_multi=false and exactly one complaint using the original text.
If the text describes multiple independent public-infrastructure issues, return one item per issue.
Keep each complaint self-contained and preserve any location mention tied to that issue.
If a location appears once and later complaint clauses omit a location, copy the shared location into
each child complaint unless the text clearly gives different locations.
Do not split just because the text contains "and", "but", "so", or "now".
Do not split details that describe the same issue, such as cause/effect/severity of one complaint.
Keep these as single complaints:
- garbage burning near a school so black smoke is spreading into the street
- a broken water pipe leaking for days and now the road is collapsing around it
- internet cables hanging low and touching a streetlight pole
Split only when there are clearly independent issues that need separate routing, such as
an electricity outage in one clause and a building fire in another."""


def _safe_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _coerce_result(original_text: str, source: str, output: _LLMSplitOutput) -> ComplaintSplitResult:
    items = []
    seen: set[str] = set()
    for item in output.complaints[:SPLITTER_MAX_CHILDREN]:
        text = _safe_text(item.complaint_text)
        if len(text) < 10:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(item.model_copy(update={"complaint_text": text}))

    if not items:
        items = [ComplaintSplitItem(complaint_text=_safe_text(original_text), confidence=1.0)]

    is_multi = len(items) > 1 and bool(output.is_multi)
    if not is_multi:
        items = [ComplaintSplitItem(complaint_text=_safe_text(original_text), confidence=1.0)]

    result = ComplaintSplitResult(
        original_text=original_text,
        is_multi=is_multi,
        source=source if is_multi else "single",
        complaints=items,
        confidence=output.confidence,
        review_reason=output.reason or None,
    )
    _record_split_metrics(result)
    return result


async def split_complaint_text(text: str) -> ComplaintSplitResult:
    original = _safe_text(text)
    if not SPLITTER_ENABLED or len(original) < 25:
        result = _single(original, "single")
        _record_split_metrics(result)
        return result

    if SPLITTER_LLM_ENABLED and QWEN_BASE_URL:
        try:
            return await _split_with_llm(original)
        except Exception as exc:
            fallback = _single(original, "fallback")
            fallback.review_reason = f"LLM splitter failed; left submission as single: {type(exc).__name__}"
            return fallback

    return _single(original, "single")


async def _split_with_llm(text: str) -> ComplaintSplitResult:
    import openai

    client = openai.AsyncOpenAI(
        api_key=QWEN_API_KEY,
        base_url=QWEN_BASE_URL,
        max_retries=0,
        timeout=SPLITTER_TIMEOUT,
    )
    kwargs: dict[str, Any] = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Split this submission if and only if it contains multiple independent complaints.\n\n"
                    f"Submission:\n{text}"
                ),
            },
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    response = await client.chat.completions.create(**kwargs)
    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    output = _LLMSplitOutput.model_validate(data)
    return _coerce_result(text, "llm", output)


def _split_heuristically(text: str) -> ComplaintSplitResult:
    parts = _enumerated_parts(text)
    if len(parts) <= 1:
        result = _single(text, "single")
        _record_split_metrics(result)
        return result

    items = [
        ComplaintSplitItem(
            complaint_text=part,
            confidence=0.68,
            reason="Detected as an enumerated/list item in the submitted text.",
        )
        for part in parts[:SPLITTER_MAX_CHILDREN]
    ]
    result = ComplaintSplitResult(
        original_text=text,
        is_multi=len(items) > 1,
        source="heuristic",
        complaints=items,
        confidence=0.68,
        review_reason="Heuristic split from explicit list/enumeration.",
    )
    _record_split_metrics(result)
    return result


def _enumerated_parts(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n")
    marker_pattern = re.compile(r"(?:^|\n|\s)(?:\d+[\).\-\:]|[-*•])\s+")
    matches = list(marker_pattern.finditer(normalized))
    if len(matches) >= 2:
        parts = []
        for idx, match in enumerate(matches):
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
            part = _safe_text(normalized[start:end])
            if len(part) >= 10:
                parts.append(part)
        return parts

    delimiter_parts = [
        _safe_text(part)
        for part in re.split(r"\s+(?:also|and also|plus|بالإضافة|كمان)\s+", text, flags=re.IGNORECASE)
    ]
    strong_issue_words = re.compile(
        r"\b(pothole|garbage|trash|waste|electricity|power|water|internet|streetlight|traffic|flood|pipe)\b",
        re.IGNORECASE,
    )
    if (
        2 <= len(delimiter_parts) <= SPLITTER_MAX_CHILDREN
        and sum(1 for part in delimiter_parts if strong_issue_words.search(part)) >= 2
    ):
        return [part for part in delimiter_parts if len(part) >= 10]

    clause_parts = _independent_issue_clauses(text)
    if len(clause_parts) > 1:
        return clause_parts

    return [text]


_ISSUE_GROUP_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("electricity", re.compile(r"\b(electricity|power|outage|blackout|kahraba|electrical)\b", re.IGNORECASE)),
    ("fire", re.compile(r"\b(fire|burning|smoke|flames?)\b", re.IGNORECASE)),
    ("water", re.compile(r"\b(water|pipe|leak|may|maye)\b", re.IGNORECASE)),
    ("waste", re.compile(r"\b(garbage|trash|waste|dump|sanitation)\b", re.IGNORECASE)),
    ("road", re.compile(r"\b(pothole|road|street|asphalt|sidewalk|bridge)\b", re.IGNORECASE)),
    ("drainage", re.compile(r"\b(flood|drain|sewer|sewage|manhole|overflow)\b", re.IGNORECASE)),
    ("telecom", re.compile(r"\b(internet|phone|telecom|cable)\b", re.IGNORECASE)),
    ("traffic", re.compile(r"\b(traffic|signal|accident|blocked)\b", re.IGNORECASE)),
]


def _issue_groups(text: str) -> set[str]:
    return {group for group, pattern in _ISSUE_GROUP_PATTERNS if pattern.search(text)}


def _independent_issue_clauses(text: str) -> list[str]:
    parts = [
        _safe_text(part)
        for part in re.split(r"\s+(?:and|و|w)\s+(?=(?:the\s+|there\s+|fi\s+|there's\s+)?)", text, flags=re.IGNORECASE)
        if _safe_text(part)
    ]
    if not (2 <= len(parts) <= SPLITTER_MAX_CHILDREN):
        return []

    groups_by_part = [_issue_groups(part) for part in parts]
    if any(not groups for groups in groups_by_part):
        return []

    all_groups = set().union(*groups_by_part)
    if len(all_groups) < 2:
        return []

    for idx, groups in enumerate(groups_by_part):
        others = set().union(*(g for j, g in enumerate(groups_by_part) if j != idx))
        if not (groups - others):
            return []

    return [part for part in parts if len(part) >= 10]


def _single(text: str, source: str) -> ComplaintSplitResult:
    return ComplaintSplitResult(
        original_text=text,
        is_multi=False,
        source=source,
        complaints=[ComplaintSplitItem(complaint_text=text, confidence=1.0)],
        confidence=1.0,
    )


def _record_split_metrics(result: ComplaintSplitResult) -> None:
    MULTI_COMPLAINT_SPLIT_TOTAL.labels(
        source=result.source,
        is_multi=str(bool(result.is_multi)).lower(),
    ).inc()
    MULTI_COMPLAINT_CHILD_COUNT.labels(source=result.source).observe(len(result.complaints))

"""
Offline GPT-4o LLM-as-Judge evaluation service.

This module is intentionally isolated from the complaint processing pipeline.
It gathers completed decisions, asks GPT-4o to judge them, stores the returned
JSON, and publishes aggregate monitoring data. It must never write back to any
pipeline decision fields.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
import uuid
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import text

from cedarfix_shared.db import engine
from cedarfix_shared.metrics import (
    EVALUATION_AVG_EXTRACTION_SCORE,
    EVALUATION_AVG_OVERALL_SCORE,
    EVALUATION_AVG_ROUTING_SCORE,
    EVALUATION_BATCH_DURATION,
    EVALUATION_COUNT,
    EVALUATION_TOTAL_GAUGE,
)


PROMPT_VERSION = "evaluation_judge_v3"
DEFAULT_JUDGE_MODEL = os.getenv("EVALUATION_JUDGE_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o"))
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SAMPLE_RATE = float(os.getenv("EVALUATION_SAMPLE_RATE", "0.20"))
BATCH_SIZE = int(os.getenv("EVALUATION_BATCH_SIZE", "4"))
TIMEZONE = os.getenv("EVALUATION_TIMEZONE", "Asia/Beirut")
SCHEDULE_ENABLED = os.getenv("EVALUATION_SCHEDULER_ENABLED", "true").lower() == "true"
RUN_ON_STARTUP = os.getenv("EVALUATION_RUN_ON_STARTUP", "false").lower() == "true"
REQUEST_TIMEOUT_SECONDS = float(os.getenv("EVALUATION_REQUEST_TIMEOUT", "90"))
INCLUDE_IMAGE_PARTS = os.getenv("EVALUATION_INCLUDE_IMAGE_PARTS", "false").lower() == "true"
BATCH_DELAY_SECONDS = float(os.getenv("EVALUATION_BATCH_DELAY_SECONDS", "20"))
MAX_RETRIES = int(os.getenv("EVALUATION_MAX_RETRIES", "3"))
MAX_TOKENS = int(os.getenv("EVALUATION_MAX_TOKENS", "4096"))


JUDGE_SYSTEM_PROMPT = """You are GPT-4o acting as CedarFix's independent offline evaluation judge.

You are NOT part of the CedarFix complaint processing pipeline.
Your scores must be independent quality judgments for monitoring, research, thesis evaluation, and model comparison only.

You will receive a batch of CedarFix complaint decisions. For each complaint, evaluate the system decision using the rubric below.

CRITICAL:
- Execute the evaluation rubric yourself.
- Do not ask the backend to compute scores.
- Return strict JSON only.
- Do not include markdown.
- Do not include text outside the JSON object.
- Evaluate factual correctness, routing correctness, multimodal consistency, and decision quality.
- Ignore writing style, grammar, and wording quality unless it changes factual meaning.
- Be strict. Do not give a 10 unless the component has no material mistakes.
- Penalize contradictions between section-level outputs and final top-level decision fields.
- Penalize generic routing when a more specific authority is clearly required by location or issue.
- Penalize irrelevant secondary authorities.
- Penalize explanations that contradict severity, routing, review status, or final decision.
- If a component is mostly correct but has an important consistency issue, score at most 7.
- If explanation severity contradicts text or final decision severity, explanation score must be at most 5.
- If the final decision has a serious unresolved inconsistency, overall_decision score must be at most 6.
- If routing includes an unrelated secondary authority, routing score must be at most 7.
- If routing uses a generic placeholder authority where a specific local/sector authority is available in the decision context, routing score must be at most 7.
- If both generic routing and an unrelated secondary authority are present, routing score must be at most 6.
- If final top-level severity conflicts with extracted text or image severity, overall_decision score must be at most 5 unless the decision explicitly explains why the severity was changed.
- If a complaint requires review but the explanation reads like a normal completed route, explanation score must be at most 6.
- If a component is absent because no image was submitted, score image understanding 10 only when the system cleanly represents image as absent. Do not let the no-image 10 hide serious text/routing/final-decision problems.

Rubric:

Text Understanding:
Evaluate whether issue type, category, severity, summary, and extracted information are correct and faithful.
10 = extraction completely correct
8-9 = minor inaccuracies
5-7 = partially correct
1-4 = major errors
0 = incorrect

Image Understanding:
Evaluate whether the image issue was identified correctly, visual reasoning is correct, and visual category is correct.
10 = issue correctly identified
8-9 = correct issue with minor detail errors
5-7 = broad category only
1-4 = wrong issue
0 = unrelated interpretation
If no image was provided, score based on whether the system correctly treated image understanding as absent/not applicable.

Media Validation:
Evaluate whether the system correctly determined if text and image describe the same complaint.
10 = correct validation decision
5 = acceptable but uncertain
0 = clearly wrong

Routing:
Evaluate whether the selected authority is appropriate.
10 = correct authority
8-9 = reasonable authority
5-7 = partially correct
1-4 = weak routing
0 = clearly wrong authority
Consider primary and secondary authority, confidence, auto_routed, requires_review, review_reason, retrieved candidates, issue type, and location. If the primary authority is only a generic placeholder while the complaint location implies a specific municipality/agency, do not score 10. If a secondary authority is unrelated to the issue, reduce the score.
Calibration:
- Correct primary authority and no problematic secondary authority can score 9-10.
- Correct generic primary authority but missing specificity should score 7-8.
- Correct primary authority plus unrelated secondary authority should score at most 7.
- Generic primary authority plus unrelated secondary authority should score at most 6.
- Wrong authority should score 0-4.

Explanation:
Evaluate whether the explanation is faithful to the actual decision.
10 = fully faithful
5 = partially faithful
0 = misleading

Overall Decision:
Evaluate whether a human reviewer would likely approve the final CedarFix decision.
10 = highly likely to approve
5 = partially acceptable
0 = unacceptable
Calibration:
- Any unresolved severity mismatch between extracted understanding and final decision should prevent a score above 5.
- Any unrelated secondary authority should prevent a score above 7.
- Multiple unresolved consistency errors should score 6 or lower.

For each complaint, return this exact object shape:
{
  "complaint_id": "...",
  "text_understanding": {"score": 0, "reason": "...", "errors": []},
  "image_understanding": {"score": 0, "reason": "...", "errors": []},
  "media_validation": {"score": 0, "reason": "...", "errors": []},
  "routing": {"score": 0, "reason": "...", "errors": []},
  "explanation": {"score": 0, "reason": "...", "errors": []},
  "overall_decision": {"score": 0, "reason": "...", "errors": []}
}

For a batch, return:
{
  "evaluations": [
    {the exact complaint evaluation object}
  ]
}
"""


class JudgeSection(BaseModel):
    score: int = Field(ge=0, le=10)
    reason: str
    errors: list[str] = Field(default_factory=list)


class ComplaintJudgeOutput(BaseModel):
    complaint_id: str
    text_understanding: JudgeSection
    image_understanding: JudgeSection
    media_validation: JudgeSection
    routing: JudgeSection
    explanation: JudgeSection
    overall_decision: JudgeSection


class BatchJudgeOutput(BaseModel):
    evaluations: list[ComplaintJudgeOutput]

    @field_validator("evaluations")
    @classmethod
    def must_have_evaluations(cls, value: list[ComplaintJudgeOutput]) -> list[ComplaintJudgeOutput]:
        if not value:
            raise ValueError("evaluations must not be empty")
        return value


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=True, default=str)
        return value
    except Exception:
        return json.loads(json.dumps(value, ensure_ascii=True, default=str))


def _extract_decision_section(decision: dict[str, Any], key: str) -> Any:
    if not isinstance(decision, dict):
        return None
    return decision.get(key)


def _sanitize_for_judge(value: Any) -> Any:
    """Remove vectors/noisy payload parts that make the judge prompt expensive and less focused."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if "embedding" in key_lower or key_lower.endswith("_vector") or key_lower == "vector":
                if isinstance(item, list):
                    sanitized[key] = f"[omitted numeric vector length={len(item)}]"
                else:
                    sanitized[key] = "[omitted embedding]"
                continue
            sanitized[key] = _sanitize_for_judge(item)
        return sanitized
    if isinstance(value, list):
        if len(value) > 20 and all(isinstance(item, (int, float)) for item in value):
            return f"[omitted numeric vector length={len(value)}]"
        return [_sanitize_for_judge(item) for item in value]
    return value


def _compact_text_analysis(text_json: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(text_json, dict):
        return None
    keep = [
        "language", "english_translation", "normalized_text", "summary", "category",
        "subcategory", "issue_type", "severity", "confidence", "location",
        "location_mentions", "signals", "routing_features", "evidence",
        "semantic_domain", "physical_component", "failure_mode",
    ]
    return {key: text_json.get(key) for key in keep if key in text_json}


def _compact_image_analysis(image_json: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(image_json, dict):
        return None
    keep = [
        "image_present", "quality", "caption", "visual_understanding",
        "vlm_analysis", "visual_candidates", "semantic_domain",
        "physical_component", "failure_mode", "confidence",
    ]
    return {key: image_json.get(key) for key in keep if key in image_json}


def _compact_routing(routing: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(routing, dict):
        return None
    compact = {
        "primary_entity": routing.get("primary_entity"),
        "primary_confidence": routing.get("primary_confidence"),
        "secondary_entity": routing.get("secondary_entity"),
        "secondary_confidence": routing.get("secondary_confidence"),
        "auto_routed": routing.get("auto_routed"),
        "requires_review": routing.get("requires_review"),
        "review_reason": routing.get("review_reason"),
        "routing_source": routing.get("routing_source"),
        "routing_rationale": routing.get("routing_rationale"),
        "rag_no_candidates": routing.get("rag_no_candidates"),
    }
    candidates = routing.get("retrieved_candidates")
    if isinstance(candidates, list):
        compact["retrieved_candidates"] = [
            {
                "doc_id": candidate.get("doc_id"),
                "entity_enum": candidate.get("entity_enum"),
                "entity_name": candidate.get("entity_name"),
                "doc_type": candidate.get("doc_type"),
                "route_mode": candidate.get("route_mode"),
                "responsibility_level": candidate.get("responsibility_level"),
                "allows_auto_route": candidate.get("allows_auto_route"),
                "rag_score": candidate.get("rag_score"),
                "rerank_score": candidate.get("rerank_score"),
            }
            for candidate in candidates[:5]
            if isinstance(candidate, dict)
        ]
    return {key: value for key, value in compact.items() if value is not None}


def _compact_explanation(explanation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(explanation, dict):
        return None
    keep = ["mode", "explanation_text", "key_factors", "citizen_message", "admin_summary"]
    return {key: explanation.get(key) for key in keep if key in explanation}


def _compact_final_decision(row: Any, decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "complaint_id": row.id,
        "status": getattr(row, "status", None),
        "complaint_type": getattr(row, "complaint_type", None),
        "severity": getattr(row, "severity", None),
        "priority_score": getattr(row, "priority_score", None),
        "assigned_entity": getattr(row, "assigned_entity", None),
        "routing_confidence": getattr(row, "routing_confidence", None),
        "requires_review": getattr(row, "requires_review", None),
        "auto_routed": getattr(row, "auto_routed", None),
        "is_duplicate": decision.get("is_duplicate"),
        "duplicate_detection": decision.get("duplicate_detection"),
        "confidence_bundle": decision.get("confidence_bundle"),
    }


def _image_url(row: Any) -> str | None:
    image_filename = getattr(row, "image_filename", None)
    if not image_filename:
        return None
    image_ref = str(image_filename)
    if image_ref.startswith(("http://", "https://", "gs://")):
        return image_ref
    bucket = os.getenv("GCS_BUCKET", "")
    if os.getenv("STORAGE_BACKEND", "").lower() == "gcs" and bucket:
        return f"https://storage.googleapis.com/{bucket}/complaints/{image_ref}"
    return image_ref


def _build_complaint_payload(row: Any) -> dict[str, Any]:
    decision = _sanitize_for_judge(row.full_decision_json or {})
    text_json = _compact_text_analysis(_extract_decision_section(decision, "text_analysis"))
    image_json = _compact_image_analysis(_extract_decision_section(decision, "image_analysis"))
    routing = _compact_routing(_extract_decision_section(decision, "routing"))
    explanation = _compact_explanation(_extract_decision_section(decision, "explanation"))
    return {
        "complaint_id": row.id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "original_complaint_text": row.original_text,
        "original_image_url": _image_url(row),
        "top_level_database_fields": {
            "status": getattr(row, "status", None),
            "complaint_type": getattr(row, "complaint_type", None),
            "severity": getattr(row, "severity", None),
            "assigned_entity": getattr(row, "assigned_entity", None),
            "routing_confidence": getattr(row, "routing_confidence", None),
        },
        "text_json": text_json,
        "image_json": image_json,
        "media_validation_result": _extract_decision_section(decision, "media_validation"),
        "routing_result": routing,
        "explanation_result": explanation,
        "final_complaint_decision": _compact_final_decision(row, decision),
    }


def _previous_day_window() -> tuple[datetime, datetime]:
    tz = ZoneInfo(TIMEZONE)
    today = datetime.now(tz).date()
    previous = today - timedelta(days=1)
    local_start = datetime.combine(previous, dt_time.min, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    start_utc = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = local_end.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def _seconds_until_next_midnight() -> float:
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    next_midnight = datetime.combine(now.date() + timedelta(days=1), dt_time.min, tzinfo=tz)
    return max(1.0, (next_midnight - now).total_seconds())


def _ensure_table() -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS complaint_evaluations (
                id                  SERIAL PRIMARY KEY,
                complaint_id        VARCHAR(36) NOT NULL,
                evaluated_at        TIMESTAMP DEFAULT NOW(),
                judge_model         VARCHAR(100) NOT NULL,
                prompt_version      VARCHAR(100) NOT NULL,
                text_score          INTEGER,
                image_score         INTEGER,
                alignment_score     INTEGER,
                routing_score       INTEGER,
                explanation_score   INTEGER,
                overall_score       INTEGER,
                reasoning_json      JSONB NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_complaint_evaluations_complaint_id
            ON complaint_evaluations(complaint_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_complaint_evaluations_evaluated_at
            ON complaint_evaluations(evaluated_at)
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_complaint_evaluations_once_per_prompt
            ON complaint_evaluations(complaint_id, prompt_version)
        """))


def select_previous_day_sample(limit_override: int | None = None) -> list[Any]:
    start_utc, end_utc = _previous_day_window()
    with engine.begin() as conn:
        count = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM complaints c
                WHERE c.created_at >= :start_utc
                  AND c.created_at < :end_utc
                  AND c.full_decision_json IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM complaint_evaluations e
                      WHERE e.complaint_id = c.id
                        AND e.prompt_version = :prompt_version
                  )
            """),
            {"start_utc": start_utc, "end_utc": end_utc, "prompt_version": PROMPT_VERSION},
        ).scalar() or 0
        limit = math.ceil(count * SAMPLE_RATE) if count else 0
        if limit_override is not None:
            limit = min(max(1, limit_override), count)
        if limit <= 0:
            return []
        result = conn.execute(
            text("""
                SELECT
                    id, created_at, original_text, image_filename,
                    status, complaint_type, severity, assigned_entity,
                    routing_confidence, full_decision_json
                FROM complaints c
                WHERE c.created_at >= :start_utc
                  AND c.created_at < :end_utc
                  AND c.full_decision_json IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM complaint_evaluations e
                      WHERE e.complaint_id = c.id
                        AND e.prompt_version = :prompt_version
                  )
                ORDER BY random()
                LIMIT :limit
            """),
            {
                "start_utc": start_utc,
                "end_utc": end_utc,
                "prompt_version": PROMPT_VERSION,
                "limit": limit,
            },
        )
        return list(result)


def select_specific_complaint(complaint_id: str) -> list[Any]:
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                SELECT
                    id, created_at, original_text, image_filename,
                    status, complaint_type, severity, assigned_entity,
                    routing_confidence, full_decision_json
                FROM complaints
                WHERE id = :complaint_id
                  AND full_decision_json IS NOT NULL
            """),
            {"complaint_id": complaint_id},
        )
        return list(result)


def select_latest_complaints(limit: int) -> list[Any]:
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                SELECT
                    id, created_at, original_text, image_filename,
                    status, complaint_type, severity, assigned_entity,
                    routing_confidence, full_decision_json
                FROM complaints
                WHERE full_decision_json IS NOT NULL
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": max(1, limit)},
        )
        return list(result)


def _build_batch_request(batch: list[Any]) -> dict[str, Any]:
    return {
        "prompt_version": PROMPT_VERSION,
        "task": "offline_cedarfix_decision_quality_evaluation",
        "complaints": [_build_complaint_payload(row) for row in batch],
    }


def _extract_json_object(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    return json.loads(raw)


async def _call_gpt4o_judge(request_payload: dict[str, Any], judge_model: str) -> tuple[BatchJudgeOutput, str, int]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    started = time.time()
    user_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": json.dumps(request_payload, ensure_ascii=False, default=str),
        }
    ]
    if INCLUDE_IMAGE_PARTS:
        for complaint in request_payload.get("complaints", []):
            image_url = complaint.get("original_image_url")
            if isinstance(image_url, str) and image_url.startswith(("http://", "https://")):
                user_content.append({
                    "type": "text",
                    "text": f"Original image for complaint_id={complaint.get('complaint_id')}",
                })
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url},
                })

    payload = {
        "model": judge_model,
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for attempt in range(MAX_RETRIES + 1):
            response = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json=payload,
            )
            if response.status_code == 429 and attempt < MAX_RETRIES:
                retry_after = response.headers.get("Retry-After")
                wait_seconds = float(retry_after) if retry_after else min(120.0, 10.0 * (2 ** attempt))
                print(f"[evaluation-judge] OpenAI 429, retrying in {wait_seconds:.1f}s")
                await asyncio.sleep(wait_seconds)
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body = response.text[:2000]
                raise RuntimeError(
                    f"OpenAI HTTP {response.status_code}: {body}"
                ) from exc
            data = response.json()
            break
    raw_output = data["choices"][0]["message"]["content"]
    parsed = BatchJudgeOutput.model_validate(_extract_json_object(raw_output))
    return parsed, raw_output, int((time.time() - started) * 1000)


def _store_evaluations(evaluations: list[ComplaintJudgeOutput], judge_model: str) -> int:
    stored = 0
    with engine.begin() as conn:
        for evaluation in evaluations:
            result = conn.execute(
                text("""
                    INSERT INTO complaint_evaluations (
                        complaint_id, judge_model, prompt_version,
                        text_score, image_score, alignment_score,
                        routing_score, explanation_score, overall_score,
                        reasoning_json
                    )
                    VALUES (
                        :complaint_id, :judge_model, :prompt_version,
                        :text_score, :image_score, :alignment_score,
                        :routing_score, :explanation_score, :overall_score,
                        CAST(:reasoning_json AS JSONB)
                    )
                    ON CONFLICT (complaint_id, prompt_version) DO NOTHING
                """),
                {
                    "complaint_id": evaluation.complaint_id,
                    "judge_model": judge_model,
                    "prompt_version": PROMPT_VERSION,
                    "text_score": evaluation.text_understanding.score,
                    "image_score": evaluation.image_understanding.score,
                    "alignment_score": evaluation.media_validation.score,
                    "routing_score": evaluation.routing.score,
                    "explanation_score": evaluation.explanation.score,
                    "overall_score": evaluation.overall_decision.score,
                    "reasoning_json": json.dumps(evaluation.model_dump(), ensure_ascii=False, default=str),
                },
            )
            stored += result.rowcount or 0
    return stored


def _log_mlflow_batch(
    *,
    batch_id: str,
    judge_model: str,
    request_payload: dict[str, Any],
    raw_output: str | None,
    parsed_output: dict[str, Any] | None,
    latency_ms: int | None,
    status: str,
    error: Exception | None = None,
) -> None:
    uri = os.getenv("MLFLOW_TRACKING_URI", "")
    if not uri:
        return
    try:
        import mlflow

        mlflow.set_tracking_uri(uri)
        exp = mlflow.get_experiment_by_name("cedarfix/evaluation_judge")
        exp_id = exp.experiment_id if exp else mlflow.create_experiment("cedarfix/evaluation_judge")
        with mlflow.start_run(experiment_id=exp_id, run_name=PROMPT_VERSION):
            mlflow.set_tags({
                "batch_id": batch_id,
                "service": "monitoring_service",
                "provider": "openai",
                "judge_model": judge_model,
                "prompt_version": PROMPT_VERSION,
                "status": status,
            })
            mlflow.log_param("prompt_version", PROMPT_VERSION)
            mlflow.log_param("judge_model", judge_model)
            mlflow.log_param("batch_size", len(request_payload.get("complaints", [])))
            if latency_ms is not None:
                mlflow.log_metric("latency_ms", latency_ms)
            if parsed_output and parsed_output.get("evaluations"):
                mlflow.log_metric("evaluated_count", len(parsed_output["evaluations"]))
            mlflow.log_text(JUDGE_SYSTEM_PROMPT, f"prompt/{PROMPT_VERSION}.txt")
            mlflow.log_dict(_json_safe(request_payload), "request_payload.json")
            if raw_output is not None:
                mlflow.log_text(raw_output, "raw_output.txt")
            if parsed_output is not None:
                mlflow.log_dict(_json_safe(parsed_output), "parsed_output.json")
            if error is not None:
                mlflow.set_tag("error", str(error)[:500])
    except Exception as exc:
        print(f"[evaluation-judge] MLflow logging skipped: {exc}")


def refresh_evaluation_metrics() -> dict[str, Any]:
    _ensure_table()
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT
                prompt_version,
                judge_model,
                COUNT(*) AS evaluation_count,
                AVG(routing_score)::float AS avg_routing_score,
                AVG(((COALESCE(text_score, 0) + COALESCE(image_score, 0)) / 2.0))::float
                    AS avg_extraction_score,
                AVG(overall_score)::float AS avg_overall_score
            FROM complaint_evaluations
            GROUP BY prompt_version, judge_model
        """)).mappings().all()
    snapshot: list[dict[str, Any]] = []
    for row in rows:
        labels = (row["prompt_version"], row["judge_model"])
        EVALUATION_TOTAL_GAUGE.labels(*labels).set(row["evaluation_count"] or 0)
        EVALUATION_AVG_ROUTING_SCORE.labels(*labels).set(row["avg_routing_score"] or 0.0)
        EVALUATION_AVG_EXTRACTION_SCORE.labels(*labels).set(row["avg_extraction_score"] or 0.0)
        EVALUATION_AVG_OVERALL_SCORE.labels(*labels).set(row["avg_overall_score"] or 0.0)
        snapshot.append(dict(row))
    return {"evaluations": snapshot}


async def run_daily_evaluation_once(
    judge_model: str | None = None,
    limit: int | None = None,
    complaint_id: str | None = None,
    latest: bool = False,
) -> dict[str, Any]:
    _ensure_table()
    judge_model = judge_model or DEFAULT_JUDGE_MODEL
    if complaint_id:
        rows = select_specific_complaint(complaint_id)
        selection_mode = "complaint_id"
    elif latest:
        rows = select_latest_complaints(limit or BATCH_SIZE)
        selection_mode = "latest"
    else:
        rows = select_previous_day_sample(limit_override=limit)
        selection_mode = "previous_day_sample"
    if not rows:
        refresh_evaluation_metrics()
        return {
            "status": "no_candidates",
            "prompt_version": PROMPT_VERSION,
            "judge_model": judge_model,
            "complaint_id": complaint_id,
            "selection_mode": selection_mode,
            "selected_count": 0,
            "stored_count": 0,
        }

    stored_total = 0
    failed_batches = 0
    for index in range(0, len(rows), BATCH_SIZE):
        batch = rows[index:index + BATCH_SIZE]
        batch_id = str(uuid.uuid4())
        request_payload = _build_batch_request(batch)
        started = time.time()
        raw_output: str | None = None
        parsed_output: dict[str, Any] | None = None
        try:
            parsed, raw_output, latency_ms = await _call_gpt4o_judge(request_payload, judge_model)
            parsed_output = parsed.model_dump()
            expected_ids = {row.id for row in batch}
            returned_ids = {item.complaint_id for item in parsed.evaluations}
            missing = expected_ids - returned_ids
            if missing:
                raise ValueError(f"judge response missing complaint IDs: {sorted(missing)}")
            stored = _store_evaluations(parsed.evaluations, judge_model)
            stored_total += stored
            EVALUATION_COUNT.labels(PROMPT_VERSION, judge_model, "success").inc(stored)
            EVALUATION_BATCH_DURATION.labels(PROMPT_VERSION, judge_model, "success").observe(
                max(0.0, time.time() - started)
            )
            _log_mlflow_batch(
                batch_id=batch_id,
                judge_model=judge_model,
                request_payload=request_payload,
                raw_output=raw_output,
                parsed_output=parsed_output,
                latency_ms=latency_ms,
                status="success",
            )
        except (httpx.HTTPError, ValidationError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            failed_batches += 1
            EVALUATION_COUNT.labels(PROMPT_VERSION, judge_model, "error").inc(len(batch))
            EVALUATION_BATCH_DURATION.labels(PROMPT_VERSION, judge_model, "error").observe(
                max(0.0, time.time() - started)
            )
            _log_mlflow_batch(
                batch_id=batch_id,
                judge_model=judge_model,
                request_payload=request_payload,
                raw_output=raw_output,
                parsed_output=parsed_output,
                latency_ms=None,
                status="error",
                error=exc,
            )
            print(f"[evaluation-judge] batch failed: {exc}")
        if index + BATCH_SIZE < len(rows) and BATCH_DELAY_SECONDS > 0:
            await asyncio.sleep(BATCH_DELAY_SECONDS)

    metrics = refresh_evaluation_metrics()
    return {
        "status": "completed",
        "prompt_version": PROMPT_VERSION,
        "judge_model": judge_model,
        "complaint_id": complaint_id,
        "selection_mode": selection_mode,
        "selected_count": len(rows),
        "stored_count": stored_total,
        "failed_batches": failed_batches,
        "metrics": metrics,
    }


async def scheduler_loop() -> None:
    if RUN_ON_STARTUP:
        try:
            await run_daily_evaluation_once()
        except Exception as exc:
            print(f"[evaluation-judge] startup run failed: {exc}")

    while True:
        await asyncio.sleep(_seconds_until_next_midnight())
        try:
            await run_daily_evaluation_once()
        except Exception as exc:
            print(f"[evaluation-judge] scheduled run failed: {exc}")

import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text

log = logging.getLogger(__name__)

LLM_AUDIT_ENABLED = os.getenv("LLM_AUDIT_ENABLED", "true").lower() == "true"
LLM_AUDIT_MAX_JSON_CHARS = int(os.getenv("LLM_AUDIT_MAX_JSON_CHARS", "50000"))
LLM_AUDIT_MAX_RAW_CHARS = int(os.getenv("LLM_AUDIT_MAX_RAW_CHARS", "50000"))
LLM_AUDIT_GCS_ENABLED = os.getenv("LLM_AUDIT_GCS_ENABLED", "false").lower() == "true"
LLM_AUDIT_GCS_PREFIX = os.getenv("LLM_AUDIT_GCS_PREFIX", "llm-audit")
GCS_BUCKET = os.getenv("GCS_BUCKET", "")
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "")


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=True, default=str)
        return value
    except Exception:
        return json.loads(json.dumps(value, ensure_ascii=True, default=str))


def _truncate_json(value: Any, max_chars: int = LLM_AUDIT_MAX_JSON_CHARS) -> Any:
    if value is None:
        return None
    safe = _json_safe(value)
    raw = json.dumps(safe, ensure_ascii=True, default=str)
    if len(raw) <= max_chars:
        return safe
    return {
        "_truncated": True,
        "_original_chars": len(raw),
        "preview": raw[:max_chars],
    }


def _truncate_text(value: Any, max_chars: int = LLM_AUDIT_MAX_RAW_CHARS) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value)
    if len(text_value) <= max_chars:
        return text_value
    return text_value[:max_chars] + f"... [truncated {len(text_value) - max_chars} chars]"


def _error_type(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    text_value = str(exc).lower()
    if "timeout" in name or "timeout" in text_value:
        return "timeout"
    if "connection" in name or "connect" in text_value:
        return "connection"
    if "json" in name or "json" in text_value:
        return "json_parse"
    return name or "unknown"


def _write_gcs_artifact(audit_id: str, record: dict) -> Optional[str]:
    if not LLM_AUDIT_GCS_ENABLED or not GCS_BUCKET:
        return None
    try:
        from google.cloud import storage

        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        created = datetime.utcnow().strftime("%Y/%m/%d")
        name = f"{LLM_AUDIT_GCS_PREFIX}/{created}/{audit_id}.json"
        blob = bucket.blob(name)
        blob.upload_from_string(
            json.dumps(record, ensure_ascii=False, default=str, indent=2),
            content_type="application/json",
        )
        return f"gs://{GCS_BUCKET}/{name}"
    except Exception as exc:
        log.warning("[llm-audit] GCS artifact write failed: %s", exc)
        return None


def _log_mlflow_metadata(record: dict, full_record: Optional[dict] = None) -> None:
    if not MLFLOW_TRACKING_URI:
        return
    try:
        import mlflow

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        exp = mlflow.get_experiment_by_name("cedarfix/llm_audit")
        exp_id = exp.experiment_id if exp else mlflow.create_experiment("cedarfix/llm_audit")
        with mlflow.start_run(experiment_id=exp_id, run_name=record["call_type"]):
            mlflow.set_tags({
                "audit_id": record["id"],
                "complaint_id": record.get("complaint_id") or "",
                "service": record["service"],
                "provider": record["provider"],
                "model": record["model"],
                "prompt_version": record.get("prompt_version") or "",
                "status": record["status"],
            })
            if record.get("latency_ms") is not None:
                mlflow.log_metric("latency_ms", record["latency_ms"])
            artifact_record = full_record or record
            mlflow.log_dict(
                _json_safe(artifact_record.get("request_payload")),
                "request_payload.json",
            )
            if artifact_record.get("raw_output") is not None:
                mlflow.log_text(
                    str(artifact_record["raw_output"]),
                    "raw_output.txt",
                )
            if artifact_record.get("parsed_output") is not None:
                mlflow.log_dict(
                    _json_safe(artifact_record.get("parsed_output")),
                    "parsed_output.json",
                )
            mlflow.log_dict(
                {
                    "audit_id": artifact_record.get("id"),
                    "complaint_id": artifact_record.get("complaint_id"),
                    "service": artifact_record.get("service"),
                    "call_type": artifact_record.get("call_type"),
                    "provider": artifact_record.get("provider"),
                    "model": artifact_record.get("model"),
                    "prompt_version": artifact_record.get("prompt_version"),
                    "status": artifact_record.get("status"),
                    "latency_ms": artifact_record.get("latency_ms"),
                    "error_type": artifact_record.get("error_type"),
                    "error_message": artifact_record.get("error_message"),
                },
                "audit_metadata.json",
            )
    except Exception as exc:
        log.debug("[llm-audit] MLflow metadata log skipped: %s", exc)


def write_llm_audit(
    *,
    complaint_id: Optional[str],
    service: str,
    call_type: str,
    provider: str,
    model: str,
    prompt_version: str,
    request_payload: Any,
    raw_output: Any = None,
    parsed_output: Any = None,
    status: str,
    latency_ms: Optional[int] = None,
    error: Optional[Exception] = None,
) -> None:
    if not LLM_AUDIT_ENABLED:
        return

    audit_id = str(uuid.uuid4())
    full_record = {
        "id": audit_id,
        "created_at": datetime.utcnow().isoformat(),
        "complaint_id": complaint_id,
        "service": service,
        "call_type": call_type,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "status": status,
        "latency_ms": latency_ms,
        "request_payload": _json_safe(request_payload),
        "raw_output": str(raw_output) if raw_output is not None else None,
        "parsed_output": _json_safe(parsed_output) if parsed_output is not None else None,
        "error_type": _error_type(error) if error else None,
        "error_message": str(error) if error else None,
    }
    artifact_uri = _write_gcs_artifact(audit_id, full_record)

    record = {
        "id": audit_id,
        "created_at": full_record["created_at"],
        "complaint_id": complaint_id,
        "service": service,
        "call_type": call_type,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "status": status,
        "latency_ms": latency_ms,
        "request_payload": _truncate_json(request_payload),
        "raw_output": _truncate_text(raw_output),
        "parsed_output": _truncate_json(parsed_output),
        "error_type": full_record["error_type"],
        "error_message": _truncate_text(error) if error else None,
        "artifact_uri": artifact_uri,
    }

    try:
        from cedarfix_shared.db import engine

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO llm_audit_logs (
                    id, complaint_id, service, call_type, provider, model,
                    prompt_version, status, latency_ms, request_payload,
                    raw_output, parsed_output, error_type, error_message,
                    artifact_uri
                )
                VALUES (
                    :id, :complaint_id, :service, :call_type, :provider, :model,
                    :prompt_version, :status, :latency_ms, CAST(:request_payload AS JSONB),
                    :raw_output, CAST(:parsed_output AS JSONB), :error_type,
                    :error_message, :artifact_uri
                )
            """), {
                **record,
                "request_payload": json.dumps(record["request_payload"], ensure_ascii=False, default=str),
                "parsed_output": json.dumps(record["parsed_output"], ensure_ascii=False, default=str)
                if record["parsed_output"] is not None else None,
            })
    except Exception as exc:
        log.warning("[llm-audit] Postgres audit write failed: %s", exc)

    _log_mlflow_metadata(record, full_record)


@asynccontextmanager
async def llm_audit_context(
    *,
    complaint_id: Optional[str],
    service: str,
    call_type: str,
    provider: str,
    model: str,
    prompt_version: str,
    request_payload: Any,
):
    start = time.time()
    state: dict[str, Any] = {"raw_output": None, "parsed_output": None}
    try:
        yield state
        write_llm_audit(
            complaint_id=complaint_id,
            service=service,
            call_type=call_type,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            request_payload=request_payload,
            raw_output=state.get("raw_output"),
            parsed_output=state.get("parsed_output"),
            status="success",
            latency_ms=int((time.time() - start) * 1000),
        )
    except Exception as exc:
        write_llm_audit(
            complaint_id=complaint_id,
            service=service,
            call_type=call_type,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            request_payload=request_payload,
            raw_output=state.get("raw_output"),
            parsed_output=state.get("parsed_output"),
            status="error",
            latency_ms=int((time.time() - start) * 1000),
            error=exc,
        )
        raise

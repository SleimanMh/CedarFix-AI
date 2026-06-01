"""IEP-3 Redis Streams worker — calibrated routing and priority.

Reads from  cedarfix:iep3:jobs
Writes to   cedarfix:iep4:jobs  (after updating the DB)

Consumer group: iep3-workers
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import select, update

from src.eep.db import Complaint, SessionLocal
from src.eep.models import ComplaintState
from src.eep.queue import STREAM_IEP3, STREAM_IEP4, STREAM_IEP6
from src.iep3.router import compute_routing_risk, route as legacy_route
from src.route_complaint import route as kb_route
from src.shared import metrics as M
from src.shared.schemas import RoutingDecisionEvidence

logger = logging.getLogger("iep3.worker")

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CONSUMER_GROUP = "iep3-workers"
CONSUMER_NAME = os.getenv("HOSTNAME", "iep3-0")
BLOCK_MS = 2_000
BATCH_SIZE = 5

_CONFIDENCE_TO_FLOAT = {
    "high": 0.82,
    "medium_high": 0.78,
    "medium": 0.68,
    "low": 0.45,
}

_KB_PROMOTION_SECTORS = {
    "WATER": {"WATER", "FLOODING", "OTHER", "UNKNOWN", ""},
    "ELECTRICITY": {"ELECTRICITY", "OTHER", "UNKNOWN", ""},
    "ROADS": {"ROADS", "OTHER", "UNKNOWN", ""},
    "WASTE": {"WASTE", "OTHER", "UNKNOWN", ""},
    "TELECOM": {"TELECOM", "OTHER", "UNKNOWN", ""},
    "FLOODING": {"FLOODING", "WATER", "ROADS", "OTHER", "UNKNOWN", ""},
    "SAFETY": {"SAFETY", "WATER", "ELECTRICITY", "FLOODING", "ROADS", "OTHER", "UNKNOWN", ""},
    "ENVIRONMENT": {"ENVIRONMENT", "OTHER", "UNKNOWN", ""},
}


async def _ensure_group(r: aioredis.Redis) -> None:
    try:
        await r.xgroup_create(STREAM_IEP3, CONSUMER_GROUP, id="0", mkstream=True)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _set_error_flag(complaint_id: str, flag: str) -> None:
    async with SessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Complaint).where(Complaint.id == complaint_id)
        )
        complaint = result.scalar_one_or_none()
        if complaint:
            flags = list(complaint.error_flags or [])
            flags.append(flag)
            await session.execute(
                update(Complaint)
                .where(Complaint.id == complaint_id)
                .values(error_flags=flags)
            )
            await session.commit()


def _route_text(text_raw: str | None, normalized_text: str | None) -> str:
    parts = [part.strip() for part in (text_raw, normalized_text) if part and part.strip()]
    if len(parts) == 2 and parts[1] in parts[0]:
        return parts[0]
    return "\n".join(parts)


def _confidence_value(label: str | None, fallback: float) -> float:
    return _CONFIDENCE_TO_FLOAT.get((label or "").lower(), fallback)


def _db_entity(entity: str | None) -> tuple[str, str | None]:
    value = (entity or "").strip() or "HITL"
    if len(value) <= 16:
        return value, None
    return "HITL", value


def _hitl_reason(kb_result, fallback: str | None, boundary_entity: str | None) -> str | None:
    if boundary_entity:
        reason = f"kb_boundary:{boundary_entity}"
    elif kb_result.hitl_reason_codes:
        reason = "kb:" + ",".join(kb_result.hitl_reason_codes[:4])
    elif kb_result.hitl_reason:
        reason = "kb:" + kb_result.hitl_reason
    else:
        reason = fallback
    if reason and len(reason) > 128:
        return reason[:125] + "..."
    return reason


def _hitl_reason_codes(hitl_reason: str | None) -> list[str]:
    if not hitl_reason:
        return []
    if hitl_reason.startswith("kb:"):
        return [code.strip() for code in hitl_reason[3:].split(",") if code.strip()]
    if hitl_reason.startswith("kb_boundary:"):
        return ["kb_boundary_entity"]
    return [hitl_reason]


def _build_routing_intelligence(
    complaint_id: str,
    decision: dict,
    issue_type: str | None,
    issue_type_confidence: float | None,
    hitl_required: bool,
    hitl_reason: str | None,
) -> dict:
    shap_top3 = dict(decision.get("shap_top3") or {})
    router_version = str(shap_top3.get("router_version") or "sector_agency_map")
    routing_confidence = float(decision.get("routing_confidence") or 0.0)
    return RoutingDecisionEvidence(
        complaint_id=complaint_id,
        router_version=router_version,
        routing_sector=str(decision.get("routing_sector") or "OTHER"),
        routing_entity=str(decision.get("routing_entity") or "HITL"),
        routing_confidence=routing_confidence,
        priority_score=float(decision.get("priority_score") or 0.0),
        hitl_required=hitl_required,
        hitl_reason=hitl_reason,
        hitl_reason_codes=_hitl_reason_codes(hitl_reason),
        auto_route_eligible=(not hitl_required and routing_confidence >= 0.65),
        issue_type=issue_type,
        issue_type_confidence=issue_type_confidence,
        kb_route_reason=shap_top3.get("kb_route_reason"),
        kb_complaint_type_id=shap_top3.get("kb_complaint_type_id"),
        kb_complaint_type=shap_top3.get("kb_complaint_type"),
        kb_primary_entity_raw=shap_top3.get("kb_primary_entity_raw"),
        kb_secondary_entity=shap_top3.get("kb_secondary_entity"),
        kb_location_method=shap_top3.get("kb_location_method"),
        kb_municipality_id=shap_top3.get("kb_municipality_id"),
        kb_municipality_name=shap_top3.get("kb_municipality_name"),
        kb_boundary_entity=shap_top3.get("kb_boundary_entity"),
        kb_warnings=shap_top3.get("kb_warnings") or [],
        shap_top3=shap_top3,
        routing_risk_score=shap_top3.get("routing_risk_score"),
        routing_risk_factors=shap_top3.get("routing_risk_factors") or [],
        neuro_symbolic_trace=shap_top3.get("neuro_symbolic_trace") or {},
    ).model_dump(mode="json")


def _model_rules_disagreement(iep1_signal_json: dict | None) -> bool:
    trace = (iep1_signal_json or {}).get("classification_trace") or {}
    risks = ((trace.get("hybrid") or {}).get("risk_reasons") or [])
    return any("model_rules_" in str(reason) for reason in risks)


def _route_with_kb(
    complaint_id: str,
    text_raw: str | None,
    normalized_text: str | None,
    routing_sector: str | None,
    issue_type: str | None,
    issue_type_confidence: float | None,
    drift_score: int | None,
    gps_lat: float | None,
    gps_lon: float | None,
    iep1_signal_json: dict | None = None,
) -> dict:
    legacy_decision = legacy_route(
        complaint_id=complaint_id,
        routing_sector=routing_sector,
        issue_type=issue_type,
        issue_type_confidence=issue_type_confidence,
        drift_score=drift_score,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
    )

    route_text = _route_text(text_raw, normalized_text)
    if not route_text:
        return legacy_decision

    try:
        kb_result = kb_route(
            complaint_text=route_text,
            gps_lat=gps_lat,
            gps_lon=gps_lon,
        )
    except Exception as exc:  # noqa: BLE001 - keep IEP-3 durable if KB routing fails
        logger.warning("KB router fallback complaint=%s: %s", complaint_id, exc, exc_info=True)
        return legacy_decision

    kb_sector = (kb_result.sector or "UNKNOWN").upper()
    legacy_sector = (legacy_decision.get("routing_sector") or "UNKNOWN").upper()
    allowed_legacy_sectors = _KB_PROMOTION_SECTORS.get(kb_sector)
    if not allowed_legacy_sectors or legacy_sector not in allowed_legacy_sectors:
        return legacy_decision

    entity, boundary_entity = _db_entity(kb_result.primary_entity)
    hitl_required = bool(kb_result.hitl_required) or bool(legacy_decision.get("hitl_required")) or bool(boundary_entity)
    confidence = _confidence_value(kb_result.confidence, legacy_decision.get("routing_confidence", 0.5))
    if hitl_required:
        confidence = min(confidence, 0.60)

    shap_top3 = dict(legacy_decision.get("shap_top3") or {})
    shap_top3.update(
        {
            "router_version": "route_complaint_kb",
            "kb_route_reason": kb_result.reason,
            "kb_complaint_type_id": kb_result.complaint_type_id,
            "kb_complaint_type": kb_result.complaint_type,
            "kb_primary_entity_raw": kb_result.primary_entity,
            "kb_secondary_entity": kb_result.secondary_entity,
            "kb_location_method": kb_result.location_method,
            "kb_municipality_id": kb_result.municipality_id,
            "kb_municipality_name": kb_result.municipality_name,
            "kb_warnings": kb_result.warnings[:5],
        }
    )
    if boundary_entity:
        shap_top3["kb_boundary_entity"] = boundary_entity

    risk_packet = compute_routing_risk(
        routing_confidence=confidence,
        issue_type_confidence=issue_type_confidence,
        drift_score=drift_score,
        hitl_required=hitl_required,
        kb_warnings=kb_result.warnings[:5],
        kb_location_method=kb_result.location_method,
        boundary_entity=boundary_entity,
        model_rules_disagreement=_model_rules_disagreement(iep1_signal_json),
    )
    shap_top3.update(
        {
            "routing_risk_score": risk_packet["routing_risk_score"],
            "routing_risk_factors": risk_packet["routing_risk_factors"],
            "neuro_symbolic_trace": {
                "ai_layer": "iep1_model_and_confidence",
                "symbolic_layer": "route_complaint_kb",
                "safety_layer": "hitl_gates_and_risk_model",
                "auto_route_allowed": not hitl_required and risk_packet["routing_risk_score"] < 0.55,
            },
        }
    )
    if risk_packet["routing_risk_score"] >= 0.55 and not hitl_required:
        hitl_required = True
        shap_top3["risk_forced_hitl"] = True

    decision = dict(legacy_decision)
    decision.update(
        {
            "routing_sector": kb_sector,
            "routing_entity": entity,
            "routing_confidence": round(confidence, 4),
            "hitl_required": hitl_required,
            "hitl_reason": (
                "routing_risk_model"
                if shap_top3.get("risk_forced_hitl")
                else _hitl_reason(kb_result, legacy_decision.get("hitl_reason"), boundary_entity)
            ),
            "shap_top3": shap_top3,
        }
    )
    return decision


async def _process_message(r: aioredis.Redis, msg_id: str, data: dict) -> None:
    complaint_id: str = data.get("complaint_id", "")
    logger.info("IEP-3 processing complaint=%s", complaint_id)

    # Fetch signals from DB
    async with SessionLocal() as session:
        result = await session.execute(
            select(
                Complaint.routing_sector,
                Complaint.issue_type,
                Complaint.issue_type_confidence,
                Complaint.text_raw,
                Complaint.normalized_text,
                Complaint.drift_score,
                Complaint.iep1_signal_json,
                Complaint.gps_lat,
                Complaint.gps_lon,
                Complaint.hitl_required,
                Complaint.hitl_reason,
                (Complaint.image_b64.isnot(None)).label("has_image"),
            ).where(Complaint.id == complaint_id)
        )
        row = result.one_or_none()
        if row is None:
            logger.warning("IEP-3: complaint %s not found", complaint_id)
            await r.xack(STREAM_IEP3, CONSUMER_GROUP, msg_id)
            return

    try:
        decision = _route_with_kb(
            complaint_id=complaint_id,
            text_raw=row.text_raw,
            normalized_text=row.normalized_text,
            routing_sector=row.routing_sector,
            issue_type=row.issue_type,
            issue_type_confidence=row.issue_type_confidence,
            drift_score=row.drift_score,
            gps_lat=row.gps_lat,
            gps_lon=row.gps_lon,
            iep1_signal_json=row.iep1_signal_json,
        )
    except Exception as exc:
        logger.error("IEP-3 route failed complaint=%s: %s", complaint_id, exc, exc_info=True)
        await _set_error_flag(complaint_id, f"iep3_route_error:{type(exc).__name__}")
        await r.xack(STREAM_IEP3, CONSUMER_GROUP, msg_id)
        return

    # Merge HITL flags: if IEP-1 already set hitl, keep it
    hitl_required = decision["hitl_required"] or bool(row.hitl_required)
    hitl_reason = decision.get("hitl_reason") or row.hitl_reason
    routing_intelligence = _build_routing_intelligence(
        complaint_id=complaint_id,
        decision=decision,
        issue_type=row.issue_type,
        issue_type_confidence=row.issue_type_confidence,
        hitl_required=hitl_required,
        hitl_reason=hitl_reason,
    )

    next_state = (
        ComplaintState.HITL_REQUIRED if hitl_required else ComplaintState.PARTIALLY_PROCESSED
    )

    async with SessionLocal() as session:
        await session.execute(
            update(Complaint)
            .where(Complaint.id == complaint_id)
            .values(
                routing_sector=decision["routing_sector"],
                routing_entity=decision["routing_entity"],
                routing_confidence=decision["routing_confidence"],
                priority_score=decision["priority_score"],
                hitl_required=hitl_required,
                hitl_reason=hitl_reason,
                shap_top3=decision["shap_top3"],
                iep3_routing_json=routing_intelligence,
                state=next_state.value,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    # Routing observability: confidence + priority distributions per sector.
    _sector_label = decision["routing_sector"] or "unknown"
    M.ROUTING_CONFIDENCE.labels(sector=_sector_label).observe(
        float(decision["routing_confidence"])
    )
    M.IEP3_PRIORITY_SCORE.labels(sector=_sector_label).observe(
        float(decision["priority_score"])
    )

    # Forward to IEP-6 (image fusion) when a photo is present, otherwise
    # straight to IEP-4 for explanation. IEP-6 forwards on to IEP-4 itself.
    if getattr(row, "has_image", False):
        await r.xadd(
            STREAM_IEP6,
            {
                "complaint_id": complaint_id,
                "image_b64": "",  # IEP-6 reads the image from the DB
            },
        )
    else:
        await r.xadd(
            STREAM_IEP4,
            {
                "complaint_id": complaint_id,
                "routing_sector": decision["routing_sector"],
                "routing_entity": decision["routing_entity"],
                "hitl_required": "true" if hitl_required else "false",
            },
        )

    await r.xack(STREAM_IEP3, CONSUMER_GROUP, msg_id)
    logger.info(
        "IEP-3 done complaint=%s sector=%s entity=%s conf=%.3f priority=%.1f hitl=%s",
        complaint_id,
        decision["routing_sector"],
        decision["routing_entity"],
        decision["routing_confidence"],
        decision["priority_score"],
        hitl_required,
    )


async def run_worker() -> None:
    r = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    await _ensure_group(r)
    logger.info("IEP-3 worker started, consuming %s", STREAM_IEP3)

    while True:
        try:
            results = await r.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_IEP3: ">"},
                count=BATCH_SIZE,
                block=BLOCK_MS,
            )
            if not results:
                continue
            for _stream, messages in results:
                for msg_id, data in messages:
                    await _process_message(r, msg_id, data)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("IEP-3 worker loop error: %s", exc, exc_info=True)
            await asyncio.sleep(1.0)

    await r.aclose()

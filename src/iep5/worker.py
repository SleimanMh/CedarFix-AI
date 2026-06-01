"""IEP-5 Redis Streams worker — incident lifecycle state machine.

Reads from  cedarfix:iep5:jobs   (enqueued by IEP-4 after the terminal stage)

Responsibilities:
- Maintain an event-sourced incident lifecycle (append-only events table +
  current-state projection).
- Detect REOPENED incidents (a new complaint attaching to a resolved/closed
  incident) and emit a RetrainingCandidate — the project's core
  "reopen = retraining signal" novelty.

Consumer group: iep5-workers
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import func, select, update

from src.eep.db import (
    Complaint,
    Incident,
    IncidentLifecycleEvent,
    RetrainingCandidate,
    SessionLocal,
)
from src.eep.queue import STREAM_IEP5
from src.iep5.lifecycle import plan_event_for_new_complaint
from src.iep5.risk import score_retraining_priority
from src.shared import metrics as M
from src.shared.lifecycle_schemas import (
    InvalidTransition,
    IncidentState,
    LifecycleEventType,
    is_reopen_trigger,
    next_state,
)

logger = logging.getLogger("iep5.worker")

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CONSUMER_GROUP = "iep5-workers"
CONSUMER_NAME = os.getenv("HOSTNAME", "iep5-0")
BLOCK_MS = 2_000
BATCH_SIZE = 5


async def _ensure_group(r: aioredis.Redis) -> None:
    try:
        await r.xgroup_create(STREAM_IEP5, CONSUMER_GROUP, id="0", mkstream=True)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _append_event(
    session,
    *,
    incident_id: str,
    complaint_id: str | None,
    from_state: IncidentState | None,
    to_state: IncidentState,
    event: LifecycleEventType,
    reason: str,
    actor: str = "system",
) -> None:
    session.add(
        IncidentLifecycleEvent(
            id=str(uuid.uuid4()),
            incident_id=incident_id,
            complaint_id=complaint_id,
            from_state=from_state.value if from_state else None,
            to_state=to_state.value,
            event=event.value,
            reason=reason[:256],
            actor=actor,
        )
    )


async def _emit_retraining_candidate(
    session,
    *,
    complaint_id: str,
    incident_id: str | None,
    source: str,
    reason: str,
    original_routing: dict | None,
) -> None:
    priority = score_retraining_priority(
        source=source,
        reason=reason,
        original_routing=original_routing,
    )
    enriched_routing = dict(original_routing or {})
    enriched_routing.update(priority)
    session.add(
        RetrainingCandidate(
            id=str(uuid.uuid4()),
            complaint_id=complaint_id,
            incident_id=incident_id,
            source=source,
            reason=reason[:256],
            original_routing=enriched_routing,
            status="pending",
        )
    )


async def _apply_new_complaint(
    *,
    complaint_id: str,
    incident_id: str,
    routing_json: dict,
) -> None:
    """Create or advance an incident in response to a routed complaint."""
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        existing = (
            await session.execute(
                select(Incident).where(Incident.incident_id == incident_id)
            )
        ).scalar_one_or_none()

        current = IncidentState(existing.current_state) if existing else None
        plan = plan_event_for_new_complaint(current)

        if existing is None:
            session.add(
                Incident(
                    incident_id=incident_id,
                    current_state=plan.to_state.value,
                    complaint_count=1,
                    reopen_count=0,
                    routing_sector=routing_json.get("routing_sector"),
                    routing_entity=routing_json.get("routing_entity"),
                    last_routing_json=routing_json,
                    first_seen_at=now,
                    last_event_at=now,
                )
            )
            await _append_event(
                session,
                incident_id=incident_id,
                complaint_id=complaint_id,
                from_state=None,
                to_state=plan.to_state,
                event=plan.event,
                reason=plan.reason,
            )
        else:
            values: dict = {
                "current_state": plan.to_state.value,
                "complaint_count": existing.complaint_count + 1,
                "last_event_at": now,
                "last_routing_json": routing_json or existing.last_routing_json,
                "routing_sector": routing_json.get("routing_sector")
                or existing.routing_sector,
                "routing_entity": routing_json.get("routing_entity")
                or existing.routing_entity,
            }
            if plan.is_reopen:
                values["reopen_count"] = existing.reopen_count + 1
                values["resolved_at"] = None
            await session.execute(
                update(Incident)
                .where(Incident.incident_id == incident_id)
                .values(**values)
            )
            await _append_event(
                session,
                incident_id=incident_id,
                complaint_id=complaint_id,
                from_state=current,
                to_state=plan.to_state,
                event=plan.event,
                reason=plan.reason,
            )
            if plan.is_reopen:
                await _emit_retraining_candidate(
                    session,
                    complaint_id=complaint_id,
                    incident_id=incident_id,
                    source="reopen",
                    reason=plan.reason,
                    original_routing=existing.last_routing_json,
                )
                M.IEP5_REOPEN_TOTAL.labels(
                    sector=(routing_json.get("routing_sector") or existing.routing_sector or "unknown")
                ).inc()
                # Mark the complaint as needing review — a reopen means the
                # earlier resolution did not hold.
                await session.execute(
                    update(Complaint)
                    .where(Complaint.id == complaint_id)
                    .values(hitl_required=True, hitl_reason="incident_reopened")
                )
                logger.info(
                    "IEP-5 REOPEN incident=%s complaint=%s -> retraining candidate",
                    incident_id,
                    complaint_id,
                )

        await session.commit()


async def transition_incident(
    incident_id: str,
    event: LifecycleEventType,
    *,
    actor: str = "operator",
    reason: str = "",
    complaint_id: str | None = None,
) -> IncidentState:
    """Apply an operator-driven transition; raises InvalidTransition if illegal."""
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        existing = (
            await session.execute(
                select(Incident).where(Incident.incident_id == incident_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            raise InvalidTransition(f"unknown incident {incident_id}")
        current = IncidentState(existing.current_state)
        target = next_state(current, event)
        values: dict = {"current_state": target.value, "last_event_at": now}
        if target == IncidentState.RESOLVED:
            values["resolved_at"] = now
        await session.execute(
            update(Incident).where(Incident.incident_id == incident_id).values(**values)
        )
        await _append_event(
            session,
            incident_id=incident_id,
            complaint_id=complaint_id,
            from_state=current,
            to_state=target,
            event=event,
            reason=reason or f"operator_{event.value}",
            actor=actor,
        )
        await session.commit()
        return target


async def scan_for_stale_reopens() -> int:
    """Scheduled scan: resolved incidents that gained complaints post-resolution.

    Belt-and-braces alongside the event-driven path — catches reopen signals
    even if a complaint slipped in without a lifecycle event (e.g. backfill).
    Returns the number of reopen candidates emitted.
    """
    emitted = 0
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Incident).where(
                    Incident.current_state.in_(
                        [IncidentState.RESOLVED.value, IncidentState.CLOSED.value]
                    )
                )
            )
        ).scalars().all()
        for incident in rows:
            if incident.resolved_at is None:
                continue
            newer = (
                await session.execute(
                    select(func.count(Complaint.id)).where(
                        Complaint.incident_id == incident.incident_id,
                        Complaint.created_at > incident.resolved_at,
                    )
                )
            ).scalar_one()
            already = (
                await session.execute(
                    select(func.count(RetrainingCandidate.id)).where(
                        RetrainingCandidate.incident_id == incident.incident_id,
                        RetrainingCandidate.source == "reopen",
                    )
                )
            ).scalar_one()
            if newer and not already:
                await _emit_retraining_candidate(
                    session,
                    complaint_id=f"scan:{incident.incident_id}",
                    incident_id=incident.incident_id,
                    source="reopen",
                    reason="scheduled_scan_detected_post_resolution_complaint",
                    original_routing=incident.last_routing_json,
                )
                emitted += 1
        if emitted:
            await session.commit()
    if emitted:
        logger.info("IEP-5 scheduled scan emitted %d reopen candidate(s)", emitted)
    return emitted


async def _process_message(r: aioredis.Redis, msg_id: str, data: dict) -> None:
    complaint_id: str = data.get("complaint_id", "")
    incident_id: str = data.get("incident_id", "") or complaint_id
    raw_routing = data.get("routing_json", "") or ""
    try:
        routing_json = json.loads(raw_routing) if raw_routing else {}
    except json.JSONDecodeError:
        routing_json = {}

    try:
        await _apply_new_complaint(
            complaint_id=complaint_id,
            incident_id=incident_id,
            routing_json=routing_json,
        )
    except Exception as exc:  # noqa: BLE001 - keep the consumer durable
        logger.error(
            "IEP-5 lifecycle failed complaint=%s incident=%s: %s",
            complaint_id,
            incident_id,
            exc,
            exc_info=True,
        )

    await r.xack(STREAM_IEP5, CONSUMER_GROUP, msg_id)


async def run_worker() -> None:
    r = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    await _ensure_group(r)
    logger.info("IEP-5 worker started, consuming %s", STREAM_IEP5)
    try:
        while True:
            try:
                results = await r.xreadgroup(
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    {STREAM_IEP5: ">"},
                    count=BATCH_SIZE,
                    block=BLOCK_MS,
                )
                if not results:
                    continue
                for _stream, messages in results:
                    for msg_id, data in messages:
                        await _process_message(r, msg_id, data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("IEP-5 worker loop error: %s", exc, exc_info=True)
                await asyncio.sleep(1.0)
    finally:
        await r.aclose()
        logger.info("IEP-5 worker stopped")

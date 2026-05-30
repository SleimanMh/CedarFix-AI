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
from src.eep.queue import STREAM_IEP3, STREAM_IEP4
from src.iep3.router import route

logger = logging.getLogger("iep3.worker")

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CONSUMER_GROUP = "iep3-workers"
CONSUMER_NAME = os.getenv("HOSTNAME", "iep3-0")
BLOCK_MS = 2_000
BATCH_SIZE = 5


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
                Complaint.drift_score,
                Complaint.gps_lat,
                Complaint.gps_lon,
                Complaint.hitl_required,
            ).where(Complaint.id == complaint_id)
        )
        row = result.one_or_none()
        if row is None:
            logger.warning("IEP-3: complaint %s not found", complaint_id)
            await r.xack(STREAM_IEP3, CONSUMER_GROUP, msg_id)
            return

    try:
        decision = route(
            complaint_id=complaint_id,
            routing_sector=row.routing_sector,
            issue_type=row.issue_type,
            issue_type_confidence=row.issue_type_confidence,
            drift_score=row.drift_score,
            gps_lat=row.gps_lat,
            gps_lon=row.gps_lon,
        )
    except Exception as exc:
        logger.error("IEP-3 route failed complaint=%s: %s", complaint_id, exc, exc_info=True)
        await _set_error_flag(complaint_id, f"iep3_route_error:{type(exc).__name__}")
        await r.xack(STREAM_IEP3, CONSUMER_GROUP, msg_id)
        return

    # Merge HITL flags: if IEP-1 already set hitl, keep it
    hitl_required = decision["hitl_required"] or bool(row.hitl_required)
    hitl_reason = decision.get("hitl_reason")

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
                state=next_state.value,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    # Always forward to IEP-4 for explanation generation
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

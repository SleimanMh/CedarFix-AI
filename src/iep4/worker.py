"""IEP-4 Redis Streams worker — explanation and HITL decision support.

Reads from  cedarfix:iep4:jobs
Terminal stage — writes citizen/admin explanations back to DB.

Consumer group: iep4-workers
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
from src.eep.queue import STREAM_IEP4
from src.iep4.explainer import explain

logger = logging.getLogger("iep4.worker")

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CONSUMER_GROUP = "iep4-workers"
CONSUMER_NAME = os.getenv("HOSTNAME", "iep4-0")
BLOCK_MS = 2_000
BATCH_SIZE = 5


async def _ensure_group(r: aioredis.Redis) -> None:
    try:
        await r.xgroup_create(STREAM_IEP4, CONSUMER_GROUP, id="0", mkstream=True)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _set_error_flag(complaint_id: str, flag: str) -> None:
    async with SessionLocal() as session:
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
    logger.info("IEP-4 processing complaint=%s", complaint_id)

    # Fetch full complaint context from DB
    async with SessionLocal() as session:
        result = await session.execute(
            select(
                Complaint.routing_sector,
                Complaint.routing_entity,
                Complaint.routing_confidence,
                Complaint.priority_score,
                Complaint.issue_type,
                Complaint.gps_lat,
                Complaint.gps_lon,
                Complaint.hitl_required,
            ).where(Complaint.id == complaint_id)
        )
        row = result.one_or_none()
        if row is None:
            logger.warning("IEP-4: complaint %s not found", complaint_id)
            await r.xack(STREAM_IEP4, CONSUMER_GROUP, msg_id)
            return

    try:
        explanations = explain(
            complaint_id=complaint_id,
            routing_sector=row.routing_sector,
            routing_entity=row.routing_entity,
            routing_confidence=row.routing_confidence,
            priority_score=row.priority_score,
            issue_type=row.issue_type,
            gps_lat=row.gps_lat,
            gps_lon=row.gps_lon,
            hitl_required=bool(row.hitl_required),
        )
    except Exception as exc:
        logger.error("IEP-4 explain failed complaint=%s: %s", complaint_id, exc, exc_info=True)
        await _set_error_flag(complaint_id, f"iep4_explain_error:{type(exc).__name__}")
        await r.xack(STREAM_IEP4, CONSUMER_GROUP, msg_id)
        return

    # Final state: HITL_REQUIRED stays if already set, otherwise PROCESSED
    final_state = (
        ComplaintState.HITL_REQUIRED if row.hitl_required
        else ComplaintState.PROCESSED
    )

    async with SessionLocal() as session:
        await session.execute(
            update(Complaint)
            .where(Complaint.id == complaint_id)
            .values(
                citizen_explanation=explanations["citizen_explanation"],
                admin_explanation=explanations["admin_explanation"],
                state=final_state.value,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    await r.xack(STREAM_IEP4, CONSUMER_GROUP, msg_id)
    logger.info(
        "IEP-4 done complaint=%s state=%s",
        complaint_id,
        final_state.value,
    )


async def run_worker() -> None:
    r = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    await _ensure_group(r)
    logger.info("IEP-4 worker started, consuming %s", STREAM_IEP4)

    while True:
        try:
            results = await r.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_IEP4: ">"},
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
            logger.error("IEP-4 worker loop error: %s", exc, exc_info=True)
            await asyncio.sleep(1.0)

    await r.aclose()

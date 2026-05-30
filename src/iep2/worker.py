"""IEP-2 Redis Streams worker — duplicate/cluster detection.

Reads from  cedarfix:iep2:jobs
Writes to   cedarfix:iep3:jobs  (after updating the DB)

Consumer group: iep2-workers
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import select, update

from src.eep.db import Complaint, SessionLocal
from src.eep.models import ComplaintState
from src.eep.queue import STREAM_IEP2, STREAM_IEP3
from src.iep2.dedup import classify_pair

logger = logging.getLogger("iep2.worker")

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CONSUMER_GROUP = "iep2-workers"
CONSUMER_NAME = os.getenv("HOSTNAME", "iep2-0")
BLOCK_MS = 2_000
BATCH_SIZE = 5
# Maximum candidates to pull from DB for dedup comparison
CANDIDATE_WINDOW = 200


async def _ensure_group(r: aioredis.Redis) -> None:
    try:
        await r.xgroup_create(STREAM_IEP2, CONSUMER_GROUP, id="0", mkstream=True)
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


async def _fetch_candidates(complaint_id: str, issue_type: str | None) -> list[dict]:
    """Pull recent resolved complaints to compare against."""
    async with SessionLocal() as session:
        stmt = (
            select(
                Complaint.id,
                Complaint.incident_id,
                Complaint.text_embedding_ref,
                Complaint.gps_lat,
                Complaint.gps_lon,
                Complaint.issue_type,
            )
            .where(Complaint.id != complaint_id)
            .where(Complaint.incident_id.is_not(None))
            .order_by(Complaint.created_at.desc())
            .limit(CANDIDATE_WINDOW)
        )
        rows = (await session.execute(stmt)).all()
        return [
            {
                "complaint_id": r.id,
                "incident_id": r.incident_id,
                "text_embedding_ref": r.text_embedding_ref,
                "gps_lat": r.gps_lat,
                "gps_lon": r.gps_lon,
                "issue_type": r.issue_type,
            }
            for r in rows
        ]


async def _process_message(r: aioredis.Redis, msg_id: str, data: dict) -> None:
    complaint_id: str = data.get("complaint_id", "")
    issue_type: str | None = data.get("issue_type") or None
    embedding_ref: str | None = data.get("embedding_ref") or None

    logger.info("IEP-2 processing complaint=%s", complaint_id)

    # Fetch current complaint's GPS
    async with SessionLocal() as session:
        result = await session.execute(
            select(Complaint.gps_lat, Complaint.gps_lon, Complaint.text_embedding_ref)
            .where(Complaint.id == complaint_id)
        )
        row = result.one_or_none()
        if row is None:
            logger.warning("IEP-2: complaint %s not found in DB", complaint_id)
            await r.xack(STREAM_IEP2, CONSUMER_GROUP, msg_id)
            return
        gps_lat, gps_lon = row.gps_lat, row.gps_lon
        if embedding_ref is None:
            embedding_ref = row.text_embedding_ref

    try:
        candidates = await _fetch_candidates(complaint_id, issue_type)
        decision = classify_pair(
            complaint_id=complaint_id,
            embedding_ref=embedding_ref,
            lat=gps_lat,
            lon=gps_lon,
            issue_type=issue_type,
            candidates=candidates,
        )
    except Exception as exc:
        logger.error("IEP-2 dedup failed complaint=%s: %s", complaint_id, exc, exc_info=True)
        await _set_error_flag(complaint_id, f"iep2_dedup_error:{type(exc).__name__}")
        await r.xack(STREAM_IEP2, CONSUMER_GROUP, msg_id)
        return

    next_state = ComplaintState.PARTIALLY_PROCESSED

    async with SessionLocal() as session:
        await session.execute(
            update(Complaint)
            .where(Complaint.id == complaint_id)
            .values(
                is_duplicate=decision["is_duplicate"],
                incident_id=decision["incident_id"],
                state=next_state.value,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    # Always pass to IEP-3 — routing needs to happen even for duplicates
    await r.xadd(
        STREAM_IEP3,
        {
            "complaint_id": complaint_id,
            "issue_type": issue_type or "",
            "incident_id": decision["incident_id"],
        },
    )

    await r.xack(STREAM_IEP2, CONSUMER_GROUP, msg_id)
    logger.info(
        "IEP-2 done complaint=%s dup=%s incident=%s",
        complaint_id,
        decision["is_duplicate"],
        decision["incident_id"],
    )


async def run_worker() -> None:
    r = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    await _ensure_group(r)
    logger.info("IEP-2 worker started, consuming %s", STREAM_IEP2)

    while True:
        try:
            results = await r.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_IEP2: ">"},
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
            logger.error("IEP-2 worker loop error: %s", exc, exc_info=True)
            await asyncio.sleep(1.0)

    await r.aclose()

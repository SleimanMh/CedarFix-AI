"""IEP-1 Redis Streams consumer group worker.

Reads from  cedarfix:iep1:jobs
Writes to   cedarfix:iep2:jobs  (after updating the DB)

Consumer group: iep1-workers
Consumer name:  $HOSTNAME (or iep1-0)

Reliability:
- Messages are only ACK'd after a successful DB write.
- On per-message failure the message stays in the PEL (pending entries list).
- EEP marks the complaint with an error_flag instead of crashing the pipeline.
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
from src.eep.queue import STREAM_IEP1, STREAM_IEP2
from src.iep1.extractor import extract
from src.shared import metrics as M
from src.shared.schemas import IEP1LanguageSignal

logger = logging.getLogger("iep1.worker")

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CONSUMER_GROUP = "iep1-workers"
CONSUMER_NAME = os.getenv("HOSTNAME", "iep1-0")
BLOCK_MS = 2_000  # block up to 2 s per XREADGROUP call
BATCH_SIZE = 5


async def _ensure_group(r: aioredis.Redis) -> None:
    """Create the consumer group if it doesn't exist yet."""
    try:
        await r.xgroup_create(STREAM_IEP1, CONSUMER_GROUP, id="0", mkstream=True)
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
    text: str = data.get("text", "")
    language_hint: str | None = data.get("language_hint") or None

    logger.info("IEP-1 processing complaint=%s", complaint_id)

    try:
        result = extract(complaint_id, text, language_hint)
    except Exception as exc:
        logger.error("IEP-1 extract failed complaint=%s: %s", complaint_id, exc, exc_info=True)
        await _set_error_flag(complaint_id, f"iep1_extract_error:{type(exc).__name__}")
        # ACK to remove from PEL — we recorded the error in the DB
        await r.xack(STREAM_IEP1, CONSUMER_GROUP, msg_id)
        return

    # Check if language-risk HITL is required before writing state
    signal_json = result.get("iep1_signal_json") or {}
    signal_obj = IEP1LanguageSignal.model_validate(signal_json)
    force_hitl = signal_obj.force_hitl()
    hitl_reason = "language_drift_or_high_risk_oov" if force_hitl else None
    next_state = (
        ComplaintState.HITL_REQUIRED if force_hitl else ComplaintState.PARTIALLY_PROCESSED
    )

    db_values: dict = {
        "language": result["language"],
        "language_confidence": result["language_confidence"],
        "drift_score": result["drift_score"],
        "issue_type": result["issue_type"],
        "issue_type_confidence": result["issue_type_confidence"],
        "routing_sector": result["routing_sector"],
        "normalized_text": result["normalized_text"],
        "text_embedding_ref": result["text_embedding_ref"],
        "text_embedding_vector": result.get("_embedding_vector"),
        "iep1_signal_json": result["iep1_signal_json"],
        "state": next_state.value,
        "updated_at": datetime.now(timezone.utc),
    }
    if hitl_reason:
        db_values["hitl_required"] = True
        db_values["hitl_reason"] = hitl_reason

    async with SessionLocal() as session:
        await session.execute(
            update(Complaint).where(Complaint.id == complaint_id).values(**db_values)
        )
        await session.commit()

    # Observability: drift distribution, OOV pressure, and HITL escalations.
    M.IEP1_DRIFT_SCORE.labels(language=result["language"]).observe(result["drift_score"])
    oov_rate = float((signal_json or {}).get("oov_token_rate", 0.0) or 0.0)
    risk_level = "high" if oov_rate >= 0.30 else "medium" if oov_rate >= 0.10 else "low"
    M.OOV_TOKEN_RATE.labels(risk_level=risk_level).set(oov_rate)
    if force_hitl:
        M.HITL_REQUIRED.labels(
            sector=result.get("routing_sector") or "unknown",
            reason="language_drift_or_high_risk_oov",
        ).inc()
    embedding = result.get("_embedding_vector")
    iep2_payload: dict = {
        "complaint_id": complaint_id,
        "language": result["language"],
        "issue_type": result["issue_type"],
        "gps_lat": "",  # IEP-2 reads GPS from DB
        "gps_lon": "",
        "embedding": json.dumps(embedding) if embedding else "",
        "force_hitl": "1" if force_hitl else "0",
    }
    await r.xadd(STREAM_IEP2, iep2_payload)

    await r.xack(STREAM_IEP1, CONSUMER_GROUP, msg_id)
    logger.info(
        "IEP-1 done complaint=%s lang=%s issue=%s drift=%d hitl=%s",
        complaint_id,
        result["language"],
        result["issue_type"],
        result["drift_score"],
        force_hitl,
    )


async def run_worker() -> None:
    """Main async consumer loop. Runs until cancelled."""
    r = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    await _ensure_group(r)
    logger.info("IEP-1 worker started — consuming %s as %s", STREAM_IEP1, CONSUMER_NAME)

    try:
        while True:
            try:
                results = await r.xreadgroup(
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    {STREAM_IEP1: ">"},
                    count=BATCH_SIZE,
                    block=BLOCK_MS,
                )
                if not results:
                    continue
                for _stream, messages in results:
                    for msg_id, data in messages:
                        try:
                            await _process_message(r, msg_id, data)
                        except Exception as exc:
                            logger.error(
                                "IEP-1 unhandled message error id=%s: %s",
                                msg_id,
                                exc,
                                exc_info=True,
                            )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("IEP-1 worker loop error: %s", exc, exc_info=True)
                await asyncio.sleep(2)
    finally:
        await r.aclose()
        logger.info("IEP-1 worker stopped")

"""IEP-6 Redis Streams worker — image-hazard fusion.

Reads from  cedarfix:iep6:jobs   (enqueued by IEP-3 when a complaint has a photo)
Writes to   cedarfix:iep4:jobs   (after fusing image + text routing)

Effect on routing:
- Classifies the photo with CLIP zero-shot (8-label hazard taxonomy).
- Fuses the visual sector with the text routing sector:
    agree    -> boost routing_confidence
    conflict -> penalise routing_confidence + force HITL review
- Persists image_issue_type and image_fusion_json on the complaint.

Consumer group: iep6-workers
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
from src.eep.queue import STREAM_IEP4, STREAM_IEP6
from src.iep6.vision import analyse
from src.shared import metrics as M

logger = logging.getLogger("iep6.worker")

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CONSUMER_GROUP = "iep6-workers"
CONSUMER_NAME = os.getenv("HOSTNAME", "iep6-0")
BLOCK_MS = 2_000
BATCH_SIZE = 3


async def _ensure_group(r: aioredis.Redis) -> None:
    try:
        await r.xgroup_create(STREAM_IEP6, CONSUMER_GROUP, id="0", mkstream=True)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


async def _process_message(r: aioredis.Redis, msg_id: str, data: dict) -> None:
    complaint_id: str = data.get("complaint_id", "")
    image_b64: str = data.get("image_b64", "")

    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(
                    Complaint.routing_sector,
                    Complaint.routing_confidence,
                    Complaint.hitl_required,
                    Complaint.hitl_reason,
                    Complaint.image_b64,
                ).where(Complaint.id == complaint_id)
            )
        ).one_or_none()
    if row is None:
        logger.warning("IEP-6: complaint %s not found", complaint_id)
        await r.xack(STREAM_IEP6, CONSUMER_GROUP, msg_id)
        return

    image_payload = image_b64 or (row.image_b64 or "")
    text_sector = row.routing_sector

    try:
        signal = analyse(image_payload, text_sector)
    except Exception as exc:  # noqa: BLE001 - keep pipeline durable
        logger.error("IEP-6 analyse failed complaint=%s: %s", complaint_id, exc, exc_info=True)
        await _forward_to_iep4(r, complaint_id)
        await r.xack(STREAM_IEP6, CONSUMER_GROUP, msg_id)
        return

    base_conf = float(row.routing_confidence or 0.5)
    new_conf = _clamp(base_conf + signal.fusion.confidence_delta)
    conflict = signal.fusion.force_hitl
    hitl_required = bool(row.hitl_required) or conflict
    hitl_reason = (
        "image_text_conflict"
        if conflict and not row.hitl_required
        else row.hitl_reason
    )

    # Fusion observability: decision outcome + image-hazard confidence.
    if signal.available:
        M.IEP6_FUSION_TOTAL.labels(decision=signal.fusion.agreement or "unknown").inc()
        M.IEP6_IMAGE_CONFIDENCE.labels(hazard=signal.image_label or "unknown").observe(
            float(signal.image_confidence or 0.0)
        )

    values: dict = {
        "image_issue_type": signal.image_label,
        "image_fusion_json": signal.model_dump(),
        "routing_confidence": round(new_conf, 4),
        "updated_at": datetime.now(timezone.utc),
    }
    if signal.available:
        values["hitl_required"] = hitl_required
        values["hitl_reason"] = hitl_reason
        if conflict:
            values["state"] = ComplaintState.HITL_REQUIRED.value

    async with SessionLocal() as session:
        await session.execute(
            update(Complaint).where(Complaint.id == complaint_id).values(**values)
        )
        await session.commit()

    await _forward_to_iep4(r, complaint_id)
    await r.xack(STREAM_IEP6, CONSUMER_GROUP, msg_id)
    logger.info(
        "IEP-6 done complaint=%s label=%s agree=%s delta=%+.2f hitl=%s",
        complaint_id,
        signal.image_label,
        signal.fusion.agreement,
        signal.fusion.confidence_delta,
        hitl_required,
    )


async def _forward_to_iep4(r: aioredis.Redis, complaint_id: str) -> None:
    await r.xadd(STREAM_IEP4, {"complaint_id": complaint_id})


async def run_worker() -> None:
    r = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    await _ensure_group(r)
    logger.info("IEP-6 worker started, consuming %s", STREAM_IEP6)
    try:
        while True:
            try:
                results = await r.xreadgroup(
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    {STREAM_IEP6: ">"},
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
                logger.error("IEP-6 worker loop error: %s", exc, exc_info=True)
                await asyncio.sleep(1.0)
    finally:
        await r.aclose()
        logger.info("IEP-6 worker stopped")

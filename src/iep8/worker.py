"""IEP-8 Redis Streams worker — grounded resolution co-pilot.

Reads from  cedarfix:iep8:jobs  (enqueued by IEP-4 after a complaint is routed).

For each routed complaint it:
- pulls the routing context from the DB,
- retrieves verified facts from the entity knowledge base,
- synthesises an evidence-cited resolution plan (extractive, anti-hallucination),
- verifies every step against its cited evidence and abstains to HITL when the
  sector is life-safety, the KB lacks coverage, or groundedness is too low,
- persists ``iep8_resolution_json`` on the complaint and emits metrics.

Consumer group: iep8-workers
"""
from __future__ import annotations

import asyncio
import logging
import os

import redis.asyncio as aioredis
from sqlalchemy import select, update

from src.eep.db import Complaint, SessionLocal
from src.eep.queue import STREAM_IEP8
from src.iep8.planner import build_plan
from src.iep8.retriever import get_kb
from src.shared import metrics as M

logger = logging.getLogger("iep8.worker")

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CONSUMER_GROUP = "iep8-workers"
CONSUMER_NAME = os.getenv("HOSTNAME", "iep8-0")
BLOCK_MS = 2_000
BATCH_SIZE = 4


async def _ensure_group(r: aioredis.Redis) -> None:
    try:
        await r.xgroup_create(STREAM_IEP8, CONSUMER_GROUP, id="0", mkstream=True)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _record_metrics(plan) -> None:
    sector = plan.routing_sector or "unknown"
    M.IEP8_RETRIEVAL_SCORE.labels(sector=sector).observe(plan.top_retrieval_score)
    M.IEP8_GROUNDEDNESS.labels(sector=sector).observe(plan.groundedness)
    M.IEP8_PLAN_CONFIDENCE.labels(sector=sector).observe(plan.plan_confidence)
    M.IEP8_COVERAGE.labels(sector=sector).observe(plan.coverage)
    if plan.conflicts:
        M.IEP8_CONFLICTS.labels(sector=sector).inc(len(plan.conflicts))
    if plan.abstained:
        M.IEP8_PLANS_TOTAL.labels(outcome="abstained").inc()
        reason = (plan.abstain_reason or "unspecified").split(":", 1)[0]
        M.IEP8_ABSTENTIONS.labels(reason=reason).inc()
        if plan.evidence_gaps:
            M.IEP8_GAPS.labels(sector=sector).inc(len(plan.evidence_gaps))
    else:
        M.IEP8_PLANS_TOTAL.labels(outcome="issued").inc()
        M.IEP8_CITATIONS.labels(sector=sector).observe(len(plan.evidence))


async def _process_message(r: aioredis.Redis, msg_id: str, data: dict) -> None:
    complaint_id: str = data.get("complaint_id", "")
    sector = data.get("routing_sector") or None
    entity = data.get("routing_entity") or None
    text = data.get("text") or ""

    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(
                    Complaint.text_raw,
                    Complaint.routing_sector,
                    Complaint.routing_entity,
                    Complaint.routing_confidence,
                    Complaint.hitl_required,
                ).where(Complaint.id == complaint_id)
            )
        ).one_or_none()

        if row is not None:
            text = text or (row.text_raw or "")
            sector = sector or row.routing_sector
            entity = entity or row.routing_entity
            confidence = row.routing_confidence
            hitl_required = bool(row.hitl_required)
        else:
            confidence = None
            hitl_required = False
            logger.warning("IEP-8: complaint %s not found, using message payload", complaint_id)

        plan = build_plan(
            complaint_id=complaint_id,
            routing_sector=sector,
            routing_entity=entity,
            complaint_text=text,
            routing_confidence=confidence,
            hitl_required=hitl_required,
            kb=get_kb(),
        )

        if row is not None:
            await session.execute(
                update(Complaint)
                .where(Complaint.id == complaint_id)
                .values(iep8_resolution_json=plan.model_dump(mode="json"))
            )
            await session.commit()

    _record_metrics(plan)
    await r.xack(STREAM_IEP8, CONSUMER_GROUP, msg_id)
    logger.info(
        "IEP-8 done complaint=%s abstained=%s groundedness=%.2f steps=%d",
        complaint_id,
        plan.abstained,
        plan.groundedness,
        len(plan.steps),
    )


async def run_worker() -> None:
    r = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    await _ensure_group(r)
    logger.info("IEP-8 worker started, consuming %s", STREAM_IEP8)

    while True:
        try:
            results = await r.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_IEP8: ">"},
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
        except Exception as exc:  # noqa: BLE001 - keep the worker alive
            logger.error("IEP-8 worker loop error: %s", exc, exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())

"""IEP-8 FastAPI application — Grounded Resolution Co-Pilot.

HTTP surface:
- GET  /health
- GET  /metrics                  — Prometheus exposition (shared registry)
- POST /resolve                  — on-demand grounded plan for a complaint_id
                                   *or* a raw {sector, entity, text} payload (demo)
- GET  /resolve/{complaint_id}   — fetch a persisted resolution plan
- GET  /kb/stats                 — knowledge-base index size
- GET  /kb/conflicts             — intra-KB conflict audit across all entities
- GET  /gaps                     — ranked knowledge-acquisition backlog from all
                                   abstained plans persisted in the DB

A background task runs the Redis Streams worker so a single container both
serves the API and drains ``cedarfix:iep8:jobs``.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from src.eep.db import Complaint, SessionLocal
from src.iep8.knowledge_gaps import acquisition_backlog_from_plans
from src.iep8.planner import build_plan, detect_conflicts
from src.iep8.retriever import get_kb
from src.iep8.worker import run_worker
from src.shared.metrics import add_metrics_route

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("iep8")


class ResolveRequest(BaseModel):
    complaint_id: str | None = None
    sector: str | None = None
    entity: str | None = None
    text: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Warm the KB index once at startup.
    get_kb()
    task = asyncio.create_task(run_worker(), name="iep8-worker")
    logger.info("IEP-8 worker task started")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("IEP-8 worker task stopped")


app = FastAPI(
    title="CedarFix IEP-8 — Grounded Resolution Co-Pilot",
    version="0.1.0",
    lifespan=lifespan,
)
add_metrics_route(app, "iep8")


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "service": "iep8", "kb_facts": get_kb().size}


@app.get("/kb/stats", tags=["ops"])
async def kb_stats() -> dict:
    return {"kb_facts": get_kb().size}


@app.get("/kb/conflicts", tags=["ops"])
async def kb_conflicts() -> dict:
    """Intra-KB consistency audit: surface facts of the same type that contradict.

    Returns every entity × fact-type pair where retrieved facts carry
    irreconcilable values (different phone numbers, different SLAs…). This is
    the *self-diagnostic* surface of IEP-8's conflict-detection layer.
    """
    kb = get_kb()
    from src.shared.resolution_schemas import EvidenceChunk

    all_chunks = [doc.chunk for doc in kb._docs]
    conflicts = detect_conflicts(all_chunks)
    return {
        "total_conflicts": len(conflicts),
        "conflicts": [c.model_dump() for c in conflicts],
    }


@app.post("/resolve", tags=["resolution"])
async def resolve(req: ResolveRequest) -> dict:
    """Produce a grounded resolution plan on demand (does not persist)."""
    sector, entity, text = req.sector, req.entity, req.text or ""
    confidence = None
    hitl_required = False
    complaint_id = req.complaint_id or "adhoc"

    if req.complaint_id:
        async with SessionLocal() as session:
            row = (
                await session.execute(
                    select(
                        Complaint.text_raw,
                        Complaint.routing_sector,
                        Complaint.routing_entity,
                        Complaint.routing_confidence,
                        Complaint.hitl_required,
                    ).where(Complaint.id == req.complaint_id)
                )
            ).one_or_none()
        if row is not None:
            text = text or (row.text_raw or "")
            sector = sector or row.routing_sector
            entity = entity or row.routing_entity
            confidence = row.routing_confidence
            hitl_required = bool(row.hitl_required)

    if not text:
        raise HTTPException(status_code=422, detail="text or a known complaint_id is required")

    plan = build_plan(
        complaint_id=complaint_id,
        routing_sector=sector,
        routing_entity=entity,
        complaint_text=text,
        routing_confidence=confidence,
        hitl_required=hitl_required,
        kb=get_kb(),
    )
    return plan.model_dump(mode="json")


@app.get("/resolve/{complaint_id}", tags=["resolution"])
async def get_resolution(complaint_id: str) -> dict:
    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(Complaint.iep8_resolution_json).where(Complaint.id == complaint_id)
            )
        ).one_or_none()
    if row is None or row.iep8_resolution_json is None:
        raise HTTPException(status_code=404, detail="no resolution plan for this complaint")
    return row.iep8_resolution_json


@app.get("/gaps", tags=["resolution"])
async def knowledge_gaps() -> dict:
    """Ranked knowledge-acquisition backlog from all abstained complaint plans.

    Aggregates every ``evidence_gaps`` array across persisted IEP-8 plans,
    groups by (sector, entity), and sorts by ``priority_score`` — a function
    of how many citizens were blocked and the life-safety severity of the gap.

    This endpoint answers: *"Which authority's facts should we source next?"*
    Operators can inspect it periodically to grow the KB moat in the direction
    that most unblocks citizens.
    """
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Complaint.iep8_resolution_json).where(
                    Complaint.iep8_resolution_json.isnot(None)
                )
            )
        ).scalars().all()
    plans = [r for r in rows if isinstance(r, dict)]
    backlog = acquisition_backlog_from_plans(plans)
    return {
        "total_abstained_plans": len(plans),
        "acquisition_backlog": backlog,
    }

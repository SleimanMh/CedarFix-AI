"""IEP-5 FastAPI application — incident lifecycle service.

HTTP surface:
- GET  /health
- GET  /incidents/{incident_id}/timeline   — event-sourced history
- POST /incidents/{incident_id}/transition  — operator-driven transition

A background task runs the Redis Streams worker; a second task periodically
scans for stale reopens.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from src.eep.db import Incident, IncidentLifecycleEvent, SessionLocal
from src.iep5.worker import run_worker, scan_for_stale_reopens, transition_incident
from src.shared import metrics as M
from src.shared.lifecycle_schemas import InvalidTransition, LifecycleEventType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("iep5")

SCAN_INTERVAL_S = int(os.getenv("IEP5_SCAN_INTERVAL_S", "300"))


async def _scan_loop() -> None:
    while True:
        try:
            await asyncio.sleep(SCAN_INTERVAL_S)
            await scan_for_stale_reopens()
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.error("IEP-5 scan loop error: %s", exc, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    worker_task = asyncio.create_task(run_worker(), name="iep5-worker")
    scan_task = asyncio.create_task(_scan_loop(), name="iep5-scan")
    logger.info("IEP-5 worker + scan tasks started")
    try:
        yield
    finally:
        for task in (worker_task, scan_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("IEP-5 tasks stopped")


app = FastAPI(
    title="CedarFix IEP-5 — Incident Lifecycle & Retraining Signal",
    version="0.1.0",
    lifespan=lifespan,
)

M.add_metrics_route(app, "iep5")


class TransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: LifecycleEventType
    actor: str = Field(default="operator", min_length=1, max_length=64)
    reason: str = Field(default="", max_length=256)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "service": "iep5"}


@app.get("/incidents/{incident_id}/timeline", tags=["lifecycle"])
async def incident_timeline(incident_id: str) -> dict:
    async with SessionLocal() as session:
        incident = (
            await session.execute(
                select(Incident).where(Incident.incident_id == incident_id)
            )
        ).scalar_one_or_none()
        if incident is None:
            raise HTTPException(status_code=404, detail="incident not found")
        events = (
            await session.execute(
                select(IncidentLifecycleEvent)
                .where(IncidentLifecycleEvent.incident_id == incident_id)
                .order_by(IncidentLifecycleEvent.created_at.asc())
            )
        ).scalars().all()

    return {
        "incident_id": incident.incident_id,
        "current_state": incident.current_state,
        "complaint_count": incident.complaint_count,
        "reopen_count": incident.reopen_count,
        "routing_sector": incident.routing_sector,
        "routing_entity": incident.routing_entity,
        "first_seen_at": incident.first_seen_at.isoformat()
        if incident.first_seen_at
        else None,
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "timeline": [
            {
                "event": event.event,
                "from_state": event.from_state,
                "to_state": event.to_state,
                "reason": event.reason,
                "actor": event.actor,
                "complaint_id": event.complaint_id,
                "at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in events
        ],
    }


@app.post("/incidents/{incident_id}/transition", tags=["lifecycle"])
async def transition(incident_id: str, body: TransitionRequest) -> dict:
    try:
        new_state = await transition_incident(
            incident_id,
            body.event,
            actor=body.actor,
            reason=body.reason,
        )
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"incident_id": incident_id, "current_state": new_state.value}

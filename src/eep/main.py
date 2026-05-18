"""EEP FastAPI application — Complaint Gateway.

POST /complaints        → 202 Accepted + complaint_id (async pipeline starts)
GET  /complaints/{id}/status → current pipeline state
GET  /hitl/queue        → complaints awaiting human review
GET  /health            → liveness probe
"""
from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status
from sqlalchemy import select, update

from src.eep.db import Complaint, get_session, init_db
from src.eep.models import (
    ComplaintAccepted,
    ComplaintRequest,
    ComplaintState,
    ComplaintStatus,
)
from src.eep.queue import close_redis, enqueue_iep1, get_redis

# ── PII scrubbing ─────────────────────────────────────────────────────────────
# Lebanese phone numbers (03-xxx-xxx, +961-x-xxx-xxx, etc.) and e-mail addresses.
_PHONE_RE = re.compile(
    r"\b(?:\+?961[-\s]?)?(?:0?[013-9]\d)[-\s]?\d{3}[-\s]?\d{3}\b"
)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _scrub_pii(text: str) -> str:
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    return text


# ── Application lifecycle ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    await get_redis()  # warm-up connection pool
    yield
    await close_redis()


app = FastAPI(
    title="CedarFix EEP — Complaint Gateway",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "service": "eep"}


@app.post(
    "/complaints",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ComplaintAccepted,
    tags=["complaints"],
)
async def submit_complaint(
    payload: ComplaintRequest,
    request: Request,
) -> ComplaintAccepted:
    """Accept a citizen complaint, persist it, and enqueue async processing."""
    complaint_id = str(uuid.uuid4())
    clean_text = _scrub_pii(payload.text)

    # 1. Persist with RECEIVED state
    async with get_session() as session:
        complaint = Complaint(
            id=complaint_id,
            state=ComplaintState.RECEIVED,
            text_raw=clean_text,
            image_b64=payload.image_b64,
            gps_lat=payload.gps_lat,
            gps_lon=payload.gps_lon,
            language_hint=payload.language_hint,
            error_flags=[],
        )
        session.add(complaint)
        await session.commit()

    # 2. Enqueue IEP-1 (non-blocking; complaint already durable)
    await enqueue_iep1(complaint_id, clean_text, payload.language_hint)

    # 3. Transition to PROCESSING
    async with get_session() as session:
        await session.execute(
            update(Complaint)
            .where(Complaint.id == complaint_id)
            .values(state=ComplaintState.PROCESSING)
        )
        await session.commit()

    base_url = str(request.base_url).rstrip("/")
    return ComplaintAccepted(
        complaint_id=complaint_id,
        status=ComplaintState.PROCESSING,
        status_url=f"{base_url}/complaints/{complaint_id}/status",
    )


@app.get(
    "/complaints/{complaint_id}/status",
    response_model=ComplaintStatus,
    tags=["complaints"],
)
async def get_status(complaint_id: str) -> ComplaintStatus:
    """Return the current pipeline state for a complaint."""
    async with get_session() as session:
        result = await session.execute(
            select(Complaint).where(Complaint.id == complaint_id)
        )
        complaint = result.scalar_one_or_none()

    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")

    return ComplaintStatus(
        complaint_id=complaint.id,
        status=ComplaintState(complaint.state),
        language=complaint.language,
        language_confidence=complaint.language_confidence,
        drift_score=complaint.drift_score,
        issue_type=complaint.issue_type,
        issue_type_confidence=complaint.issue_type_confidence,
        is_duplicate=complaint.is_duplicate,
        incident_id=complaint.incident_id,
        routing_sector=complaint.routing_sector,
        routing_entity=complaint.routing_entity,
        routing_confidence=complaint.routing_confidence,
        priority_score=complaint.priority_score,
        hitl_required=complaint.hitl_required,
        hitl_reason=complaint.hitl_reason,
        citizen_explanation=complaint.citizen_explanation,
        error_flags=complaint.error_flags or [],
    )


@app.get("/hitl/queue", tags=["ops"])
async def hitl_queue() -> dict:
    """Return all complaints currently queued for human review."""
    async with get_session() as session:
        result = await session.execute(
            select(Complaint).where(Complaint.state == ComplaintState.HITL_REQUIRED)
        )
        complaints = result.scalars().all()

    return {
        "count": len(complaints),
        "items": [
            {
                "complaint_id": c.id,
                "text": c.text_raw[:200],
                "language": c.language,
                "issue_type": c.issue_type,
                "hitl_reason": c.hitl_reason,
                "drift_score": c.drift_score,
                "created_at": c.created_at.isoformat(),
            }
            for c in complaints
        ],
    }

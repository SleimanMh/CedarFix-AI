"""EEP FastAPI application — Complaint Gateway.

POST /complaints        → 202 Accepted + complaint_id (async pipeline starts)
GET  /complaints/{id}/status → current pipeline state
GET  /hitl/queue        → complaints awaiting human review
GET  /health            → liveness probe
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status
from sqlalchemy import select, update

from src.eep.db import Complaint, RetrainingCandidate, get_session, init_db
from src.eep.models import (
    ComplaintAccepted,
    ComplaintDossier,
    ComplaintFeedback,
    ComplaintRequest,
    ComplaintState,
    ComplaintStatus,
    DossierLayer,
    RetrainingQueue,
    RetrainingQueueItem,
)
from src.eep.pii import scrub_pii
from src.eep.queue import close_redis, enqueue_iep1, get_redis
from src.shared import metrics as M

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

M.add_metrics_route(app, "eep")


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
    clean_text = scrub_pii(payload.text)
    M.COMPLAINTS_RECEIVED.labels(source=payload.language_hint or "api").inc()

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

    # 2. Enqueue IEP-1. If Redis is unavailable, keep the durable complaint and
    # force a human fallback instead of losing the citizen report.
    enqueue_failed = False
    try:
        await enqueue_iep1(complaint_id, clean_text, payload.language_hint)
    except Exception:  # noqa: BLE001 - API fallback path must catch transport failures
        enqueue_failed = True

    # 3. Transition based on async pipeline availability
    next_state = ComplaintState.HITL_REQUIRED if enqueue_failed else ComplaintState.PROCESSING
    update_values = {"state": next_state}
    if enqueue_failed:
        M.HITL_REQUIRED.labels(sector="unknown", reason="iep1_queue_unavailable").inc()
        update_values.update(
            {
                "hitl_required": True,
                "hitl_reason": "iep1_queue_unavailable",
                "error_flags": ["iep1_enqueue_failed"],
            }
        )
    async with get_session() as session:
        await session.execute(
            update(Complaint)
            .where(Complaint.id == complaint_id)
            .values(**update_values)
        )
        await session.commit()

    base_url = str(request.base_url).rstrip("/")
    return ComplaintAccepted(
        complaint_id=complaint_id,
        status=next_state,
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
        iep1_signal_json=complaint.iep1_signal_json,
        is_duplicate=complaint.is_duplicate,
        incident_id=complaint.incident_id,
        iep2_incident_json=complaint.iep2_incident_json,
        image_issue_type=complaint.image_issue_type,
        image_fusion_json=complaint.image_fusion_json,
        routing_sector=complaint.routing_sector,
        routing_entity=complaint.routing_entity,
        routing_confidence=complaint.routing_confidence,
        priority_score=complaint.priority_score,
        hitl_required=complaint.hitl_required,
        hitl_reason=complaint.hitl_reason,
        iep3_routing_json=complaint.iep3_routing_json,
        citizen_explanation=complaint.citizen_explanation,
        admin_explanation=complaint.admin_explanation,
        iep4_explanation_json=complaint.iep4_explanation_json,
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


@app.get(
    "/complaints/{complaint_id}/dossier",
    response_model=ComplaintDossier,
    tags=["complaints"],
)
async def get_dossier(complaint_id: str) -> ComplaintDossier:
    """Return the full AI decision dossier for a complaint.

    Unlike /status (which returns raw fields), /dossier assembles a structured,
    opinionated trace of every AI layer — each with its decision, confidence,
    and evidence — plus the final routing outcome and safety flags.
    """
    async with get_session() as session:
        result = await session.execute(
            select(Complaint).where(Complaint.id == complaint_id)
        )
        c = result.scalar_one_or_none()

    if c is None:
        raise HTTPException(status_code=404, detail="Complaint not found")

    layers: list[DossierLayer] = []

    # ── Layer 1: IEP-1 text intelligence ─────────────────────────────────────
    iep1 = c.iep1_signal_json or {}
    iep1_evidence: list[str] = []
    iep1_flags: list[str] = []
    if c.language:
        iep1_evidence.append(f"Detected language: {c.language} (conf={c.language_confidence:.2f})" if c.language_confidence else f"Detected language: {c.language}")
    if iep1.get("keywords_matched"):
        iep1_evidence.append(f"Rule keywords matched: {', '.join(iep1['keywords_matched'][:5])}")
    if iep1.get("model_sector"):
        iep1_evidence.append(f"Learned model sector: {iep1['model_sector']} (conf={iep1.get('model_confidence', 0):.2f})")
    if iep1.get("model_top3"):
        iep1_evidence.append(f"Model top-3: {iep1['model_top3']}")
    if c.drift_score and c.drift_score >= 3:
        iep1_flags.append(f"Drift score={c.drift_score} — unusual vocabulary detected")
    layers.append(DossierLayer(
        layer="IEP-1 text intelligence",
        decision=c.issue_type,
        confidence=c.issue_type_confidence,
        evidence=iep1_evidence,
        safety_flags=iep1_flags,
    ))

    # ── Layer 2: IEP-6 image fusion ───────────────────────────────────────────
    if c.image_fusion_json or c.image_issue_type:
        img = c.image_fusion_json or {}
        img_evidence: list[str] = []
        img_flags: list[str] = []
        if c.image_issue_type:
            img_evidence.append(f"Vision-detected hazard: {c.image_issue_type}")
        if img.get("conflict_detected"):
            img_flags.append("Image/text sector conflict — required human reconciliation")
        if img.get("kb_facts"):
            img_evidence.append(f"KB facts from image context: {img['kb_facts'][:3]}")
        layers.append(DossierLayer(
            layer="IEP-6 image fusion",
            decision=c.image_issue_type,
            evidence=img_evidence,
            safety_flags=img_flags,
        ))

    # ── Layer 3: IEP-2 incident fusion ────────────────────────────────────────
    iep2 = c.iep2_incident_json or {}
    if c.is_duplicate is not None:
        inc_evidence: list[str] = []
        inc_flags: list[str] = []
        if c.is_duplicate:
            inc_evidence.append(f"Merged into existing incident {c.incident_id}")
            inc_flags.append("Duplicate — citizen notified of merge; no new ticket created")
        else:
            inc_evidence.append("No existing incident found — new incident created")
        if iep2.get("similarity_score"):
            inc_evidence.append(f"Nearest-neighbour similarity: {iep2['similarity_score']:.3f}")
        layers.append(DossierLayer(
            layer="IEP-2 incident fusion",
            decision="DUPLICATE" if c.is_duplicate else "NEW_INCIDENT",
            evidence=inc_evidence,
            safety_flags=inc_flags,
        ))

    # ── Layer 4: IEP-3 routing ────────────────────────────────────────────────
    iep3 = c.iep3_routing_json or {}
    routing_evidence: list[str] = []
    routing_flags: list[str] = []
    if c.routing_sector:
        routing_evidence.append(f"Sector: {c.routing_sector}")
    if c.routing_entity:
        routing_evidence.append(f"Entity: {c.routing_entity}")
    if c.routing_confidence is not None:
        routing_evidence.append(f"Routing confidence: {c.routing_confidence:.2f}")
    if iep3.get("kb_facts_used"):
        routing_evidence.append(f"KB facts used: {iep3['kb_facts_used'][:3]}")
    if iep3.get("shap_top3"):
        routing_evidence.append(f"SHAP top features: {iep3['shap_top3']}")
    elif c.shap_top3:
        routing_evidence.append(f"SHAP top features: {c.shap_top3}")
    if c.hitl_required:
        routing_flags.append(f"HITL gate triggered: {c.hitl_reason or 'unspecified'}")
    layers.append(DossierLayer(
        layer="IEP-3 routing",
        decision=f"{c.routing_sector}/{c.routing_entity}" if c.routing_entity else c.routing_sector,
        confidence=c.routing_confidence,
        evidence=routing_evidence,
        safety_flags=routing_flags,
    ))

    # ── Layer 5: IEP-4 explanation ────────────────────────────────────────────
    if c.citizen_explanation or c.admin_explanation:
        exp_evidence: list[str] = []
        if c.citizen_explanation:
            exp_evidence.append(f"Citizen explanation generated ({len(c.citizen_explanation)} chars)")
        if c.admin_explanation:
            exp_evidence.append(f"Admin explanation generated ({len(c.admin_explanation)} chars)")
        layers.append(DossierLayer(
            layer="IEP-4 explanation",
            decision="EXPLANATION_GENERATED",
            evidence=exp_evidence,
        ))

    # ── Final decision ────────────────────────────────────────────────────────
    state = ComplaintState(c.state)
    if state == ComplaintState.AUTO_ROUTED:
        final_decision = "AUTO_ROUTED"
    elif state in (ComplaintState.HITL_REQUIRED, ComplaintState.HITL_IN_REVIEW):
        final_decision = "HITL_REQUIRED"
    else:
        final_decision = "PENDING"

    pipeline_complete = state in (
        ComplaintState.AUTO_ROUTED,
        ComplaintState.RESOLVED,
        ComplaintState.CLOSED,
    )

    return ComplaintDossier(
        complaint_id=c.id,
        status=state,
        submitted_text=c.text_raw[:500],
        pipeline_complete=pipeline_complete,
        layers=layers,
        final_sector=c.routing_sector,
        final_entity=c.routing_entity,
        final_decision=final_decision,
        hitl_reason=c.hitl_reason,
        routing_confidence=c.routing_confidence,
        drift_score=c.drift_score,
        priority_score=c.priority_score,
    )


# ── Active learning endpoints ─────────────────────────────────────────────────

@app.post(
    "/complaints/{complaint_id}/feedback",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["active-learning"],
)
async def submit_feedback(complaint_id: str, feedback: ComplaintFeedback) -> dict:
    """Accept a human routing correction for a complaint.

    A RetrainingCandidate record is created so the correction can be consumed
    by the offline model retraining pipeline.  The complaint is moved to
    RESOLVED state.
    """
    async with get_session() as session:
        result = await session.execute(
            select(Complaint).where(Complaint.id == complaint_id)
        )
        c = result.scalar_one_or_none()

        if c is None:
            raise HTTPException(status_code=404, detail="Complaint not found")

        allowed_states = {ComplaintState.HITL_REQUIRED, ComplaintState.HITL_IN_REVIEW}
        if ComplaintState(c.state) not in allowed_states:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Complaint is in state '{c.state}'; feedback is only accepted "
                    "for HITL_REQUIRED or HITL_IN_REVIEW complaints."
                ),
            )

        # Capture original routing before resolving.
        original_routing = {
            "sector": c.routing_sector,
            "entity": c.routing_entity,
            "confidence": c.routing_confidence,
            "hitl_reason": c.hitl_reason,
        }

        # Build retraining candidate.
        candidate = RetrainingCandidate(
            complaint_id=complaint_id,
            incident_id=c.incident_id,
            source="hitl_correction",
            reason=feedback.correction_notes or f"Reviewer corrected to {feedback.corrected_sector}/{feedback.corrected_entity}",
            original_routing=original_routing,
            status="pending",
        )
        session.add(candidate)

        # Apply correction to the complaint row.
        if feedback.corrected_sector:
            c.routing_sector = feedback.corrected_sector
        if feedback.corrected_entity:
            c.routing_entity = feedback.corrected_entity
        c.state = ComplaintState.RESOLVED

        await session.commit()

    return {
        "complaint_id": complaint_id,
        "candidate_id": candidate.id,
        "message": "Feedback recorded; complaint resolved.",
    }


@app.get(
    "/retraining-queue",
    response_model=RetrainingQueue,
    tags=["active-learning"],
)
async def retraining_queue(limit: int = 200) -> RetrainingQueue:
    """Return pending retraining candidates ordered by creation time (oldest first).

    The offline retraining pipeline polls this endpoint to fetch the corrections
    that should be incorporated into the next model training run.
    """
    async with get_session() as session:
        result = await session.execute(
            select(RetrainingCandidate)
            .where(RetrainingCandidate.status == "pending")
            .order_by(RetrainingCandidate.created_at)
            .limit(limit)
        )
        rows = result.scalars().all()

    items = [
        RetrainingQueueItem(
            candidate_id=r.id,
            complaint_id=r.complaint_id,
            source=r.source,
            reason=r.reason,
            original_routing=r.original_routing,
            status=r.status,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]

    return RetrainingQueue(count=len(items), items=items)



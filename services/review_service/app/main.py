"""
IEP-8 — Human Review + Active Learning Service
================================================
Owned by: Systems/Integration Engineer

Responsibilities:
- Surface low-confidence complaints for admin review
- Accept admin corrections and store them
- Feed correction events into the retraining pipeline
- Queue submissions that failed media validation (contradictions, unclear)

DATA THIS SERVICE GENERATES (important for MLOps):
  - admin_corrections table rows → training examples for IEP-5, IEP-6
  - human_review_queue rows → flagged submissions for admin attention
"""

import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from cedarfix_shared.schemas import (
    AdminCorrection, RoutingEntity, SeverityLevel, ComplaintType,
    HumanReviewItem, ResolveReviewItem,
)
from .store import (
    get_review_queue, save_correction,
    add_human_review_item, get_human_review_queue, resolve_human_review_item,
)

app = FastAPI(title="IEP-8: Human Review Service", version="0.2.0")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "review-service"}


# ---------------------------------------------------------------------------
# Routing/Severity corrections queue (existing)
# ---------------------------------------------------------------------------

@app.get("/queue")
async def get_queue(limit: int = 20):
    """
    Returns complaints awaiting human review (low confidence routing).
    Active Learning: sorted by lowest routing_confidence first.
    """
    return await get_review_queue(limit=limit)


@app.post("/corrections/{complaint_id}", status_code=201)
async def submit_correction(complaint_id: str, correction: AdminCorrection):
    """
    Admin submits a correction to routing, severity, or type.
    This record becomes a gold-label training example.
    """
    correction.complaint_id = complaint_id
    await save_correction(correction)
    return {"status": "correction_saved", "complaint_id": complaint_id}


# ---------------------------------------------------------------------------
# Human review queue — media validation failures
# ---------------------------------------------------------------------------

@app.post("/human-review", status_code=201)
async def add_to_human_review(item: HumanReviewItem):
    """
    Called by the gateway when a submission fails media validation
    (NEEDS_CLARIFICATION or HUMAN_REVIEW status).
    """
    row_id = await add_human_review_item(
        complaint_id=item.complaint_id,
        validation_status=item.validation_status,
        review_reason=item.review_reason,
        original_text=item.original_text,
        image_filename=item.image_filename,
        image_detected_type=item.image_detected_type,
        text_detected_type=item.text_detected_type,
    )
    return {"status": "queued", "id": row_id, "complaint_id": item.complaint_id}


@app.get("/human-review")
async def list_human_review(limit: int = 50):
    """
    Returns submissions pending human review, newest first.
    Used by the admin dashboard.
    """
    return await get_human_review_queue(limit=limit)


@app.post("/human-review/{item_id}/resolve", status_code=200)
async def resolve_review(item_id: int, body: ResolveReviewItem):
    """
    Admin resolves a human review item with notes.
    """
    await resolve_human_review_item(item_id, body.resolution_notes, body.admin_id)
    return {"status": "resolved", "id": item_id}

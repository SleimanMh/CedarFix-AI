"""
IEP-8 — Human Review + Active Learning Service
================================================
Owned by: Systems/Integration Engineer

Responsibilities:
- Surface low-confidence complaints for admin review
- Accept admin corrections and store them
- Feed correction events into the retraining pipeline
- Queue submissions that failed media validation (contradictions, unclear)
- Manage the retraining_store: review, correction, and export of fine-tuning data

DATA THIS SERVICE GENERATES (important for MLOps):
  - admin_corrections table rows → training examples for IEP-5, IEP-6
  - human_review_queue rows → flagged submissions for admin attention
  - retraining_store rows → gold-label fine-tuning examples after admin review
"""

import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from cedarfix_shared.schemas import (
    AdminCorrection, RoutingEntity, SeverityLevel, ComplaintType,
    HumanReviewItem, ResolveReviewItem, RetrainingReviewRequest,
)
from .store import (
    get_review_queue, save_correction,
    add_human_review_item, get_human_review_queue, resolve_human_review_item,
    get_retraining_queue, get_retraining_record,
    save_retraining_review, get_retraining_export,
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


# ---------------------------------------------------------------------------
# Retraining Store — review, correction, and fine-tuning export
# ---------------------------------------------------------------------------

@app.get("/retraining")
def list_retraining_queue(
    pending_only: bool = True,
    rag_no_match_only: bool = False,
    page: int = 1,
    limit: int = 50,
):
    """
    Returns retraining_store rows for admin review.

    Filters:
      pending_only=true (default) → only unreviewed records
      rag_no_match_only=true      → only records where RAG found zero candidates

    Sorted newest-first so the most recent unsupported complaints appear first.
    """
    offset = (page - 1) * limit
    return get_retraining_queue(
        pending_only=pending_only,
        rag_no_match_only=rag_no_match_only,
        limit=limit,
        offset=offset,
    )


@app.get("/retraining/{complaint_id}")
def get_retraining_detail(complaint_id: str):
    """
    Returns the full retraining_store row for a complaint, including all raw and
    corrected JSON fields. Use this to inspect pipeline outputs before filling
    in corrections.
    """
    record = get_retraining_record(complaint_id)
    if not record:
        raise HTTPException(status_code=404, detail="Retraining record not found")
    return record


@app.post("/retraining/{complaint_id}/review", status_code=200)
def submit_review(complaint_id: str, body: RetrainingReviewRequest):
    """
    Admin submits a review decision for a retraining_store row.

    admin_decision must be one of:
      can_be_processed    – valid complaint, in scope; fill corrected_* for a gold label
      cannot_be_processed – valid but outside current CedarFix coverage
      fake                – spam / test / not a real complaint
      unsupported         – complaint type not in taxonomy yet; kept for future expansion

    When admin_decision='can_be_processed':
      - Provide corrected_text_json (sector, issue_type, entity, urgency, …)
      - Provide corrected_rag_response (correct routing entity + rationale)
      - Optionally provide corrected_image_json if an image was submitted
      - The row's usable_for_finetuning flag is set to TRUE automatically.
      - It will appear in the next export batch.

    When admin_decision is NOT 'can_be_processed':
      - The row is kept (usable_for_finetuning=FALSE) for taxonomy/gap analysis.
      - corrected_* fields are ignored.
    """
    allowed = {"can_be_processed", "cannot_be_processed", "fake", "unsupported"}
    if body.admin_decision not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"admin_decision must be one of: {', '.join(sorted(allowed))}",
        )
    save_retraining_review(
        complaint_id=complaint_id,
        admin_id=body.admin_id,
        admin_decision=body.admin_decision,
        admin_notes=body.admin_notes,
        corrected_text_json=body.corrected_text_json,
        corrected_image_json=body.corrected_image_json,
        corrected_rag_response=body.corrected_rag_response,
    )
    return {
        "status": "reviewed",
        "complaint_id": complaint_id,
        "decision": body.admin_decision,
        "usable_for_finetuning": body.admin_decision == "can_be_processed",
    }


@app.get("/retraining/export")
def export_retraining_data(mark_exported: bool = False):
    """
    Returns all retraining_store records that are ready for fine-tuning:
      usable_for_finetuning=TRUE  AND  finetuning_exported=FALSE

    Each record contains:
      complaint_text            – raw user text (LLM fine-tuning input)
      image_filename            – image reference (null if no image)
      text_classification_json  – original IEP-1 output
      image_classification_json – original IEP-2 output (null if no image)
      rag_routing_response      – original IEP-6 routing result
      corrected_text_json       – admin gold label for text classification
      corrected_image_json      – admin gold label for image classification
      corrected_rag_response    – admin gold label for routing

    Set mark_exported=true to atomically mark them as exported,
    preventing duplicate inclusion in future export batches.
    """
    return get_retraining_export(mark_exported=mark_exported)

"""
EEP — Complaint Gateway
=======================
The single external entry point for all complaint submissions.
Orchestrates IEP-1 through IEP-7 in the correct order.
Returns a structured ComplaintDecision.

TEAM: Backend Engineer
"""

import asyncio
import logging
import os
import time
import uuid
from typing import Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from prometheus_client import make_asgi_app

from cedarfix_shared.schemas import (
    ComplaintDecision, ComplaintRequest, ComplaintSubmissionResponse,
    LocationInput, PipelineStatus,
)
from cedarfix_shared.metrics import COMPLAINTS_TOTAL, PIPELINE_DURATION
from cedarfix_shared.location import normalize_location
from cedarfix_shared.storage import local_image_path, save_image_ref, signed_image_url
from .orchestrator import run_pipeline
from .splitter import split_complaint_text
from .config import settings
from .database import (
    init_db, save_complaint, fetch_complaint,
    create_user, get_user_by_username, get_user_by_email, get_user_by_login,
    normalize_username, normalize_email, update_last_login,
    fetch_user_complaints, fetch_admin_stats,
    fetch_all_complaints_admin, fetch_review_queue_admin,
    fetch_resolved_review_admin,
    fetch_duplicates_admin, resolve_review_item,
    save_retraining_record, fetch_retraining_queue,
    fetch_retraining_record, submit_retraining_review,
    fetch_retraining_export,
)
from .auth import (
    hash_password, verify_password, create_token,
    get_current_user, require_user, require_admin,
)

app = FastAPI(
    title="CedarFix AI — Gateway",
    description="Complaint submission and pipeline orchestration endpoint",
    version="0.1.0",
)
log = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}


# =============================================================================
# Auth endpoints
# =============================================================================

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"   # clients should send "user"; "admin" requires a secret


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/register", status_code=201)
async def register(body: RegisterRequest):
    username = normalize_username(body.username)
    email = normalize_email(body.email)
    if len(username) < 3 or len(body.password) < 6 or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Username >= 3 chars, valid email required, password >= 6 chars")
    if await get_user_by_username(username):
        raise HTTPException(status_code=409, detail="Username already taken")
    if await get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email already registered")
    role = "admin" if body.role == "admin" else "user"
    user = await create_user(username, email, hash_password(body.password), role)
    if not user:
        raise HTTPException(status_code=409, detail="Username or email already registered")
    log.info("[auth] registered user_id=%s username=%s email=%s role=%s", user["id"], user["username"], user.get("email"), user["role"])
    token = create_token(user["id"], user["username"], user["role"], user.get("email"))
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "user_id": user["id"],
        "username": user["username"],
        "email": user.get("email"),
    }
    username = normalize_username(body.username)
    if len(username) < 3 or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Username ≥ 3 chars, password ≥ 6 chars")
    existing = await get_user_by_username(username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")
    # Only allow admin role if the correct env secret is configured
    role = "user"
    if body.role == "admin":
        import os
        admin_secret = os.getenv("ADMIN_REGISTRATION_SECRET", "")
        # For capstone demo, allow admin role freely (no secret required)
        role = "admin"
    user = await create_user(username, hash_password(body.password), role)
    if not user:
        raise HTTPException(status_code=409, detail="Username already taken")
    log.info("[auth] registered user_id=%s username=%s role=%s", user["id"], user["username"], user["role"])
    token = create_token(user["id"], user["username"], user["role"])
    return {"access_token": token, "token_type": "bearer",
            "role": user["role"], "user_id": user["id"], "username": user["username"]}


@app.post("/auth/login")
async def login(body: LoginRequest):
    identifier = (body.username or "").strip()
    user = await get_user_by_login(identifier)
    if not user or not verify_password(body.password, user["password_hash"]):
        log.info("[auth] failed login identifier=%s", identifier)
        raise HTTPException(status_code=401, detail="Invalid username/email or password")
    await update_last_login(user["id"])
    log.info("[auth] login user_id=%s username=%s email=%s role=%s", user["id"], user["username"], user.get("email"), user["role"])
    token = create_token(user["id"], user["username"], user["role"], user.get("email"))
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "user_id": user["id"],
        "username": user["username"],
        "email": user.get("email"),
    }
    username = normalize_username(body.username)
    user = await get_user_by_username(username)
    if not user or not verify_password(body.password, user["password_hash"]):
        log.info("[auth] failed login username=%s", username)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    await update_last_login(user["id"])
    log.info("[auth] login user_id=%s username=%s role=%s", user["id"], user["username"], user["role"])
    token = create_token(user["id"], user["username"], user["role"])
    return {"access_token": token, "token_type": "bearer",
            "role": user["role"], "user_id": user["id"], "username": user["username"]}


@app.post("/complaints", response_model=ComplaintSubmissionResponse, status_code=201)
async def submit_complaint(
    text: str = Form(..., min_length=10, max_length=2000),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    address_hint: Optional[str] = Form(None),
    district: Optional[str] = Form(None),
    location_input_mode: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    Submit a complaint with optional image and GPS coordinates.
    If a JWT token is present, user_id is taken from it automatically.
    Returns one or more ComplaintDecision objects. If the submitted text contains
    multiple independent complaints, each child complaint is processed and stored
    separately under the same parent submission id.
    """
    # Prefer authenticated user_id over form-submitted one
    resolved_user_id = (current_user["user_id"] if current_user else None) or user_id

    start_ms = int(time.time() * 1000)
    submission_id = str(uuid.uuid4())

    # Handle image upload
    image_filename = None
    if image:
        image_filename = f"{submission_id}_{image.filename}"
        image_bytes = await image.read()
        image_filename = _save_image(image_filename, image_bytes, image.content_type or "application/octet-stream")

    # Build and resolve submitted location if provided.
    # This is the authoritative location for routing; LLM-extracted text
    # location is only used as a fallback/evaluation signal.
    location = None
    submitted_location_text = (address_hint or district or "").strip()
    if latitude is not None or longitude is not None or submitted_location_text:
        resolved = await normalize_location(
            raw_text=submitted_location_text,
            lat=latitude if latitude is not None and longitude is not None else None,
            lng=longitude if latitude is not None and longitude is not None else None,
            user_hint=submitted_location_text,
        )
        resolved_lat = resolved.get("latitude") if resolved else None
        resolved_lng = resolved.get("longitude") if resolved else None
        location = LocationInput(
            latitude=resolved_lat if resolved_lat is not None else latitude,
            longitude=resolved_lng if resolved_lng is not None else longitude,
            address_hint=submitted_location_text or address_hint,
            district=(resolved.get("district") if resolved else None) or district or submitted_location_text or None,
            municipality=resolved.get("municipality") if resolved else None,
            governorate=resolved.get("governorate") if resolved else None,
            normalized=(resolved.get("normalized") if resolved else None) or submitted_location_text or None,
            source=(resolved.get("source") if resolved else None) or (
                "gps" if latitude is not None and longitude is not None else "user_text"
            ),
            confidence=float(resolved.get("confidence") or 0.55) if resolved else 0.55,
        )

    resolved_location_mode = location_input_mode or (
        "current_device" if latitude is not None and longitude is not None else
        "manual_text" if submitted_location_text else
        "unspecified"
    )

    COMPLAINTS_TOTAL.labels(status="received").inc()

    try:
        split_result = await split_complaint_text(text)
        child_items = split_result.complaints or []
        is_multi = bool(split_result.is_multi and len(child_items) > 1)
        split_total = len(child_items)

        decisions: list[ComplaintDecision] = []
        for idx, item in enumerate(child_items, 1):
            child_start_ms = int(time.time() * 1000)
            complaint_id = str(uuid.uuid4()) if is_multi else submission_id
            request = ComplaintRequest(
                text=item.complaint_text,
                location=location,
                location_input_mode=resolved_location_mode,
                image_filename=image_filename,
                user_id=resolved_user_id,
                parent_submission_id=submission_id if is_multi else None,
                split_index=idx if is_multi else None,
                split_total=split_total if is_multi else None,
                split_source=split_result.source,
                original_submission_text=text if is_multi else None,
            )

            decision = await run_pipeline(complaint_id, request)
            decision.total_pipeline_ms = int(time.time() * 1000) - child_start_ms
            await save_complaint(decision)
            # Always persist the pipeline outputs for retraining / active learning.
            # The retraining_store row will be reviewed by an admin later, especially
            # when rag_no_match=TRUE or requires_review=TRUE.
            await save_retraining_record(decision)
            decisions.append(decision)

        COMPLAINTS_TOTAL.labels(status="completed").inc()
        total_ms = int(time.time() * 1000) - start_ms
        PIPELINE_DURATION.labels(stage="full").observe(total_ms / 1000)

        return ComplaintSubmissionResponse(
            submission_id=submission_id,
            mode="multi" if is_multi else "single",
            is_multi=is_multi,
            complaint_count=len(decisions),
            split_result=split_result,
            complaints=decisions,
            primary_decision=decisions[0] if decisions else None,
            total_pipeline_ms=total_ms,
        )

    except Exception as e:
        import traceback
        COMPLAINTS_TOTAL.labels(status="failed").inc()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.get("/complaints/{complaint_id}", response_model=ComplaintDecision)
async def get_complaint(
    complaint_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    result = await fetch_complaint(complaint_id)
    if not result:
        raise HTTPException(status_code=404, detail="Complaint not found")
    # Users can only view their own complaints; admins can view all
    if current_user and current_user.get("role") != "admin":
        if result.user_id and result.user_id != current_user.get("user_id"):
            raise HTTPException(status_code=403, detail="Access denied")
    return result


# =============================================================================
# User routes
# =============================================================================

@app.get("/my-complaints")
async def my_complaints(
    page: int = 1,
    limit: int = 20,
    current_user: dict = Depends(require_user),
):
    return await fetch_user_complaints(current_user["user_id"], page, limit)


# =============================================================================
# Admin routes
# =============================================================================

@app.get("/admin/stats")
async def admin_stats(admin: dict = Depends(require_admin)):
    return await fetch_admin_stats()


@app.get("/admin/complaints")
async def admin_complaints(
    page: int = 1,
    limit: int = 50,
    admin: dict = Depends(require_admin),
):
    return await fetch_all_complaints_admin(page, limit)


@app.get("/admin/review-queue")
async def admin_review_queue(admin: dict = Depends(require_admin)):
    return await fetch_review_queue_admin()


@app.get("/admin/review-resolved")
async def admin_review_resolved(
    limit: int = 200,
    admin: dict = Depends(require_admin),
):
    return await fetch_resolved_review_admin(limit=limit)


@app.get("/admin/duplicates")
async def admin_duplicates(
    page: int = 1,
    limit: int = 50,
    admin: dict = Depends(require_admin),
):
    return await fetch_duplicates_admin(page, limit)


class ResolveRequest(BaseModel):
    notes: str = ""
    # Optional feedback-loop decision. If provided, the linked retraining_store
    # row for this complaint is updated in the same request.
    # Allowed values mirror /admin/retraining/{complaint_id}/review.
    admin_decision: Optional[str] = None
    corrected_text_json: Optional[dict] = None
    corrected_image_json: Optional[dict] = None
    corrected_rag_response: Optional[dict] = None
    # New review-editor fields stored in admin_review_edits
    image_text_match: Optional[bool] = None
    text_llm_json: Optional[dict] = None
    image_llm_json: Optional[dict] = None
    routing_json: Optional[dict] = None


@app.post("/admin/review/{item_id}/resolve")
async def admin_resolve_review(
    item_id: int,
    body: ResolveRequest,
    admin: dict = Depends(require_admin),
):
    allowed_decisions = {"can_be_processed", "cannot_be_processed", "fake", "unsupported"}
    if body.admin_decision is not None and body.admin_decision not in allowed_decisions:
        raise HTTPException(
            status_code=422,
            detail=f"admin_decision must be one of: {', '.join(sorted(allowed_decisions))}",
        )

    await resolve_review_item(
        item_id=item_id,
        resolved_by=admin["sub"],
        notes=body.notes,
        admin_decision=body.admin_decision,
        corrected_text_json=body.corrected_text_json or body.text_llm_json,
        corrected_image_json=body.corrected_image_json or body.image_llm_json,
        corrected_rag_response=body.corrected_rag_response or body.routing_json,
        image_text_match=body.image_text_match,
        text_llm_json=body.text_llm_json,
        image_llm_json=body.image_llm_json,
        routing_json=body.routing_json,
    )
    return {"status": "resolved", "item_id": item_id}


@app.get("/media")
async def get_media_ref(ref: str = Query(..., min_length=1)):
    """Serve or redirect to a stored image reference."""
    if ref.startswith(("http://", "https://")):
        return RedirectResponse(ref)
    if ref.startswith("gcs://"):
        return RedirectResponse(signed_image_url(ref))

    file_path = local_image_path(ref, uploads_dir=settings.uploads_dir)
    if not file_path or not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(file_path))


@app.get("/media/{image_name}")
async def get_media(image_name: str):
    """
    Legacy local image preview route.
    New code should call /media?ref=... so GCS refs are supported too.
    """
    file_path = local_image_path(image_name, uploads_dir=settings.uploads_dir)
    if not file_path or not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(file_path))


# =============================================================================
# Admin — Retraining Store
# =============================================================================

class RetrainingReviewBody(BaseModel):
    """
    Sent by admin to review a retraining_store row.

    admin_decision:
      can_be_processed    – valid, in-scope; fill corrected_* for gold label
      cannot_be_processed – valid but outside current CedarFix scope
      fake                – spam / test / not a real complaint
      unsupported         – complaint type not in taxonomy yet
    """
    admin_decision: str
    admin_notes: Optional[str] = None
    corrected_text_json: Optional[dict] = None
    corrected_image_json: Optional[dict] = None
    corrected_rag_response: Optional[dict] = None


@app.get("/admin/retraining")
async def admin_retraining_queue(
    pending_only: bool = True,
    rag_no_match_only: bool = False,
    page: int = 1,
    limit: int = 50,
    admin: dict = Depends(require_admin),
):
    """
    Returns retraining_store rows.
    pending_only=true (default) shows only unreviewed records.
    rag_no_match_only=true filters to only complaints where RAG found zero candidates.
    """
    offset = (page - 1) * limit
    return await fetch_retraining_queue(
        pending_only=pending_only,
        rag_no_match_only=rag_no_match_only,
        limit=limit,
        offset=offset,
    )


@app.get("/admin/retraining/{complaint_id}")
async def admin_retraining_detail(
    complaint_id: str,
    admin: dict = Depends(require_admin),
):
    """
    Returns the full retraining_store row for a complaint (including all JSONB columns)
    so the admin can inspect pipeline outputs and fill in corrections.
    """
    record = await fetch_retraining_record(complaint_id)
    if not record:
        raise HTTPException(status_code=404, detail="Retraining record not found")
    return record


@app.post("/admin/retraining/{complaint_id}/review", status_code=200)
async def admin_submit_retraining_review(
    complaint_id: str,
    body: RetrainingReviewBody,
    admin: dict = Depends(require_admin),
):
    """
    Admin submits a review decision for a retraining_store row.

    When admin_decision='can_be_processed':
      - Provide corrected_text_json and/or corrected_rag_response to create a gold label.
      - The row's usable_for_finetuning flag is set to TRUE automatically.
      - This record will appear in the next /admin/retraining/export batch.

    When admin_decision is 'cannot_be_processed', 'fake', or 'unsupported':
      - The row is kept (usable_for_finetuning=FALSE) for future taxonomy analysis.
      - corrected_* fields are ignored.
    """
    allowed_decisions = {"can_be_processed", "cannot_be_processed", "fake", "unsupported"}
    if body.admin_decision not in allowed_decisions:
        raise HTTPException(
            status_code=422,
            detail=f"admin_decision must be one of: {', '.join(sorted(allowed_decisions))}",
        )
    await submit_retraining_review(
        complaint_id=complaint_id,
        admin_id=admin["sub"],
        admin_decision=body.admin_decision,
        admin_notes=body.admin_notes,
        corrected_text_json=body.corrected_text_json,
        corrected_image_json=body.corrected_image_json,
        corrected_rag_response=body.corrected_rag_response,
    )
    return {"status": "reviewed", "complaint_id": complaint_id, "decision": body.admin_decision}


@app.get("/admin/retraining/export")
async def admin_retraining_export(
    mark_exported: bool = False,
    admin: dict = Depends(require_admin),
):
    """
    Returns all retraining_store rows that are usable for fine-tuning
    (usable_for_finetuning=TRUE, finetuning_exported=FALSE).

    Each record contains:
      - complaint_text          → user input (LLM fine-tuning prompt)
      - image_filename          → image reference if complaint had an image
      - text_classification_json → original IEP-1 output
      - image_classification_json → original IEP-2 output (null if no image)
      - rag_routing_response    → original IEP-6 routing output
      - corrected_text_json     → admin-corrected IEP-1 (gold label)
      - corrected_image_json    → admin-corrected IEP-2 (gold label)
      - corrected_rag_response  → admin-corrected routing (gold label)

    Set mark_exported=true to atomically mark records as exported
    (prevents duplicate exports).
    """
    return await fetch_retraining_export(mark_exported=mark_exported)


def _save_image(filename: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """
    Save image and return a reference string.
    Local deployments return local://filename.
    GCS deployments return gcs://bucket/complaints/filename.
    """
    return save_image_ref(filename, data, content_type=content_type, uploads_dir=settings.uploads_dir)

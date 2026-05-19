"""
EEP — Complaint Gateway
=======================
The single external entry point for all complaint submissions.
Orchestrates IEP-1 through IEP-7 in the correct order.
Returns a structured ComplaintDecision.

TEAM: Backend Engineer
"""

import asyncio
import time
import uuid
from typing import Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from cedarfix_shared.schemas import (
    ComplaintDecision, ComplaintRequest, LocationInput, PipelineStatus,
)
from cedarfix_shared.metrics import COMPLAINTS_TOTAL, PIPELINE_DURATION
from .orchestrator import run_pipeline
from .config import settings
from .database import init_db, save_complaint

app = FastAPI(
    title="CedarFix AI — Gateway",
    description="Complaint submission and pipeline orchestration endpoint",
    version="0.1.0",
)

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


@app.post("/complaints", response_model=ComplaintDecision, status_code=201)
async def submit_complaint(
    text: str = Form(..., min_length=10, max_length=2000),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    address_hint: Optional[str] = Form(None),
    district: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    """
    Submit a complaint with optional image and GPS coordinates.
    Returns the full ComplaintDecision with routing, severity, and dedup result.
    """
    start_ms = int(time.time() * 1000)
    complaint_id = str(uuid.uuid4())

    # Handle image upload
    image_filename = None
    if image:
        image_filename = f"{complaint_id}_{image.filename}"
        image_bytes = await image.read()
        _save_image(image_filename, image_bytes)

    # Build location if provided
    location = None
    if latitude is not None and longitude is not None:
        location = LocationInput(
            latitude=latitude,
            longitude=longitude,
            address_hint=address_hint,
            district=district,
        )

    request = ComplaintRequest(
        text=text,
        location=location,
        image_filename=image_filename,
        user_id=user_id,
    )

    COMPLAINTS_TOTAL.labels(status="received").inc()

    try:
        decision = await run_pipeline(complaint_id, request)
        decision.total_pipeline_ms = int(time.time() * 1000) - start_ms

        await save_complaint(decision)
        COMPLAINTS_TOTAL.labels(status="completed").inc()
        PIPELINE_DURATION.labels(stage="full").observe(decision.total_pipeline_ms / 1000)

        return decision

    except Exception as e:
        COMPLAINTS_TOTAL.labels(status="failed").inc()
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.get("/complaints/{complaint_id}", response_model=ComplaintDecision)
async def get_complaint(complaint_id: str):
    from .database import fetch_complaint
    result = await fetch_complaint(complaint_id)
    if not result:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return result


def _save_image(filename: str, data: bytes):
    import os
    uploads_dir = settings.uploads_dir
    os.makedirs(uploads_dir, exist_ok=True)
    with open(os.path.join(uploads_dir, filename), "wb") as f:
        f.write(data)

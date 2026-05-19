"""
IEP-8 — Human Review + Active Learning Service
================================================
Owned by: Systems/Integration Engineer

Responsibilities:
- Surface low-confidence complaints for admin review
- Accept admin corrections and store them
- Feed correction events into the retraining pipeline

DATA THIS SERVICE GENERATES (important for MLOps):
  - admin_corrections table rows → training examples for IEP-5, IEP-6
"""

import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from cedarfix_shared.schemas import AdminCorrection, RoutingEntity, SeverityLevel, ComplaintType
from .store import get_review_queue, save_correction

app = FastAPI(title="IEP-8: Human Review Service", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "review-service"}


@app.get("/queue")
async def get_queue(limit: int = 20):
    """
    Returns complaints awaiting human review.
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

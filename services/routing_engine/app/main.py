"""
IEP-6 — Routing Engine
========================
Owned by: Backend Engineer

Responsibilities:
- Map complaint to correct Lebanese public-sector entity
- Confidence-aware fallback:
    > 0.85  → auto-route
    0.65–0.85 → route + flag for review
    < 0.65  → send to Human Review Queue

MODEL (MVP): Rule-based keyword + type + district mapping
MODEL (Stretch): Fine-tuned multilingual classifier in MLflow Model Registry

DATA NEEDED:
  - Ground-truth routing labels (complaint → entity)
  - Lebanese municipality boundary data (optional: lat/lng → entity)
  - Minimum 50 labeled examples per entity for fine-tuning
"""

import os
import time
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List
from prometheus_client import make_asgi_app
from cedarfix_shared.schemas import RoutingResult, RoutingEntity
from cedarfix_shared.metrics import ROUTING_CONFIDENCE, LOW_CONFIDENCE_ROUTING, ROUTING_ENTITY
from .router import ComplaintRouter

AUTO_ROUTE_THRESHOLD = float(os.getenv("AUTO_ROUTE_THRESHOLD", "0.85"))
REVIEW_THRESHOLD = float(os.getenv("REVIEW_THRESHOLD", "0.65"))

app = FastAPI(title="IEP-6: Routing Engine", version="0.1.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

router = ComplaintRouter(AUTO_ROUTE_THRESHOLD, REVIEW_THRESHOLD)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "routing-engine"}


class RoutingRequest(BaseModel):
    complaint_id: str
    complaint_type: Optional[str] = None
    severity: Optional[str] = None
    location_district: Optional[str] = None
    location_mentions: List[str] = []
    extracted_keywords: List[str] = []


@app.post("/route", response_model=RoutingResult)
async def route_complaint(request: RoutingRequest):
    start = time.time()
    result = router.route(
        complaint_id=request.complaint_id,
        complaint_type=request.complaint_type,
        severity=request.severity,
        location_district=request.location_district,
        location_mentions=request.location_mentions,
        keywords=request.extracted_keywords,
    )
    result.processing_ms = int((time.time() - start) * 1000)

    ROUTING_CONFIDENCE.observe(result.primary_confidence)
    ROUTING_ENTITY.labels(entity=result.primary_entity).inc()
    if result.primary_confidence < REVIEW_THRESHOLD:
        LOW_CONFIDENCE_ROUTING.inc()

    return result

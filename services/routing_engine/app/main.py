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
from cedarfix_shared.metrics import (
    LOW_CONFIDENCE_ROUTING,
    RAG_NO_CANDIDATES_TOTAL,
    ROUTING_CONFIDENCE,
    ROUTING_ENTITY,
    ROUTING_REVIEW_TOTAL,
    ROUTING_SOURCE_TOTAL,
)
from .router import ComplaintRouter

AUTO_ROUTE_THRESHOLD = float(os.getenv("AUTO_ROUTE_THRESHOLD", "0.85"))
REVIEW_THRESHOLD = float(os.getenv("REVIEW_THRESHOLD", "0.65"))

app = FastAPI(title="IEP-6: Routing Engine", version="0.2.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

router = ComplaintRouter(AUTO_ROUTE_THRESHOLD, REVIEW_THRESHOLD)


def _review_reason_label(result: RoutingResult) -> str:
    reason = (result.review_reason or "").lower()
    if result.rag_no_candidates:
        return "rag_no_candidates"
    if "conflict" in result.routing_source or "rag suggests" in reason:
        return "rag_static_conflict"
    if "low" in reason and "confidence" in reason:
        return "low_confidence"
    if result.primary_confidence < REVIEW_THRESHOLD:
        return "low_confidence"
    if "human" in reason:
        return "llm_requested_review"
    return "unspecified"


@app.get("/health")
async def health():
    return {"status": "ok", "service": "routing-engine"}


class RoutingRequest(BaseModel):
    complaint_id: str
    complaint_type: Optional[str] = None
    category: Optional[str] = "other"
    subcategory: Optional[str] = "unknown"
    summary: Optional[str] = ""
    severity: Optional[str] = None
    original_text: Optional[str] = ""
    location_district: Optional[str] = None
    location_municipality: Optional[str] = None
    location_governorate: Optional[str] = None
    location_mentions: List[str] = []
    extracted_keywords: List[str] = []
    signals: Optional[dict] = None
    routing_features: Optional[dict] = None
    evidence_text: List[str] = []
    evidence_image: List[str] = []
    alignment_features: Optional[dict] = None
    multimodal_alignment: Optional[dict] = None


@app.post("/route", response_model=RoutingResult)
async def route_complaint(request: RoutingRequest):
    start = time.time()
    result = await router.route_async(
        complaint_id=request.complaint_id,
        complaint_type=request.complaint_type,
        category=request.category or "other",
        subcategory=request.subcategory or "unknown",
        summary=request.summary or "",
        severity=request.severity,
        original_text=request.original_text or "",
        location_district=request.location_district,
        location_municipality=request.location_municipality,
        location_governorate=request.location_governorate,
        location_mentions=request.location_mentions,
        keywords=request.extracted_keywords,
        signals=request.signals or {},
        routing_features=request.routing_features or {},
        evidence_text=request.evidence_text,
        evidence_image=request.evidence_image,
        alignment_features=request.alignment_features or {},
        multimodal_alignment=request.multimodal_alignment or {},
    )
    result.processing_ms = int((time.time() - start) * 1000)

    ROUTING_CONFIDENCE.observe(result.primary_confidence)
    ROUTING_ENTITY.labels(entity=result.primary_entity).inc()
    ROUTING_SOURCE_TOTAL.labels(source=result.routing_source).inc()
    if result.rag_no_candidates:
        RAG_NO_CANDIDATES_TOTAL.labels(complaint_type=request.complaint_type or "unknown").inc()
    if result.requires_review:
        ROUTING_REVIEW_TOTAL.labels(
            source=result.routing_source,
            reason=_review_reason_label(result),
        ).inc()
    if result.primary_confidence < REVIEW_THRESHOLD:
        LOW_CONFIDENCE_ROUTING.inc()

    return result

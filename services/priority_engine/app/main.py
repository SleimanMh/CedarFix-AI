"""
IEP-5 — Priority + Severity Engine
=====================================
Owned by: Backend Engineer

Responsibilities:
- Score complaint severity: LOW / MEDIUM / HIGH / CRITICAL
- Compute priority score 0.0–1.0
- Factor in: complaint type, cluster size, visual severity, location risk

MODEL (MVP): Rule-based scoring with weighted factors
MODEL (Stretch): Fine-tuned multilingual classifier on labeled severity data

DATA NEEDED:
  - Historical complaints with ground-truth severity labels
  - Location risk map (districts with higher infrastructure risk)
  - Cluster size data from IEP-4
"""

import time
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List
from prometheus_client import make_asgi_app
from cedarfix_shared.schemas import PriorityResult, SeverityLevel
from cedarfix_shared.metrics import SEVERITY_DISTRIBUTION, PRIORITY_SCORE
from .scorer import PriorityScorer

app = FastAPI(title="IEP-5: Priority Engine", version="0.1.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

scorer = PriorityScorer()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "priority-engine"}


class PriorityRequest(BaseModel):
    complaint_id: str
    complaint_type: Optional[str] = None
    cluster_size: int = 0
    visual_severity: str = "LOW"
    location_district: Optional[str] = None
    top_similarity_score: float = 0.0


@app.post("/predict", response_model=PriorityResult)
async def predict_priority(request: PriorityRequest):
    start = time.time()
    result = scorer.score(
        complaint_id=request.complaint_id,
        complaint_type=request.complaint_type,
        cluster_size=request.cluster_size,
        visual_severity=request.visual_severity,
        location_district=request.location_district,
        top_similarity_score=request.top_similarity_score,
    )
    result.processing_ms = int((time.time() - start) * 1000)

    SEVERITY_DISTRIBUTION.labels(level=result.severity).inc()
    PRIORITY_SCORE.observe(result.priority_score)

    return result

"""
IEP-4 — Clustering + Duplicate Detection Service
===================================================
Owned by: AI Engineer 1 (NLP)

Responsibilities:
- Per-request: classify a complaint as NEW / DUPLICATE / NEAR_DUPLICATE
  based on similarity scores from IEP-3
- Background job: run HDBSCAN on all embeddings to discover clusters

THRESHOLDS (tunable via env vars):
  DUPLICATE:       similarity >= 0.92
  NEAR_DUPLICATE:  similarity >= 0.78

DATA NEEDED:
  - At least 500 complaints in Qdrant before HDBSCAN produces meaningful clusters
  - Seed data script generates these synthetically
"""

import os
import asyncio
import time
from typing import List
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from prometheus_client import make_asgi_app
from cedarfix_shared.schemas import ClusteringResult, DuplicateStatus, SimilarComplaint
from cedarfix_shared.metrics import DUPLICATE_RATE
from .classifier import DuplicateClassifier
from .hdbscan_job import run_hdbscan_clustering

DUPLICATE_THRESHOLD = float(os.getenv("SIMILARITY_DUPLICATE_THRESHOLD", "0.92"))
NEAR_DUPLICATE_THRESHOLD = float(os.getenv("SIMILARITY_NEAR_DUPLICATE_THRESHOLD", "0.78"))

app = FastAPI(title="IEP-4: Clustering Service", version="0.1.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

classifier = DuplicateClassifier(DUPLICATE_THRESHOLD, NEAR_DUPLICATE_THRESHOLD)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "clustering-service"}


class ClusterRequest(BaseModel):
    complaint_id: str
    similar_complaints: List[dict]
    top_similarity_score: float


@app.post("/classify", response_model=ClusteringResult)
async def classify(request: ClusterRequest):
    start = time.time()
    result = classifier.classify(
        complaint_id=request.complaint_id,
        similar_complaints=request.similar_complaints,
        top_similarity_score=request.top_similarity_score,
    )
    result.processing_ms = int((time.time() - start) * 1000)

    DUPLICATE_RATE.labels(status=result.duplicate_status).inc()
    return result


@app.post("/run_clustering")
async def trigger_clustering(background_tasks: BackgroundTasks):
    """Trigger HDBSCAN batch clustering as a background job."""
    background_tasks.add_task(run_hdbscan_clustering)
    return {"status": "clustering_job_started"}


@app.get("/clusters")
async def get_clusters():
    from .hdbscan_job import get_cluster_summary
    return await get_cluster_summary()

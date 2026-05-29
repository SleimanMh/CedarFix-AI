"""
IEP-4 — Clustering + Duplicate Detection Service
===================================================
Responsibilities:
- Per-request: run the full multimodal deduplication pipeline
  (embedding similarity → scorer → LLM judge → cluster assign)

Input:  EmbeddingServiceResult from IEP-3
Output: MultimodalClusteringResult
"""

import time
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from prometheus_client import make_asgi_app

from cedarfix_shared.db import SessionLocal
from cedarfix_shared.schemas import EmbeddingServiceResult, MultimodalClusteringResult
from cedarfix_shared.metrics import DUPLICATE_RATE

from .classifier import MultimodalDuplicateClassifier

app = FastAPI(title="IEP-4: Clustering Service", version="0.2.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

_classifier = MultimodalDuplicateClassifier()


@contextmanager
def _db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "clustering-service"}


@app.post("/classify", response_model=MultimodalClusteringResult)
async def classify(embed_result: EmbeddingServiceResult):
    start = time.time()
    try:
        with _db_session() as db:
            result = _classifier.classify(embed_result, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    result.processing_ms = int((time.time() - start) * 1000)
    DUPLICATE_RATE.labels(status=result.duplicate_status.value).inc()
    return result





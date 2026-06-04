"""
IEP-1 — Text Understanding Service
====================================
Owned by: AI Engineer 1 (NLP)

Responsibilities:
- Detect language (Arabic / French / English)
- Normalize and clean text
- Classify complaint type
- Extract named entities and location mentions
- Produce multilingual sentence embedding

Model: sentence-transformers/paraphrase-multilingual-mpnet-base-v2
       (768-dim, supports Arabic + French + English natively)
"""

import time
from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_client import make_asgi_app
from cedarfix_shared.schemas import TextUnderstandingResult
from cedarfix_shared.metrics import (
    LANGUAGE_DISTRIBUTION,
    TEXT_ANALYSIS_DURATION,
    TEXT_CONFIDENCE_SCORE,
    TEXT_LOCATION_CONFIDENCE,
    TEXT_MISSING_LOCATION_TOTAL,
    TEXT_NOT_COMPLAINT_TOTAL,
    TEXT_UNKNOWN_TYPE_TOTAL,
)
from .model import TextUnderstandingModel

app = FastAPI(title="IEP-1: Text Understanding", version="0.2.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

model: TextUnderstandingModel = None


@app.on_event("startup")
async def load_models():
    global model
    model = TextUnderstandingModel()
    await model.load()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "text-understanding", "model_loaded": model is not None}


class TextAnalysisRequest(BaseModel):
    complaint_id: str
    text: str


@app.post("/analyze", response_model=TextUnderstandingResult)
async def analyze_text(request: TextAnalysisRequest):
    start = time.time()
    result = await model.analyze(request.complaint_id, request.text)
    elapsed_ms = int((time.time() - start) * 1000)
    result.processing_ms = elapsed_ms
    TEXT_ANALYSIS_DURATION.observe(elapsed_ms / 1000)
    LANGUAGE_DISTRIBUTION.labels(lang=result.language).inc()
    category = result.category or "unknown"
    issue_type = result.issue_type or "unknown"
    TEXT_CONFIDENCE_SCORE.labels(category=category, issue_type=issue_type).observe(result.confidence)
    TEXT_LOCATION_CONFIDENCE.labels(source=result.location.source or "none").observe(result.location.confidence)
    if issue_type == "unknown":
        TEXT_UNKNOWN_TYPE_TOTAL.labels(category=category).inc()
    if not result.location.normalized:
        TEXT_MISSING_LOCATION_TOTAL.labels(issue_type=issue_type).inc()
    if result.confidence == 0.0 and issue_type == "unknown":
        TEXT_NOT_COMPLAINT_TOTAL.inc()
    return result

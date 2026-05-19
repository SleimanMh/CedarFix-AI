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
import os
from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_client import make_asgi_app
from cedarfix_shared.schemas import TextAnalysisResult, Language, ComplaintType
from cedarfix_shared.metrics import TEXT_ANALYSIS_DURATION, LANGUAGE_DISTRIBUTION
from .model import TextUnderstandingModel

app = FastAPI(title="IEP-1: Text Understanding", version="0.1.0")
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


@app.post("/analyze", response_model=TextAnalysisResult)
async def analyze_text(request: TextAnalysisRequest):
    start = time.time()

    result = await model.analyze(request.complaint_id, request.text)

    elapsed_ms = int((time.time() - start) * 1000)
    result.processing_ms = elapsed_ms

    TEXT_ANALYSIS_DURATION.observe(elapsed_ms / 1000)
    LANGUAGE_DISTRIBUTION.labels(lang=result.detected_language).inc()

    return result

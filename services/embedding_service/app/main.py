"""
IEP-3 — Embedding + Similarity Service
=========================================
Owned by: AI Engineer 2 (Vision/Multimodal)

Responsibilities:
- Fuse text embedding (768-dim) + image embedding (512-dim) into one vector
- Store fused vector in Qdrant
- Search Qdrant for top-K similar complaints
- Return similarity scores for deduplication

FUSION STRATEGY (MVP):
  Weighted average after projecting both to same dimension (768):
    fused = alpha * text_emb + (1 - alpha) * project(image_emb)
  alpha = 0.7 if image is available and relevant, else 1.0 (text only)

DATA NEEDED:
  - No additional labeled data required for MVP (unsupervised similarity)
  - For stretch: pairs of (duplicate, non-duplicate) complaints for contrastive learning
"""

import time
import os
from typing import List, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_client import make_asgi_app
from cedarfix_shared.schemas import EmbeddingResult, SimilarComplaint
from cedarfix_shared.metrics import SIMILARITY_SCORE, DUPLICATE_RATE
from .fusion import fuse_embeddings
from .qdrant_client import QdrantStore

app = FastAPI(title="IEP-3: Embedding Service", version="0.1.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

qdrant: QdrantStore = None


@app.on_event("startup")
async def startup():
    global qdrant
    qdrant = QdrantStore()
    await qdrant.init_collection()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "embedding-service"}


class EmbedRequest(BaseModel):
    complaint_id: str
    text_embedding: List[float]
    image_embedding: List[float] = []
    image_available: bool = False


@app.post("/embed", response_model=EmbeddingResult)
async def embed(request: EmbedRequest):
    start = time.time()

    # 1. Fuse embeddings
    fused, strategy, text_w, image_w = fuse_embeddings(
        text_emb=request.text_embedding,
        image_emb=request.image_embedding,
        image_available=request.image_available,
    )

    # 2. Search Qdrant for similar complaints
    similar = await qdrant.search(fused, top_k=10)
    top_score = similar[0].similarity_score if similar else 0.0

    # 3. Store embedding for this complaint
    await qdrant.store(request.complaint_id, fused)

    elapsed_ms = int((time.time() - start) * 1000)

    SIMILARITY_SCORE.observe(top_score)

    return EmbeddingResult(
        complaint_id=request.complaint_id,
        fused_embedding=fused,
        fusion_strategy=strategy,
        text_weight=text_w,
        image_weight=image_w,
        similar_complaints=similar,
        top_similarity_score=top_score,
        processing_ms=elapsed_ms,
    )

"""
IEP-3 — Embedding + Retrieval Service
========================================
Owned by: AI Engineer 1/2 (Multimodal pipeline)

Responsibilities:
- Compute intra-complaint modal alignment (TextImageAlignment)
- Store text + image + fused embeddings in separate Qdrant collections
- Perform INDEPENDENT retrieval: text search, image search, geo-time search
- Merge candidate pools and return EmbeddingServiceResult

For fusion strategy see fusion.py.
For alignment logic see alignment.py.
For candidate retrieval see retrieval.py.
"""

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_client import make_asgi_app

from cedarfix_shared.schemas import (
    CanonicalComplaint,
    CanonicalLocationJSON,
    EmbeddingServiceResult,
    ImageUnderstandingResult,
    SignalsJSON,
    TextUnderstandingResult,
)
from cedarfix_shared.metrics import SIMILARITY_SCORE

from .alignment import ModalAlignmentComputer
from .qdrant_client import QdrantStore
from .retrieval import CandidateRetriever

app = FastAPI(title="IEP-3: Embedding + Retrieval Service", version="0.2.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

qdrant: QdrantStore = None
retriever: CandidateRetriever = None
aligner = ModalAlignmentComputer()


@app.on_event("startup")
async def startup():
    global qdrant, retriever
    qdrant = QdrantStore()
    await qdrant.init_collections()
    retriever = CandidateRetriever(qdrant)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "embedding-service"}


class EmbedRequest(BaseModel):
    complaint_id: str
    text_result: dict          # TextUnderstandingResult serialised as dict
    image_result: Optional[dict] = None   # ImageUnderstandingResult | None


@app.post("/embed", response_model=EmbeddingServiceResult)
async def embed(request: EmbedRequest):
    start = time.time()

    # ── Deserialise IEP-1 / IEP-2 results ───────────────────────────────────
    text_result = TextUnderstandingResult(**request.text_result)
    image_result = (
        ImageUnderstandingResult(**request.image_result)
        if request.image_result
        else None
    )

    text_emb = text_result.text_embedding
    image_emb = (image_result.image_embedding or []) if image_result else []
    image_present = bool(image_result and image_result.image_present and image_emb)
    image_relevance = (
        image_result.visual_understanding.confidence
        if image_present
        else 0.0
    )

    # ── 1. Intra-complaint modal alignment ───────────────────────────────────
    alignment = aligner.compute(text_result, image_result)

    # ── 2. Build canonical complaint ─────────────────────────────────────────
    loc = text_result.location
    canonical_loc = CanonicalLocationJSON(
        normalized_location=loc.normalized,
        district=loc.district,
        governorate=loc.governorate,
        latitude=loc.latitude,
        longitude=loc.longitude,
    )
    canonical = CanonicalComplaint(
        complaint_id=text_result.complaint_id,
        timestamp=datetime.now(tz=timezone.utc),
        summary=text_result.summary,
        category=text_result.category,
        subcategory=text_result.subcategory,
        issue_type=text_result.issue_type,
        severity=text_result.severity,
        location=canonical_loc,
        signals=text_result.signals,
        modality="TEXT_AND_IMAGE" if image_present else "TEXT_ONLY",
        text_embedding_id=f"txt_emb_{text_result.complaint_id}",
        image_embedding_id=f"img_emb_{text_result.complaint_id}" if image_present else "",
    )

    # ── 3. Build Qdrant payload metadata ─────────────────────────────────────
    base_payload = {
        "summary":              canonical.summary,
        "issue_type":           canonical.issue_type.value,
        "subcategory":          canonical.subcategory,
        "normalized_location":  canonical.location.normalized_location,
        "district":             canonical.location.district,
        "latitude":             canonical.location.latitude,
        "longitude":            canonical.location.longitude,
        "severity":             canonical.severity.value,
        "timestamp":            canonical.timestamp.timestamp(),
    }

    # ── 4. Store embeddings (text + image separately, no random projection) ──
    if text_emb:
        await qdrant.store_text(canonical.complaint_id, text_emb, base_payload)
    if image_present and image_emb:
        await qdrant.store_image(canonical.complaint_id, image_emb, base_payload)

    # ── 5. Independent candidate retrieval ───────────────────────────────────
    candidates = await retriever.retrieve(
        canonical=canonical,
        text_embedding=text_emb,
        image_embedding=image_emb,
        image_present=image_present,
    )

    elapsed_ms = int((time.time() - start) * 1000)
    top_score = max((c.raw_text_similarity for c in candidates), default=0.0)
    SIMILARITY_SCORE.observe(top_score)

    return EmbeddingServiceResult(
        complaint_id=canonical.complaint_id,
        canonical=canonical,
        alignment=alignment,
        candidates=candidates,
        text_embedding=text_emb,
        image_embedding=image_emb,
        processing_ms=elapsed_ms,
    )


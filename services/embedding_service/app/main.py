"""
IEP-3 — Embedding + Retrieval Service
========================================
Owned by: AI Engineer 1/2 (Multimodal pipeline)

Responsibilities:
- Compute intra-complaint modal alignment (TextImageAlignment)
- Store MPNet text embeddings in text_embeddings and CLIP embeddings in clip_embeddings
- Compute CLIP text encoding for every complaint (enables cross-modal duplicate detection)
- Perform INDEPENDENT retrieval: MPNet text search, CLIP text search, CLIP image search,
  geo-time search; merge with RRF and return EmbeddingServiceResult

For alignment logic see alignment.py.
For candidate retrieval see retrieval.py.
"""

import os
import time
from datetime import datetime, timezone
from typing import List, Optional

import torch
from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_client import make_asgi_app
from transformers import CLIPTextModelWithProjection, CLIPTokenizer

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

CLIP_MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "openai/clip-vit-base-patch32")

app = FastAPI(title="IEP-3: Embedding + Retrieval Service", version="0.3.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

qdrant: QdrantStore = None
retriever: CandidateRetriever = None
aligner = ModalAlignmentComputer()
_clip_tokenizer: CLIPTokenizer = None
_clip_text_model: CLIPTextModelWithProjection = None


def _encode_clip_text(text: str) -> List[float]:
    """Encode text with CLIP text encoder -> 512D L2-normalised vector."""
    inputs = _clip_tokenizer(
        [text],
        padding=True,
        truncation=True,
        max_length=77,
        return_tensors="pt",
    )
    with torch.no_grad():
        text_embeds = _clip_text_model(**inputs).text_embeds  # (1, 512)
    emb = text_embeds[0]
    emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb.tolist()


@app.on_event("startup")
async def startup():
    global qdrant, retriever, _clip_tokenizer, _clip_text_model
    qdrant = QdrantStore()
    await qdrant.init_collections()
    retriever = CandidateRetriever(qdrant)
    print(f"[IEP-3] Loading CLIP text encoder from {CLIP_MODEL_NAME} …")
    _clip_tokenizer = CLIPTokenizer.from_pretrained(CLIP_MODEL_NAME)
    _clip_text_model = CLIPTextModelWithProjection.from_pretrained(CLIP_MODEL_NAME)
    _clip_text_model.eval()
    print("[IEP-3] CLIP text encoder ready.")


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

    # ── 4. CLIP text encoding (always — enables cross-modal duplicate search) ───
    # Prefer clip_text_embedding pre-computed by IEP-2 (if image was present and
    # IEP-2 encoded the complaint text).  Otherwise compute it here.
    clip_text_emb: List[float] = (
        image_result.clip_text_embedding
        if (image_result and image_result.clip_text_embedding)
        else _encode_clip_text(text_result.normalized_text or text_result.original_text)
    )

    # ── 5. Store embeddings ────────────────────────────────────────────────
    if text_emb:
        await qdrant.store_text(canonical.complaint_id, text_emb, base_payload)
    # CLIP text entry always stored (drives cross-modal search)
    if clip_text_emb:
        await qdrant.store_clip_text(canonical.complaint_id, clip_text_emb, base_payload)
    # CLIP image entry stored only when image is present
    if image_present and image_emb:
        await qdrant.store_clip_image(canonical.complaint_id, image_emb, base_payload)

    # ── 6. Independent candidate retrieval ───────────────────────────────────
    candidates = await retriever.retrieve(
        canonical=canonical,
        text_embedding=text_emb,
        image_embedding=image_emb,
        clip_text_embedding=clip_text_emb,
        image_present=image_present,
    )

    elapsed_ms = int((time.time() - start) * 1000)
    top_score = max(
        (max(c.raw_mpnet_text_sim, c.raw_clip_text_sim, c.raw_clip_image_sim)
         for c in candidates),
        default=0.0,
    )
    SIMILARITY_SCORE.observe(top_score)

    return EmbeddingServiceResult(
        complaint_id=canonical.complaint_id,
        canonical=canonical,
        alignment=alignment,
        candidates=candidates,
        text_embedding=text_emb,
        image_embedding=image_emb,
        clip_text_embedding=clip_text_emb,
        processing_ms=elapsed_ms,
    )


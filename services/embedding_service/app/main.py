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
from sentence_transformers import SentenceTransformer
from transformers import CLIPTextModelWithProjection, CLIPTokenizer

from cedarfix_shared.schemas import (
    CanonicalComplaint,
    CanonicalLocationJSON,
    EmbeddingServiceResult,
    ImageUnderstandingResult,
    SignalsJSON,
    TextUnderstandingResult,
)
from cedarfix_shared.metrics import (
    EMBEDDING_CANDIDATE_COUNT,
    RETRIEVAL_SOURCE_HITS,
    SIMILARITY_SCORE,
    TEXT_IMAGE_ALIGNMENT_SCORE,
    TEXT_IMAGE_ALIGNMENT_TOTAL,
    TEXT_IMAGE_CONFLICT_FEATURE_TOTAL,
)

from .alignment import ModalAlignmentComputer
from .qdrant_client import QdrantStore
from .retrieval import CandidateRetriever

CLIP_MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "openai/clip-vit-base-patch32")
TEXT_MODEL_NAME = os.getenv("MODEL_NAME", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
AUGMENT_TEXT_EMBEDDING_WITH_IMAGE_CAPTION = (
    os.getenv("AUGMENT_TEXT_EMBEDDING_WITH_IMAGE_CAPTION", "true").lower() == "true"
)
STORE_IMAGE_CANDIDATE_EMBEDDINGS = (
    os.getenv("STORE_IMAGE_CANDIDATE_EMBEDDINGS", "true").lower() == "true"
)
CAPTION_AUGMENT_CONFIDENCE_THRESHOLD = float(os.getenv("CAPTION_AUGMENT_CONFIDENCE_THRESHOLD", "0.55"))

app = FastAPI(title="IEP-3: Embedding + Retrieval Service", version="0.3.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

qdrant: QdrantStore = None
retriever: CandidateRetriever = None
aligner = ModalAlignmentComputer()
_clip_tokenizer: CLIPTokenizer = None
_clip_text_model: CLIPTextModelWithProjection = None
_text_encoder: SentenceTransformer = None


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


def _english_complaint_text(text_result: TextUnderstandingResult) -> str:
    return (
        text_result.english_translation
        or text_result.normalized_text
        or text_result.original_text
        or ""
    ).strip()


def _image_caption(image_result: Optional[ImageUnderstandingResult]) -> str:
    if not image_result:
        return ""
    if image_result.vlm_analysis and image_result.vlm_analysis.caption:
        return image_result.vlm_analysis.caption.strip()
    if image_result.visual_understanding and image_result.visual_understanding.caption:
        return image_result.visual_understanding.caption.strip()
    return ""


def _should_augment_text_embedding(text_result: TextUnderstandingResult, caption: str) -> bool:
    if not AUGMENT_TEXT_EMBEDDING_WITH_IMAGE_CAPTION or not caption:
        return False
    issue_type = (text_result.issue_type or "").strip().lower()
    weak_type = issue_type in {"", "unknown", "other", "unspecified", "unspecified_issue"}
    return weak_type or float(text_result.confidence or 0.0) < CAPTION_AUGMENT_CONFIDENCE_THRESHOLD


def _image_issue_candidates(image_result: Optional[ImageUnderstandingResult]) -> list:
    if not image_result:
        return []
    if image_result.vlm_analysis and image_result.vlm_analysis.visual_candidates:
        return list(image_result.vlm_analysis.visual_candidates[:3])
    if image_result.visual_understanding and image_result.visual_understanding.visual_candidates:
        return list(image_result.visual_understanding.visual_candidates[:3])
    return []


def _candidate_embedding_text(candidate) -> str:
    parts = [
        getattr(candidate, "caption", "") or "",
        f"category: {getattr(candidate, 'visual_category', '') or ''}",
        f"subcategory: {getattr(candidate, 'visual_subcategory', '') or ''}",
        f"domain: {getattr(candidate, 'semantic_domain', '') or ''}",
        f"component: {getattr(candidate, 'physical_component', '') or ''}",
        f"failure: {getattr(candidate, 'failure_mode', '') or ''}",
        getattr(candidate, "evidence", "") or "",
    ]
    return " | ".join(part.strip() for part in parts if str(part or "").strip())


def _candidate_payload(base_payload: dict, candidate, index: int) -> dict:
    caption = getattr(candidate, "caption", "") or ""
    visual_subcategory = getattr(candidate, "visual_subcategory", "") or base_payload.get("subcategory")
    return {
        **base_payload,
        "summary": caption or base_payload.get("summary", ""),
        "issue_type": visual_subcategory or base_payload.get("issue_type", "unknown"),
        "subcategory": visual_subcategory or base_payload.get("subcategory", ""),
        "image_candidate_index": index,
        "image_candidate_caption": caption,
        "image_candidate_category": getattr(candidate, "visual_category", "") or "",
        "image_candidate_semantic_domain": getattr(candidate, "semantic_domain", None),
        "image_candidate_physical_component": getattr(candidate, "physical_component", None),
        "image_candidate_failure_mode": getattr(candidate, "failure_mode", None),
        "image_candidate_confidence": float(getattr(candidate, "confidence", 0.0) or 0.0),
    }


@app.on_event("startup")
async def startup():
    global qdrant, retriever, _clip_tokenizer, _clip_text_model, _text_encoder
    qdrant = QdrantStore()
    await qdrant.init_collections()
    retriever = CandidateRetriever(qdrant)
    print(f"[IEP-3] Loading CLIP text encoder from {CLIP_MODEL_NAME} …")
    _clip_tokenizer = CLIPTokenizer.from_pretrained(CLIP_MODEL_NAME)
    _clip_text_model = CLIPTextModelWithProjection.from_pretrained(CLIP_MODEL_NAME)
    _clip_text_model.eval()
    print("[IEP-3] CLIP text encoder ready.")
    if AUGMENT_TEXT_EMBEDDING_WITH_IMAGE_CAPTION or STORE_IMAGE_CANDIDATE_EMBEDDINGS:
        print(f"[IEP-3] Loading MPNet text encoder for caption augmentation: {TEXT_MODEL_NAME}")
        _text_encoder = SentenceTransformer(TEXT_MODEL_NAME)
        print("[IEP-3] MPNet auxiliary text encoder ready.")


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

    english_text = _english_complaint_text(text_result)
    caption = _image_caption(image_result)
    augmented_text_embedding = _should_augment_text_embedding(text_result, caption)
    if augmented_text_embedding and _text_encoder:
        embedding_text = f"Complaint: {english_text}\nImage caption: {caption}"
        text_emb = _text_encoder.encode(embedding_text).tolist()
    else:
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
    TEXT_IMAGE_ALIGNMENT_TOTAL.labels(
        status=alignment.alignment_status.value,
        reconciliation_status=alignment.reconciliation_status.value,
        conflict_detected=str(bool(alignment.conflict_detected)).lower(),
    ).inc()
    TEXT_IMAGE_ALIGNMENT_SCORE.labels(status=alignment.alignment_status.value).observe(
        alignment.alignment_score
    )
    for feature in alignment.conflicting_features:
        TEXT_IMAGE_CONFLICT_FEATURE_TOTAL.labels(feature=feature).inc()

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
        "embedding_text_source": "complaint_plus_image_caption" if augmented_text_embedding else "complaint_text",
        "image_caption":        caption or None,
        "issue_type":           canonical.issue_type,
        "subcategory":          canonical.subcategory,
        "normalized_location":  canonical.location.normalized_location,
        "district":             canonical.location.district,
        "latitude":             canonical.location.latitude,
        "longitude":            canonical.location.longitude,
        "severity":             canonical.severity.value,
        "timestamp":            canonical.timestamp.timestamp(),
    }

    # ── 4. CLIP text encoding (always — enables cross-modal duplicate search) ───
    # Use the English complaint text so multilingual/raw input maps consistently.
    clip_text_emb: List[float] = _encode_clip_text(english_text)

    # ── 5. Store embeddings ────────────────────────────────────────────────
    if text_emb:
        await qdrant.store_text(canonical.complaint_id, text_emb, base_payload)
    # CLIP text entry always stored (drives cross-modal search)
    if clip_text_emb:
        await qdrant.store_clip_text(canonical.complaint_id, clip_text_emb, base_payload)
    # CLIP image entry stored only when image is present
    if image_present and image_emb:
        await qdrant.store_clip_image(canonical.complaint_id, image_emb, base_payload)

    if STORE_IMAGE_CANDIDATE_EMBEDDINGS and image_present:
        for index, candidate in enumerate(_image_issue_candidates(image_result)):
            candidate_text = _candidate_embedding_text(candidate)
            if not candidate_text:
                continue

            candidate_payload = _candidate_payload(base_payload, candidate, index)
            if _text_encoder:
                candidate_text_emb = _text_encoder.encode(candidate_text).tolist()
                await qdrant.store_text_candidate(
                    canonical.complaint_id,
                    index,
                    candidate_text_emb,
                    candidate_payload,
                )
            candidate_clip_text_emb = _encode_clip_text(candidate_text)
            await qdrant.store_clip_image_candidate(
                canonical.complaint_id,
                index,
                candidate_clip_text_emb,
                candidate_payload,
            )

    # ── 6. Independent candidate retrieval ───────────────────────────────────
    candidates = await retriever.retrieve(
        canonical=canonical,
        text_embedding=text_emb,
        image_embedding=image_emb,
        clip_text_embedding=clip_text_emb,
        image_present=image_present,
    )
    modality = "text_and_image" if image_present else "text_only"
    EMBEDDING_CANDIDATE_COUNT.labels(modality=modality).observe(len(candidates))
    for candidate in candidates:
        for source in candidate.sources:
            RETRIEVAL_SOURCE_HITS.labels(source=source).inc()

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


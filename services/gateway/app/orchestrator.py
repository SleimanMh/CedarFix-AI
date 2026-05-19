"""
Pipeline Orchestrator — calls IEPs in the correct order.
IEP-1 and IEP-2 run in parallel (text and image are independent).
IEP-3 through IEP-6 run sequentially (each depends on prior results).
"""

import asyncio
import time
import httpx

from cedarfix_shared.schemas import (
    ComplaintDecision, ComplaintRequest, PipelineStatus,
    TextAnalysisResult, ImageAnalysisResult, EmbeddingResult,
    ClusteringResult, PriorityResult, RoutingResult, ExplanationResult,
)
from cedarfix_shared.metrics import PIPELINE_DURATION
from .config import settings

TIMEOUT = httpx.Timeout(30.0)


async def run_pipeline(complaint_id: str, request: ComplaintRequest) -> ComplaintDecision:
    """
    Full EEP → IEP orchestration.
    Returns a complete ComplaintDecision.
    """
    decision = ComplaintDecision(
        complaint_id=complaint_id,
        status=PipelineStatus.PROCESSING,
        original_text=request.text,
        location=request.location,
        image_filename=request.image_filename,
    )

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:

        # --- Stage 1: IEP-1 + IEP-2 in parallel ---
        t0 = time.time()
        text_task = _call_text_understanding(client, complaint_id, request)
        image_task = _call_image_understanding(client, complaint_id, request)
        text_result, image_result = await asyncio.gather(text_task, image_task)
        PIPELINE_DURATION.labels(stage="iep1_iep2").observe(time.time() - t0)

        decision.text_analysis = text_result
        decision.image_analysis = image_result

        if text_result:
            decision.complaint_type = text_result.complaint_type

        # --- Stage 2: IEP-3 Embedding + Similarity ---
        t0 = time.time()
        embedding_result = await _call_embedding_service(client, complaint_id, text_result, image_result)
        decision.embedding = embedding_result
        PIPELINE_DURATION.labels(stage="iep3").observe(time.time() - t0)

        # --- Stage 3: IEP-4 Clustering + Deduplication ---
        t0 = time.time()
        clustering_result = await _call_clustering_service(client, complaint_id, embedding_result)
        decision.clustering = clustering_result
        if clustering_result:
            decision.is_duplicate = clustering_result.duplicate_status in ("DUPLICATE",)
        PIPELINE_DURATION.labels(stage="iep4").observe(time.time() - t0)

        # --- Stage 4: IEP-5 Priority ---
        t0 = time.time()
        priority_result = await _call_priority_engine(client, complaint_id, decision)
        decision.priority = priority_result
        if priority_result:
            decision.severity = priority_result.severity
            decision.priority_score = priority_result.priority_score
        PIPELINE_DURATION.labels(stage="iep5").observe(time.time() - t0)

        # --- Stage 5: IEP-6 Routing ---
        t0 = time.time()
        routing_result = await _call_routing_engine(client, complaint_id, decision)
        decision.routing = routing_result
        if routing_result:
            decision.assigned_entity = routing_result.primary_entity
            decision.routing_confidence = routing_result.primary_confidence
        PIPELINE_DURATION.labels(stage="iep6").observe(time.time() - t0)

        # --- Stage 6: IEP-7 Explanation (non-blocking, fire-and-forget) ---
        explanation_result = await _call_explanation_service(client, complaint_id, decision)
        decision.explanation = explanation_result

    decision.status = PipelineStatus.REVIEW_REQUIRED if (
        routing_result and routing_result.requires_review
    ) else PipelineStatus.COMPLETED

    return decision


# ---------------------------------------------------------------------------
# IEP Callers — each wraps one HTTP call with graceful degradation
# ---------------------------------------------------------------------------

async def _call_text_understanding(client, complaint_id, request) -> TextAnalysisResult | None:
    try:
        resp = await client.post(
            f"{settings.text_service_url}/analyze",
            json={"complaint_id": complaint_id, "text": request.text},
        )
        resp.raise_for_status()
        return TextAnalysisResult(**resp.json())
    except Exception as e:
        # Graceful degradation: log and continue with None
        print(f"[WARN] IEP-1 failed: {e}")
        return None


async def _call_image_understanding(client, complaint_id, request) -> ImageAnalysisResult | None:
    if not request.image_filename:
        return ImageAnalysisResult(
            complaint_id=complaint_id,
            image_available=False,
            processing_ms=0,
        )
    try:
        resp = await client.post(
            f"{settings.image_service_url}/analyze",
            json={"complaint_id": complaint_id, "image_filename": request.image_filename},
        )
        resp.raise_for_status()
        return ImageAnalysisResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-2 failed: {e}")
        return ImageAnalysisResult(complaint_id=complaint_id, image_available=False, processing_ms=0)


async def _call_embedding_service(client, complaint_id, text_result, image_result) -> EmbeddingResult | None:
    try:
        payload = {
            "complaint_id": complaint_id,
            "text_embedding": text_result.text_embedding if text_result else [],
            "image_embedding": image_result.image_embedding if image_result else [],
            "image_available": image_result.image_available if image_result else False,
        }
        resp = await client.post(f"{settings.embedding_service_url}/embed", json=payload)
        resp.raise_for_status()
        return EmbeddingResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-3 failed: {e}")
        return None


async def _call_clustering_service(client, complaint_id, embedding_result) -> ClusteringResult | None:
    try:
        payload = {
            "complaint_id": complaint_id,
            "similar_complaints": [s.dict() for s in embedding_result.similar_complaints] if embedding_result else [],
            "top_similarity_score": embedding_result.top_similarity_score if embedding_result else 0.0,
        }
        resp = await client.post(f"{settings.clustering_service_url}/classify", json=payload)
        resp.raise_for_status()
        return ClusteringResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-4 failed: {e}")
        return ClusteringResult(complaint_id=complaint_id, duplicate_status="NEW", processing_ms=0)


async def _call_priority_engine(client, complaint_id, decision) -> PriorityResult | None:
    try:
        payload = {
            "complaint_id": complaint_id,
            "complaint_type": decision.complaint_type,
            "cluster_size": decision.clustering.cluster_size if decision.clustering else 0,
            "visual_severity": decision.image_analysis.visual_severity_signal if decision.image_analysis else "LOW",
            "location_district": decision.location.district if decision.location else None,
            "top_similarity_score": decision.embedding.top_similarity_score if decision.embedding else 0.0,
        }
        resp = await client.post(f"{settings.priority_service_url}/predict", json=payload)
        resp.raise_for_status()
        return PriorityResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-5 failed: {e}")
        return None


async def _call_routing_engine(client, complaint_id, decision) -> RoutingResult | None:
    try:
        payload = {
            "complaint_id": complaint_id,
            "complaint_type": decision.complaint_type,
            "severity": decision.severity,
            "location_district": decision.location.district if decision.location else None,
            "location_mentions": decision.text_analysis.location_mentions if decision.text_analysis else [],
            "extracted_keywords": decision.text_analysis.extracted_keywords if decision.text_analysis else [],
        }
        resp = await client.post(f"{settings.routing_service_url}/route", json=payload)
        resp.raise_for_status()
        return RoutingResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-6 failed: {e}")
        return None


async def _call_explanation_service(client, complaint_id, decision) -> ExplanationResult | None:
    try:
        resp = await client.post(
            f"{settings.explanation_service_url}/explain",
            json={
                "complaint_id": complaint_id,
                "complaint_type": decision.complaint_type,
                "severity": decision.severity,
                "assigned_entity": decision.assigned_entity,
                "routing_confidence": decision.routing_confidence,
                "is_duplicate": decision.is_duplicate,
                "urgency_factors": decision.priority.urgency_factors if decision.priority else [],
            },
        )
        resp.raise_for_status()
        return ExplanationResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-7 failed: {e}")
        return None

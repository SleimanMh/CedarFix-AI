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
    TextUnderstandingResult, ImageUnderstandingResult,
    EmbeddingServiceResult, MultimodalClusteringResult,
    DuplicateStatus,
    PriorityResult, RoutingResult, ExplanationResult,
    ComplaintType, MediaValidationResult, MediaValidationStatus,
    HumanReviewItem, TextImageAlignment,
)
from cedarfix_shared.metrics import PIPELINE_DURATION
from .config import settings

TIMEOUT = httpx.Timeout(60.0)


async def run_pipeline(complaint_id: str, request: ComplaintRequest) -> ComplaintDecision:
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
        text_result, image_result = await asyncio.gather(
            _call_text_understanding(client, complaint_id, request),
            _call_image_understanding(client, complaint_id, request),
        )
        PIPELINE_DURATION.labels(stage="iep1_iep2").observe(time.time() - t0)

        decision.text_analysis = text_result
        decision.image_analysis = image_result

        if text_result:
            decision.complaint_type = text_result.issue_type

        # --- Media Validation Gate ---
        # Runs after IEP-1+IEP-2, before any downstream IEPs.
        # Catches: no complaint in text, text/image contradictions, ambiguous submissions.
        validation = _validate_media(text_result, image_result)
        decision.media_validation = validation

        if validation.status == MediaValidationStatus.CONTRADICTION:
            decision.status = PipelineStatus.CONTRADICTION
            return decision

        if validation.status == MediaValidationStatus.NEEDS_CLARIFICATION:
            decision.status = PipelineStatus.NEEDS_CLARIFICATION
            await _add_to_human_review(client, complaint_id, request, validation)
            return decision

        if validation.status == MediaValidationStatus.HUMAN_REVIEW:
            decision.status = PipelineStatus.REVIEW_REQUIRED
            await _add_to_human_review(client, complaint_id, request, validation)
            return decision

        if validation.status == MediaValidationStatus.INVALID_NO_COMPLAINT:
            decision.status = PipelineStatus.INVALID_NO_COMPLAINT
            return decision

        # --- Stage 2: IEP-3 Embedding + Retrieval ---
        t0 = time.time()
        embedding_result = await _call_embedding_service(client, complaint_id, text_result, image_result)
        decision.embedding = embedding_result
        if embedding_result and embedding_result.alignment:
            decision.text_image_alignment = embedding_result.alignment
            a = embedding_result.alignment
            if (
                a.conflict_detected
                and getattr(a, "reconciliation_status", None) in ("MODAL_CONFLICT", "modal_conflict")
                and image_result and image_result.image_present
            ):
                decision.status = PipelineStatus.CONTRADICTION
                decision.media_validation = MediaValidationResult(
                    status=MediaValidationStatus.CONTRADICTION,
                    text_is_complaint=True,
                    image_has_complaint=True,
                    text_detected_type=str(a.text_issue_type) if a.text_issue_type else None,
                    image_detected_type=str(a.image_issue_type) if a.image_issue_type else None,
                    contradiction_reason=(
                        f"Your text describes a {a.text_issue_type or 'infrastructure'} issue "
                        f"but your image appears to show something different "
                        f"({a.image_issue_type or 'unrelated content'}). "
                        f"Please resubmit with a photo that matches your complaint."
                    ),
                )
                return decision
        PIPELINE_DURATION.labels(stage="iep3").observe(time.time() - t0)

        # --- Stage 3: IEP-4 Clustering + Deduplication ---
        t0 = time.time()
        clustering_result = await _call_clustering_service(client, complaint_id, embedding_result)
        decision.clustering = clustering_result
        if clustering_result:
            decision.is_duplicate = clustering_result.duplicate_status == DuplicateStatus.DUPLICATE
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

        # --- Stage 6: IEP-7 Explanation ---
        explanation_result = await _call_explanation_service(client, complaint_id, decision)
        decision.explanation = explanation_result

    decision.status = PipelineStatus.REVIEW_REQUIRED if (
        routing_result and routing_result.requires_review
    ) else PipelineStatus.COMPLETED

    return decision


# ---------------------------------------------------------------------------
# IEP Callers
# ---------------------------------------------------------------------------

async def _call_text_understanding(
    client, complaint_id: str, request: ComplaintRequest
) -> TextUnderstandingResult | None:
    try:
        resp = await client.post(
            f"{settings.text_service_url}/analyze",
            json={"complaint_id": complaint_id, "text": request.text},
        )
        resp.raise_for_status()
        return TextUnderstandingResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-1 failed: {e}")
        return None


async def _call_image_understanding(
    client, complaint_id: str, request: ComplaintRequest
) -> ImageUnderstandingResult | None:
    if not request.image_filename:
        return None
    try:
        resp = await client.post(
            f"{settings.image_service_url}/analyze",
            json={
                "complaint_id": complaint_id,
                "image_filename": request.image_filename,
                # Pass complaint text so IEP-2 can compute clip_text_embedding.
                # This enables alignment.py to use CLIP-native cosine similarity
                # (same 512-dim space) instead of the cross-model random projection.
                "complaint_text": request.text,
            },
        )
        resp.raise_for_status()
        return ImageUnderstandingResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-2 failed: {e}")
        return None


async def _call_embedding_service(
    client, complaint_id: str,
    text_result: TextUnderstandingResult | None,
    image_result: ImageUnderstandingResult | None,
) -> EmbeddingServiceResult | None:
    if not text_result:
        print("[WARN] IEP-3 skipped: no text result")
        return None
    try:
        payload = {
            "complaint_id": complaint_id,
            "text_result": text_result.model_dump(),
            "image_result": image_result.model_dump() if image_result else None,
        }
        resp = await client.post(f"{settings.embedding_service_url}/embed", json=payload)
        resp.raise_for_status()
        return EmbeddingServiceResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-3 failed: {e}")
        return None


async def _call_clustering_service(
    client, complaint_id: str,
    embedding_result: EmbeddingServiceResult | None,
) -> MultimodalClusteringResult | None:
    if not embedding_result:
        return None
    try:
        resp = await client.post(
            f"{settings.clustering_service_url}/classify",
            json=embedding_result.model_dump(mode="json"),
        )
        resp.raise_for_status()
        return MultimodalClusteringResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-4 failed: {e}")
        return None


async def _call_priority_engine(client, complaint_id: str, decision: ComplaintDecision) -> PriorityResult | None:
    try:
        text = decision.text_analysis
        image = decision.image_analysis
        clustering = decision.clustering
        payload = {
            "complaint_id": complaint_id,
            "complaint_type": decision.complaint_type,
            "cluster_size": clustering.cluster_size if clustering else 0,
            "visual_severity": (
                image.visual_understanding.visual_severity
                if image and image.image_present and image.visual_understanding
                else "LOW"
            ),
            "location_district": decision.location.district if decision.location else None,
            "top_similarity_score": (
                max((c.multimodal_score for c in clustering.top_candidates), default=0.0)
                if clustering and clustering.top_candidates
                else 0.0
            ),
        }
        resp = await client.post(f"{settings.priority_service_url}/predict", json=payload)
        resp.raise_for_status()
        return PriorityResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-5 failed: {e}")
        return None


async def _call_routing_engine(client, complaint_id: str, decision: ComplaintDecision) -> RoutingResult | None:
    try:
        text = decision.text_analysis
        payload = {
            "complaint_id": complaint_id,
            "complaint_type": decision.complaint_type,
            "severity": decision.severity,
            "location_district": decision.location.district if decision.location else None,
            "location_mentions": (
                [text.location.normalized] if text and text.location else []
            ),
            "extracted_keywords": text.urgency_keywords if text else [],
        }
        resp = await client.post(f"{settings.routing_service_url}/route", json=payload)
        resp.raise_for_status()
        return RoutingResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-6 failed: {e}")
        return None


async def _call_explanation_service(
    client, complaint_id: str, decision: ComplaintDecision
) -> ExplanationResult | None:
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


# ---------------------------------------------------------------------------
# Media Validation Gate helpers
# ---------------------------------------------------------------------------

# Maps issue_type → broad visual category for contradiction detection
_TYPE_TO_CATEGORY: dict = {
    "pothole":            "roads",
    "road_damage":        "roads",
    "traffic_light":      "roads",
    "sidewalk_damage":    "roads",
    "traffic_incident":   "roads",
    "flooding":           "drainage",
    "waste_accumulation": "sanitation",
    "electricity_outage": "electricity",
    "streetlight":        "electricity",
    "water_pipe":         "water",
    "telecom_outage":     "telecom",
    "public_safety":      "other",
}


def _validate_media(
    text_result: TextUnderstandingResult | None,
    image_result: ImageUnderstandingResult | None,
) -> MediaValidationResult:
    """
    Gate logic after IEP-1 + IEP-2, before IEP-3.
    Returns a MediaValidationResult indicating whether to proceed or stop.
    """
    # --- Assess text ---
    text_is_complaint = False
    text_type_str: str | None = None
    text_category: str | None = None
    text_service_failed = text_result is None   # IEP-1 completely unavailable

    if text_result:
        raw = text_result.issue_type
        text_type_str = raw.value if hasattr(raw, "value") else str(raw)
        text_is_complaint = (
            text_result.confidence >= 0.35 and text_type_str != "other"
        ) or text_result.confidence >= 0.55
        text_category = _TYPE_TO_CATEGORY.get(text_type_str)

    # --- Assess image ---
    image_has_complaint = False
    image_type_str: str | None = None
    image_category: str | None = None
    has_image = image_result is not None and image_result.image_present

    if has_image:
        vu = image_result.visual_understanding
        iq = image_result.image_quality
        image_has_complaint = iq.usable and vu.damage_visible and vu.confidence >= 0.40
        image_type_str = vu.visual_subcategory or None
        image_category = vu.visual_category or None

    # --- Decision matrix ---
    # If IEP-1 service was completely unreachable, don't block — let pipeline continue
    if text_service_failed:
        return MediaValidationResult(
            status=MediaValidationStatus.VALID,
            text_is_complaint=False,
            image_has_complaint=image_has_complaint,
            text_detected_type=None,
            image_detected_type=image_type_str,
        )

    if text_is_complaint:
        # Contradiction: text and image point to different infrastructure categories
        if (
            image_has_complaint
            and text_category
            and image_category
            and text_category != image_category
            and image_result.visual_understanding.confidence >= 0.50
        ):
            return MediaValidationResult(
                status=MediaValidationStatus.CONTRADICTION,
                text_is_complaint=True,
                image_has_complaint=True,
                text_detected_type=text_type_str,
                image_detected_type=image_type_str,
                contradiction_reason=(
                    f"Your text describes a {text_category} issue "
                    f"({text_type_str.replace('_', ' ')}), but your image shows "
                    f"a {image_category} issue ({(image_type_str or 'unknown').replace('_', ' ')}). "
                    f"Please resubmit with matching text and photo."
                ),
            )
        return MediaValidationResult(
            status=MediaValidationStatus.VALID,
            text_is_complaint=True,
            image_has_complaint=image_has_complaint,
            text_detected_type=text_type_str,
            image_detected_type=image_type_str,
        )

    # Text is NOT a complaint — check image
    if image_has_complaint:
        return MediaValidationResult(
            status=MediaValidationStatus.NEEDS_CLARIFICATION,
            text_is_complaint=False,
            image_has_complaint=True,
            image_detected_type=image_type_str,
            text_detected_type=text_type_str,
            clarification_question=(
                f"Your text doesn't clearly describe a public infrastructure complaint, "
                f"but your image shows a {image_category or 'infrastructure'} issue "
                f"({(image_type_str or 'unknown').replace('_', ' ')}). "
                f"Did you mean to report this? Please add a text description."
            ),
        )

    if has_image:
        return MediaValidationResult(
            status=MediaValidationStatus.HUMAN_REVIEW,
            text_is_complaint=False,
            image_has_complaint=False,
            clarification_question=(
                "Your submission is unclear — neither the text nor the image clearly "
                "shows a public infrastructure problem. A human reviewer will assess it."
            ),
        )

    return MediaValidationResult(
        status=MediaValidationStatus.INVALID_NO_COMPLAINT,
        text_is_complaint=False,
        image_has_complaint=False,
    )


async def _add_to_human_review(
    client: httpx.AsyncClient,
    complaint_id: str,
    request: ComplaintRequest,
    validation: MediaValidationResult,
) -> None:
    """Fire-and-forget: queue flagged submissions in the review service."""
    try:
        item = HumanReviewItem(
            complaint_id=complaint_id,
            validation_status=validation.status.value,
            review_reason=validation.clarification_question or "",
            original_text=request.text,
            image_filename=request.image_filename,
            image_detected_type=validation.image_detected_type,
            text_detected_type=validation.text_detected_type,
        )
        await client.post(
            f"{settings.review_service_url}/human-review",
            json=item.model_dump(),
        )
    except Exception as e:
        print(f"[WARN] Could not queue human review item: {e}")
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
            decision.complaint_type = text_result.issue_type

        # --- Stage 2: IEP-3 Embedding + Similarity ---
        t0 = time.time()
        embedding_result = await _call_embedding_service(client, complaint_id, text_result, image_result)
        decision.embedding = embedding_result
        if embedding_result and embedding_result.alignment:
            decision.text_image_alignment = embedding_result.alignment
            a = embedding_result.alignment
            if (
                a.conflict_detected
                and getattr(a, "reconciliation_status", None) in ("MODAL_CONFLICT", "modal_conflict")
                and image_result and image_result.image_present
            ):
                decision.status = PipelineStatus.CONTRADICTION
                decision.media_validation = MediaValidationResult(
                    status=MediaValidationStatus.CONTRADICTION,
                    text_is_complaint=True,
                    image_has_complaint=True,
                    text_detected_type=str(a.text_issue_type) if a.text_issue_type else None,
                    image_detected_type=str(a.image_issue_type) if a.image_issue_type else None,
                    contradiction_reason=(
                        f"Your text describes a {a.text_issue_type or 'infrastructure'} issue "
                        f"but your image appears to show something different "
                        f"({a.image_issue_type or 'unrelated content'}). "
                        f"Please resubmit with a photo that matches your complaint."
                    ),
                )
                return decision
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

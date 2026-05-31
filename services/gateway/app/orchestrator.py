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
    ConfidenceBundle, StageConfidence,
)
from cedarfix_shared.metrics import PIPELINE_DURATION
from .config import settings
from .moderation import moderate, ModerationDecisionEnum

TIMEOUT = httpx.Timeout(60.0)


async def run_pipeline(complaint_id: str, request: ComplaintRequest) -> ComplaintDecision:
    decision = ComplaintDecision(
        complaint_id=complaint_id,
        status=PipelineStatus.PROCESSING,
        original_text=request.text,
        user_id=request.user_id,
        location=request.location,
        image_filename=request.image_filename,
    )

    # --- IEP-0: Moderation Gate (runs before everything else) ---
    t0 = time.time()
    mod_result = await moderate(
        complaint_text=request.text,
        image_filename=request.image_filename or None,
        user_id=getattr(request, "user_id", None),
    )
    decision.moderation = mod_result
    PIPELINE_DURATION.labels(stage="iep0_moderation").observe(time.time() - t0)

    if mod_result.decision == ModerationDecisionEnum.REJECT:
        decision.status = PipelineStatus.REJECTED
        return decision

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

            # RAG no-match: routing knowledge base has zero candidates for this complaint.
            # Flag for HITL immediately so an admin can classify it:
            # unsupported type, data gap, fake, or out-of-scope.
            if routing_result.rag_no_candidates:
                decision.status = PipelineStatus.REVIEW_REQUIRED
                await _add_to_human_review(
                    client, complaint_id, request,
                    MediaValidationResult(
                        status=MediaValidationStatus.HUMAN_REVIEW,
                        text_is_complaint=True,
                        image_has_complaint=bool(request.image_filename),
                        text_detected_type=(
                            str(decision.complaint_type)
                            if decision.complaint_type else None
                        ),
                        contradiction_reason=routing_result.review_reason,
                        clarification_question=None,
                    ),
                )

        PIPELINE_DURATION.labels(stage="iep6").observe(time.time() - t0)

        # --- Confidence bundle assembly ---
        decision.confidence_bundle = _build_confidence_bundle(
            text_result=decision.text_analysis,
            image_result=decision.image_analysis,
            clustering_result=decision.clustering,
            routing_result=routing_result,
            alignment_result=embedding_result.alignment if embedding_result else None,
        )

        # --- Stage 6: IEP-7 Explanation ---
        explanation_result = await _call_explanation_service(client, complaint_id, decision)
        decision.explanation = explanation_result

    decision.status = PipelineStatus.REVIEW_REQUIRED if (
        routing_result and routing_result.requires_review
    ) else PipelineStatus.COMPLETED

    return decision


# ---------------------------------------------------------------------------
# Confidence Bundle Assembly
# ---------------------------------------------------------------------------

def _build_confidence_bundle(
    text_result,
    image_result,
    clustering_result,
    routing_result,
    alignment_result=None,
) -> ConfidenceBundle:
    """
    Assembles per-stage StageConfidence objects and computes a final
    weighted geometric mean confidence for the pipeline decision.

    Weights (must sum to 1.0):
      text_type       0.30
      text_location   0.10
      image_clf       0.15  (0 if no image)
      image_alignment 0.10  (0 if no image)
      duplicate       0.20
      routing         0.15
    """
    import math

    stages: dict[str, "StageConfidence"] = {}

    # Text type classification
    if text_result and text_result.confidence is not None:
        stages["text_type"] = StageConfidence(
            score=text_result.confidence,
            method="llm",
            reliable=text_result.confidence >= 0.50,
        )

    # Text location confidence
    if text_result and text_result.location:
        loc = text_result.location
        # location 'source' indicates how it was resolved
        source = getattr(loc, "source", "none")
        loc_conf = 0.90 if source == "gps" else 0.80 if source in ("seed", "llm") else 0.50
        stages["text_location"] = StageConfidence(
            score=loc_conf,
            method=source or "heuristic",
            reliable=loc_conf >= 0.70,
        )

    # Image classification
    if image_result and image_result.image_present and image_result.visual_understanding:
        vu = image_result.visual_understanding
        img_conf = getattr(vu, "confidence", 0.70)
        stages["image_classification"] = StageConfidence(
            score=img_conf,
            method="clip",
            reliable=img_conf >= 0.55,
        )

    # Image alignment
    if alignment_result and getattr(alignment_result, "alignment_status", None):
        alignment = str(alignment_result.alignment_status)
        ali_conf = {
            "SUPPORTS": 0.90,
            "UNCERTAIN": 0.50,
            "CONTRADICTS": 0.25,
            "UNRELATED": 0.30,
            "NO_IMAGE": 0.0,
        }.get(alignment, 0.50)
        stages["image_alignment"] = StageConfidence(
            score=ali_conf,
            method="clip_cosine",
            reliable=ali_conf >= 0.60,
        )

    # Duplicate detection
    if clustering_result:
        dup_conf = getattr(clustering_result, "confidence", 0.70)
        stages["duplicate"] = StageConfidence(
            score=dup_conf,
            method="multimodal_scorer",
            reliable=dup_conf >= 0.60,
        )

    # Routing
    if routing_result:
        stages["routing"] = StageConfidence(
            score=routing_result.primary_confidence,
            method=routing_result.routing_source,
            reliable=routing_result.primary_confidence >= 0.65,
        )

    has_image = image_result is not None and getattr(image_result, "image_present", False)

    if has_image:
        weights = {
            "text_type":          0.30,
            "text_location":      0.08,
            "image_classification": 0.14,
            "image_alignment":    0.10,
            "duplicate":          0.20,
            "routing":            0.18,
        }
    else:
        weights = {
            "text_type":  0.40,
            "text_location": 0.10,
            "duplicate":  0.28,
            "routing":    0.22,
        }

    # Weighted geometric mean (log-sum of log(score) * weight)
    log_sum = 0.0
    total_w = 0.0
    for stage_key, w in weights.items():
        sc = stages.get(stage_key)
        if sc and sc.score > 0:
            log_sum += w * math.log(max(sc.score, 1e-6))
            total_w += w

    final_conf = round(math.exp(log_sum / total_w), 3) if total_w > 0 else 0.50

    # Determine weakest stage and review triggers
    weakest = None
    review_triggers: list[str] = []
    for stage_key, sc in stages.items():
        if not sc.reliable:
            review_triggers.append(stage_key)
        if weakest is None or sc.score < stages[weakest].score:
            weakest = stage_key

    # Extra review triggers from routing flags
    if routing_result and getattr(routing_result, "requires_review", False):
        if "routing" not in review_triggers:
            review_triggers.append("routing")
    if text_result and getattr(text_result, "unknown_type", False):
        if "text_type" not in review_triggers:
            review_triggers.append("text_type")

    return ConfidenceBundle(
        text_type=stages.get("text_type") or StageConfidence(),
        text_location=stages.get("text_location") or StageConfidence(),
        image_classification=stages.get("image_classification"),
        image_alignment=stages.get("image_alignment"),
        duplicate=stages.get("duplicate"),
        routing=stages.get("routing"),
        final=final_conf,
        weakest_stage=weakest or "",
        review_triggered_by=", ".join(review_triggers) if review_triggers else "",
    )


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
        loc = text.location if text else None
        payload = {
            "complaint_id": complaint_id,
            "complaint_type": decision.complaint_type,
            "category": text.category if text else "other",
            "severity": decision.severity,
            "original_text": decision.original_text or "",
            "location_district": loc.district if loc else (decision.location.district if decision.location else None),
            "location_municipality": loc.municipality if loc else None,
            "location_governorate": loc.governorate if loc else None,
            "location_mentions": ([loc.normalized] if loc and loc.normalized else []),
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
    "water_outage":       "water",
    "telecom_outage":     "telecom",
    "public_safety":      "other",
}


def _descriptor_overlap(
    text_domain: str | None, text_component: str | None, text_mode: str | None,
    image_domain: str | None, image_component: str | None, image_mode: str | None,
) -> int:
    """
    Count how many of the 3 semantic dimensions (domain, physical_component, failure_mode)
    match between text and image.  Returns 0–3.

    0 = completely incompatible (strong contradiction signal)
    1 = same broad domain only (weak agreement — trust text)
    2 = same domain + component (good compatibility)
    3 = full match (strong agreement)
    """
    score = 0
    if text_domain and image_domain and text_domain == image_domain:
        score += 1
    if text_component and image_component and text_component == image_component:
        score += 1
    if text_mode and image_mode and text_mode == image_mode:
        score += 1
    return score


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
    text_confidence: float | None = None
    text_service_failed = text_result is None   # IEP-1 completely unavailable
    text_semantic_domain: str | None = None
    text_physical_component: str | None = None
    text_failure_mode: str | None = None

    if text_result:
        raw = text_result.issue_type
        text_type_str = raw.value if hasattr(raw, "value") else str(raw)
        text_confidence = float(text_result.confidence)
        text_is_complaint = (
            text_confidence >= 0.35 and text_type_str != "other"
        ) or text_confidence >= 0.55
        text_category = _TYPE_TO_CATEGORY.get(text_type_str)
        text_semantic_domain = getattr(text_result, "semantic_domain", None)
        text_physical_component = getattr(text_result, "physical_component", None)
        text_failure_mode = getattr(text_result, "failure_mode", None)

    # --- Assess image ---
    image_has_complaint = False
    image_type_str: str | None = None
    image_category: str | None = None
    image_confidence: float | None = None
    image_semantic_domain: str | None = None
    image_physical_component: str | None = None
    image_failure_mode: str | None = None
    has_image = image_result is not None and image_result.image_present

    if has_image:
        vu = image_result.visual_understanding
        iq = image_result.image_quality
        vlm = image_result.vlm_analysis  # may be None
        image_has_complaint = iq.usable and vu.damage_visible and vu.confidence >= 0.40
        image_type_str = vu.visual_subcategory or None
        image_category = vu.visual_category or None
        image_confidence = float(vu.confidence)
        # Prefer VLM descriptors (richer semantics); fall back to CLIP-derived ones
        descriptor_src = vlm if vlm else vu
        image_semantic_domain = getattr(descriptor_src, "semantic_domain", None)
        image_physical_component = getattr(descriptor_src, "physical_component", None)
        image_failure_mode = getattr(descriptor_src, "failure_mode", None)

    # --- Decision matrix ---
    # If IEP-1 service was completely unreachable, don't block — let pipeline continue
    if text_service_failed:
        return MediaValidationResult(
            status=MediaValidationStatus.VALID,
            text_is_complaint=False,
            image_has_complaint=image_has_complaint,
            text_detected_type=None,
            text_detected_category=None,
            text_confidence=None,
            image_detected_type=image_type_str,
            image_detected_category=image_category,
            image_confidence=image_confidence,
            text_semantic_domain=None,
            text_physical_component=None,
            text_failure_mode=None,
            image_semantic_domain=image_semantic_domain,
            image_physical_component=image_physical_component,
            image_failure_mode=image_failure_mode,
            modality_overlap_score=None,
            reconciled_type=image_type_str,
            reconciled_source="image" if image_has_complaint else None,
        )

    if text_is_complaint:
        # Compute dimensional overlap across 3 semantic descriptors.
        # When both sides have descriptors, overlap score drives the contradiction decision.
        # Fallback to category comparison when descriptors are absent (e.g. old CLIP data).
        overlap: int | None = None
        if text_semantic_domain is not None and image_semantic_domain is not None:
            overlap = _descriptor_overlap(
                text_semantic_domain, text_physical_component, text_failure_mode,
                image_semantic_domain, image_physical_component, image_failure_mode,
            )
            is_contradiction = (
                image_has_complaint
                and overlap == 0
                and image_confidence is not None and image_confidence >= 0.50
            )
        else:
            # Legacy fallback: compare top-level categories only
            is_contradiction = (
                image_has_complaint
                and text_category and image_category
                and text_category != image_category
                and image_confidence is not None and image_confidence >= 0.50
            )

        if is_contradiction:
            return MediaValidationResult(
                status=MediaValidationStatus.CONTRADICTION,
                text_is_complaint=True,
                image_has_complaint=True,
                text_detected_type=text_type_str,
                text_detected_category=text_category,
                text_confidence=text_confidence,
                image_detected_type=image_type_str,
                image_detected_category=image_category,
                image_confidence=image_confidence,
                text_semantic_domain=text_semantic_domain,
                text_physical_component=text_physical_component,
                text_failure_mode=text_failure_mode,
                image_semantic_domain=image_semantic_domain,
                image_physical_component=image_physical_component,
                image_failure_mode=image_failure_mode,
                modality_overlap_score=overlap,
                reconciled_type=None,
                reconciled_source="contradiction",
                contradiction_reason=(
                    f"Your text describes a {text_category} issue "
                    f"({text_type_str.replace('_', ' ')}), but your image shows "
                    f"a {image_category} issue ({(image_type_str or 'unknown').replace('_', ' ')}). "
                    f"Please resubmit with matching text and photo."
                ),
            )
        # Both modalities are compatible — rec_source reflects degree of agreement
        if overlap is None:
            rec_source = (
                "both" if (image_has_complaint and image_type_str == text_type_str) else "text"
            )
        else:
            rec_source = "both" if (image_has_complaint and overlap >= 2) else "text"
        return MediaValidationResult(
            status=MediaValidationStatus.VALID,
            text_is_complaint=True,
            image_has_complaint=image_has_complaint,
            text_detected_type=text_type_str,
            text_detected_category=text_category,
            text_confidence=text_confidence,
            image_detected_type=image_type_str,
            image_detected_category=image_category,
            image_confidence=image_confidence,
            text_semantic_domain=text_semantic_domain,
            text_physical_component=text_physical_component,
            text_failure_mode=text_failure_mode,
            image_semantic_domain=image_semantic_domain,
            image_physical_component=image_physical_component,
            image_failure_mode=image_failure_mode,
            modality_overlap_score=overlap,
            reconciled_type=text_type_str,
            reconciled_source=rec_source,
        )

    # Text is NOT a complaint — check image
    if image_has_complaint:
        return MediaValidationResult(
            status=MediaValidationStatus.NEEDS_CLARIFICATION,
            text_is_complaint=False,
            image_has_complaint=True,
            text_detected_type=text_type_str,
            text_detected_category=text_category,
            text_confidence=text_confidence,
            image_detected_type=image_type_str,
            image_detected_category=image_category,
            image_confidence=image_confidence,
            text_semantic_domain=text_semantic_domain,
            text_physical_component=text_physical_component,
            text_failure_mode=text_failure_mode,
            image_semantic_domain=image_semantic_domain,
            image_physical_component=image_physical_component,
            image_failure_mode=image_failure_mode,
            modality_overlap_score=None,
            reconciled_type=image_type_str,
            reconciled_source="image",
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
            text_detected_type=text_type_str,
            text_detected_category=text_category,
            text_confidence=text_confidence,
            image_detected_type=image_type_str,
            image_detected_category=image_category,
            image_confidence=image_confidence,
            text_semantic_domain=text_semantic_domain,
            text_physical_component=text_physical_component,
            text_failure_mode=text_failure_mode,
            image_semantic_domain=image_semantic_domain,
            image_physical_component=image_physical_component,
            image_failure_mode=image_failure_mode,
            modality_overlap_score=None,
            reconciled_type=None,
            reconciled_source=None,
            clarification_question=(
                "Your submission is unclear — neither the text nor the image clearly "
                "shows a public infrastructure problem. A human reviewer will assess it."
            ),
        )

    return MediaValidationResult(
        status=MediaValidationStatus.INVALID_NO_COMPLAINT,
        text_is_complaint=False,
        image_has_complaint=False,
        text_detected_type=text_type_str,
        text_detected_category=text_category,
        text_confidence=text_confidence,
        image_detected_type=image_type_str,
        image_detected_category=image_category,
        image_confidence=image_confidence,
        text_semantic_domain=text_semantic_domain,
        text_physical_component=text_physical_component,
        text_failure_mode=text_failure_mode,
        image_semantic_domain=image_semantic_domain,
        image_physical_component=image_physical_component,
        image_failure_mode=image_failure_mode,
        modality_overlap_score=None,
        reconciled_type=None,
        reconciled_source=None,
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

        # --- Confidence bundle assembly ---
        decision.confidence_bundle = _build_confidence_bundle(
            text_result=decision.text_analysis,
            image_result=decision.image_analysis,
            clustering_result=decision.clustering,
            routing_result=routing_result,
            alignment_result=embedding_result.alignment if embedding_result else None,
        )

        # --- Stage 6: IEP-7 Explanation (non-blocking, fire-and-forget) ---
        explanation_result = await _call_explanation_service(client, complaint_id, decision)
        decision.explanation = explanation_result

    decision.status = PipelineStatus.REVIEW_REQUIRED if (
        routing_result and routing_result.requires_review
    ) else PipelineStatus.COMPLETED

    return decision

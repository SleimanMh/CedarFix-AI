"""
Pipeline Orchestrator â€” calls IEPs in the correct order.
IEP-1 and IEP-2 run in parallel (text and image are independent).
IEP-3 through IEP-6 run sequentially (each depends on prior results).
"""

import asyncio
import re
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
from cedarfix_shared.metrics import (
    GATEWAY_SERVICE_CALL_DURATION,
    GATEWAY_SERVICE_CALL_ERRORS,
    PIPELINE_DURATION,
)
from .config import settings
from .moderation import moderate, ModerationDecisionEnum

TIMEOUT = httpx.Timeout(60.0)
SINGLE_MODAL_REVIEW_CONFIDENCE = 0.85
IMAGE_CANDIDATE_CONFIDENCE_THRESHOLD = 0.40


def _error_type(exc: Exception) -> str:
    return type(exc).__name__


def _as_json_dict(value) -> dict:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {}


async def _post_json(
    client: httpx.AsyncClient,
    *,
    service: str,
    endpoint: str,
    url: str,
    payload: dict,
) -> httpx.Response:
    start = time.time()
    try:
        resp = await client.post(url, json=payload)
    except Exception as exc:
        GATEWAY_SERVICE_CALL_ERRORS.labels(
            service=service,
            endpoint=endpoint,
            error_type=_error_type(exc),
        ).inc()
        GATEWAY_SERVICE_CALL_DURATION.labels(
            service=service,
            endpoint=endpoint,
            status="error",
        ).observe(time.time() - start)
        raise
    GATEWAY_SERVICE_CALL_DURATION.labels(
        service=service,
        endpoint=endpoint,
        status=str(resp.status_code),
    ).observe(time.time() - start)
    try:
        resp.raise_for_status()
    except Exception as exc:
        GATEWAY_SERVICE_CALL_ERRORS.labels(
            service=service,
            endpoint=endpoint,
            error_type=_error_type(exc),
        ).inc()
        raise
    return resp


async def run_pipeline(complaint_id: str, request: ComplaintRequest) -> ComplaintDecision:
    decision = ComplaintDecision(
        complaint_id=complaint_id,
        status=PipelineStatus.PROCESSING,
        original_text=request.text,
        user_id=request.user_id,
        location=request.location,
        location_input_mode=request.location_input_mode,
        image_filename=request.image_filename,
        parent_submission_id=request.parent_submission_id,
        split_index=request.split_index,
        split_total=request.split_total,
        split_source=request.split_source,
        original_submission_text=request.original_submission_text,
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
        decision.location_evaluation = _evaluate_location_extraction(
            submitted_location=decision.location,
            text_location=text_result.location if text_result else None,
            input_mode=request.location_input_mode,
        )

        if text_result:
            decision.complaint_type = text_result.issue_type

        # --- Media Validation Gate ---
        # Runs after IEP-1+IEP-2, before any downstream IEPs.
        # Catches: no complaint in text, text/image contradictions, ambiguous submissions.
        validation = _validate_media(text_result, image_result)
        decision.media_validation = validation
        force_review_after_pipeline = False

        if validation.reconciled_type:
            decision.complaint_type = validation.reconciled_type

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
            if validation.text_is_complaint or validation.image_has_complaint:
                force_review_after_pipeline = True
            else:
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
        force_review_after_pipeline or (routing_result and routing_result.requires_review)
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


def _has_location_signal(location) -> bool:
    if not location:
        return False
    return any(
        getattr(location, field, None)
        for field in ("normalized", "municipality", "district", "governorate", "address_hint")
    ) or (
        getattr(location, "latitude", None) is not None
        and getattr(location, "longitude", None) is not None
    )


def _norm_location_value(value) -> str:
    return str(value or "").strip().casefold()


def _evaluate_location_extraction(submitted_location, text_location, input_mode: str | None) -> dict:
    """
    Compare the LLM/text-extracted location with the submitted/resolved location.
    The submitted/resolved location remains authoritative for routing.
    """
    if not submitted_location and not text_location:
        return {
            "input_mode": input_mode or "unspecified",
            "submitted_location_available": False,
            "llm_location_available": False,
            "llm_matches_submitted": None,
            "usable_for_finetuning": False,
        }

    submitted_parts = {
        "normalized": getattr(submitted_location, "normalized", None),
        "municipality": getattr(submitted_location, "municipality", None),
        "district": getattr(submitted_location, "district", None),
        "governorate": getattr(submitted_location, "governorate", None),
        "source": getattr(submitted_location, "source", None),
        "confidence": getattr(submitted_location, "confidence", 0.0),
    } if submitted_location else {}
    llm_parts = {
        "normalized": getattr(text_location, "normalized", None),
        "municipality": getattr(text_location, "municipality", None),
        "district": getattr(text_location, "district", None),
        "governorate": getattr(text_location, "governorate", None),
        "source": getattr(text_location, "source", None),
        "confidence": getattr(text_location, "confidence", 0.0),
    } if text_location else {}

    submitted_values = {
        _norm_location_value(v)
        for v in (
            submitted_parts.get("normalized"),
            submitted_parts.get("municipality"),
            submitted_parts.get("district"),
            submitted_parts.get("governorate"),
        )
        if v
    }
    llm_values = {
        _norm_location_value(v)
        for v in (
            llm_parts.get("normalized"),
            llm_parts.get("municipality"),
            llm_parts.get("district"),
            llm_parts.get("governorate"),
        )
        if v
    }

    match = None
    if submitted_values and llm_values:
        match = bool(submitted_values & llm_values)
    elif llm_values:
        match = False

    return {
        "input_mode": input_mode or "unspecified",
        "submitted_location_available": bool(submitted_values),
        "submitted_location": submitted_parts,
        "llm_location_available": bool(llm_values),
        "llm_location": llm_parts,
        "llm_matches_submitted": match,
        "authoritative_location_source": submitted_parts.get("source"),
        "routing_uses_submitted_location": bool(submitted_values),
        "usable_for_finetuning": bool(submitted_values and llm_values),
        "finetuning_note": (
            "Use submitted/resolved location as correction label."
            if submitted_values and llm_values and match is False
            else "Use as positive location extraction sample."
            if submitted_values and llm_values and match is True
            else "No LLM location label to correct."
            if submitted_values and not llm_values
            else ""
        ),
    }


# ---------------------------------------------------------------------------
# IEP Callers
# ---------------------------------------------------------------------------

async def _call_text_understanding(
    client, complaint_id: str, request: ComplaintRequest
) -> TextUnderstandingResult | None:
    try:
        resp = await _post_json(
            client,
            service="text_understanding",
            endpoint="/analyze",
            url=f"{settings.text_service_url}/analyze",
            payload={"complaint_id": complaint_id, "text": request.text},
        )
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
        resp = await _post_json(
            client,
            service="image_understanding",
            endpoint="/analyze",
            url=f"{settings.image_service_url}/analyze",
            payload={
                "complaint_id": complaint_id,
                "image_filename": request.image_filename,
                # Pass complaint text so IEP-2 can compute clip_text_embedding.
                # This enables alignment.py to use CLIP-native cosine similarity
                # (same 512-dim space) instead of the cross-model random projection.
                "complaint_text": request.text,
            },
        )
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
        resp = await _post_json(
            client,
            service="embedding_service",
            endpoint="/embed",
            url=f"{settings.embedding_service_url}/embed",
            payload=payload,
        )
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
        resp = await _post_json(
            client,
            service="clustering_service",
            endpoint="/classify",
            url=f"{settings.clustering_service_url}/classify",
            payload=embedding_result.model_dump(mode="json"),
        )
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
        resp = await _post_json(
            client,
            service="priority_engine",
            endpoint="/predict",
            url=f"{settings.priority_service_url}/predict",
            payload=payload,
        )
        return PriorityResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-5 failed: {e}")
        return None


async def _call_routing_engine(client, complaint_id: str, decision: ComplaintDecision) -> RoutingResult | None:
    try:
        text = decision.text_analysis
        image = decision.image_analysis
        submitted_loc = decision.location
        llm_loc = text.location if text else None
        loc = submitted_loc if _has_location_signal(submitted_loc) else llm_loc

        text_rf = _as_json_dict(getattr(text, "routing_features", None) if text else None)
        text_af = _as_json_dict(getattr(text, "alignment_features", None) if text else None)
        text_ev = _as_json_dict(getattr(text, "evidence", None) if text else None)

        img_vlm = image.vlm_analysis if image and image.image_present else None
        image_rf = _as_json_dict(getattr(img_vlm, "routing_features", None) if img_vlm else None)
        image_af = _as_json_dict(getattr(img_vlm, "alignment_features", None) if img_vlm else None)
        image_ev = _as_json_dict(getattr(img_vlm, "evidence", None) if img_vlm else None)
        validation = decision.media_validation
        use_image_for_routing = (
            validation is not None
            and getattr(validation, "reconciled_source", None) == "image"
            and getattr(validation, "reconciled_type", None)
        )

        if use_image_for_routing:
            derived_domain = getattr(validation, "image_semantic_domain", None) or (
                image_rf.get("domain") if isinstance(image_rf, dict) else None
            ) or "unknown"
            derived_component = getattr(validation, "image_physical_component", None) or (
                image_rf.get("physical_component") if isinstance(image_rf, dict) else None
            ) or "unknown"
            derived_failure_mode = getattr(validation, "image_failure_mode", None) or (
                image_rf.get("failure_mode") if isinstance(image_rf, dict) else None
            ) or "unknown"
        else:
            derived_domain = (
                text_rf.get("domain") if isinstance(text_rf, dict) else None
            ) or (text.semantic_domain if text else None) or (text.category if text else None) or "unknown"
            derived_component = (
                text_rf.get("physical_component") if isinstance(text_rf, dict) else None
            ) or (text.physical_component if text else None) or "unknown"
            derived_failure_mode = (
                text_rf.get("failure_mode") if isinstance(text_rf, dict) else None
            ) or (text.failure_mode if text else None) or "unknown"

        mm = decision.text_image_alignment
        mm_payload = {
            "alignment": str(mm.alignment_status) if mm else "NO_IMAGE",
            "score": float(mm.alignment_score) if mm else 0.0,
            "matched_features": list(getattr(mm, "matched_features", []) or []),
            "conflicting_features": list(getattr(mm, "conflicting_features", []) or []),
            "reason": getattr(mm, "reason", None),
        }

        location_mentions = list(getattr(text, "location_mentions", []) or []) if text else []
        for value in [
            getattr(submitted_loc, "address_hint", None),
            getattr(submitted_loc, "normalized", None),
            getattr(submitted_loc, "municipality", None),
            getattr(submitted_loc, "district", None),
            getattr(llm_loc, "normalized", None),
        ]:
            if value:
                location_mentions.append(value)

        payload = {
            "complaint_id": complaint_id,
            "complaint_type": decision.complaint_type,
            "category": (
                validation.image_detected_category
                if use_image_for_routing
                else (text.category if text else "unknown")
            ),
            "subcategory": (
                validation.image_detected_type
                if use_image_for_routing
                else (text.subcategory if text else "unknown")
            ),
            "summary": (
                f"Image shows a {(validation.image_detected_type or 'public infrastructure issue').replace('_', ' ')}."
                if use_image_for_routing
                else (text.summary if text else (decision.original_text or ""))
            ),
            "severity": decision.severity,
            "original_text": decision.original_text or "",
            "location_district": getattr(loc, "district", None) if loc else None,
            "location_municipality": getattr(loc, "municipality", None) if loc else None,
            "location_governorate": getattr(loc, "governorate", None) if loc else None,
            "location_mentions": location_mentions,
            "location_resolution": {
                "input_mode": decision.location_input_mode,
                "authoritative_source": getattr(submitted_loc, "source", None) if submitted_loc else None,
                "authoritative_confidence": getattr(submitted_loc, "confidence", 0.0) if submitted_loc else 0.0,
                "llm_location": getattr(llm_loc, "normalized", None) if llm_loc else None,
                "llm_source": getattr(llm_loc, "source", None) if llm_loc else None,
                "llm_matches_submitted": (decision.location_evaluation or {}).get("llm_matches_submitted"),
            },
            "extracted_keywords": text.urgency_keywords if text else [],
            "signals": text.signals.model_dump(mode="json") if text and text.signals else {},
            "routing_features": {
                "text": text_rf,
                "image": image_rf,
                "derived": {
                    "domain": derived_domain,
                    "physical_component": derived_component,
                    "failure_mode": derived_failure_mode,
                    "hazard_type": "none",
                    "affected_public_space": True,
                    "requires_emergency_attention": bool(text.signals.emergency_signal) if text and text.signals else False,
                },
            },
            "evidence_text": list((text_ev.get("text_evidence") if isinstance(text_ev, dict) else []) or []),
            "evidence_image": list((image_ev.get("image_evidence") if isinstance(image_ev, dict) else []) or []),
            "alignment_features": {
                "text": text_af,
                "image": image_af,
            },
            "multimodal_alignment": mm_payload,
        }
        resp = await _post_json(
            client,
            service="routing_engine",
            endpoint="/route",
            url=f"{settings.routing_service_url}/route",
            payload=payload,
        )
        return RoutingResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-6 failed: {e}")
        return None


async def _call_explanation_service(
    client, complaint_id: str, decision: ComplaintDecision
) -> ExplanationResult | None:
    try:
        resp = await _post_json(
            client,
            service="explanation_service",
            endpoint="/explain",
            url=f"{settings.explanation_service_url}/explain",
            payload={
                "complaint_id": complaint_id,
                "complaint_type": decision.complaint_type,
                "severity": decision.severity,
                "assigned_entity": decision.assigned_entity,
                "routing_confidence": decision.routing_confidence,
                "is_duplicate": decision.is_duplicate,
                "urgency_factors": decision.priority.urgency_factors if decision.priority else [],
            },
        )
        return ExplanationResult(**resp.json())
    except Exception as e:
        print(f"[WARN] IEP-7 failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Media Validation Gate helpers
# ---------------------------------------------------------------------------

# Maps issue_type â†’ broad visual category for contradiction detection
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

_TYPE_TO_DESCRIPTORS: dict[str, tuple[str, str, str]] = {
    "pothole":            ("transportation", "road_surface",    "damage"),
    "road_damage":        ("transportation", "road_surface",    "damage"),
    "traffic_light":      ("transportation", "traffic_signal",  "damage"),
    "sidewalk_damage":    ("transportation", "sidewalk",        "damage"),
    "traffic_incident":   ("transportation", "road_surface",    "blockage"),
    "flooding":           ("environment",    "drainage_system", "overflow"),
    "waste_accumulation": ("environment",    "public_space",    "accumulation"),
    "electricity_outage": ("utilities",      "electrical_line", "outage"),
    "streetlight":        ("transportation", "street_light",    "damage"),
    "water_pipe":         ("utilities",      "water_pipe",      "damage"),
    "water_outage":       ("utilities",      "water_supply",    "outage"),
    "telecom_outage":     ("utilities",      "electrical_line", "outage"),
    "public_safety":      ("safety",         "public_space",    "other"),
}

_CATEGORY_ALIASES: dict[str, str] = {
    "roads": "transportation",
    "road_surface": "transportation",
    "sidewalk": "transportation",
    "traffic_signal": "transportation",
    "street_light": "transportation",
    "drainage": "environment",
    "drainage_system": "environment",
    "sanitation": "environment",
    "public_space_issue": "environment",
    "water": "utilities",
    "water_network": "utilities",
    "electricity": "utilities",
    "electrical_grid": "utilities",
    "electrical_line": "utilities",
    "power_line": "utilities",
    "utility_line": "utilities",
    "telecom": "utilities",
    "telecom_network": "utilities",
    "telecom_cable": "utilities",
    "cable": "utilities",
    "public_transport_stop": "transportation",
    "bike_lane": "transportation",
    "pedestrian_infrastructure": "transportation",
}


def _norm_label(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return normalized or None


_DESCRIPTOR_STOPWORDS = {
    "a",
    "an",
    "and",
    "area",
    "detected",
    "issue",
    "visible",
    "public",
    "infrastructure",
    "object",
    "other",
    "unknown",
    "unspecified",
}


def _descriptor_tokens(value: str | None) -> set[str]:
    label = _norm_label(value)
    if not label:
        return set()
    return {
        token
        for token in re.split(r"_+", label)
        if len(token) >= 3 and token not in _DESCRIPTOR_STOPWORDS
    }


def _descriptor_similarity(left: str | None, right: str | None) -> float:
    left_label = _norm_label(left)
    right_label = _norm_label(right)
    if not left_label or not right_label:
        return 0.0
    if left_label == right_label:
        return 1.0

    left_tokens = _descriptor_tokens(left_label)
    right_tokens = _descriptor_tokens(right_label)
    if not left_tokens or not right_tokens:
        return 0.0

    overlap = left_tokens & right_tokens
    if not overlap:
        return 0.0
    containment = len(overlap) / min(len(left_tokens), len(right_tokens))
    jaccard = len(overlap) / len(left_tokens | right_tokens)
    return max(jaccard, containment * 0.85)


def _display_label(value: str | None, fallback: str = "unknown") -> str:
    return (_norm_label(value) or fallback).replace("_", " ")


def _derive_descriptors(
    issue_type: str | None,
    semantic_domain: str | None,
    physical_component: str | None,
    failure_mode: str | None,
    category: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    issue_key = _norm_label(issue_type)
    derived = _TYPE_TO_DESCRIPTORS.get(issue_key or "", (None, None, None))
    domain = _norm_label(semantic_domain) or derived[0]
    component = _norm_label(physical_component) or derived[1]
    mode = _norm_label(failure_mode) or derived[2]
    category_group = _CATEGORY_ALIASES.get(_norm_label(category) or "")
    component_group = _CATEGORY_ALIASES.get(component or "")
    inferred_group = component_group or category_group
    if domain is None:
        domain = inferred_group
    elif inferred_group and inferred_group != domain and domain in {"other", "environment", "safety"}:
        domain = inferred_group
    return domain, component, mode


def _semantic_group(
    category: str | None,
    semantic_domain: str | None,
    physical_component: str | None,
) -> str | None:
    return (
        _CATEGORY_ALIASES.get(_norm_label(category) or "")
        or _CATEGORY_ALIASES.get(_norm_label(physical_component) or "")
        or _norm_label(semantic_domain)
    )


def _descriptor_overlap(
    text_domain: str | None, text_component: str | None, text_mode: str | None,
    image_domain: str | None, image_component: str | None, image_mode: str | None,
) -> int:
    """
    Count how many of the 3 semantic dimensions (domain, physical_component, failure_mode)
    match between text and image.  Returns 0â€“3.

    0 = completely incompatible (strong contradiction signal)
    1 = same broad domain only (weak agreement â€” trust text)
    2 = same domain + component (good compatibility)
    3 = full match (strong agreement)
    """
    score = 0
    if _descriptor_similarity(text_domain, image_domain) >= 0.65:
        score += 1
    if _descriptor_similarity(text_component, image_component) >= 0.65:
        score += 1
    if _descriptor_similarity(text_mode, image_mode) >= 0.65:
        score += 1
    return score


def _issues_explicitly_match(text_type: str | None, image_type: str | None) -> bool:
    return _descriptor_similarity(text_type, image_type) >= 0.75


def _is_generic_visual_label(value: str | None) -> bool:
    return (_norm_label(value) or "") in {"", "unknown", "other", "infrastructure_issue", "damage"}


def _visual_issue_candidates(image_result: ImageUnderstandingResult | None) -> list[dict]:
    if not image_result or not image_result.image_present:
        return []

    vu = image_result.visual_understanding
    raw_candidates = (
        list(getattr(image_result.vlm_analysis, "visual_candidates", []) or [])
        if image_result.vlm_analysis
        else []
    )
    if not raw_candidates:
        raw_candidates = list(getattr(vu, "visual_candidates", []) or [])

    candidates: list[dict] = []
    for candidate in raw_candidates[:3]:
        get = candidate.get if isinstance(candidate, dict) else lambda key, default=None: getattr(candidate, key, default)
        image_type = get("visual_subcategory") or get("visual_category")
        image_category = get("visual_category")
        domain, component, mode = _derive_descriptors(
            image_type,
            get("semantic_domain"),
            get("physical_component"),
            get("failure_mode"),
            image_category,
        )
        candidates.append({
            "image_type": image_type,
            "image_category": image_category,
            "image_confidence": float(get("confidence", 0.0) or 0.0),
            "image_semantic_domain": domain,
            "image_physical_component": component,
            "image_failure_mode": mode,
        })

    if candidates:
        return candidates

    vlm = image_result.vlm_analysis
    descriptor_src = vlm if vlm else vu
    domain, component, mode = _derive_descriptors(
        vu.visual_subcategory or None,
        getattr(descriptor_src, "semantic_domain", None),
        getattr(descriptor_src, "physical_component", None),
        getattr(descriptor_src, "failure_mode", None),
        vu.visual_category or None,
    )
    return [{
        "image_type": vu.visual_subcategory or None,
        "image_category": vu.visual_category or None,
        "image_confidence": float(vu.confidence),
        "image_semantic_domain": domain,
        "image_physical_component": component,
        "image_failure_mode": mode,
    }]


def _confident_specific_image_candidates(candidates: list[dict]) -> list[dict]:
    return [
        candidate for candidate in candidates
        if (candidate.get("image_confidence") or 0.0) >= IMAGE_CANDIDATE_CONFIDENCE_THRESHOLD
        and not _is_generic_visual_label(candidate.get("image_type"))
    ]


def _best_image_candidate_for_text(
    candidates: list[dict],
    text_type: str | None,
    text_domain: str | None,
    text_component: str | None,
    text_mode: str | None,
) -> tuple[dict | None, int | None, bool]:
    best: dict | None = None
    best_overlap: int | None = None
    best_exact = False

    for candidate in candidates:
        exact = _issues_explicitly_match(text_type, candidate.get("image_type"))
        overlap = _descriptor_overlap(
            text_domain, text_component, text_mode,
            candidate.get("image_semantic_domain"),
            candidate.get("image_physical_component"),
            candidate.get("image_failure_mode"),
        )
        rank = (1 if exact else 0, overlap, candidate.get("image_confidence") or 0.0)
        if best is None:
            best, best_overlap, best_exact = candidate, overlap, exact
            best_rank = rank
            continue
        if rank > best_rank:
            best, best_overlap, best_exact = candidate, overlap, exact
            best_rank = rank

    return best, best_overlap, best_exact


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
        is_unknown_type = (text_type_str or "").strip().lower() in ("", "unknown", "other")
        text_is_complaint = (
            text_confidence >= 0.35 and not is_unknown_type
        ) or text_confidence >= 0.55
        text_category = getattr(text_result, "category", None) or _TYPE_TO_CATEGORY.get(text_type_str)
        text_semantic_domain, text_physical_component, text_failure_mode = _derive_descriptors(
            text_type_str,
            getattr(text_result, "semantic_domain", None),
            getattr(text_result, "physical_component", None),
            getattr(text_result, "failure_mode", None),
            text_category,
        )

    # --- Assess image ---
    image_has_complaint = False
    image_type_str: str | None = None
    image_category: str | None = None
    image_confidence: float | None = None
    image_semantic_domain: str | None = None
    image_physical_component: str | None = None
    image_failure_mode: str | None = None
    image_candidates: list[dict] = []
    has_image = image_result is not None and image_result.image_present

    if has_image:
        vu = image_result.visual_understanding
        iq = image_result.image_quality
        vlm = image_result.vlm_analysis  # may be None
        image_has_complaint = iq.usable and vu.damage_visible and vu.confidence >= 0.40
        image_type_str = vu.visual_subcategory or None
        image_category = vu.visual_category or None
        image_confidence = float(vu.confidence)
        image_candidates = _visual_issue_candidates(image_result)
        # Prefer VLM descriptors (richer semantics); fall back to CLIP-derived ones
        descriptor_src = vlm if vlm else vu
        image_semantic_domain, image_physical_component, image_failure_mode = _derive_descriptors(
            image_type_str,
            getattr(descriptor_src, "semantic_domain", None),
            getattr(descriptor_src, "physical_component", None),
            getattr(descriptor_src, "failure_mode", None),
            image_category,
        )

    # --- Decision matrix ---
    # If IEP-1 service was completely unreachable, don't block â€” let pipeline continue
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
        best_candidate, overlap, exact_type_match = _best_image_candidate_for_text(
            image_candidates,
            text_type_str,
            text_semantic_domain,
            text_physical_component,
            text_failure_mode,
        )
        if best_candidate:
            image_type_str = best_candidate.get("image_type")
            image_category = best_candidate.get("image_category")
            image_confidence = best_candidate.get("image_confidence")
            image_semantic_domain = best_candidate.get("image_semantic_domain")
            image_physical_component = best_candidate.get("image_physical_component")
            image_failure_mode = best_candidate.get("image_failure_mode")
        else:
            exact_type_match = _issues_explicitly_match(text_type_str, image_type_str)
        # Compute dimensional overlap across 3 semantic descriptors.
        # When both sides have descriptors, overlap score drives the contradiction decision.
        # Fallback to category comparison when descriptors are absent (e.g. old CLIP data).
        if text_semantic_domain is not None and image_semantic_domain is not None:
            if overlap is None:
                overlap = _descriptor_overlap(
                    text_semantic_domain, text_physical_component, text_failure_mode,
                    image_semantic_domain, image_physical_component, image_failure_mode,
                )
            generic_image = (
                _is_generic_visual_label(image_type_str)
                or (
                    _is_generic_visual_label(image_semantic_domain)
                    and _is_generic_visual_label(image_physical_component)
                )
            )
            is_contradiction = (
                image_has_complaint
                and not exact_type_match
                and not generic_image
                and (overlap is None or overlap < 2)
                and image_confidence is not None and image_confidence >= 0.50
            )
        else:
            # Legacy fallback: compare normalized semantic groups rather than raw labels
            text_group = _semantic_group(text_category, text_semantic_domain, text_physical_component)
            image_group = _semantic_group(image_category, image_semantic_domain, image_physical_component)
            is_contradiction = (
                image_has_complaint
                and not exact_type_match
                and not _is_generic_visual_label(image_type_str)
                and text_group and image_group
                and text_group != image_group
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
                    f"Your text describes a {_display_label(text_type_str, 'public infrastructure')} issue, "
                    f"but your image appears to show {_display_label(image_type_str)}. "
                    f"Please resubmit with matching text and photo."
                ),
            )
        # Both modalities are compatible â€” rec_source reflects degree of agreement
        if (
            has_image
            and not image_has_complaint
            and text_confidence is not None
            and text_confidence >= SINGLE_MODAL_REVIEW_CONFIDENCE
        ):
            return MediaValidationResult(
                status=MediaValidationStatus.HUMAN_REVIEW,
                text_is_complaint=True,
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
                reconciled_type=text_type_str,
                reconciled_source="text",
                clarification_question=(
                    f"Your text clearly describes a {_display_label(text_type_str, 'public infrastructure')} issue, "
                    "but the image does not clearly show a public infrastructure problem. "
                    "A human reviewer will verify the submission."
                ),
            )
        if overlap is None:
            rec_source = "both" if (image_has_complaint and exact_type_match) else "text"
        else:
            rec_source = "both" if (image_has_complaint and (exact_type_match or overlap >= 2)) else "text"
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

    # Text is NOT a complaint â€” check image
    if image_has_complaint:
        confident_candidates = _confident_specific_image_candidates(image_candidates)
        if len(confident_candidates) > 1:
            issue_labels = [
                _display_label(candidate.get("image_type"), "infrastructure issue")
                for candidate in confident_candidates[:3]
            ]
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
                reconciled_type=None,
                reconciled_source=None,
                clarification_question=(
                    "Your text doesn't clearly describe which issue you are reporting, "
                    f"and the image appears to show multiple issues: {', '.join(issue_labels)}. "
                    "Please specify which one you want to report."
                ),
            )

        if len(confident_candidates) == 1:
            selected = confident_candidates[0]
            image_type_str = selected.get("image_type")
            image_category = selected.get("image_category")
            image_confidence = selected.get("image_confidence")
            image_semantic_domain = selected.get("image_semantic_domain")
            image_physical_component = selected.get("image_physical_component")
            image_failure_mode = selected.get("image_failure_mode")

        status = (
            MediaValidationStatus.HUMAN_REVIEW
            if image_confidence is not None and image_confidence >= SINGLE_MODAL_REVIEW_CONFIDENCE
            else MediaValidationStatus.NEEDS_CLARIFICATION
        )
        return MediaValidationResult(
            status=status,
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
                "Your submission is unclear â€” neither the text nor the image clearly "
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
        await _post_json(
            client,
            service="review_service",
            endpoint="/human-review",
            url=f"{settings.review_service_url}/human-review",
            payload=item.model_dump(),
        )
    except Exception as e:
        print(f"[WARN] Could not queue human review item: {e}")

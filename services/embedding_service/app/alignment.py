"""Modal alignment engine for IEP-3."""

from __future__ import annotations

from typing import Optional

from cedarfix_shared.schemas import (
    AlignmentFeaturesJSON,
    AlignmentStatus,
    ImageUnderstandingResult,
    ReconciliationStatus,
    RoutingFeaturesJSON,
    TextImageAlignment,
    TextUnderstandingResult,
)


def _safe_set(values) -> set[str]:
    out: set[str] = set()
    for v in values or []:
        s = str(v).strip().lower().replace("-", "_").replace(" ", "_")
        if s:
            out.add(s)
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.5
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _known(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    return text if text and text.lower() not in {"unknown", "none"} else None


def _derive_text_routing_features(text: TextUnderstandingResult) -> RoutingFeaturesJSON:
    rf = getattr(text, "routing_features", None)
    if rf is None:
        rf = {}
    if isinstance(rf, RoutingFeaturesJSON):
        base = rf
    else:
        base = RoutingFeaturesJSON(**rf)
    return RoutingFeaturesJSON(
        domain=(_known(base.domain) or _known(text.semantic_domain) or _known(text.category) or "unknown"),
        physical_component=(_known(base.physical_component) or _known(text.physical_component) or "unknown"),
        failure_mode=(_known(base.failure_mode) or _known(text.failure_mode) or "unknown"),
        hazard_type=(_known(base.hazard_type) or "none"),
        affected_public_space=bool(base.affected_public_space if base.affected_public_space is not None else True),
        requires_emergency_attention=bool(base.requires_emergency_attention or getattr(text.signals, "emergency_signal", False)),
    )


def _derive_text_alignment_features(text: TextUnderstandingResult, rf: RoutingFeaturesJSON) -> AlignmentFeaturesJSON:
    af = getattr(text, "alignment_features", None)
    if af is None:
        af = {}
    if isinstance(af, AlignmentFeaturesJSON):
        base = af
    else:
        base = AlignmentFeaturesJSON(**af)
    return AlignmentFeaturesJSON(
        domain=(_known(base.domain) or _known(rf.domain) or "unknown"),
        physical_component=(_known(base.physical_component) or _known(rf.physical_component) or "unknown"),
        failure_mode=(_known(base.failure_mode) or _known(rf.failure_mode) or "unknown"),
        visible_hazard=bool(base.visible_hazard),
        objects=list(base.objects or []),
        actions=list(base.actions or []),
        location_context=list(base.location_context or []),
    )


def _derive_image_routing_features(image: ImageUnderstandingResult) -> RoutingFeaturesJSON:
    vu = image.visual_understanding
    src = image.vlm_analysis if image.vlm_analysis else vu
    rf = getattr(src, "routing_features", None)
    if rf is None:
        rf = {}
    if isinstance(rf, RoutingFeaturesJSON):
        base = rf
    else:
        base = RoutingFeaturesJSON(**rf)
    return RoutingFeaturesJSON(
        domain=(
            _known(base.domain)
            or _known(getattr(src, "semantic_domain", None))
            or _known(getattr(vu, "semantic_domain", None))
            or _known(vu.visual_category)
            or "unknown"
        ),
        physical_component=(
            _known(base.physical_component)
            or _known(getattr(src, "physical_component", None))
            or _known(getattr(vu, "physical_component", None))
            or "unknown"
        ),
        failure_mode=(
            _known(base.failure_mode)
            or _known(getattr(src, "failure_mode", None))
            or _known(getattr(vu, "failure_mode", None))
            or "unknown"
        ),
        hazard_type=(_known(base.hazard_type) or "none"),
        affected_public_space=bool(base.affected_public_space if base.affected_public_space is not None else True),
        requires_emergency_attention=bool(base.requires_emergency_attention),
    )


def _derive_image_alignment_features(image: ImageUnderstandingResult, rf: RoutingFeaturesJSON) -> AlignmentFeaturesJSON:
    vu = image.visual_understanding
    src = image.vlm_analysis if image.vlm_analysis else vu
    af = getattr(src, "alignment_features", None)
    if af is None:
        af = {}
    if isinstance(af, AlignmentFeaturesJSON):
        base = af
    else:
        base = AlignmentFeaturesJSON(**af)
    inferred_objects = list(getattr(vu, "detected_objects", []) or [])
    return AlignmentFeaturesJSON(
        domain=(_known(base.domain) or _known(rf.domain) or "unknown"),
        physical_component=(_known(base.physical_component) or _known(rf.physical_component) or "unknown"),
        failure_mode=(_known(base.failure_mode) or _known(rf.failure_mode) or "unknown"),
        visible_hazard=bool(base.visible_hazard if base.visible_hazard is not None else getattr(vu, "damage_visible", False)),
        objects=list(base.objects or inferred_objects),
        actions=list(base.actions or []),
        location_context=list(base.location_context or []),
    )


def compute_multimodal_alignment(
    text_output: TextUnderstandingResult,
    image_output: Optional[ImageUnderstandingResult],
    clip_score: float,
    vlm_alignment: Optional[dict] = None,
) -> dict:
    if image_output is None or not image_output.image_present:
        return {
            "alignment": "NO_IMAGE",
            "score": 0.0,
            "matched_features": [],
            "conflicting_features": [],
            "reason": "No image submitted.",
        }

    if not image_output.image_quality.usable:
        return {
            "alignment": "NO_IMAGE",
            "score": 0.0,
            "matched_features": [],
            "conflicting_features": ["image_quality"],
            "reason": f"Image unusable: {image_output.image_quality.issues}",
        }

    t_rf = _derive_text_routing_features(text_output)
    i_rf = _derive_image_routing_features(image_output)
    t_af = _derive_text_alignment_features(text_output, t_rf)
    i_af = _derive_image_alignment_features(image_output, i_rf)

    matched: list[str] = []
    conflicting: list[str] = []

    clip_component = max(0.0, min(1.0, float(clip_score)))
    if clip_component >= 0.65:
        matched.append("clip_similarity")
    elif clip_component <= 0.25:
        conflicting.append("clip_similarity")

    domain_match = (t_rf.domain == i_rf.domain and t_rf.domain not in ("", "unknown"))
    component_match = (
        t_rf.physical_component == i_rf.physical_component
        and t_rf.physical_component not in ("", "unknown")
    )
    domain_component_component = (1.0 if domain_match else 0.0) * 0.5 + (1.0 if component_match else 0.0) * 0.5
    if domain_match:
        matched.append("domain")
    elif t_rf.domain not in ("", "unknown") and i_rf.domain not in ("", "unknown"):
        conflicting.append("domain")
    if component_match:
        matched.append("physical_component")
    elif t_rf.physical_component not in ("", "unknown") and i_rf.physical_component not in ("", "unknown"):
        conflicting.append("physical_component")

    failure_match = (
        t_rf.failure_mode == i_rf.failure_mode
        and t_rf.failure_mode not in ("", "unknown")
    )
    hazard_match = (
        t_rf.hazard_type == i_rf.hazard_type
        and t_rf.hazard_type not in ("", "none", "unknown")
    )
    failure_hazard_component = (1.0 if failure_match else 0.0) * 0.5 + (1.0 if hazard_match else 0.0) * 0.5
    if failure_match:
        matched.append("failure_mode")
    elif t_rf.failure_mode not in ("", "unknown") and i_rf.failure_mode not in ("", "unknown"):
        conflicting.append("failure_mode")
    if hazard_match:
        matched.append("hazard_type")
    elif t_rf.hazard_type not in ("", "none", "unknown") and i_rf.hazard_type not in ("", "none", "unknown"):
        conflicting.append("hazard_type")

    object_overlap = _jaccard(_safe_set(t_af.objects), _safe_set(i_af.objects))
    action_overlap = _jaccard(_safe_set(t_af.actions), _safe_set(i_af.actions))
    object_action_component = 0.7 * object_overlap + 0.3 * action_overlap
    if object_overlap > 0.4:
        matched.append("objects")
    elif object_overlap == 0 and t_af.objects and i_af.objects:
        conflicting.append("objects")
    if action_overlap > 0.4:
        matched.append("actions")

    loc_text = _safe_set(getattr(text_output, "location_mentions", []))
    loc_img = _safe_set((image_output.vlm_analysis.location_cues.get("detected_text", []) if image_output.vlm_analysis else []))
    loc_img |= _safe_set((image_output.vlm_analysis.location_cues.get("landmarks", []) if image_output.vlm_analysis else []))
    loc_img |= _safe_set((image_output.vlm_analysis.location_cues.get("street_signs", []) if image_output.vlm_analysis else []))
    loc_img |= _safe_set((image_output.vlm_analysis.location_cues.get("storefront_names", []) if image_output.vlm_analysis else []))
    loc_img |= _safe_set(i_af.location_context)
    location_component = _jaccard(loc_text, loc_img)
    if location_component > 0.4:
        matched.append("location_context")

    vlm_component = 0.5
    if vlm_alignment:
        al = str(vlm_alignment.get("alignment", "UNCERTAIN")).upper()
        conf = float(vlm_alignment.get("confidence", 0.5))
        base = {
            "CONFIRMS": 1.0,
            "RELATED": 0.75,
            "UNCERTAIN": 0.5,
            "CONTRADICTS": 0.0,
            "UNRELATED": 0.1,
        }.get(al, 0.5)
        vlm_component = max(0.0, min(1.0, base * (0.5 + 0.5 * conf)))
        if al in ("CONFIRMS", "RELATED"):
            matched.append("vlm_alignment")
        elif al in ("CONTRADICTS", "UNRELATED"):
            conflicting.append("vlm_alignment")

    score = (
        0.30 * clip_component
        + 0.20 * domain_component_component
        + 0.20 * failure_hazard_component
        + 0.15 * object_action_component
        + 0.10 * vlm_component
        + 0.05 * location_component
    )
    score = round(max(0.0, min(1.0, score)), 4)

    if clip_component < 0.2 and domain_component_component == 0 and failure_hazard_component == 0:
        alignment = "UNRELATED"
    elif score >= 0.72 and len(conflicting) <= 1:
        alignment = "SUPPORTS"
    elif score >= 0.56 and domain_component_component > 0:
        alignment = "RELATED"
    elif score <= 0.28 and ("domain" in conflicting or "physical_component" in conflicting):
        alignment = "CONTRADICTS"
    else:
        alignment = "UNCERTAIN"

    reason = (
        f"clip={clip_component:.2f}, domain_component={domain_component_component:.2f}, "
        f"failure_hazard={failure_hazard_component:.2f}, object_action={object_action_component:.2f}, "
        f"vlm={vlm_component:.2f}, location={location_component:.2f}"
    )

    return {
        "alignment": alignment,
        "score": score,
        "matched_features": sorted(set(matched)),
        "conflicting_features": sorted(set(conflicting)),
        "reason": reason,
    }


class ModalAlignmentComputer:
    def compute(self, text_result: TextUnderstandingResult, image_result: Optional[ImageUnderstandingResult]) -> TextImageAlignment:
        if image_result is None or not image_result.image_present:
            res = compute_multimodal_alignment(text_result, image_result, 0.0, None)
            return TextImageAlignment(
                complaint_id=text_result.complaint_id,
                alignment_status=AlignmentStatus.NO_IMAGE,
                alignment_score=0.0,
                text_issue_type=text_result.issue_type,
                image_issue_type=None,
                text_subcategory=text_result.subcategory,
                image_subcategory="",
                matched_features=res["matched_features"],
                conflicting_features=res["conflicting_features"],
                reason=res["reason"],
                conflict_detected=False,
                conflict_reason=None,
                reconciliation_status=ReconciliationStatus.INSUFFICIENT_EVIDENCE,
                reconciliation_note="No image submitted.",
            )

        clip_score = 0.0
        if image_result.clip_text_embedding and image_result.image_embedding:
            import math
            a = image_result.clip_text_embedding
            b = image_result.image_embedding
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a)) + 1e-8
            nb = math.sqrt(sum(x * x for x in b)) + 1e-8
            clip_score = dot / (na * nb)

        vlm_alignment = None
        if image_result.vlm_analysis and image_result.vlm_analysis.vlm_alignment:
            vlm_alignment = {
                "alignment": str(image_result.vlm_analysis.vlm_alignment),
                "confidence": float(image_result.vlm_analysis.vlm_alignment_confidence or 0.5),
            }

        res = compute_multimodal_alignment(text_result, image_result, clip_score, vlm_alignment)
        status = AlignmentStatus[res["alignment"]] if res["alignment"] in AlignmentStatus.__members__ else AlignmentStatus.UNCERTAIN
        conflict = status in (AlignmentStatus.CONTRADICTS, AlignmentStatus.UNRELATED)
        recon = ReconciliationStatus.MODAL_CONFLICT if conflict else (
            ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT if status == AlignmentStatus.SUPPORTS else ReconciliationStatus.INSUFFICIENT_EVIDENCE
        )

        return TextImageAlignment(
            complaint_id=text_result.complaint_id,
            alignment_status=status,
            alignment_score=float(res["score"]),
            text_issue_type=text_result.issue_type,
            image_issue_type=image_result.visual_understanding.visual_subcategory,
            text_subcategory=text_result.subcategory,
            image_subcategory=image_result.visual_understanding.visual_subcategory,
            matched_features=res["matched_features"],
            conflicting_features=res["conflicting_features"],
            reason=res["reason"],
            conflict_detected=conflict,
            conflict_reason=res["reason"] if conflict else None,
            reconciliation_status=recon,
            reconciliation_note=res["reason"],
        )

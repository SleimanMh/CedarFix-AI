from __future__ import annotations

import math

import pytest

from conftest import import_or_skip


pytestmark = pytest.mark.unit


def _norm(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values))


def test_project_image_embedding_is_deterministic_unit_vector():
    fusion = import_or_skip("services.embedding_service.app.fusion")

    image = [0.1] * fusion.IMAGE_DIM
    first = fusion.project_image_embedding(image)
    second = fusion.project_image_embedding(image)

    assert len(first) == fusion.FUSED_DIM
    assert first == second
    assert _norm(first) == pytest.approx(1.0, abs=1e-5)


def test_fuse_embeddings_text_only_and_weighted_paths():
    fusion = import_or_skip("services.embedding_service.app.fusion")

    text = [1.0] + [0.0] * (fusion.TEXT_DIM - 1)
    image = [0.5] * fusion.IMAGE_DIM

    text_only, strategy, text_weight, image_weight = fusion.fuse_embeddings(text, [], False)
    assert strategy == "text_only"
    assert text_weight == 1.0
    assert image_weight == 0.0
    assert len(text_only) == fusion.FUSED_DIM

    fused, strategy, text_weight, image_weight = fusion.fuse_embeddings(
        text,
        image,
        image_available=True,
        image_relevance=2.0,
    )
    assert strategy == "weighted_avg"
    assert text_weight == 0.6
    assert image_weight == 0.4
    assert len(fused) == fusion.FUSED_DIM
    assert _norm(fused) == pytest.approx(1.0, abs=1e-5)


def _text_result(schemas, **overrides):
    payload = {
        "complaint_id": "c-1",
        "original_text": "A pothole damaged the road in Hamra.",
        "normalized_text": "A pothole damaged the road in Hamra.",
        "language": "en",
        "summary": "Road pothole in Hamra",
        "category": "transportation",
        "subcategory": "pothole",
        "issue_type": "pothole",
        "location_mentions": ["Hamra"],
        "severity": schemas.SeverityLevel.HIGH,
        "confidence": 0.92,
        "semantic_domain": "transportation",
        "physical_component": "road_surface",
        "failure_mode": "damage",
        "routing_features": schemas.RoutingFeaturesJSON(
            domain="transportation",
            physical_component="road_surface",
            failure_mode="damage",
            hazard_type="road_hazard",
        ),
        "alignment_features": schemas.AlignmentFeaturesJSON(
            domain="transportation",
            physical_component="road_surface",
            failure_mode="damage",
            objects=["pothole", "road"],
            actions=["damage"],
            location_context=["Hamra"],
        ),
    }
    payload.update(overrides)
    return schemas.TextUnderstandingResult(**payload)


def _image_result(schemas, **overrides):
    visual = schemas.VisualUnderstandingJSON(
        visual_category="transportation",
        visual_subcategory="pothole",
        detected_objects=["pothole", "road"],
        damage_visible=True,
        visual_severity=schemas.SeverityLevel.HIGH,
        confidence=0.91,
        semantic_domain="transportation",
        physical_component="road_surface",
        failure_mode="damage",
    )
    payload = {
        "complaint_id": "c-1",
        "image_present": True,
        "image_quality": schemas.ImageQualityJSON(usable=True, quality_score=0.9),
        "visual_understanding": visual,
        "clip_text_embedding": [1.0, 0.0],
        "image_embedding": [1.0, 0.0],
    }
    payload.update(overrides)
    return schemas.ImageUnderstandingResult(**payload)


def _vlm_features(schemas, *, domain: str, component: str, failure: str):
    return schemas.VLMImageAnalysis(
        image_type="infrastructure",
        is_valid_complaint_image=True,
        damage_visible=True,
        visual_category=domain,
        visual_subcategory=component,
        semantic_domain=domain,
        physical_component=component,
        failure_mode=failure,
        confidence=0.9,
        routing_features=schemas.RoutingFeaturesJSON(
            domain=domain,
            physical_component=component,
            failure_mode=failure,
            hazard_type="road_hazard" if component == "road_surface" else "none",
        ),
        alignment_features=schemas.AlignmentFeaturesJSON(
            domain=domain,
            physical_component=component,
            failure_mode=failure,
        ),
    )


def test_compute_multimodal_alignment_supports_matching_modalities(schemas):
    alignment = import_or_skip("services.embedding_service.app.alignment")

    result = alignment.compute_multimodal_alignment(
        _text_result(schemas),
        _image_result(
            schemas,
            vlm_analysis=_vlm_features(
                schemas,
                domain="transportation",
                component="road_surface",
                failure="damage",
            ),
        ),
        clip_score=0.96,
    )

    assert result["alignment"] == "SUPPORTS"
    assert result["score"] >= 0.72
    assert {"clip_similarity", "domain", "physical_component", "failure_mode"} <= set(result["matched_features"])
    assert not result["conflicting_features"]


def test_modal_alignment_computer_flags_clear_conflict(schemas):
    alignment = import_or_skip("services.embedding_service.app.alignment")
    image = _image_result(
        schemas,
        visual_understanding=schemas.VisualUnderstandingJSON(
            visual_category="sanitation",
            visual_subcategory="waste_accumulation",
            detected_objects=["garbage"],
            damage_visible=True,
            confidence=0.9,
            semantic_domain="environment",
            physical_component="public_space",
            failure_mode="accumulation",
        ),
        vlm_analysis=_vlm_features(
            schemas,
            domain="environment",
            component="public_space",
            failure="accumulation",
        ),
        clip_text_embedding=[1.0, 0.0],
        image_embedding=[0.0, 1.0],
    )

    result = alignment.ModalAlignmentComputer().compute(_text_result(schemas), image)

    assert result.alignment_status in {schemas.AlignmentStatus.CONTRADICTS, schemas.AlignmentStatus.UNRELATED}
    assert result.conflict_detected is True
    assert "domain" in result.conflicting_features


def test_priority_scorer_clamps_high_risk_cluster_to_critical(schemas):
    scorer_mod = import_or_skip("services.priority_engine.app.scorer")

    result = scorer_mod.PriorityScorer().score(
        complaint_id="p-1",
        complaint_type="flooding",
        cluster_size=10,
        visual_severity="HIGH",
        location_district="Tripoli",
        top_similarity_score=0.0,
    )

    assert result.priority_score == 1.0
    assert result.severity == schemas.SeverityLevel.CRITICAL
    assert result.cluster_size_factor == 0.3
    assert result.location_risk_factor == 0.15


def _alignment_for_decision(schemas):
    return schemas.TextImageAlignment(
        complaint_id="c-1",
        alignment_status=schemas.AlignmentStatus.SUPPORTS,
        alignment_score=0.9,
        text_issue_type="pothole",
        image_issue_type="pothole",
        text_subcategory="pothole",
        image_subcategory="pothole",
    )


def _candidate(schemas, **overrides):
    payload = {
        "candidate_complaint_id": "old-1",
        "candidate_cluster_id": "cluster-1",
        "candidate_summary": "Existing pothole",
        "candidate_issue_type": "pothole",
        "candidate_subcategory": "pothole",
        "similarity_scores": schemas.SimilarityScores(
            text_similarity=0.96,
            image_similarity=0.94,
            clip_text_similarity=0.90,
            clip_image_similarity=0.91,
            location_similarity=0.95,
            time_similarity=0.85,
            issue_type_similarity=1.0,
        ),
        "candidate_source": ["text_search", "clip_image_search"],
        "multimodal_score": 0.97,
        "per_candidate_reconciliation": schemas.ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT,
    }
    payload.update(overrides)
    return schemas.DuplicateCandidate(**payload)


def test_decision_engine_returns_new_incident_without_candidates(schemas):
    decision_mod = import_or_skip("services.clustering_service.app.decision")

    decision = decision_mod.DecisionEngine().decide([], _alignment_for_decision(schemas))

    assert decision.duplicate_decision == schemas.DuplicateDecisionEnum.NEW_INCIDENT
    assert decision.requires_admin_review is False


def test_decision_engine_accepts_strong_duplicate(schemas):
    decision_mod = import_or_skip("services.clustering_service.app.decision")

    decision = decision_mod.DecisionEngine().decide([_candidate(schemas)], _alignment_for_decision(schemas))

    assert decision.duplicate_decision == schemas.DuplicateDecisionEnum.DUPLICATE
    assert decision.matched_complaint_id == "old-1"
    assert decision.requires_admin_review is False


def test_decision_engine_routes_boundary_conflicts_to_admin_review(schemas):
    decision_mod = import_or_skip("services.clustering_service.app.decision")
    conflicted = _candidate(
        schemas,
        multimodal_score=0.90,
        similarity_scores=schemas.SimilarityScores(
            text_similarity=0.70,
            image_similarity=0.88,
            location_similarity=0.90,
            time_similarity=0.75,
            issue_type_similarity=0.2,
        ),
        recheck_triggered=True,
        per_candidate_reconciliation=schemas.ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT,
    )

    decision = decision_mod.DecisionEngine().decide([conflicted], _alignment_for_decision(schemas))

    assert decision.duplicate_decision == schemas.DuplicateDecisionEnum.NEEDS_ADMIN_REVIEW
    assert decision.requires_admin_review is True
    assert {"boundary_score", "type_mismatch_high_image", "recheck_triggered"} <= set(decision.review_reasons)

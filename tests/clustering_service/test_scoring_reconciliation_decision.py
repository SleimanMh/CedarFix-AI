from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cedarfix_shared.schemas import (
    AlignmentStatus,
    CanonicalComplaint,
    CanonicalLocationJSON,
    DuplicateCandidate,
    DuplicateDecisionEnum,
    RawCandidate,
    ReconciliationStatus,
    SimilarityScores,
    TextImageAlignment,
)


def _canonical() -> CanonicalComplaint:
    return CanonicalComplaint(
        complaint_id="incoming",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        issue_type="pothole",
        subcategory="pothole",
        location=CanonicalLocationJSON(
            normalized_location="Hamra",
            district="Beirut",
            latitude=33.8938,
            longitude=35.4881,
        ),
    )


def _alignment(status: AlignmentStatus = AlignmentStatus.SUPPORTS) -> TextImageAlignment:
    return TextImageAlignment(
        complaint_id="incoming",
        alignment_status=status,
        conflict_detected=status == AlignmentStatus.CONTRADICTS,
    )


def _candidate(score: float, rec: ReconciliationStatus) -> DuplicateCandidate:
    return DuplicateCandidate(
        candidate_complaint_id="existing",
        candidate_cluster_id="cluster-1",
        similarity_scores=SimilarityScores(
            text_similarity=score,
            image_similarity=score,
            location_similarity=0.95,
            time_similarity=0.9,
            issue_type_similarity=1.0,
        ),
        multimodal_score=score,
        per_candidate_reconciliation=rec,
    )


def test_scorer_uses_strong_multimodal_weight_set(import_service_module):
    scorer_mod = import_service_module("clustering_service", "app.scorer")
    raw = RawCandidate(
        complaint_id="existing",
        cluster_id="cluster-1",
        issue_type="pothole",
        subcategory="pothole",
        location=CanonicalLocationJSON(district="Beirut", latitude=33.8939, longitude=35.4882),
        timestamp=datetime(2026, 1, 1, 2, tzinfo=timezone.utc),
        raw_mpnet_text_sim=0.9,
        raw_clip_text_sim=0.8,
        raw_clip_image_sim=0.85,
    )

    result = scorer_mod.MultimodalScorer().score(_canonical(), raw, [1], [1], image_present=True)

    assert result.multimodal_score > 0.82
    assert result.similarity_scores.issue_type_similarity == 1.0
    assert result.similarity_scores.location_similarity > 0.95


def test_scorer_penalizes_cross_modal_but_adds_convergence_bonus(import_service_module):
    scorer_mod = import_service_module("clustering_service", "app.scorer")
    raw = RawCandidate(
        complaint_id="existing",
        issue_type="pothole",
        location=CanonicalLocationJSON(district="Beirut"),
        timestamp=datetime.now(timezone.utc),
        raw_mpnet_text_sim=0.4,
        raw_clip_text_sim=0.8,
        raw_clip_image_sim=0.8,
        clip_text_is_xmodal=True,
        clip_image_is_xmodal=True,
    )

    result = scorer_mod.MultimodalScorer().score(_canonical(), raw, [1], [1], image_present=True)

    assert result.similarity_scores.clip_text_similarity == 0.72
    assert result.similarity_scores.clip_image_similarity == 0.72
    assert result.multimodal_score > 0.55


def test_similarity_subfunctions(import_service_module):
    scorer_mod = import_service_module("clustering_service", "app.scorer")
    assert scorer_mod._type_match_score("pothole", "road_damage") == 0.4
    assert scorer_mod._type_match_score("other", "other", "bench", "graffiti") == 0.2
    assert scorer_mod._location_similarity(None, None, "Beirut", None, None, "Beirut") == 0.8
    assert scorer_mod._location_similarity(None, None, "Beirut", None, None, "Tripoli") == 0.1
    assert scorer_mod._temporal_similarity(None, datetime.now(timezone.utc)) == 0.5
    assert scorer_mod._temporal_similarity(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    ) == 0.3679


def test_reconciler_statuses(import_service_module):
    reconciler_mod = import_service_module("clustering_service", "app.reconciler")
    engine = reconciler_mod.ReconciliationEngine()

    strong = _candidate(0.9, ReconciliationStatus.INSUFFICIENT_EVIDENCE)
    assert engine.reconcile(strong, _alignment()) == ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT

    image_override = _candidate(0.5, ReconciliationStatus.INSUFFICIENT_EVIDENCE)
    image_override.similarity_scores.image_similarity = 0.9
    image_override.similarity_scores.text_similarity = 0.4
    assert engine.reconcile(image_override, _alignment()) == ReconciliationStatus.IMAGE_OVERRIDES_WEAK_TEXT

    conflict = _candidate(0.7, ReconciliationStatus.INSUFFICIENT_EVIDENCE)
    assert engine.reconcile(conflict, _alignment(AlignmentStatus.CONTRADICTS)) == ReconciliationStatus.MODAL_CONFLICT


def test_decision_engine_duplicate_related_review_and_new(import_service_module):
    decision_mod = import_service_module("clustering_service", "app.decision")
    engine = decision_mod.DecisionEngine()

    duplicate = engine.decide(
        [_candidate(0.95, ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT)],
        _alignment(),
    )
    assert duplicate.duplicate_decision == DuplicateDecisionEnum.DUPLICATE
    assert duplicate.requires_admin_review is False

    related = engine.decide(
        [_candidate(0.75, ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT)],
        _alignment(),
    )
    assert related.duplicate_decision == DuplicateDecisionEnum.RELATED_SAME_CLUSTER

    review = engine.decide(
        [_candidate(1.0, ReconciliationStatus.MODAL_CONFLICT)],
        _alignment(AlignmentStatus.CONTRADICTS),
    )
    assert review.duplicate_decision == DuplicateDecisionEnum.NEEDS_ADMIN_REVIEW
    assert "modal_conflict" in review.review_reasons

    new = engine.decide([], _alignment())
    assert new.duplicate_decision == DuplicateDecisionEnum.NEW_INCIDENT

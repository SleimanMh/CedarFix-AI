from __future__ import annotations

import math

from cedarfix_shared.schemas import (
    CanonicalLocationJSON,
    ImageQualityJSON,
    ImageUnderstandingResult,
    RawCandidate,
    TextUnderstandingResult,
    VisualUnderstandingJSON,
)


def _norm(values):
    return math.sqrt(sum(v * v for v in values))


def test_fuse_embeddings_text_only_is_normalized(import_service_module):
    fusion = import_service_module("embedding_service", "app.fusion")
    fused, strategy, text_weight, image_weight = fusion.fuse_embeddings([2.0] * 768, [], False)
    assert strategy == "text_only"
    assert text_weight == 1.0
    assert image_weight == 0.0
    assert abs(_norm(fused) - 1.0) < 1e-5


def test_fuse_embeddings_with_image_is_deterministic_and_weighted(import_service_module):
    fusion = import_service_module("embedding_service", "app.fusion")
    args = ([1.0] * 768, [0.5] * 512, True, 2.0)
    first = fusion.fuse_embeddings(*args)
    second = fusion.fuse_embeddings(*args)
    assert first[0] == second[0]
    assert first[1:] == ("weighted_avg", 0.6, 0.4)
    assert abs(_norm(first[0]) - 1.0) < 1e-5


def test_rrf_merge_deduplicates_sources_and_maxes_scores(import_service_module):
    retrieval = import_service_module("embedding_service", "app.retrieval", qdrant=True)
    a1 = RawCandidate(
        complaint_id="a",
        sources=["text_search"],
        raw_text_similarity=0.7,
        raw_mpnet_text_sim=0.7,
    )
    b = RawCandidate(complaint_id="b", sources=["text_search"], raw_text_similarity=0.9)
    a2 = RawCandidate(
        complaint_id="a",
        sources=["clip_image_search"],
        raw_clip_image_sim=0.85,
        clip_image_is_xmodal=True,
    )

    merged = retrieval._rrf_merge([[a1, b], [a2]])

    assert [c.complaint_id for c in merged] == ["a", "b"]
    assert merged[0].sources == ["text_search", "clip_image_search"]
    assert merged[0].raw_clip_image_sim == 0.85
    assert merged[0].clip_image_is_xmodal is True


def test_alignment_supports_matching_text_and_image(import_service_module):
    alignment = import_service_module("embedding_service", "app.alignment")
    text = TextUnderstandingResult(
        complaint_id="c1",
        original_text="Broken road in Hamra",
        normalized_text="Broken road in Hamra",
        issue_type="road_damage",
        category="roads",
        subcategory="road_damage",
        confidence=0.8,
        semantic_domain="transportation",
        physical_component="road_surface",
        failure_mode="damage",
    )
    image = ImageUnderstandingResult(
        complaint_id="c1",
        image_present=True,
        image_quality=ImageQualityJSON(usable=True, quality_score=0.9),
        visual_understanding=VisualUnderstandingJSON(
            visual_category="roads",
            visual_subcategory="road_damage",
            damage_visible=True,
            confidence=0.8,
            semantic_domain="transportation",
            physical_component="road_surface",
            failure_mode="damage",
        ),
        image_embedding=[1.0, 0.0],
        clip_text_embedding=[1.0, 0.0],
    )

    result = alignment.ModalAlignmentComputer().compute(text, image)

    assert result.alignment_status.value == "SUPPORTS"
    assert result.conflict_detected is False
    assert "physical_component" in result.matched_features


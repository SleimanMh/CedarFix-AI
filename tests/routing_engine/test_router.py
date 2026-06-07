from __future__ import annotations

import asyncio

from cedarfix_shared.schemas import RoutingEntity


def _doc(**overrides):
    base = {
        "doc_id": "doc-1",
        "entity_name": "Ogero",
        "entity_enum": "Ogero",
        "entity_type": "utility",
        "description": "Ogero handles telecom internet outages.",
        "route_mode": "routing_candidate",
        "route_authority": "authoritative",
        "retrieval_stage": "stage1_dispatch",
        "stage_priority": 1,
        "responsibility_level": "primary",
        "keywords": ["internet", "dsl", "ogero"],
        "exact_match_terms": ["internet outage"],
        "complaint_types": ["telecom_outage"],
        "confidence_prior": 0.9,
        "retrieval_weight": 1.0,
        "_rag_score": 0.88,
    }
    base.update(overrides)
    return base


def test_routing_doc_auto_route_rules(import_service_module):
    router = import_service_module("routing_engine", "app.router", qdrant=True)
    assert router._doc_allows_auto_route(_doc()) is True
    assert router._doc_allows_auto_route(_doc(retrieval_stage="stage3_evidence")) is False
    assert router._doc_allows_auto_route(_doc(route_mode="supporting_context")) is False
    assert router._doc_allows_auto_route(_doc(route_authority="blocker")) is False
    assert router._doc_allows_auto_route(_doc(hitl_always_required=True)) is False


def test_rerank_prefers_dispatch_authority_and_exact_terms(import_service_module):
    router = import_service_module("routing_engine", "app.router", qdrant=True)
    support = _doc(
        doc_id="support",
        route_mode="supporting_context",
        retrieval_stage="stage3_evidence",
        _rag_score=0.95,
        exact_match_terms=[],
    )
    dispatch = _doc(doc_id="dispatch", _rag_score=0.8)

    ranked = router._rerank_docs("internet outage in Beirut with dsl issue", [support, dispatch], top_k=2)

    assert ranked[0]["doc_id"] == "dispatch"
    assert ranked[0]["_rerank_score"] > ranked[1]["_rerank_score"]


def test_static_route_and_entity_resolution(import_service_module):
    router = import_service_module("routing_engine", "app.router", qdrant=True)
    primary, secondary, conf, rationale = router._static_route(
        "waste_accumulation",
        location_district="Tripoli",
        location_mentions=[],
        location_municipality="Tripoli",
        location_governorate=None,
    )
    assert primary == RoutingEntity.NORTH_MUNICIPALITY
    assert secondary == RoutingEntity.MINISTRY_ENVIRONMENT
    assert conf < 0.87
    assert router._resolve_entity("Electricite du Liban (EDL)") == RoutingEntity.EDL
    assert router._resolve_entity("unknown body") is None
    assert rationale


def test_rag_confidence_clamps_and_uses_priors(import_service_module):
    router = import_service_module("routing_engine", "app.router", qdrant=True)
    assert router._rag_confidence(_doc(_rag_score=2.0, confidence_prior=2.0)) == 0.97
    assert router._rag_confidence(_doc(_rag_score=-1.0, confidence_prior=-1.0)) >= 0.35


def test_route_async_no_candidates_requires_review(import_service_module, monkeypatch):
    router = import_service_module("routing_engine", "app.router", qdrant=True)
    monkeypatch.setattr(router, "RAG_ENABLED", True)
    monkeypatch.setattr(router, "_retrieve_docs", lambda *_args, **_kwargs: [])
    result = asyncio.run(
        router.ComplaintRouter(0.85, 0.65).route_async(
            complaint_id="c1",
            complaint_type="telecom_outage",
            category="telecom",
            subcategory="internet",
            summary="internet outage",
            severity=None,
            original_text="Internet outage in Beirut",
            location_district="Beirut",
            location_municipality="Beirut",
            location_governorate="Beirut Governorate",
            location_mentions=[],
            keywords=["internet"],
            signals={},
            routing_features={},
            evidence_text=[],
            evidence_image=[],
            alignment_features={},
            multimodal_alignment={},
        )
    )
    assert result.primary_entity == RoutingEntity.HUMAN_REVIEW
    assert result.requires_review is True
    assert result.rag_no_candidates is True


def test_route_async_uses_top_allowed_rag_doc(import_service_module, monkeypatch):
    router = import_service_module("routing_engine", "app.router", qdrant=True)
    monkeypatch.setattr(router, "RAG_ENABLED", True)
    monkeypatch.setattr(router, "_retrieve_docs", lambda *_args, **_kwargs: [_doc()])

    async def no_llm(_prompt):
        return None

    monkeypatch.setattr(router, "_call_llm_routing", no_llm)

    result = asyncio.run(
        router.ComplaintRouter(0.85, 0.65).route_async(
            complaint_id="c1",
            complaint_type="telecom_outage",
            category="telecom",
            subcategory="internet",
            summary="internet outage",
            severity=None,
            original_text="Internet outage in Beirut",
            location_district="Beirut",
            location_municipality="Beirut",
            location_governorate="Beirut Governorate",
            location_mentions=[],
            keywords=["internet"],
            signals={},
            routing_features={},
            evidence_text=[],
            evidence_image=[],
            alignment_features={},
            multimodal_alignment={},
        )
    )

    assert result.primary_entity == RoutingEntity.OGERO
    assert result.routing_source == "rag_retrieval"
    assert result.auto_routed is True

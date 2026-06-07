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
    assert router._doc_allows_auto_route(_doc(hitl_always_required=True)) is True


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


def test_rerank_prefers_location_scoped_candidate(import_service_module):
    router = import_service_module("routing_engine", "app.router", qdrant=True)
    beirut = _doc(doc_id="beirut", municipalities=["Beirut"], _rag_score=0.82)
    tripoli = _doc(doc_id="tripoli", municipalities=["Tripoli"], _rag_score=0.82)
    context = router._build_location_context("Tripoli", "Tripoli", "North Governorate", [])

    ranked = router._rerank_docs("garbage collection issue in Tripoli", [beirut, tripoli], top_k=2, location_context=context)

    assert ranked[0]["doc_id"] == "tripoli"
    assert ranked[0]["_rerank_score"] > ranked[1]["_rerank_score"]


def test_build_query_text_adds_fixed_telecom_context_only_for_physical_assets(import_service_module):
    router = import_service_module("routing_engine", "app.router", qdrant=True)

    fixed = router._build_query_text(
        "telecom_cable_cut",
        "telecom",
        "cable",
        "internet cable hanging low",
        "Beirut",
        "Beirut",
        "Beirut Governorate",
        ["Hamra"],
        {"all": {"hamra"}},
        ["internet", "cable"],
        {},
        {},
        [],
        [],
        {},
        {},
        "The internet cable is hanging low over the street",
    )
    mobile = router._build_query_text(
        "mobile_outage",
        "telecom",
        "mobile",
        "mobile 4g outage",
        "Beirut",
        "Beirut",
        "Beirut Governorate",
        [],
        {},
        ["mobile", "4g"],
        {},
        {},
        [],
        [],
        {},
        {},
        "Mobile 4g has weak signal",
    )

    assert "telecom_context: fixed_telecom" in fixed
    assert "telecom_context: fixed_telecom" not in mobile


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


def test_route_async_keeps_hitl_authority_primary_but_requires_review(import_service_module, monkeypatch):
    router = import_service_module("routing_engine", "app.router", qdrant=True)
    monkeypatch.setattr(router, "RAG_ENABLED", True)
    monkeypatch.setattr(
        router,
        "_retrieve_docs",
        lambda *_args, **_kwargs: [
            _doc(
                entity_name="Lebanese Civil Defense",
                entity_enum="Lebanese Civil Defense",
                keywords=["fire", "smoke", "emergency"],
                complaint_types=["fire", "public_safety"],
                description="Civil Defense handles fires, rescue, and emergency safety hazards.",
                hitl_always_required=True,
                _rag_score=0.94,
            )
        ],
    )

    async def no_llm(_prompt):
        return None

    monkeypatch.setattr(router, "_call_llm_routing", no_llm)

    result = asyncio.run(
        router.ComplaintRouter(0.85, 0.65).route_async(
            complaint_id="c-fire",
            complaint_type="fire",
            category="safety",
            subcategory="smoke",
            summary="fire and smoke near a building",
            severity=None,
            original_text="There is fire and smoke near the building entrance",
            location_district="Beirut",
            location_municipality="Beirut",
            location_governorate="Beirut Governorate",
            location_mentions=[],
            keywords=["fire", "smoke"],
            signals={"emergency_signal": True},
            routing_features={"requires_emergency_attention": True},
            evidence_text=[],
            evidence_image=[],
            alignment_features={},
            multimodal_alignment={},
        )
    )

    assert result.primary_entity == RoutingEntity.CIVIL_DEFENSE
    assert result.requires_review is True
    assert result.auto_routed is False
    assert "requires human review" in result.review_reason


def test_route_async_selects_secondary_entity_from_allowed_rag_docs(import_service_module, monkeypatch):
    router = import_service_module("routing_engine", "app.router", qdrant=True)
    monkeypatch.setattr(router, "RAG_ENABLED", True)
    monkeypatch.setattr(
        router,
        "_retrieve_docs",
        lambda *_args, **_kwargs: [
            _doc(
                entity_name="Ogero",
                entity_enum="Ogero",
                complaint_types=["telecom_cable_cut"],
                exact_match_terms=["internet cable"],
                _rag_score=0.9,
            ),
            _doc(
                doc_id="municipality",
                entity_name="Beirut Municipality",
                entity_enum="Beirut Municipality",
                entity_type="municipality",
                responsibility_level="secondary",
                complaint_types=["public_space_hazard"],
                keywords=["public space", "street"],
                _rag_score=0.75,
            ),
        ],
    )

    async def no_llm(_prompt):
        return None

    monkeypatch.setattr(router, "_call_llm_routing", no_llm)

    result = asyncio.run(
        router.ComplaintRouter(0.85, 0.65).route_async(
            complaint_id="c-telecom",
            complaint_type="telecom_cable_cut",
            category="telecom",
            subcategory="cable",
            summary="internet cable hanging low",
            severity=None,
            original_text="Internet cable is hanging low over the street",
            location_district="Beirut",
            location_municipality="Beirut",
            location_governorate="Beirut Governorate",
            location_mentions=[],
            keywords=["internet", "cable"],
            signals={},
            routing_features={},
            evidence_text=[],
            evidence_image=[],
            alignment_features={},
            multimodal_alignment={},
        )
    )

    assert result.primary_entity == RoutingEntity.OGERO
    assert result.secondary_entity == RoutingEntity.BEIRUT_MUNICIPALITY

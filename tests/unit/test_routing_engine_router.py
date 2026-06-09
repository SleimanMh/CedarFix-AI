from __future__ import annotations

import asyncio
import json

import pytest


pytestmark = pytest.mark.unit


def _routing_doc(schemas, doc_id: str, entity, **overrides) -> dict:
    doc = {
        "doc_id": doc_id,
        "entity_name": entity.value,
        "entity_enum": entity.value,
        "entity_type": "utility",
        "doc_type": "responsibility",
        "route_mode": "routing_candidate",
        "route_authority": "authoritative",
        "retrieval_stage": "stage1_dispatch",
        "retrieval_lane": "dispatch",
        "stage_priority": 1,
        "source_reliability": "verified",
        "responsibility_level": "primary",
        "retrieval_weight": 1.0,
        "confidence_prior": 0.85,
        "governs_nationally": False,
        "governorates": [],
        "districts": [],
        "municipalities": [],
        "complaint_types": ["pothole"],
        "keywords": ["pothole", "road", "hazard"],
        "exact_match_terms": ["pothole"],
        "negative_signals": [],
        "not_responsible_for": [],
        "hitl_always_required": False,
        "hitl_conditions": [],
        "source_ids": ["SRC-TEST"],
        "description": f"{entity.value} handles this complaint type.",
        "_rag_score": 0.82,
    }
    doc.update(overrides)
    return doc


def _route_kwargs(**overrides) -> dict:
    payload = {
        "complaint_id": "complaint-1",
        "complaint_type": "pothole",
        "category": "roads",
        "subcategory": "pothole",
        "summary": "A large pothole is blocking traffic.",
        "severity": "HIGH",
        "original_text": "There is a large pothole in Hamra blocking cars.",
        "location_district": "Beirut",
        "location_municipality": "Beirut",
        "location_governorate": "Beirut Governorate",
        "location_mentions": ["Hamra"],
        "keywords": ["pothole", "road"],
        "signals": {},
        "routing_features": {},
        "evidence_text": [],
        "evidence_image": [],
        "alignment_features": {},
        "multimodal_alignment": {},
    }
    payload.update(overrides)
    return payload


def _compiled_routing_doc(
    repo_root,
    doc_id: str,
    *,
    rag_score: float = 0.94,
    expected: dict | None = None,
) -> dict:
    path = repo_root / "RAG Data" / "compiled" / "routing_knowledge_compiled_production.json"
    docs = json.loads(path.read_text(encoding="utf-8-sig"))
    for doc in docs:
        if doc.get("doc_id") == doc_id:
            mismatches = {
                field: {"expected": value, "actual": doc.get(field)}
                for field, value in (expected or {}).items()
                if doc.get(field) != value
            }
            assert mismatches == {}, (
                f"Compiled routing doc {doc_id!r} no longer matches the router fixture contract: "
                f"{mismatches}"
            )
            copied = dict(doc)
            copied["_rag_score"] = rag_score
            return copied
    raise AssertionError(f"Compiled routing doc {doc_id!r} was not found")


async def _no_llm(prompt):
    return None


def test_resolve_entity_accepts_aliases_and_suffixes(router_module, schemas):
    assert router_module._resolve_entity("Ogero Telecom") == schemas.RoutingEntity.OGERO
    assert router_module._resolve_entity("Electricite de Liban") == schemas.RoutingEntity.EDL
    assert router_module._resolve_entity("Electricite Du Liban - EDL") == schemas.RoutingEntity.EDL
    assert (
        router_module._resolve_entity("Beirut and Mount Lebanon Water Establishment - EBML")
        == schemas.RoutingEntity.WATER_AUTHORITY
    )
    assert router_module._resolve_entity("Definitely Not A CedarFix Entity") is None


def test_location_context_normalizes_explicit_location_fields(router_module):
    context = router_module._build_location_context(
        "Sin el Fil Municipality",
        "Baabda District",
        "Mount Lebanon Governorate",
        [],
    )

    assert "sin el fil" in context["municipalities"]
    assert "baabda" in context["districts"]
    assert "mount lebanon" in context["governorates"]
    assert {"sin", "fil", "baabda", "mount", "lebanon"} <= context["all"]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"route_mode": "routing_candidate", "route_authority": "authoritative"}, True),
        ({"route_mode": "contact_fallback_only"}, False),
        ({"route_authority": "fallback_only_not_auto_route"}, False),
        ({"retrieval_stage": "stage3_evidence"}, False),
        ({"route_mode": "routing_guardrail", "route_authority": "guardrail"}, True),
        (
            {
                "route_mode": "routing_guardrail",
                "route_authority": "guardrail",
                "entity_enum": "Human Review Queue",
                "entity_name": "Human Review Queue",
            },
            False,
        ),
    ],
)
def test_doc_allows_auto_route_respects_blocking_policy(router_module, schemas, overrides, expected):
    doc = _routing_doc(schemas, "doc", schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS, **overrides)
    assert router_module._doc_allows_auto_route(doc) is expected


def test_rerank_prefers_authoritative_stage1_over_support_context(router_module, schemas):
    support_doc = _routing_doc(
        schemas,
        "support",
        schemas.RoutingEntity.HUMAN_REVIEW,
        route_mode="supporting_context",
        route_authority="supporting_audit",
        retrieval_stage="stage3_evidence",
        responsibility_level="boundary",
        _rag_score=0.99,
    )
    authority_doc = _routing_doc(
        schemas,
        "authority",
        schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS,
        route_mode="routing_rule",
        retrieval_stage="stage1_dispatch",
        responsibility_level="primary",
        _rag_score=0.72,
    )

    ranked = router_module._rerank_docs("urgent pothole road hazard", [support_doc, authority_doc], top_k=2)

    assert ranked[0]["doc_id"] == "authority"
    assert ranked[0]["_rerank_score"] > ranked[1]["_rerank_score"]


def test_telecom_query_boosts_fixed_infrastructure_docs(router_module, schemas):
    mobile_doc = _routing_doc(
        schemas,
        "mobile",
        schemas.RoutingEntity.MOBILE_OPERATOR,
        keywords=["mobile", "cellular", "4g"],
        description="Mobile operator radio network outage handling.",
        _rag_score=0.80,
    )
    fixed_doc = _routing_doc(
        schemas,
        "fixed",
        schemas.RoutingEntity.OGERO,
        keywords=["internet", "fiber", "cable", "landline"],
        exact_match_terms=["internet cable"],
        description="Fixed telecom cables, cabinets, landline and fiber infrastructure.",
        _rag_score=0.75,
    )

    ranked = router_module._rerank_docs(
        "internet fiber cable hanging from a pole",
        [mobile_doc, fixed_doc],
        top_k=2,
    )

    assert ranked[0]["doc_id"] == "fixed"


def test_rag_confidence_is_clamped_and_stage_aware(router_module, schemas):
    weak = _routing_doc(
        schemas,
        "weak",
        schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS,
        _rag_score=-4,
        confidence_prior=-2,
        retrieval_stage="stage3_evidence",
    )
    strong = _routing_doc(
        schemas,
        "strong",
        schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS,
        _rag_score=2,
        confidence_prior=2,
        retrieval_stage="stage1_dispatch",
    )

    assert router_module._rag_confidence(weak) == 0.35
    assert router_module._rag_confidence(strong) == 0.97


def test_async_router_sends_zero_rag_candidates_to_review(router_module, monkeypatch, schemas):
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: [])
    monkeypatch.setattr(router_module, "_call_llm_routing", lambda prompt: None)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(router.route_async(**_route_kwargs()))

    assert result.primary_entity == schemas.RoutingEntity.HUMAN_REVIEW
    assert result.routing_source == "rag_no_match"
    assert result.rag_no_candidates is True
    assert result.requires_review is True


def test_async_router_requires_review_when_rag_disabled_without_static_fallback(router_module, monkeypatch, schemas):
    monkeypatch.setattr(router_module, "RAG_ENABLED", False)
    monkeypatch.setattr(router_module, "STATIC_FALLBACK_ENABLED", False)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(router.route_async(**_route_kwargs()))

    assert result.primary_entity == schemas.RoutingEntity.HUMAN_REVIEW
    assert result.routing_source == "rag_disabled"
    assert result.requires_review is True


def test_async_router_static_fallback_uses_regional_water_authority(router_module, monkeypatch, schemas):
    monkeypatch.setattr(router_module, "RAG_ENABLED", False)
    monkeypatch.setattr(router_module, "STATIC_FALLBACK_ENABLED", True)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(
        router.route_async(
            **_route_kwargs(
                complaint_type="water_pipe",
                category="water",
                subcategory="pipe_leak",
                location_governorate="South Governorate",
                location_district="Tyre",
                location_municipality="Tyre",
            )
        )
    )

    assert result.primary_entity == schemas.RoutingEntity.WATER_SOUTH
    assert result.routing_source == "static_fallback"
    assert result.auto_routed is True


def test_async_router_rejects_support_only_rag_candidates(router_module, monkeypatch, schemas):
    docs = [
        _routing_doc(
            schemas,
            "support",
            schemas.RoutingEntity.HUMAN_REVIEW,
            route_mode="supporting_context",
            route_authority="supporting_audit",
            retrieval_stage="stage2_operations",
        )
    ]
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: docs)

    async def no_llm(prompt):
        return None

    monkeypatch.setattr(router_module, "_call_llm_routing", no_llm)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(router.route_async(**_route_kwargs()))

    assert result.primary_entity == schemas.RoutingEntity.HUMAN_REVIEW
    assert result.routing_source == "rag_support_only"
    assert result.requires_review is True


def test_async_router_unresolved_top_entity_goes_to_review(router_module, monkeypatch, schemas):
    docs = [
        _routing_doc(
            schemas,
            "mystery",
            schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS,
            entity_name="Mystery Authority",
            entity_enum="Mystery Authority",
        )
    ]
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: docs)

    async def no_llm(prompt):
        return None

    monkeypatch.setattr(router_module, "_call_llm_routing", no_llm)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(router.route_async(**_route_kwargs()))

    assert result.primary_entity == schemas.RoutingEntity.HUMAN_REVIEW
    assert result.routing_source == "rag_unresolved_entity"
    assert result.requires_review is True


def test_async_router_low_confidence_authority_is_not_auto_routed(router_module, monkeypatch, schemas):
    docs = [
        _routing_doc(
            schemas,
            "weak-authority",
            schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS,
            _rag_score=0.08,
            confidence_prior=0.2,
        )
    ]
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: docs)

    async def no_llm(prompt):
        return None

    monkeypatch.setattr(router_module, "_call_llm_routing", no_llm)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(router.route_async(**_route_kwargs()))

    assert result.primary_entity == schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS
    assert result.primary_confidence < 0.65
    assert result.auto_routed is False
    assert result.requires_review is True
    assert result.review_reason == "Low RAG routing confidence"


def test_async_router_keeps_hitl_authority_as_primary(router_module, monkeypatch, schemas):
    docs = [
        _routing_doc(
            schemas,
            "civil-defense-emergency",
            schemas.RoutingEntity.CIVIL_DEFENSE,
            hitl_always_required=True,
            keywords=["fire", "collapse", "emergency"],
            complaint_types=["public_safety"],
            _rag_score=0.95,
        )
    ]
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: docs)

    async def no_llm(prompt):
        return None

    monkeypatch.setattr(router_module, "_call_llm_routing", no_llm)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(
        router.route_async(
            **_route_kwargs(
                complaint_type="public_safety",
                category="public_safety",
                subcategory="structural_hazard",
                original_text="There is smoke and a collapse risk near the building.",
            )
        )
    )

    assert result.primary_entity == schemas.RoutingEntity.CIVIL_DEFENSE
    assert result.requires_review is True
    assert result.auto_routed is False
    assert "human review" in result.review_reason.lower()


def test_async_router_guardrail_lock_keeps_top_authority_as_primary(router_module, monkeypatch, schemas):
    docs = [
        _routing_doc(
            schemas,
            "guardrail",
            schemas.RoutingEntity.CIVIL_DEFENSE,
            route_mode="routing_guardrail",
            route_authority="guardrail",
            keywords=["fire", "collapse", "emergency"],
            _rag_score=0.91,
        ),
        _routing_doc(
            schemas,
            "isf",
            schemas.RoutingEntity.INTERNAL_SECURITY,
            _rag_score=0.85,
        ),
    ]
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: docs)

    async def llm_selects_isf(prompt):
        return {
            "primary_entity": "Internal Security Forces",
            "secondary_entity": None,
            "confidence": 0.9,
            "rationale": "Police coordination is needed.",
            "requires_human_review": False,
            "review_reason": None,
        }

    monkeypatch.setattr(router_module, "_call_llm_routing", llm_selects_isf)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(
        router.route_async(
            **_route_kwargs(
                complaint_type="public_safety",
                category="public_safety",
                subcategory="emergency_response",
                original_text="Fire and collapse risk reported near a residential building.",
            )
        )
    )

    assert result.primary_entity == schemas.RoutingEntity.CIVIL_DEFENSE
    assert result.secondary_entity == schemas.RoutingEntity.INTERNAL_SECURITY
    assert result.requires_review is True
    assert result.auto_routed is False
    assert "guardrail" in result.review_reason.lower()


def test_async_router_real_authority_remains_primary_when_llm_requests_human_review(
    router_module,
    monkeypatch,
    schemas,
):
    docs = [
        _routing_doc(
            schemas,
            "ogero",
            schemas.RoutingEntity.OGERO,
            route_mode="service_catalog",
            retrieval_stage="stage2_operations",
            complaint_types=["telecom_outage"],
            keywords=["internet", "cable", "fiber"],
            _rag_score=0.9,
        )
    ]
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: docs)

    async def llm_requests_review(prompt):
        return {
            "primary_entity": "Human Review Queue",
            "secondary_entity": None,
            "confidence": 0.7,
            "rationale": "Ambiguous ownership.",
            "requires_human_review": True,
            "review_reason": "Ambiguous fixed telecom ownership",
        }

    monkeypatch.setattr(router_module, "_call_llm_routing", llm_requests_review)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(
        router.route_async(
            **_route_kwargs(
                complaint_type="telecom_outage",
                category="telecom",
                subcategory="internet_outage",
                original_text="The fixed internet cable and fiber line are down.",
                keywords=["internet", "cable", "fiber"],
            )
        )
    )

    assert result.primary_entity == schemas.RoutingEntity.OGERO
    assert result.primary_confidence >= 0.7
    assert result.requires_review is True
    assert result.review_reason == "Ambiguous fixed telecom ownership"


def test_async_router_preserves_strong_rag_primary_when_llm_disagrees(router_module, monkeypatch, schemas):
    docs = [
        _routing_doc(
            schemas,
            "mpwt-stage1",
            schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS,
            route_mode="routing_rule",
            _rag_score=0.88,
        ),
        _routing_doc(
            schemas,
            "beirut-context",
            schemas.RoutingEntity.BEIRUT_MUNICIPALITY,
            route_mode="complaint_intake_or_channel",
            retrieval_stage="stage2_operations",
            responsibility_level="secondary",
            _rag_score=0.86,
        ),
    ]
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: docs)

    async def disagreeing_llm(prompt):
        return {
            "primary_entity": "Beirut Municipality",
            "secondary_entity": None,
            "confidence": 0.93,
            "rationale": "Municipality mentioned in location.",
            "requires_human_review": False,
            "review_reason": None,
        }

    monkeypatch.setattr(router_module, "_call_llm_routing", disagreeing_llm)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(router.route_async(**_route_kwargs()))

    assert result.primary_entity == schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS
    assert result.secondary_entity == schemas.RoutingEntity.BEIRUT_MUNICIPALITY
    assert result.routing_source == "rag_llm"
    assert "kept as primary" in " ".join(result.routing_rationale)


def test_async_router_routes_with_real_compiled_ogero_rag_doc(router_module, monkeypatch, schemas, repo_root):
    doc = _compiled_routing_doc(
        repo_root,
        "ogero-fixed_internet_outage",
        expected={
            "entity_enum": schemas.RoutingEntity.OGERO.value,
            "route_mode": "routing_candidate",
            "route_authority": "authoritative",
            "retrieval_stage": "stage1_dispatch",
            "responsibility_level": "primary",
            "hitl_always_required": False,
        },
    )
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: [doc])
    monkeypatch.setattr(router_module, "_call_llm_routing", _no_llm)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(
        router.route_async(
            **_route_kwargs(
                complaint_type="fixed_internet_outage",
                category="telecom",
                subcategory="internet_outage",
                original_text="The fixed internet fiber line is down in Hamra.",
                keywords=["fixed", "internet", "fiber"],
            )
        )
    )

    assert result.primary_entity == schemas.RoutingEntity.OGERO
    assert result.routing_source == "rag_retrieval"
    assert result.auto_routed is True
    assert result.requires_review is False
    assert result.retrieved_sources == ["ogero-fixed_internet_outage"]


def test_async_router_keeps_real_compiled_civil_defense_hitl_authority(router_module, monkeypatch, schemas, repo_root):
    doc = _compiled_routing_doc(
        repo_root,
        "cd-building_collapse",
        rag_score=0.97,
        expected={
            "entity_enum": schemas.RoutingEntity.CIVIL_DEFENSE.value,
            "route_mode": "routing_candidate",
            "route_authority": "authoritative",
            "retrieval_stage": "stage1_dispatch",
            "responsibility_level": "primary",
            "hitl_always_required": True,
        },
    )
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: [doc])
    monkeypatch.setattr(router_module, "_call_llm_routing", _no_llm)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(
        router.route_async(
            **_route_kwargs(
                complaint_type="building_collapse",
                category="public_safety",
                subcategory="structural_hazard",
                original_text="A building wall is collapsing and people may be trapped.",
                keywords=["collapse", "trapped", "emergency"],
                signals={"emergency_signal": True},
            )
        )
    )

    assert result.primary_entity == schemas.RoutingEntity.CIVIL_DEFENSE
    assert result.primary_confidence >= 0.9
    assert result.auto_routed is False
    assert result.requires_review is True
    assert "human review" in result.review_reason.lower()


def test_async_router_real_compiled_mpwt_guardrail_auto_routes_national_road(
    router_module,
    monkeypatch,
    schemas,
    repo_root,
):
    doc = _compiled_routing_doc(
        repo_root,
        "boundary_bc_007",
        expected={
            "entity_enum": schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS.value,
            "route_mode": "routing_guardrail",
            "route_authority": "guardrail",
            "retrieval_stage": "stage1_dispatch",
            "responsibility_level": "primary",
            "hitl_always_required": False,
        },
    )
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: [doc])
    monkeypatch.setattr(router_module, "_call_llm_routing", _no_llm)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(
        router.route_async(
            **_route_kwargs(
                complaint_type="road_damage_national_road_or_bridge",
                category="roads",
                subcategory="classified_road_damage",
                original_text="There is serious damage on the national coastal road bridge.",
                keywords=["national", "road", "bridge", "damage"],
            )
        )
    )

    assert result.primary_entity == schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS
    assert result.routing_source == "rag_retrieval"
    assert result.auto_routed is True
    assert result.requires_review is False


def test_async_router_real_compiled_municipality_guardrail_locks_primary_when_llm_disagrees(
    router_module,
    monkeypatch,
    schemas,
    repo_root,
):
    local_road_doc = _compiled_routing_doc(
        repo_root,
        "boundary_bc_006",
        rag_score=0.94,
        expected={
            "entity_enum": schemas.RoutingEntity.GENERIC_MUNICIPALITY.value,
            "route_mode": "routing_guardrail",
            "route_authority": "guardrail",
            "retrieval_stage": "stage1_dispatch",
            "responsibility_level": "primary",
            "hitl_always_required": False,
        },
    )
    mpwt_doc = _compiled_routing_doc(
        repo_root,
        "boundary_bc_007",
        rag_score=0.91,
        expected={
            "entity_enum": schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS.value,
            "route_mode": "routing_guardrail",
            "route_authority": "guardrail",
            "retrieval_stage": "stage1_dispatch",
            "responsibility_level": "primary",
            "hitl_always_required": False,
        },
    )
    monkeypatch.setattr(router_module, "RAG_ENABLED", True)
    monkeypatch.setattr(router_module, "_retrieve_docs", lambda *args, **kwargs: [local_road_doc, mpwt_doc])

    async def llm_selects_mpwt(prompt):
        return {
            "primary_entity": "Ministry of Public Works",
            "secondary_entity": None,
            "confidence": 0.92,
            "rationale": "The LLM over-selected the national road authority.",
            "requires_human_review": False,
            "review_reason": None,
        }

    monkeypatch.setattr(router_module, "_call_llm_routing", llm_selects_mpwt)

    router = router_module.ComplaintRouter(auto_threshold=0.85, review_threshold=0.65)
    result = asyncio.run(
        router.route_async(
            **_route_kwargs(
                complaint_type="road_damage_local_street",
                category="roads",
                subcategory="local_street_pothole",
                original_text="A pothole damaged the small residential street beside our building.",
                keywords=["local", "residential", "street", "pothole"],
            )
        )
    )

    assert result.primary_entity == schemas.RoutingEntity.GENERIC_MUNICIPALITY
    assert result.secondary_entity == schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS
    assert result.auto_routed is False
    assert result.requires_review is True
    assert "guardrail" in result.review_reason.lower()

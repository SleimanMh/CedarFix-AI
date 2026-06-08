from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from conftest import import_or_skip


pytestmark = pytest.mark.contract


ALLOWED_ROUTE_MODES = {
    "cdr_project_boundary",
    "complaint_intake_or_channel",
    "complaint_workflow",
    "contact_context",
    "emergency_instruction",
    "entity_fact_context",
    "entity_legal_scope",
    "geo_district_reference",
    "geo_service_area",
    "geo_service_area_map",
    "geo_service_route",
    "geo_union_context",
    "historical_case_context",
    "human_review_gate",
    "human_review_user_assist",
    "intake_requirements",
    "municipality_resolution_bundle",
    "negative_boundary",
    "operator_context",
    "query_and_type_expansion",
    "resolution_context",
    "resolution_policy",
    "routing_candidate",
    "routing_guardrail",
    "routing_rule",
    "sector_policy_map",
    "service_catalog",
    "shared_service_context",
    "source_provenance",
    "supporting_context",
    "waste_site_context",
}
ALLOWED_AUTHORITIES = {
    "authoritative",
    "authoritative_map",
    "authoritative_policy",
    "authoritative_profile",
    "authoritative_rule",
    "district_map",
    "evidence_case",
    "geo_union_membership_bundle",
    "guarded_user_confirmed",
    "guardrail",
    "location_map_bundle",
    "location_resolution_bundle",
    "manual_review_gate",
    "policy_context",
    "process_requirement",
    "project_owner_boundary",
    "provenance_context",
    "site_context",
    "supporting",
    "verified_channel",
}
ALLOWED_STAGES = {"stage1_dispatch", "stage2_operations", "stage3_evidence"}
ALLOWED_LEVELS = {"primary", "secondary", "boundary", "context"}
ALLOWED_LANES = {"dispatch", "operations", "evidence", "geo_context"}


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _assert_no_new_policy_values(docs: list[dict], field: str, allowed: set[str]) -> None:
    unexpected = sorted({doc.get(field) for doc in docs} - allowed)
    offenders = [
        f"{doc.get('doc_id', '<missing-id>')}={doc.get(field)!r}"
        for doc in docs
        if doc.get(field) in unexpected
    ][:20]

    assert unexpected == [], (
        f"New {field} policy value(s) detected: {unexpected}. "
        "If intentional, update the allowed policy set and review router auto-route semantics. "
        f"Sample docs: {offenders}"
    )


def test_compiled_routing_knowledge_has_unique_ids_and_required_fields(repo_root, schemas):
    path = repo_root / "RAG Data" / "compiled" / "routing_knowledge_compiled_production.json"
    docs = _load_json(path)
    required = {
        "doc_id",
        "entity_name",
        "entity_enum",
        "route_mode",
        "route_authority",
        "retrieval_stage",
        "responsibility_level",
        "confidence_prior",
        "retrieval_weight",
        "description",
    }
    allowed_entities = {entity.value for entity in schemas.RoutingEntity}

    ids = [doc.get("doc_id") for doc in docs]
    duplicates = [doc_id for doc_id, count in Counter(ids).items() if count > 1]
    missing_required = [
        doc.get("doc_id", "<missing-id>")
        for doc in docs
        if required - set(doc)
    ]
    unknown_entities = sorted({doc.get("entity_enum") for doc in docs} - allowed_entities)
    bad_confidence = [
        doc["doc_id"]
        for doc in docs
        if not 0.0 <= float(doc.get("confidence_prior", -1)) <= 1.0
    ]
    bad_weight = [
        doc["doc_id"]
        for doc in docs
        if not 0.0 < float(doc.get("retrieval_weight", 0)) <= 2.0
    ]

    assert isinstance(docs, list)
    assert len(docs) > 100
    assert duplicates == []
    assert missing_required == []
    assert unknown_entities == []
    assert bad_confidence == []
    assert bad_weight == []


def test_compiled_routing_knowledge_validates_against_shared_schema(repo_root, schemas):
    path = repo_root / "RAG Data" / "compiled" / "routing_knowledge_compiled_production.json"
    docs = _load_json(path)

    failures: list[str] = []
    for doc in docs:
        try:
            schemas.RoutingKnowledgeDoc.model_validate(doc)
        except Exception as exc:
            failures.append(f"{doc.get('doc_id', '<missing-id>')}: {exc}")

    assert failures == []


def test_compiled_routing_knowledge_uses_known_policy_enums(repo_root):
    path = repo_root / "RAG Data" / "compiled" / "routing_knowledge_compiled_production.json"
    docs = _load_json(path)

    _assert_no_new_policy_values(docs, "route_mode", ALLOWED_ROUTE_MODES)
    _assert_no_new_policy_values(docs, "route_authority", ALLOWED_AUTHORITIES)
    _assert_no_new_policy_values(docs, "retrieval_stage", ALLOWED_STAGES)
    _assert_no_new_policy_values(docs, "responsibility_level", ALLOWED_LEVELS)
    _assert_no_new_policy_values(docs, "retrieval_lane", ALLOWED_LANES)


def test_compiled_routing_knowledge_separates_dispatch_from_evidence(repo_root):
    path = repo_root / "RAG Data" / "compiled" / "routing_knowledge_compiled_production.json"
    docs = _load_json(path)

    stage3_auto_candidates = [
        doc["doc_id"]
        for doc in docs
        if doc.get("retrieval_stage") == "stage3_evidence"
        and doc.get("stage1_dispatch_candidate") is True
    ]
    empty_descriptions = [
        doc["doc_id"]
        for doc in docs
        if not str(doc.get("description") or "").strip()
    ]

    assert stage3_auto_candidates == []
    assert empty_descriptions == []


def test_compiled_routing_knowledge_blocks_support_only_auto_route(repo_root):
    router = import_or_skip("services.routing_engine.app.router")
    path = repo_root / "RAG Data" / "compiled" / "routing_knowledge_compiled_production.json"
    docs = _load_json(path)
    support_modes = set(router._SUPPORT_ONLY_MODES) - {"routing_guardrail"}

    support_only_auto_routeable = [
        doc["doc_id"]
        for doc in docs
        if (
            doc.get("route_mode") in support_modes
            or doc.get("route_authority") in router._BLOCKING_AUTHORITIES
            or doc.get("retrieval_stage") == "stage3_evidence"
        )
        and router._doc_allows_auto_route(doc)
    ]

    assert support_only_auto_routeable == []


def test_municipality_lookup_contract_preserves_safe_auto_route_policy(repo_root):
    path = repo_root / "RAG Data" / "municipality" / "municipality_lookup_compiled_production.json"
    docs = _load_json(path)

    ids = [doc.get("municipality_id") for doc in docs]
    duplicates = [mid for mid, count in Counter(ids).items() if count > 1]
    empty_retrieval_text = [
        doc.get("municipality_id")
        for doc in docs
        if not str(doc.get("retrieval_text") or "").strip()
    ]
    blind_submit_allowed = [
        doc.get("municipality_id")
        for doc in docs
        if doc.get("routing", {}).get("blind_auto_submit_allowed") is True
    ]
    confirmation_not_required = [
        doc.get("municipality_id")
        for doc in docs
        if doc.get("routing", {}).get("user_confirmation_required") is not True
    ]
    autoroute_count = sum(1 for doc in docs if doc.get("routing", {}).get("can_auto_route") is True)

    assert isinstance(docs, list)
    assert len(docs) == 1065
    assert duplicates == []
    assert empty_retrieval_text == []
    assert blind_submit_allowed == []
    assert confirmation_not_required == []
    assert autoroute_count == 180


@pytest.mark.parametrize("relative_path", [
    "RAG Data/BMLWE.json",
    "RAG Data/EDL.json",
    "RAG Data/OGERO.json",
    "RAG Data/dossiers/entities/MUN.json",
    "RAG Data/dossiers/advanced/structured_rag_docs.jsonl",
])
def test_rag_source_files_are_parseable(repo_root, relative_path):
    path = repo_root / relative_path
    assert path.exists()

    if path.suffix == ".jsonl":
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if line.strip():
                assert isinstance(json.loads(line), dict), f"{relative_path}:{line_number}"
    else:
        assert _load_json(path)

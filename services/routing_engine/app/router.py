"""
IEP-6 Routing Engine — RAG + Static Fallback
=============================================

Flow:
  1. Build semantic query from complaint fields.
  2. Retrieve top-K routing documents from Qdrant "routing_knowledge" collection.
  3. Pass retrieved docs + complaint to Qwen LLM when available.
  4. If Qwen is unavailable, choose from the top reranked Qdrant candidate.
  5. If Qdrant has no production routing authority, send to Human Review Queue.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
from typing import Optional, List

import httpx
from cedarfix_shared.schemas import RoutingResult, RoutingEntity
from cedarfix_shared.location import haversine_km, lookup_text
from cedarfix_shared.qdrant import create_qdrant_client, qdrant_target_label
from cedarfix_shared.metrics import (
    RAG_CANDIDATE_COUNT,
    RAG_RETRIEVAL_DURATION,
    RAG_RETRIEVAL_ERRORS_TOTAL,
    RAG_TOP_SCORE,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "")
QWEN_MODEL: str = os.getenv("QWEN_MODEL", "Qwen/Qwen2.5-3B-Instruct")
QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "none")
QWEN_ENABLED: bool = os.getenv("QWEN_ENABLED", "true").lower() == "true"
QWEN_ROUTING_TIMEOUT: float = float(os.getenv("QWEN_ROUTING_TIMEOUT", "20"))
QWEN_ROUTING_MAX_TOKENS: int = max(128, int(os.getenv("QWEN_ROUTING_MAX_TOKENS", "512")))

RAG_ENABLED: bool = os.getenv("ROUTING_RAG_ENABLED", "true").lower() == "true"
RAG_TOP_K: int = int(os.getenv("ROUTING_RAG_TOP_K", "8"))
RAG_STAGE_PRIORITY_ENABLED: bool = os.getenv("ROUTING_RAG_STAGE_PRIORITY_ENABLED", "true").lower() == "true"
RAG_STAGE1_TARGET: int = int(os.getenv("ROUTING_RAG_STAGE1_TARGET", "12"))
RAG_STAGE2_TARGET: int = int(os.getenv("ROUTING_RAG_STAGE2_TARGET", "8"))
RAG_STAGE3_TARGET: int = int(os.getenv("ROUTING_RAG_STAGE3_TARGET", "6"))
STATIC_FALLBACK_ENABLED: bool = os.getenv("ROUTING_STATIC_FALLBACK_ENABLED", "false").lower() == "true"
QDRANT_HOST: str = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
RAG_COLLECTION: str = os.getenv("ROUTING_QDRANT_COLLECTION", "routing_knowledge")
EMBED_MODEL: str = os.getenv(
    "MODEL_NAME",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
)

# ---------------------------------------------------------------------------
# Legacy static fallback table.
#
# Runtime routing is Qdrant-first. This table is used only when
# ROUTING_STATIC_FALLBACK_ENABLED=true or by the old synchronous compatibility
# shim at the bottom of the module.
# ---------------------------------------------------------------------------

TYPE_TO_ENTITY = {
    "pothole":            (RoutingEntity.MINISTRY_PUBLIC_WORKS,    RoutingEntity.BEIRUT_MUNICIPALITY,  0.88),
    "road_damage":        (RoutingEntity.MINISTRY_PUBLIC_WORKS,    RoutingEntity.BEIRUT_MUNICIPALITY,  0.88),
    "flooding":           (RoutingEntity.MINISTRY_ENVIRONMENT,     RoutingEntity.MINISTRY_PUBLIC_WORKS, 0.82),
    "water_pipe":         (RoutingEntity.WATER_AUTHORITY,          RoutingEntity.BEIRUT_MUNICIPALITY,  0.90),
    "electricity_outage": (RoutingEntity.EDL,                      None,                               0.95),
    "telecom_outage":     (RoutingEntity.OGERO,                    None,                               0.95),
    "streetlight":        (RoutingEntity.EDL,                      RoutingEntity.BEIRUT_MUNICIPALITY,  0.80),
    "traffic_light":      (RoutingEntity.INTERNAL_SECURITY,        RoutingEntity.BEIRUT_MUNICIPALITY,  0.85),
    "traffic_incident":   (RoutingEntity.INTERNAL_SECURITY,        RoutingEntity.MINISTRY_PUBLIC_WORKS, 0.88),
    "waste_accumulation": (RoutingEntity.BEIRUT_MUNICIPALITY,      RoutingEntity.MINISTRY_ENVIRONMENT, 0.87),
    "sidewalk_damage":    (RoutingEntity.BEIRUT_MUNICIPALITY,      RoutingEntity.MINISTRY_PUBLIC_WORKS, 0.83),
    "public_safety":      (RoutingEntity.INTERNAL_SECURITY,        RoutingEntity.BEIRUT_MUNICIPALITY,  0.82),
    "other":              (RoutingEntity.HUMAN_REVIEW,             None,                               0.40),
}

# Municipality → RoutingEntity override (used when complaint is outside Beirut)
MUNICIPALITY_ENTITY_MAP = {
    "Beirut":     RoutingEntity.BEIRUT_MUNICIPALITY,
    "Tripoli":    RoutingEntity.NORTH_MUNICIPALITY,
    "Zgharta":    RoutingEntity.NORTH_MUNICIPALITY,
    "Batroun":    RoutingEntity.NORTH_MUNICIPALITY,
    "Halba":      RoutingEntity.NORTH_MUNICIPALITY,
    "Byblos":     RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Jbeil":      RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Jounieh":    RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Baabda":     RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Jdeideh":    RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Dekwaneh":   RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Sin el Fil": RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Aley":       RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Antelias":   RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Dbayeh":     RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Choueifat":  RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Khalde":     RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Sidon":      RoutingEntity.SOUTH_MUNICIPALITY,
    "Tyre":       RoutingEntity.SOUTH_MUNICIPALITY,
    "Nabatieh":   RoutingEntity.SOUTH_MUNICIPALITY,
    "Bint Jbeil": RoutingEntity.SOUTH_MUNICIPALITY,
    "Zahle":      RoutingEntity.BEKAA_MUNICIPALITY,
    "Baalbek":    RoutingEntity.BEKAA_MUNICIPALITY,
    "Chtaura":    RoutingEntity.BEKAA_MUNICIPALITY,
}

# Water authority by governorate
WATER_BY_GOVERNORATE = {
    "Beirut Governorate":           RoutingEntity.WATER_AUTHORITY,
    "Mount Lebanon Governorate":    RoutingEntity.WATER_AUTHORITY,
    "North Governorate":            RoutingEntity.WATER_NORTH,
    "Akkar Governorate":            RoutingEntity.WATER_NORTH,
    "South Governorate":            RoutingEntity.WATER_SOUTH,
    "Nabatieh Governorate":         RoutingEntity.WATER_SOUTH,
    "Bekaa Governorate":            RoutingEntity.WATER_BEKAA,
    "Baalbek-Hermel Governorate":   RoutingEntity.WATER_BEKAA,
}

# ---------------------------------------------------------------------------
# LLM Routing Prompt
# ---------------------------------------------------------------------------

_ROUTING_SYSTEM = """\
You are a routing expert for CedarFix, a Lebanese public infrastructure complaint platform.
You receive a complaint and a list of candidate Lebanese public-sector entities retrieved
from the routing knowledge base.

Return ONLY a valid JSON object — no explanation, no markdown:
{
  "primary_entity": "<exact entity_name from the candidates below>",
  "secondary_entity": "<exact entity_name or null>",
  "confidence": <0.0–1.0>,
  "rationale": "<2–3 sentences citing specific responsibilities>",
  "requires_human_review": <true|false>,
  "review_reason": "<reason or null>"
}

Rules:
- You MUST choose primary_entity from the provided candidates. Do not invent entities.
- secondary_entity is optional — only set if two entities genuinely share responsibility.
- confidence < 0.65 → set requires_human_review: true.
- Prefer candidates whose responsibility_level is primary, whose route_mode is routing_candidate,
  routing_rule, or geo_service_route, and whose handles match the complaint.
- Prefer retrieval_stage=stage1_dispatch for the primary routing decision.
- Use retrieval_stage=stage2_operations for channel, required fields, workflow, and SLA context.
- Treat retrieval_stage=stage3_evidence as supporting evidence/provenance context, not first-line authority.
- Do NOT choose a candidate for issues listed under does NOT handle.
- Treat contact_fallback_only, audit_context, contact_context, query_and_type_expansion,
  resolution_context, resolution_policy, supporting_context, and staging_not_production
  records as supporting context only, not production routing authority.
- Do NOT auto-route from docs marked fallback_only_not_auto_route, staging_not_production,
  blocker, supporting_audit, or validation_guardrail.
- If all matching docs are support-only or hitl_always_required, choose Human Review Queue
  when available, otherwise set requires_human_review: true.
- If the best matching candidate is Human Review Queue or the candidate HITL rules apply,
  choose Human Review Queue when available, otherwise set requires_human_review: true.
- If the location is outside Beirut, prefer the correct regional or local entity over Beirut Municipality.
- For utilities, choose from the retrieved candidates using responsibility, complaint handles,
  and geographic metadata. Do not apply a default national utility when a more specific
  local, regional, or concession candidate is retrieved.
- Traffic accidents/police matters → Internal Security Forces.
"""


def _build_routing_prompt(
    complaint_type: str,
    original_text: str,
    location_district: Optional[str],
    location_governorate: Optional[str],
    location_municipality: Optional[str],
    keywords: List[str],
    docs: list[dict],
) -> str:
    docs_text = "\n\n".join([
        f"Candidate {i+1}:\n"
        f"  entity_name: {d['entity_name']}\n"
        f"  entity_type: {d['entity_type']}\n"
        f"  doc_type: {d.get('doc_type', 'responsibility')}\n"
        f"  route_mode: {d.get('route_mode', 'routing_candidate')}\n"
        f"  route_authority: {d.get('route_authority', 'authoritative')}\n"
        f"  retrieval_stage: {d.get('retrieval_stage', 'unknown')}\n"
        f"  retrieval_lane: {d.get('retrieval_lane', 'unknown')}\n"
        f"  stage_priority: {d.get('stage_priority', 'unknown')}\n"
        f"  stage1_dispatch_candidate: {d.get('stage1_dispatch_candidate', False)}\n"
        f"  source_reliability: {d.get('source_reliability', 'unknown')}\n"
        f"  responsibility_level: {d.get('responsibility_level', 'primary')}\n"
        f"  retrieval_weight: {d.get('retrieval_weight', 'unknown')}\n"
        f"  confidence_prior: {d.get('confidence_prior', 'unknown')}\n"
        f"  geographic_scope: {d.get('governorates') or 'nationwide'}\n"
        f"  districts: {', '.join(d.get('districts', [])[:8])}\n"
        f"  municipalities: {', '.join(d.get('municipalities', [])[:8])}\n"
        f"  handles: {', '.join(d.get('complaint_types', []))}\n"
        f"  keywords: {', '.join(d.get('keywords', [])[:12])}\n"
        f"  exact_match_terms: {', '.join(d.get('exact_match_terms', [])[:10])}\n"
        f"  negative_signals: {', '.join(d.get('negative_signals', [])[:10])}\n"
        f"  does NOT handle: {', '.join(d.get('not_responsible_for', []))}\n"
        f"  hitl_always_required: {d.get('hitl_always_required', False)}\n"
        f"  human_review_conditions: {', '.join(d.get('hitl_conditions', []))}\n"
        f"  source_ids: {', '.join(d.get('source_ids', [])[:6])}\n"
        f"  last_reviewed: {d.get('last_reviewed') or 'unknown'}\n"
        f"  description: {d['description']}"
        for i, d in enumerate(docs)
    ])

    location_str = " / ".join(
        p for p in [location_municipality, location_district, location_governorate, "Lebanon"]
        if p
    )

    return (
        f"Complaint type: {complaint_type}\n"
        f"Location: {location_str}\n"
        f"Keywords: {', '.join(keywords[:8]) if keywords else 'none'}\n"
        f"Complaint text: \"{original_text[:300]}\"\n\n"
        f"Retrieved routing candidates:\n{docs_text}\n\n"
        "Choose the correct entity from the candidates above."
    )


# ---------------------------------------------------------------------------
# Lazy-loaded embedding model + Qdrant client
# ---------------------------------------------------------------------------

_embed_model = None
_qdrant = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(EMBED_MODEL)
        log.info("[IEP-6] Embedding model loaded: %s", EMBED_MODEL)
    return _embed_model


def _get_qdrant():
    global _qdrant
    if _qdrant is None:
        _qdrant = create_qdrant_client()
        log.info("[IEP-6] Qdrant connected at %s", qdrant_target_label())
    return _qdrant


# ---------------------------------------------------------------------------
# RAG retrieval
# ---------------------------------------------------------------------------

def _build_query_text(
    complaint_type: str,
    category: str,
    subcategory: str,
    summary: str,
    location_municipality: Optional[str],
    location_district: Optional[str],
    location_governorate: Optional[str],
    location_mentions: Optional[List[str]],
    location_context: Optional[dict[str, set[str]]],
    keywords: List[str],
    signals: dict,
    routing_features: dict,
    evidence_text: List[str],
    evidence_image: List[str],
    alignment_features: dict,
    multimodal_alignment: dict,
    original_text: str,
) -> str:
    parts = [
        f"complaint type: {complaint_type}",
        f"category: {category}",
        f"subcategory: {subcategory}",
    ]
    if summary:
        parts.append(f"summary: {summary[:200]}")
    if location_municipality:
        parts.append(f"municipality: {location_municipality}")
    if location_district:
        parts.append(f"district: {location_district}")
    if location_governorate:
        parts.append(f"governorate: {location_governorate}")
    if location_mentions:
        parts.append(f"location_mentions: {', '.join(location_mentions[:8])}")
    if location_context:
        context_values = sorted(
            {
                value
                for values in location_context.values()
                for value in values
                if value
            }
        )
        if context_values:
            parts.append(f"location_context: {', '.join(context_values[:12])}")
    if keywords:
        parts.append(f"keywords: {', '.join(keywords[:6])}")
    if signals:
        parts.append(f"signals: {json.dumps(signals, ensure_ascii=True)}")
    if routing_features:
        parts.append(f"routing_features: {json.dumps(routing_features, ensure_ascii=True)}")
    if alignment_features:
        parts.append(f"alignment_features: {json.dumps(alignment_features, ensure_ascii=True)}")
    if evidence_text:
        parts.append(f"text_evidence: {', '.join(evidence_text[:6])}")
    if evidence_image:
        parts.append(f"image_evidence: {', '.join(evidence_image[:6])}")
    if multimodal_alignment:
        parts.append(f"multimodal_alignment: {json.dumps(multimodal_alignment, ensure_ascii=True)}")
    parts.append(f"complaint: {original_text[:200]}")
    return " | ".join(parts)


_AUTO_ROUTE_MODES = {
    "routing_candidate",
    "routing_rule",
    "geo_service_route",
    "complaint_intake_or_channel",
    "service_catalog",
    "shared_service_context",
}
_SUPPORT_ONLY_MODES = {
    "audit_context",
    "contact_context",
    "contact_fallback_only",
    "geo_service_area",
    "geo_union_context",
    "human_review_gate",
    "human_review_user_assist",
    "manual_review_only",
    "negative_boundary",
    "operator_context",
    "query_and_type_expansion",
    "resolution_context",
    "resolution_policy",
    "routing_guardrail",
    "supporting_context",
}
_BLOCKING_AUTHORITIES = {
    "blocker",
    "fallback_only_not_auto_route",
    "manual_review_gate",
    "staging_not_production",
    "supporting_audit",
    "validation_guardrail",
}
_ROUTE_MODE_BOOSTS = {
    "entity_legal_scope": 0.16,
    "geo_service_route": 0.16,
    "routing_rule": 0.14,
    "routing_candidate": 0.12,
    "complaint_intake_or_channel": 0.05,
    "service_catalog": 0.04,
    "contact_fallback_only": -0.18,
    "audit_context": -0.16,
    "query_and_type_expansion": -0.10,
    "resolution_context": -0.10,
    "resolution_policy": -0.10,
    "supporting_context": -0.08,
}

_STAGE_BOOSTS = {
    "stage1_dispatch": 0.22,
    "location_metadata": 0.18,
    "stage2_operations": 0.06,
    "stage3_evidence": -0.05,
}


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_+-]{3,}", value.lower()))


def _normalize_geo(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"\b(governorate|district|kadaa|qadaa|caza|municipality|city|area)\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _geo_variants(value: str | None) -> set[str]:
    normalized = _normalize_geo(value)
    if not normalized:
        return set()
    values = {normalized}
    values.update(token for token in normalized.split() if len(token) >= 3)
    return values


def _add_location_value(context: dict[str, set[str]], key: str, value: str | None) -> None:
    for variant in _geo_variants(value):
        context.setdefault(key, set()).add(variant)
        context.setdefault("all", set()).add(variant)


def _build_location_context(
    location_municipality: Optional[str],
    location_district: Optional[str],
    location_governorate: Optional[str],
    location_mentions: Optional[List[str]],
) -> dict[str, set[str]]:
    context: dict[str, set[str]] = {"municipalities": set(), "districts": set(), "governorates": set(), "all": set()}
    _add_location_value(context, "municipalities", location_municipality)
    _add_location_value(context, "districts", location_district)
    _add_location_value(context, "governorates", location_governorate)

    for mention in location_mentions or []:
        _add_location_value(context, "all", mention)
        resolved = lookup_text(str(mention))
        if resolved:
            _add_location_value(context, "municipalities", resolved.get("municipality") or resolved.get("name"))
            _add_location_value(context, "districts", resolved.get("district"))
            _add_location_value(context, "governorates", resolved.get("governorate"))
    return {key: values for key, values in context.items() if values}


def _doc_geo_terms(doc: dict, field: str) -> set[str]:
    terms: set[str] = set()
    for value in doc.get(field, []) or []:
        terms.update(_geo_variants(str(value)))
    return terms


def _doc_location_match_score(doc: dict, location_context: Optional[dict[str, set[str]]]) -> float:
    if not location_context:
        return 0.0

    score = 0.0
    municipality_overlap = location_context.get("municipalities", set()) & _doc_geo_terms(doc, "municipalities")
    district_overlap = location_context.get("districts", set()) & _doc_geo_terms(doc, "districts")
    governorate_overlap = location_context.get("governorates", set()) & _doc_geo_terms(doc, "governorates")

    if municipality_overlap:
        score += 0.22
    if district_overlap:
        score += 0.16
    if governorate_overlap:
        score += 0.08

    doc_has_geo = any(
        doc.get(field)
        for field in ("municipalities", "districts", "governorates")
    )
    if doc_has_geo and not (municipality_overlap or district_overlap or governorate_overlap):
        score -= 0.08
    return score


def _qdrant_geo_match_values(values: set[str], field: str) -> list[str]:
    candidates: set[str] = set()
    for value in values:
        if not value:
            continue
        title = value.title()
        candidates.add(title)
        if " " in title:
            candidates.add(title.replace(" ", "-"))
        if field == "governorates" and "governorate" not in value:
            candidates.add(f"{title} Governorate")
            if " " in title:
                candidates.add(f"{title.replace(' ', '-')} Governorate")
    return sorted(candidates)


def _doc_allows_auto_route(doc: dict) -> bool:
    route_mode = str(doc.get("route_mode") or "routing_candidate")
    authority = str(doc.get("route_authority") or "authoritative")
    retrieval_stage = str(doc.get("retrieval_stage") or "")
    if bool(doc.get("hitl_always_required")):
        return False
    if retrieval_stage == "stage3_evidence":
        return False
    if authority in _BLOCKING_AUTHORITIES or route_mode in _SUPPORT_ONLY_MODES:
        return False
    return route_mode in _AUTO_ROUTE_MODES or doc.get("responsibility_level") in {"primary", "secondary"}


def _rerank_docs(
    query_text: str,
    docs: list[dict],
    top_k: int,
    location_context: Optional[dict[str, set[str]]] = None,
) -> list[dict]:
    query_lower = query_text.lower()
    query_tokens = _tokens(query_text)
    ranked: list[dict] = []

    for doc in docs:
        route_mode = str(doc.get("route_mode") or "routing_candidate")
        retrieval_stage = str(doc.get("retrieval_stage") or doc.get("_retrieval_stage_source") or "stage3_evidence")
        stage_priority = int(doc.get("stage_priority") or 4)
        weight = float(doc.get("retrieval_weight") or 1.0)
        base_score = float(doc.get("_rag_score") or 0.0)
        score = base_score * max(0.1, min(weight, 2.0))
        score += _ROUTE_MODE_BOOSTS.get(route_mode, 0.0)
        score += _STAGE_BOOSTS.get(retrieval_stage, 0.0)
        score += max(-0.04, min(0.10, (4 - stage_priority) * 0.025))

        exact_matches = 0
        for term in doc.get("exact_match_terms", [])[:20]:
            term_text = str(term).lower().strip()
            if len(term_text) >= 3 and term_text in query_lower:
                exact_matches += 1
        score += min(0.25, exact_matches * 0.05)

        keyword_tokens = _tokens(" ".join(str(k) for k in doc.get("keywords", [])[:30]))
        if keyword_tokens:
            overlap = len(query_tokens & keyword_tokens)
            score += min(0.18, overlap * 0.015)

        if not _doc_allows_auto_route(doc):
            score -= 0.12
        if doc.get("responsibility_level") == "primary":
            score += 0.04
        elif doc.get("responsibility_level") == "secondary":
            score += 0.015

        score += _doc_location_match_score(doc, location_context)

        enriched = dict(doc)
        enriched["_rerank_score"] = round(score, 6)
        ranked.append(enriched)

    ranked.sort(key=lambda d: (float(d.get("_rerank_score") or 0.0), float(d.get("_rag_score") or 0.0)), reverse=True)
    return ranked[:top_k]


def _collect_qdrant_results(results: list, docs_by_id: dict[str, dict], stage: str) -> None:
    for r in results:
        payload = dict(r.payload or {})
        doc_id = str(payload.get("doc_id") or "").strip()
        if not doc_id:
            continue
        score = float(getattr(r, "score", 0.0) or 0.0)
        payload["_rag_score"] = score
        payload.setdefault("retrieval_stage", stage)
        payload["_retrieval_stage_source"] = stage
        current = docs_by_id.get(doc_id)
        if current is None or float(current.get("_rag_score") or 0.0) < score:
            docs_by_id[doc_id] = payload


def _qdrant_vector_search(
    qdrant,
    *,
    collection_name: str,
    query_vector: list[float],
    limit: int,
    with_payload: bool = True,
    query_filter=None,
) -> list:
    if hasattr(qdrant, "search"):
        return qdrant.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            with_payload=with_payload,
            query_filter=query_filter,
        )

    response = qdrant.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=limit,
        with_payload=with_payload,
        query_filter=query_filter,
    )
    return list(getattr(response, "points", response) or [])


def _search_stage(
    *,
    qdrant,
    qmodels,
    query_vec: list[float],
    stage: str,
    limit: int,
) -> list:
    stage_filter = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="retrieval_stage",
                match=qmodels.MatchValue(value=stage),
            )
        ]
    )
    return _qdrant_vector_search(
        qdrant,
        collection_name=RAG_COLLECTION,
        query_vector=query_vec,
        limit=max(1, limit),
        with_payload=True,
        query_filter=stage_filter,
    )


def _search_location_metadata(
    *,
    qdrant,
    qmodels,
    query_vec: list[float],
    location_context: Optional[dict[str, set[str]]],
    limit: int,
) -> list:
    if not location_context:
        return []

    results: list = []
    for field in ("municipalities", "districts", "governorates"):
        match_values = _qdrant_geo_match_values(location_context.get(field, set()), field)
        for value in match_values[:8]:
            geo_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key=field,
                        match=qmodels.MatchValue(value=value),
                    )
                ]
            )
            results.extend(
                _qdrant_vector_search(
                    qdrant,
                    collection_name=RAG_COLLECTION,
                    query_vector=query_vec,
                    limit=max(1, limit),
                    with_payload=True,
                    query_filter=geo_filter,
                )
            )
    return results


def _retrieve_docs(
    query_text: str,
    top_k: int = 5,
    location_context: Optional[dict[str, set[str]]] = None,
) -> list[dict]:
    start = time.time()
    try:
        model = _get_embed_model()
        qdrant = _get_qdrant()
        from qdrant_client import models as qmodels
        query_vec = model.encode(query_text, normalize_embeddings=True).tolist()

        expanded_limit = max(top_k * 3, top_k)
        docs_by_id: dict[str, dict] = {}

        if RAG_STAGE_PRIORITY_ENABLED:
            stage_plan = [
                ("stage1_dispatch", max(top_k, RAG_STAGE1_TARGET)),
                ("stage2_operations", max(top_k, RAG_STAGE2_TARGET)),
                ("stage3_evidence", max(top_k, RAG_STAGE3_TARGET)),
            ]
            for stage, stage_limit in stage_plan:
                stage_results = _search_stage(
                    qdrant=qdrant,
                    qmodels=qmodels,
                    query_vec=query_vec,
                    stage=stage,
                    limit=stage_limit,
                )
                _collect_qdrant_results(stage_results, docs_by_id, stage)

        if location_context:
            location_results = _search_location_metadata(
                qdrant=qdrant,
                qmodels=qmodels,
                query_vec=query_vec,
                location_context=location_context,
                limit=max(top_k, RAG_STAGE1_TARGET),
            )
            _collect_qdrant_results(location_results, docs_by_id, "location_metadata")

        # Fallback/augmentation path keeps backward compatibility and recall.
        if len(docs_by_id) < expanded_limit:
            fallback_results = _qdrant_vector_search(
                qdrant,
                collection_name=RAG_COLLECTION,
                query_vector=query_vec,
                limit=expanded_limit,
                with_payload=True,
            )
            _collect_qdrant_results(fallback_results, docs_by_id, "unfiltered")

        docs = list(docs_by_id.values())
        docs = _rerank_docs(query_text, docs, top_k=top_k, location_context=location_context)
        top_score = max((float(d.get("_rag_score") or 0.0) for d in docs), default=0.0)
        RAG_CANDIDATE_COUNT.observe(len(docs))
        if docs:
            RAG_TOP_SCORE.observe(top_score)
        RAG_RETRIEVAL_DURATION.labels(status="success").observe(time.time() - start)
        return docs
    except Exception as e:
        RAG_CANDIDATE_COUNT.observe(0)
        RAG_RETRIEVAL_ERRORS_TOTAL.labels(error_type=_error_type(e)).inc()
        RAG_RETRIEVAL_DURATION.labels(status="error").observe(time.time() - start)
        log.warning("[IEP-6] RAG retrieval failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

async def _call_llm_routing(prompt: str) -> Optional[dict]:
    if not QWEN_ENABLED or not QWEN_BASE_URL:
        return None
    try:
        import openai
        client = openai.AsyncOpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
            max_retries=0,
            timeout=QWEN_ROUTING_TIMEOUT,
        )
        resp = await client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": _ROUTING_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=QWEN_ROUTING_MAX_TOKENS,
        )
        raw = resp.choices[0].message.content
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(raw[start:end])
    except Exception as e:
        log.warning("[IEP-6] LLM routing call failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Static fallback helper
# ---------------------------------------------------------------------------

def _static_route(
    complaint_type: str,
    location_district: Optional[str],
    location_mentions: List[str],
    location_municipality: Optional[str],
    location_governorate: Optional[str],
) -> tuple[RoutingEntity, Optional[RoutingEntity], float, list[str]]:
    """Returns (primary, secondary, confidence, rationale_tags)."""
    rationale: list[str] = []
    ct = complaint_type or "other"
    primary, secondary, base_conf = TYPE_TO_ENTITY.get(ct, TYPE_TO_ENTITY["other"])
    rationale.append(f"type '{ct}' → {primary.value}")

    # Water: pick correct establishment by governorate
    if ct == "water_pipe" and location_governorate:
        water_entity = WATER_BY_GOVERNORATE.get(location_governorate)
        if water_entity:
            primary = water_entity
            rationale.append(f"water authority for {location_governorate}")

    # Municipality override for non-Beirut areas
    mentions = [location_municipality or "", location_district or ""] + list(location_mentions)
    for mention in mentions:
        if mention and mention in MUNICIPALITY_ENTITY_MAP:
            override = MUNICIPALITY_ENTITY_MAP[mention]
            if primary == RoutingEntity.BEIRUT_MUNICIPALITY and override != RoutingEntity.BEIRUT_MUNICIPALITY:
                primary = override
                base_conf *= 0.95
                rationale.append(f"location '{mention}' → {override.value}")
            break

    return primary, secondary, round(base_conf, 3), rationale


# ---------------------------------------------------------------------------
# Entity name → RoutingEntity resolver
# ---------------------------------------------------------------------------

_NAME_TO_ENTITY: dict[str, RoutingEntity] = {e.value: e for e in RoutingEntity}

# Also accept short aliases from seed docs
_NAME_TO_ENTITY.update({
    "beirut municipality":             RoutingEntity.BEIRUT_MUNICIPALITY,
    "ministry of public works":        RoutingEntity.MINISTRY_PUBLIC_WORKS,
    "ministry of public works and transport": RoutingEntity.MINISTRY_PUBLIC_WORKS,
    "electricite du liban":            RoutingEntity.EDL,
    "electricite de liban":            RoutingEntity.EDL,
    "electricité du liban":            RoutingEntity.EDL,
    "edl":                             RoutingEntity.EDL,
    "electricite de zahle":            RoutingEntity.EDZ,
    "electricité de zahle":            RoutingEntity.EDZ,
    "edz":                             RoutingEntity.EDZ,
    "ogero":                           RoutingEntity.OGERO,
    "ogero telecom":                   RoutingEntity.OGERO,
    "internal security forces":        RoutingEntity.INTERNAL_SECURITY,
    "isf":                             RoutingEntity.INTERNAL_SECURITY,
    "lebanese civil defense":          RoutingEntity.CIVIL_DEFENSE,
    "civil defense":                   RoutingEntity.CIVIL_DEFENSE,
    "cd":                              RoutingEntity.CIVIL_DEFENSE,
    "ministry of environment":         RoutingEntity.MINISTRY_ENVIRONMENT,
    "ministry of energy and water":    RoutingEntity.MINISTRY_ENERGY_WATER,
    "ministry of interior and municipalities": RoutingEntity.MINISTRY_INTERIOR_MUNICIPALITIES,
    "beirut water authority":          RoutingEntity.WATER_AUTHORITY,
    "beirut and mount lebanon water establishment": RoutingEntity.WATER_AUTHORITY,
    "beirut and mount lebanon water establishment - ebml": RoutingEntity.WATER_AUTHORITY,
    "bmlwe":                           RoutingEntity.WATER_AUTHORITY,
    "ebml":                            RoutingEntity.WATER_AUTHORITY,
    "north lebanon water establishment": RoutingEntity.WATER_NORTH,
    "nlwe":                            RoutingEntity.WATER_NORTH,
    "south lebanon water establishment": RoutingEntity.WATER_SOUTH,
    "slwe":                            RoutingEntity.WATER_SOUTH,
    "bekaa water establishment":       RoutingEntity.WATER_BEKAA,
    "bwe":                             RoutingEntity.WATER_BEKAA,
    "council for development and reconstruction": RoutingEntity.CDR,
    "cdr":                             RoutingEntity.CDR,
    "central inspection":              RoutingEntity.CENTRAL_INSPECTION,
    "general directorate of local administrations and councils": RoutingEntity.DGLAC,
    "telecommunications regulatory authority": RoutingEntity.TRA,
    "tra":                             RoutingEntity.TRA,
    "mobile network operators":        RoutingEntity.MOBILE_OPERATOR,
    "mobile operators":                RoutingEntity.MOBILE_OPERATOR,
    "litani river authority":          RoutingEntity.LRA,
    "lra":                             RoutingEntity.LRA,
    "municipal police":                RoutingEntity.MUNICIPAL_POLICE,
    "municipal enforcement units":     RoutingEntity.MUNICIPAL_POLICE,
    "local municipality":              RoutingEntity.GENERIC_MUNICIPALITY,
    "lebanese municipalities":         RoutingEntity.GENERIC_MUNICIPALITY,
    "human review queue":              RoutingEntity.HUMAN_REVIEW,
})


def _resolve_entity(name: Optional[str]) -> Optional[RoutingEntity]:
    if not name:
        return None
    raw = str(name).strip()
    without_parens = re.sub(r"\([^)]*\)", "", raw)
    without_suffix = re.sub(r"\s+-\s+[A-Za-z0-9]+$", "", without_parens).strip()
    normalized = unicodedata.normalize("NFKD", without_suffix)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"\s+", " ", normalized).lower().strip()
    return (
        _NAME_TO_ENTITY.get(raw)
        or _NAME_TO_ENTITY.get(raw.lower())
        or _NAME_TO_ENTITY.get(without_suffix.lower())
        or _NAME_TO_ENTITY.get(normalized)
    )


def _error_type(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timeout" in text:
        return "timeout"
    if "connection" in name or "connect" in text:
        return "connection"
    if "not found" in text or "missing" in text:
        return "missing_collection"
    return name or "unknown"


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _rag_confidence(doc: dict) -> float:
    semantic_score = _clamp(float(doc.get("_rag_score") or 0.0))
    confidence_prior = _clamp(float(doc.get("confidence_prior") or 0.7))
    stage_bonus = 0.08 if doc.get("retrieval_stage") == "stage1_dispatch" else 0.03
    level_bonus = 0.05 if doc.get("responsibility_level") == "primary" else 0.02
    route_bonus = 0.04 if str(doc.get("route_mode") or "") in _AUTO_ROUTE_MODES else 0.0
    confidence = (semantic_score * 0.62) + (confidence_prior * 0.24) + stage_bonus + level_bonus + route_bonus
    return round(_clamp(confidence, 0.35, 0.97), 3)


def _candidate_summary(doc: dict) -> dict:
    return {
        "doc_id": doc.get("doc_id"),
        "entity_name": doc.get("entity_name"),
        "entity_enum": doc.get("entity_enum"),
        "doc_type": doc.get("doc_type"),
        "route_mode": doc.get("route_mode"),
        "route_authority": doc.get("route_authority"),
        "responsibility_level": doc.get("responsibility_level"),
        "retrieval_stage": doc.get("retrieval_stage"),
        "rag_score": round(float(doc.get("_rag_score") or 0.0), 4),
        "rerank_score": round(float(doc.get("_rerank_score") or 0.0), 4),
        "allows_auto_route": _doc_allows_auto_route(doc),
    }


def _select_secondary_entity(primary: RoutingEntity, docs: list[dict]) -> Optional[RoutingEntity]:
    for doc in docs:
        entity = _resolve_entity(doc.get("entity_enum") or doc.get("entity_name"))
        if entity and entity != primary and _doc_allows_auto_route(doc):
            return entity
    return None


def _review_result(
    *,
    complaint_id: str,
    routing_source: str,
    review_reason: str,
    retrieved_sources: list[str] | None = None,
    retrieved_candidates: list[dict] | None = None,
    rag_no_candidates: bool = False,
    rationale: list[str] | None = None,
) -> RoutingResult:
    return RoutingResult(
        complaint_id=complaint_id,
        primary_entity=RoutingEntity.HUMAN_REVIEW,
        primary_confidence=0.0,
        secondary_entity=None,
        secondary_confidence=0.0,
        routing_rationale=rationale or [review_reason],
        retrieved_sources=retrieved_sources or [],
        retrieved_candidates=retrieved_candidates or [],
        routing_source=routing_source,
        auto_routed=False,
        requires_review=True,
        review_reason=review_reason,
        rag_no_candidates=rag_no_candidates,
        processing_ms=0,
    )


# ---------------------------------------------------------------------------
# Main Router class
# ---------------------------------------------------------------------------

class ComplaintRouter:

    def __init__(self, auto_threshold: float, review_threshold: float):
        self.auto_threshold = auto_threshold
        self.review_threshold = review_threshold

    async def route_async(
        self,
        complaint_id: str,
        complaint_type: Optional[str],
        category: str,
        subcategory: str,
        summary: str,
        severity: Optional[str],
        original_text: str,
        location_district: Optional[str],
        location_municipality: Optional[str],
        location_governorate: Optional[str],
        location_mentions: List[str],
        keywords: List[str],
        signals: dict,
        routing_features: dict,
        evidence_text: List[str],
        evidence_image: List[str],
        alignment_features: dict,
        multimodal_alignment: dict,
    ) -> RoutingResult:
        ct = complaint_type or "other"

        if not RAG_ENABLED:
            if STATIC_FALLBACK_ENABLED:
                static_primary, static_secondary, static_conf, static_rationale = _static_route(
                    ct, location_district, location_mentions, location_municipality, location_governorate
                )
                requires_review = static_conf < self.review_threshold
                return RoutingResult(
                    complaint_id=complaint_id,
                    primary_entity=static_primary,
                    primary_confidence=round(static_conf, 3),
                    secondary_entity=static_secondary,
                    secondary_confidence=round(static_conf * 0.55, 3) if static_secondary else 0.0,
                    routing_rationale=static_rationale,
                    retrieved_sources=[],
                    retrieved_candidates=[],
                    routing_source="static_fallback",
                    auto_routed=static_conf >= self.auto_threshold and not requires_review,
                    requires_review=requires_review,
                    review_reason="Low routing confidence" if requires_review else None,
                    processing_ms=0,
                )
            return _review_result(
                complaint_id=complaint_id,
                routing_source="rag_disabled",
                review_reason="RAG routing is disabled. Dynamic Qdrant routing is required for auto-routing.",
            )

        location_context = _build_location_context(
            location_municipality,
            location_district,
            location_governorate,
            location_mentions,
        )

        query_text = _build_query_text(
            ct,
            category,
            subcategory,
            summary,
            location_municipality,
            location_district,
            location_governorate,
            location_mentions,
            location_context,
            keywords,
            signals,
            routing_features,
            evidence_text,
            evidence_image,
            alignment_features,
            multimodal_alignment,
            original_text,
        )
        docs = _retrieve_docs(query_text, top_k=RAG_TOP_K, location_context=location_context)
        retrieved_sources = [d.get("doc_id", "") for d in docs]
        retrieved_candidates = [_candidate_summary(d) for d in docs]

        if not docs:
            return _review_result(
                complaint_id=complaint_id,
                routing_source="rag_no_match",
                review_reason=(
                    "Qdrant returned zero routing candidates for this complaint. "
                    "Human review is required; no static route was used."
                ),
                rag_no_candidates=True,
            )

        allowed_docs = [d for d in docs if _doc_allows_auto_route(d)]
        if not allowed_docs:
            return _review_result(
                complaint_id=complaint_id,
                routing_source="rag_support_only",
                review_reason=(
                    "Qdrant retrieved only support-only, fallback, audit, or manual-review "
                    "documents. No production routing authority was found."
                ),
                retrieved_sources=retrieved_sources,
                retrieved_candidates=retrieved_candidates,
                rationale=["Retrieved RAG docs were context only and were not allowed to auto-route."],
            )

        top_doc = allowed_docs[0]
        top_entity = _resolve_entity(top_doc.get("entity_enum") or top_doc.get("entity_name"))
        if not top_entity:
            return _review_result(
                complaint_id=complaint_id,
                routing_source="rag_unresolved_entity",
                review_reason=(
                    f"Top Qdrant candidate '{top_doc.get('entity_name')}' could not be mapped "
                    "to a RoutingEntity enum."
                ),
                retrieved_sources=retrieved_sources,
                retrieved_candidates=retrieved_candidates,
            )

        final_primary = top_entity
        final_secondary = _select_secondary_entity(final_primary, allowed_docs[1:])
        final_conf = _rag_confidence(top_doc)
        routing_source = "rag_retrieval"
        rationale = [
            (
                f"Qdrant top routing authority {top_doc.get('doc_id')} selected "
                f"{top_doc.get('entity_name')} via {top_doc.get('route_mode')} "
                f"({top_doc.get('retrieval_stage')}, score={float(top_doc.get('_rag_score') or 0.0):.3f})."
            )
        ]
        requires_review = final_conf < self.review_threshold
        review_reason: Optional[str] = "Low RAG routing confidence" if requires_review else None

        prompt = _build_routing_prompt(
            ct, original_text,
            location_district, location_governorate, location_municipality,
            keywords, allowed_docs,
        )
        llm_data = await _call_llm_routing(prompt)
        if llm_data:
            llm_entity = _resolve_entity(llm_data.get("primary_entity"))
            llm_secondary = _resolve_entity(llm_data.get("secondary_entity"))
            if llm_entity:
                final_primary = llm_entity
                final_secondary = llm_secondary or _select_secondary_entity(final_primary, allowed_docs)
                final_conf = _clamp(float(llm_data.get("confidence", 0.0)))
                routing_source = "rag_llm"
                rationale = [llm_data.get("rationale") or "Qwen selected from Qdrant-retrieved candidates."]
                requires_review = bool(llm_data.get("requires_human_review", False)) or final_conf < self.review_threshold
                review_reason = llm_data.get("review_reason") or (
                    "Low RAG LLM routing confidence" if final_conf < self.review_threshold else None
                )
            else:
                log.warning("[IEP-6] LLM returned unresolvable entity: %s", llm_data.get("primary_entity"))

        auto_routed = final_conf >= self.auto_threshold and not requires_review

        return RoutingResult(
            complaint_id=complaint_id,
            primary_entity=final_primary,
            primary_confidence=round(final_conf, 3),
            secondary_entity=final_secondary,
            secondary_confidence=round(final_conf * 0.55, 3) if final_secondary else 0.0,
            routing_rationale=rationale,
            retrieved_sources=retrieved_sources,
            retrieved_candidates=retrieved_candidates,
            routing_source=routing_source,
            auto_routed=auto_routed,
            requires_review=requires_review,
            review_reason=review_reason,
            rag_no_candidates=False,
            processing_ms=0,
        )

    # Sync shim kept for backward compatibility with existing tests
    def route(
        self,
        complaint_id: str,
        complaint_type: Optional[str],
        severity: Optional[str],
        location_district: Optional[str],
        location_mentions: List[str],
        keywords: List[str],
    ) -> RoutingResult:
        """Synchronous static-only path (used when async context not available)."""
        ct = complaint_type or "other"
        static_primary, static_secondary, static_conf, static_rationale = _static_route(
            ct, location_district, location_mentions, None, None
        )
        requires_review = static_conf < self.review_threshold
        auto_routed = static_conf >= self.auto_threshold
        if requires_review:
            static_primary = RoutingEntity.HUMAN_REVIEW
        return RoutingResult(
            complaint_id=complaint_id,
            primary_entity=static_primary,
            primary_confidence=round(static_conf, 3),
            secondary_entity=static_secondary,
            secondary_confidence=round(static_conf * 0.55, 3) if static_secondary else 0.0,
            routing_rationale=static_rationale,
            retrieved_sources=[],
            routing_source="static_fallback",
            auto_routed=auto_routed,
            requires_review=requires_review,
            review_reason="Low routing confidence" if requires_review else None,
            processing_ms=0,
        )


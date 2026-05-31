"""
IEP-6 Routing Engine — RAG + Static Fallback
=============================================

Flow:
  1. Build semantic query from complaint fields.
  2. Retrieve top-K routing documents from Qdrant "routing_knowledge" collection.
  3. Pass retrieved docs + complaint to Qwen LLM → JSON routing decision.
  4. Compare LLM result with static fallback table:
       LLM alone (high confidence)           → routing_source = "rag"
       LLM + static agree                    → routing_source = "rag_static_agree"
       LLM + static disagree, LLM conf high  → routing_source = "rag"
       LLM + static disagree, LLM conf low   → routing_source = "rag_static_conflict" + human review
       LLM failed                            → routing_source = "static_fallback"
  5. Location-based municipality override (non-Beirut complaints).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Optional, List

import httpx
from cedarfix_shared.schemas import RoutingResult, RoutingEntity
from cedarfix_shared.location import haversine_km

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "")
QWEN_MODEL: str = os.getenv("QWEN_MODEL", "Qwen/Qwen2.5-3B-Instruct")
QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "none")
QWEN_ENABLED: bool = os.getenv("QWEN_ENABLED", "true").lower() == "true"

RAG_ENABLED: bool = os.getenv("ROUTING_RAG_ENABLED", "true").lower() == "true"
RAG_TOP_K: int = int(os.getenv("ROUTING_RAG_TOP_K", "5"))
QDRANT_HOST: str = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
RAG_COLLECTION: str = os.getenv("ROUTING_QDRANT_COLLECTION", "routing_knowledge")
EMBED_MODEL: str = os.getenv(
    "MODEL_NAME",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
)

# ---------------------------------------------------------------------------
# Static fallback table (always available, used when RAG/LLM fail)
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
- If the location is outside Beirut, prefer the correct regional entity over Beirut Municipality.
- Telecom issues (internet/wifi/DSL) → Ogero. Electricity issues → EDL.
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
        f"  geographic_scope: {d.get('governorates') or 'nationwide'}\n"
        f"  handles: {', '.join(d.get('complaint_types', []))}\n"
        f"  does NOT handle: {', '.join(d.get('not_responsible_for', []))}\n"
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
        from qdrant_client import QdrantClient
        _qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        log.info("[IEP-6] Qdrant connected at %s:%s", QDRANT_HOST, QDRANT_PORT)
    return _qdrant


# ---------------------------------------------------------------------------
# RAG retrieval
# ---------------------------------------------------------------------------

def _build_query_text(
    complaint_type: str,
    category: str,
    location_municipality: Optional[str],
    location_district: Optional[str],
    location_governorate: Optional[str],
    keywords: List[str],
    original_text: str,
) -> str:
    parts = [
        f"complaint type: {complaint_type}",
        f"category: {category}",
    ]
    if location_municipality:
        parts.append(f"municipality: {location_municipality}")
    if location_district:
        parts.append(f"district: {location_district}")
    if location_governorate:
        parts.append(f"governorate: {location_governorate}")
    if keywords:
        parts.append(f"keywords: {', '.join(keywords[:6])}")
    parts.append(f"complaint: {original_text[:200]}")
    return " | ".join(parts)


def _retrieve_docs(query_text: str, top_k: int = 5) -> list[dict]:
    try:
        model = _get_embed_model()
        qdrant = _get_qdrant()
        from qdrant_client import models as qmodels
        query_vec = model.encode(query_text, normalize_embeddings=True).tolist()
        results = qdrant.search(
            collection_name=RAG_COLLECTION,
            query_vector=query_vec,
            limit=top_k,
            with_payload=True,
        )
        return [r.payload for r in results]
    except Exception as e:
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
            timeout=20.0,
        )
        resp = await client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": _ROUTING_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
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
    "edl":                             RoutingEntity.EDL,
    "ogero":                           RoutingEntity.OGERO,
    "internal security forces":        RoutingEntity.INTERNAL_SECURITY,
    "isf":                             RoutingEntity.INTERNAL_SECURITY,
    "ministry of environment":         RoutingEntity.MINISTRY_ENVIRONMENT,
    "beirut water authority":          RoutingEntity.WATER_AUTHORITY,
    "north lebanon water establishment": RoutingEntity.WATER_NORTH,
    "south lebanon water establishment": RoutingEntity.WATER_SOUTH,
    "bekaa water establishment":       RoutingEntity.WATER_BEKAA,
    "council for development and reconstruction": RoutingEntity.CDR,
    "local municipality":              RoutingEntity.GENERIC_MUNICIPALITY,
    "human review queue":              RoutingEntity.HUMAN_REVIEW,
})


def _resolve_entity(name: Optional[str]) -> Optional[RoutingEntity]:
    if not name:
        return None
    return _NAME_TO_ENTITY.get(name.lower().strip()) or _NAME_TO_ENTITY.get(name.strip())


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
        severity: Optional[str],
        original_text: str,
        location_district: Optional[str],
        location_municipality: Optional[str],
        location_governorate: Optional[str],
        location_mentions: List[str],
        keywords: List[str],
    ) -> RoutingResult:
        ct = complaint_type or "other"

        # ── Static fallback (always computed first as baseline) ──────────────
        static_primary, static_secondary, static_conf, static_rationale = _static_route(
            ct, location_district, location_mentions, location_municipality, location_governorate
        )

        routing_source = "static_fallback"
        retrieved_sources: list[str] = []
        llm_data: Optional[dict] = None
        final_primary = static_primary
        final_secondary = static_secondary
        final_conf = static_conf
        rationale = list(static_rationale)
        requires_review = final_conf < self.review_threshold
        review_reason: Optional[str] = None
        rag_no_candidates = False

        # ── RAG path ─────────────────────────────────────────────────────────
        if RAG_ENABLED:
            query_text = _build_query_text(
                ct, category, location_municipality, location_district,
                location_governorate, keywords, original_text,
            )
            docs = _retrieve_docs(query_text, top_k=RAG_TOP_K)

            if not docs:
                # RAG has no knowledge of this complaint type / location combination.
                # Flag for human review so the admin can (a) confirm unsupported type
                # or (b) correct and add a gold label to the retraining store.
                rag_no_candidates = True
                requires_review = True
                routing_source = "rag_no_match"
                review_reason = (
                    "RAG returned zero routing candidates for this complaint. "
                    "The complaint type or location may not be in the current "
                    "routing knowledge base. Human review required."
                )

            if docs:
                retrieved_sources = [d.get("doc_id", "") for d in docs]
                prompt = _build_routing_prompt(
                    ct, original_text,
                    location_district, location_governorate, location_municipality,
                    keywords, docs,
                )
                llm_data = await _call_llm_routing(prompt)

            if llm_data:
                llm_entity = _resolve_entity(llm_data.get("primary_entity"))
                llm_secondary = _resolve_entity(llm_data.get("secondary_entity"))
                llm_conf = float(llm_data.get("confidence", 0.0))
                llm_rationale = llm_data.get("rationale", "")
                llm_review = bool(llm_data.get("requires_human_review", False))
                llm_review_reason = llm_data.get("review_reason")

                if llm_entity:
                    # Determine agreement with static fallback
                    agrees = (llm_entity == static_primary)

                    if llm_conf >= self.auto_threshold:
                        # High-confidence LLM — trust it directly
                        routing_source = "rag_static_agree" if agrees else "rag"
                        final_primary = llm_entity
                        final_secondary = llm_secondary or static_secondary
                        final_conf = min(llm_conf + 0.05, 0.97) if agrees else llm_conf
                        rationale = [llm_rationale]
                        requires_review = llm_review
                        review_reason = llm_review_reason

                    elif llm_conf >= self.review_threshold:
                        if agrees:
                            # Both agree, moderate confidence → slight boost
                            routing_source = "rag_static_agree"
                            final_primary = llm_entity
                            final_secondary = llm_secondary or static_secondary
                            final_conf = min(llm_conf + 0.08, 0.90)
                            rationale = [llm_rationale]
                            requires_review = False
                        else:
                            # Disagreement at moderate confidence → human review
                            routing_source = "rag_static_conflict"
                            final_primary = RoutingEntity.HUMAN_REVIEW
                            final_conf = llm_conf
                            requires_review = True
                            review_reason = (
                                f"RAG suggests '{llm_entity.value}' "
                                f"but static rule suggests '{static_primary.value}'"
                            )
                            rationale = [
                                f"RAG: {llm_rationale}",
                                f"Static: {'; '.join(static_rationale)}",
                            ]
                    else:
                        # Low LLM confidence — fall back to static
                        routing_source = "static_fallback"
                        log.info(
                            "[IEP-6] LLM confidence %.2f too low — using static fallback", llm_conf
                        )
                else:
                    log.warning("[IEP-6] LLM returned unresolvable entity: %s", llm_data.get("primary_entity"))

        # ── Final review check ────────────────────────────────────────────────
        if final_conf < self.review_threshold and not requires_review:
            requires_review = True
            review_reason = review_reason or "Low routing confidence"

        if requires_review and final_primary != RoutingEntity.HUMAN_REVIEW:
            # Keep the entity but also flag for review (don't always override to HUMAN_REVIEW)
            pass

        auto_routed = final_conf >= self.auto_threshold and not requires_review

        return RoutingResult(
            complaint_id=complaint_id,
            primary_entity=final_primary,
            primary_confidence=round(final_conf, 3),
            secondary_entity=final_secondary,
            secondary_confidence=round(final_conf * 0.55, 3) if final_secondary else 0.0,
            routing_rationale=rationale,
            retrieved_sources=retrieved_sources,
            routing_source=routing_source,
            auto_routed=auto_routed,
            requires_review=requires_review,
            review_reason=review_reason,
            rag_no_candidates=rag_no_candidates,
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


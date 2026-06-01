"""IEP-4 explanation generator.

Produces bilingual (Arabic-Levantine / English) citizen and admin
explanations for every routed complaint.

In the current v0.1 implementation the explanations are rule-generated
from the routing decision — no LLM API call is made.  This keeps the
service deployable without an API key and establishes the schema contract
for future LLM-backed versions.

The citizen explanation is a short (1–2 sentence) Arabizi/Arabic-Levantine
summary for the submitter.
The admin explanation is a structured English paragraph for the municipal
reviewer.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_CITIZEN_PROMPT = ROOT / "prompts" / "iep4_citizen_v1.0.txt"
_ADMIN_PROMPT = ROOT / "prompts" / "iep4_admin_v1.0.txt"
_AUDIT_PROMPT = ROOT / "prompts" / "iep4_audit_v1.0.txt"
_ENTITY_DIR = ROOT / "data" / "knowledge_base" / "entities"

_ENTITY_DISPLAY_NAMES: dict[str, str] = {
    "MUN": "the responsible local authority",
    "MPWT": "the road authority",
    "CDR": "the public works project team",
    "BMLWE": "the regional water establishment",
    "NLWE": "the regional water establishment",
    "SLWE": "the regional water establishment",
    "BWE": "the regional water establishment",
    "EDL": "the electricity utility team",
    "EDZ": "the local electricity concession team",
    "OGERO": "the fixed-line and internet service team",
    "TRA": "the telecom regulator review team",
    "CD": "the emergency response team",
    "ISF": "the public safety review team",
    "MOE": "the environmental review team",
    "CENTRAL_INSPECTION": "the public administration review team",
    "HITL": "a human reviewer",
}


def _entity_display_name(entity: str | None) -> str:
    value = (entity or "HITL").upper()
    if value.startswith("MUN-"):
        return "the responsible municipality"
    return _ENTITY_DISPLAY_NAMES.get(value, "the responsible public authority")


@lru_cache(maxsize=64)
def _load_entity_file(entity: str) -> dict:
    key = (entity or "HITL").upper()
    if key.startswith("MUN-"):
        key = "MUN"
    path = _ENTITY_DIR / f"{key}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _grounding_evidence(entity: str | None, sector: str, hitl_required: bool) -> dict:
    """Retrieve compact KB fact IDs and source IDs for explanation grounding."""
    data = _load_entity_file(entity or "HITL")
    facts = list(data.get("facts") or [])
    wanted = ["legal_responsibility", "service_area", "complaint_process"]
    if hitl_required:
        wanted.append("deadline_or_sla")

    selected: list[dict] = []
    for fact_type in wanted:
        for fact in facts:
            if fact.get("fact_type") == fact_type:
                selected.append(fact)
                break
    if not selected and facts:
        selected = facts[:2]

    fact_ids = [str(item.get("fact_id")) for item in selected if item.get("fact_id")]
    source_ids = sorted(
        {
            str(source_id)
            for item in selected
            for source_id in (item.get("source_ids") or [])
            if source_id
        }
    )
    snippets = []
    for item in selected[:3]:
        value = str(item.get("value") or "")
        if value:
            snippets.append(value[:180])
    return {
        "entity_id": data.get("entity_id") or entity or "HITL",
        "entity_name": data.get("entity_name"),
        "fact_ids": fact_ids,
        "source_ids": source_ids[:8],
        "snippets": snippets,
        "sector": sector,
        "grounded": bool(fact_ids),
    }


def _gps_text(gps_lat: float | None, gps_lon: float | None) -> str:
    if gps_lat is not None and gps_lon is not None:
        return f"({gps_lat:.5f}, {gps_lon:.5f})"
    return "not provided"


def _next_action(sector: str, entity: str, hitl_required: bool) -> str:
    if hitl_required:
        return "Human reviewer should verify the boundary condition, missing details, and safe dispatch path before escalation."
    if sector == "ROADS":
        return "Confirm whether the asset is local, national, or project-owned before dispatch."
    if sector == "WATER":
        return "Confirm municipality/service area and ask for account or landmark details if needed."
    if sector == "ELECTRICITY":
        return "Check grid vs generator vs EDZ/EDL responsibility before field routing."
    if sector == "TELECOM":
        return "Confirm fixed-line/internet vs mobile/regulatory scope before dispatch."
    if sector == "SAFETY":
        return "Keep emergency handling manual and prioritize official safety channels."
    if sector == "OTHER":
        return "Human reviewer should classify the sector before routing."
    return f"Forward to {entity} with the evidence packet and request confirmation of ownership."


def _citizen_message(
    language: str | None,
    sector: str,
    destination: str,
    hitl_required: bool,
    missing_location: bool,
) -> str:
    lang = (language or "arabizi").lower()
    if lang == "en":
        if hitl_required:
            message = "We received your report and it is under human review so the right team can confirm the details. You may be contacted if more information is needed."
        else:
            message = f"We received your report and sent it to {destination}. The team will review the details without any promised repair timeline."
        if missing_location:
            message += " Please keep the exact location or a nearby landmark ready."
        return message
    if lang == "fr":
        if hitl_required:
            message = "Nous avons recu votre signalement; il est en revue humaine pour confirmer les details. Vous pouvez etre contacte si une precision est necessaire."
        else:
            message = f"Nous avons recu votre signalement et l'avons envoye a {destination}. L'equipe va verifier les details sans delai de reparation promis."
        if missing_location:
            message += " Gardez l'emplacement exact ou un point de repere pret."
        return message

    if hitl_required:
        message = "Wsolna balaghak w 3am yenraja3 men fare2na la net2akkad min l jiha l sa7. Momken netwasal ma3ak iza badna tafasil aktar."
    else:
        message = f"Wsolna balaghak w t7awwal la {destination}. Ra7 yenraja3o l tafasil bala ma nou3od bi wa2et tasli7 mou3ayyan."
    if missing_location:
        message += " Khalle l location aw 3aleme aribe jehze iza talaboha."
    if sector == "SAFETY":
        message += " Iza fi khatar fawre, twasal ma3 ra2em tawari2 rasmi halla2."
    return message


def explain(
    complaint_id: str,
    routing_sector: str | None,
    routing_entity: str | None,
    routing_confidence: float | None,
    priority_score: float | None,
    issue_type: str | None,
    gps_lat: float | None,
    gps_lon: float | None,
    hitl_required: bool = False,
    language: str | None = None,
    text_raw: str | None = None,
    hitl_reason: str | None = None,
    iep1_signal_json: dict | None = None,
    iep2_incident_json: dict | None = None,
    iep3_routing_json: dict | None = None,
    image_fusion_json: dict | None = None,
    shap_top3: dict | None = None,
) -> dict:
    """Generate citizen and admin explanations for a routed complaint.

    Returns:
        citizen_explanation  str  (Arabizi/Lebanese Arabic)
        admin_explanation    str  (English structured summary)
    """
    sector = (routing_sector or "OTHER").upper()
    entity = routing_entity or "HITL"
    conf = routing_confidence or 0.0
    priority = priority_score or 50.0
    it = issue_type or "unknown"
    gps = _gps_text(gps_lat, gps_lon)
    route_packet = iep3_routing_json or {}
    incident_packet = iep2_incident_json or {}
    signal_packet = iep1_signal_json or {}
    image_packet = image_fusion_json or {}
    shap = shap_top3 or route_packet.get("shap_top3") or {}
    hitl_codes = route_packet.get("hitl_reason_codes") or []
    missing_location = "missing_location" in hitl_codes or route_packet.get("kb_location_method") in {"not_found", "gps_out_of_range"}
    destination = _entity_display_name(entity)
    grounding = _grounding_evidence(entity, sector, hitl_required)

    citizen = _citizen_message(language, sector, destination, hitl_required, missing_location)

    cluster_state = incident_packet.get("incident_lifecycle_state", "unknown")
    cluster_size = incident_packet.get("cluster_size", "unknown")
    route_reason = route_packet.get("kb_route_reason") or "legacy sector/entity routing map"
    admin_parts = [
        f"Complaint {complaint_id}: {sector}/{it} routed to {entity} ({destination}).",
        f"Priority score: {priority:.0f}/100. Routing confidence: {conf:.0%}. GPS location: {gps}.",
        f"Incident context: state={cluster_state}, cluster_size={cluster_size}.",
        f"Route evidence: {route_reason}.",
        f"Next action: {_next_action(sector, entity, hitl_required)}",
    ]
    if grounding["fact_ids"]:
        admin_parts.append(
            "Grounding: KB facts "
            + ", ".join(grounding["fact_ids"][:4])
            + " using sources "
            + ", ".join(grounding["source_ids"][:5])
            + "."
        )
    if image_packet:
        fusion = image_packet.get("fusion") or {}
        admin_parts.append(
            "Image/text fusion: "
            f"{fusion.get('agreement', 'unknown')} ({fusion.get('reason', 'no reason')})."
        )
    if hitl_required:
        admin_parts.insert(0, "[HITL REQUIRED]")
        admin_parts.append(f"HITL reason: {hitl_reason or route_packet.get('hitl_reason') or 'manual review required'}.")
    if hitl_codes:
        admin_parts.append(f"HITL codes: {', '.join(hitl_codes)}.")
    if route_packet.get("kb_warnings"):
        admin_parts.append("KB warnings: " + "; ".join(route_packet["kb_warnings"]) + ".")
    admin = " ".join(admin_parts)

    audit_packet = {
        "complaint_id": complaint_id,
        "stage": "iep4",
        "generator_version": "rule_explainer_v2",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "prompt_templates": {
            "citizen": _CITIZEN_PROMPT.name,
            "admin": _ADMIN_PROMPT.name,
            "audit": _AUDIT_PROMPT.name,
        },
        "inputs": {
            "language": language,
            "routing_sector": sector,
            "routing_entity": entity,
            "routing_confidence": conf,
            "priority_score": priority,
            "hitl_required": hitl_required,
        },
        "evidence_refs": {
            "iep1_review_recommendation": signal_packet.get("review_recommendation"),
            "iep2_incident_lifecycle_state": cluster_state,
            "iep3_router_version": route_packet.get("router_version") or shap.get("router_version") or "sector_agency_map",
            "iep3_hitl_reason_codes": hitl_codes,
            "kb_fact_ids": grounding["fact_ids"],
            "kb_source_ids": grounding["source_ids"],
            "image_fusion_agreement": (image_packet.get("fusion") or {}).get("agreement"),
        },
        "guardrails": {
            "citizen_hides_internal_codes": entity not in citizen,
            "no_repair_timeline_promised": True,
            "raw_text_reproduced": False,
            "raw_text_available_to_generator": bool(text_raw),
            "kb_grounded": grounding["grounded"],
            "unsupported_sla_blocked": True,
            "invented_agency_blocked": True,
        },
        "verifier": {
            "allowed_fact_ids": grounding["fact_ids"],
            "allowed_source_ids": grounding["source_ids"],
            "no_unverified_deadline": True,
            "entity_supported_by_kb": grounding["grounded"] or entity == "HITL",
        },
        "outputs": {
            "citizen_chars": len(citizen),
            "admin_chars": len(admin),
            "hitl_marker_in_admin": "HITL" in admin,
        },
    }

    return {
        "citizen_explanation": citizen,
        "admin_explanation": admin,
        "iep4_explanation_json": audit_packet,
    }

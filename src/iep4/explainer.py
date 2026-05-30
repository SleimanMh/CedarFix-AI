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

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_CITIZEN_PROMPT = ROOT / "prompts" / "iep4_citizen_v1.0.txt"
_ADMIN_PROMPT = ROOT / "prompts" / "iep4_admin_v1.0.txt"

# Rule-based templates per sector (Arabizi/Lebanese Arabic)
# Each template may use {entity} for the responsible agency name.
_CITIZEN_TEMPLATES: dict[str, str] = {
    "ROADS": "T7awwel balagh taba3ak la {entity}, l jiha l mikhtasa bel torou2 bil mantiqa. Ra7 yit7akaku bil mas2ale w yrajj3oukon.",
    "WATER": "T7awwel balagh taba3ak la {entity}, l jiha l mikhtasa bel miye bil mantiqa. Ra7 yit7akaku bil mas2ale.",
    "ELECTRICITY": "Orsel balagh taba3ak la l jiha l mikhtasa — la2anno fi 3iddet jihat mikhtasa bel kahraba, ra7 y7addidou l jiha l munasibe w yit7akaku.",
    "WASTE": "T7awwel balagh taba3ak la {entity}, l jiha l mikhtasa bel nazafe bil mantiqa. Ra7 yit7akaku bil mas2ale.",
    "FLOODING": "T7awwel balagh taba3ak la {entity}. Ra7 yit3amilou ma3o bi-sour3a.",
    "SAFETY": "Orsel balagh taba3ak la l mouraaji3 l bashari 3al toul. Ra7 yit3amilou bi-sour3a.",
    "TELECOM": "T7awwel balagh taba3ak la {entity}, l jiha l mikhtasa bel internet w l telephone. Ra7 yit7akaku bil mas2ale.",
    "OTHER": "Orsel balagh taba3ak la l mouraaji3 l bashari la ta7did l jiha l mikhtasa bel mawdou3. Shukran 3al tablegh.",
}

_ADMIN_TEMPLATES: dict[str, str] = {
    "ROADS": (
        "Road infrastructure complaint forwarded to {entity}. "
        "Issue type: {issue_type}. Priority score: {priority:.0f}/100. "
        "GPS location: {gps}. Routing confidence: {conf:.0%}. "
        "Review for local street vs national road classification before dispatch."
    ),
    "WATER": (
        "Water supply complaint forwarded to regional water authority ({entity}). "
        "Issue type: {issue_type}. Priority score: {priority:.0f}/100. "
        "GPS location: {gps}. Routing confidence: {conf:.0%}."
    ),
    "ELECTRICITY": (
        "Electricity complaint flagged for HITL review — entity: {entity}. "
        "Generator vs EDL grid vs EDZ concession must be confirmed. "
        "Issue type: {issue_type}. Priority score: {priority:.0f}/100. "
        "Routing confidence: {conf:.0%}."
    ),
    "WASTE": (
        "Waste management complaint forwarded to municipality ({entity}). "
        "Issue type: {issue_type}. Priority score: {priority:.0f}/100. "
        "Routing confidence: {conf:.0%}. Flag if hazardous/medical waste."
    ),
    "FLOODING": (
        "Flood/drainage complaint forwarded to Civil Defense ({entity}) and municipality. "
        "Issue type: {issue_type}. Priority score: {priority:.0f}/100. "
        "GPS: {gps}. Routing confidence: {conf:.0%}."
    ),
    "SAFETY": (
        "Safety complaint flagged for immediate HITL review — do NOT auto-route. "
        "Primary entity: {entity}. Issue type: {issue_type}. "
        "Priority score: {priority:.0f}/100."
    ),
    "TELECOM": (
        "Telecom complaint forwarded to Ogero ({entity}) — HITL review required. "
        "Issue type: {issue_type}. Priority score: {priority:.0f}/100. "
        "Routing confidence: {conf:.0%}. Confirm fixed-line vs mobile before dispatch."
    ),
    "OTHER": (
        "Complaint sector unclear — forwarded to human reviewer for sector triage. "
        "Possible issue type: {issue_type}. Priority score: {priority:.0f}/100. "
        "Routing confidence: {conf:.0%}."
    ),
}


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
) -> dict:
    """Generate citizen and admin explanations for a routed complaint.

    Returns:
        citizen_explanation  str  (Arabizi/Lebanese Arabic)
        admin_explanation    str  (English structured summary)
    """
    sector = (routing_sector or "OTHER").upper()
    entity = routing_entity or "—"
    conf = routing_confidence or 0.0
    priority = priority_score or 50.0
    it = issue_type or "unknown"
    gps = f"({gps_lat:.5f}, {gps_lon:.5f})" if (gps_lat and gps_lon) else "not provided"

    citizen = _CITIZEN_TEMPLATES.get(sector, _CITIZEN_TEMPLATES["OTHER"]).format(entity=entity)

    admin_tmpl = _ADMIN_TEMPLATES.get(sector, _ADMIN_TEMPLATES["OTHER"])
    admin = admin_tmpl.format(
        entity=entity,
        issue_type=it,
        priority=priority,
        gps=gps,
        conf=conf,
    )

    # Always include GPS status so downstream reviewers know whether location was provided.
    if "{gps}" not in admin_tmpl:
        admin = admin + f" GPS location: {gps}."

    if hitl_required and "HITL" not in admin:
        admin = f"[HITL REQUIRED] {admin}"

    return {
        "citizen_explanation": citizen,
        "admin_explanation": admin,
    }

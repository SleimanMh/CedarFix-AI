#!/usr/bin/env python3
"""
Compile routing knowledge into RAG-ready RoutingKnowledgeDoc JSONL.

Inputs:
  - RAG Data/dossiers/entities/*.json from the feature/rag-data branch
  - CedarFix entity KB files from data/knowledge_base/entities or
    ../data/knowledge_base/entities when this branch is used as a worktree
  - structured source data from data/knowledge_base and the uploaded v74 zip

Output:
  - RAG Data/compiled/routing_knowledge_docs.jsonl
    - RAG Data/compiled/routing_knowledge_compiled_production.json
  - RAG Data/compiled/routing_knowledge_manifest.json

The compiler is deterministic and does not call an LLM. It normalizes entity
names, responsibility chunks, keywords, negative responsibilities, and HITL
conditions into the shape consumed by scripts/seed_routing_knowledge.py.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAG_DIR = REPO_ROOT / "RAG Data"
DEFAULT_RAG_DOSSIER_DIR = DEFAULT_RAG_DIR / "dossiers" / "entities"
DEFAULT_ADVANCED_DOSSIER = DEFAULT_RAG_DIR / "dossiers" / "advanced" / "structured_rag_docs.jsonl"
DEFAULT_OUTPUT = DEFAULT_RAG_DIR / "compiled" / "routing_knowledge_docs.jsonl"
DEFAULT_PRODUCTION_JSON = DEFAULT_RAG_DIR / "compiled" / "routing_knowledge_compiled_production.json"
DEFAULT_MANIFEST = DEFAULT_RAG_DIR / "compiled" / "routing_knowledge_manifest.json"
DEFAULT_STAGE1_OUTPUT = DEFAULT_RAG_DIR / "compiled" / "routing_knowledge_stage1_dispatch.jsonl"
DEFAULT_STAGE2_OUTPUT = DEFAULT_RAG_DIR / "compiled" / "routing_knowledge_stage2_operations.jsonl"
DEFAULT_STAGE3_OUTPUT = DEFAULT_RAG_DIR / "compiled" / "routing_knowledge_stage3_evidence.jsonl"

DEFAULT_ENTITY_DIR_CANDIDATES: list[Path] = []

FALLBACK_ENTITY_DIR_CANDIDATES = [
    REPO_ROOT / "data" / "knowledge_base" / "entities",
    REPO_ROOT.parent / "data" / "knowledge_base" / "entities",
]

SOURCE_DATA_ROOT_CANDIDATES = [
    REPO_ROOT / "data",
    REPO_ROOT.parent / "data",
]

V74_ZIP_CANDIDATES = [
    REPO_ROOT / "cedarfix_batch5_v74_gap_resolution_handoff.zip",
    REPO_ROOT.parent / "cedarfix_batch5_v74_gap_resolution_handoff.zip",
]


CONFIDENCE_MAP = {
    "high": 0.95,
    "medium_high": 0.88,
    "medium": 0.80,
    "low": 0.60,
    "unknown": 0.70,
}


MAIN_ENTITY_IDS = {
    "BMLWE",
    "BWE",
    "CD",
    "CDR",
    "EDL",
    "EDZ",
    "ISF",
    "LRA",
    "MOBILE_OPERATOR",
    "MOE",
    "MPWT",
    "MUN",
    "NLWE",
    "OGERO",
    "SLWE",
    "TRA",
}


MUNICIPAL_CONTEXT_CAP_DOC_TYPES = {
    "municipality_service_map",
    "municipality_resolution_bundle",
    "municipality_responsibility_map",
    "municipal_union_membership",
    "municipal_union_service",
}

STAGE1_DISPATCH_DOC_TYPES = {
    "responsibility",
    "routing_rule",
    "boundary_condition",
    "not_responsible_guardrail",
    "entity_legal_fact",
    "entity_service_area_fact",
    "entity_service_area_map",
    "entity_emergency_fact",
    "sector_agency_policy",
    "road_ownership",
    "irrigation_boundary",
    "cdr_project_service_area",
    "waste_site_registry",
    "no_contact_blocker",
    "complaint_intake_staging_candidate",
}

STAGE2_OPERATIONS_DOC_TYPES = {
    "complaint_channel",
    "contact_point",
    "municipality_channel",
    "municipality_workflow",
    "mobile_operator_channel",
    "required_fields_profile",
    "service_area",
    "service_catalog",
    "sla_policy",
    "operator_coverage",
    "entity_contact_fact",
    "entity_process_fact",
    "entity_deadline_policy_fact",
}

STAGE3_EVIDENCE_DOC_TYPES = {
    "source_registry_entry",
    "official_process_event",
    "coverage_audit",
    "validation_audit",
    "trusted_context",
    "complaint_taxonomy",
    "municipality_contact_fallback",
}

STAGE1_DISPATCH_ROUTE_MODES = {
    "routing_candidate",
    "routing_rule",
    "routing_guardrail",
    "entity_legal_scope",
    "geo_service_area_map",
    "geo_service_area",
    "sector_policy_map",
    "cdr_project_boundary",
    "negative_boundary",
    "emergency_instruction",
    "waste_site_context",
}

STAGE2_OPERATIONS_ROUTE_MODES = {
    "complaint_intake_or_channel",
    "complaint_workflow",
    "contact_context",
    "intake_requirements",
    "resolution_policy",
    "service_catalog",
    "operator_context",
    "shared_service_context",
    "geo_district_reference",
    "municipality_resolution_bundle",
}

STAGE3_EVIDENCE_ROUTE_MODES = {
    "source_provenance",
    "historical_case_context",
    "audit_context",
    "contact_fallback_only",
    "query_and_type_expansion",
}


ENTITY_MAP: dict[str, dict[str, Any]] = {
    "BMLWE": {
        "entity_name": "Beirut Water Authority",
        "entity_enum": "Beirut Water Authority",
        "entity_type": "utility",
        "short_name": "BMLWE",
        "governs_nationally": False,
        "governorates": ["Beirut Governorate", "Mount Lebanon Governorate"],
        "districts": ["Beirut", "Metn", "Keserwan", "Baabda", "Aley", "Chouf", "Jbeil"],
        "municipalities": [],
    },
    "BWE": {
        "entity_name": "Bekaa Water Establishment",
        "entity_enum": "Bekaa Water Establishment",
        "entity_type": "utility",
        "short_name": "BWE",
        "governs_nationally": False,
        "governorates": ["Bekaa Governorate", "Baalbek-Hermel Governorate"],
        "districts": ["Zahle", "Western Bekaa", "Rachaya", "Baalbek", "Hermel"],
        "municipalities": [],
    },
    "CD": {
        "entity_name": "Lebanese Civil Defense",
        "entity_enum": "Lebanese Civil Defense",
        "entity_type": "emergency_service",
        "short_name": "CD",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "CDR": {
        "entity_name": "Council for Development and Reconstruction",
        "entity_enum": "Council for Development and Reconstruction",
        "entity_type": "public_agency",
        "short_name": "CDR",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "CENTRAL_INSPECTION": {
        "entity_name": "Central Inspection",
        "entity_enum": "Central Inspection",
        "entity_type": "oversight",
        "short_name": "CI",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "DGLAC": {
        "entity_name": "General Directorate of Local Administrations and Councils",
        "entity_enum": "General Directorate of Local Administrations and Councils",
        "entity_type": "directorate",
        "short_name": "DGLAC",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "EDL": {
        "entity_name": "Electricite Du Liban",
        "entity_enum": "Electricite Du Liban",
        "entity_type": "utility",
        "short_name": "EDL",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "EDZ": {
        "entity_name": "Electricite de Zahle",
        "entity_enum": "Electricite de Zahle",
        "entity_type": "utility_concession",
        "short_name": "EDZ",
        "governs_nationally": False,
        "governorates": ["Bekaa Governorate"],
        "districts": ["Zahle"],
        "municipalities": ["Zahle"],
    },
    "ISF": {
        "entity_name": "Internal Security Forces",
        "entity_enum": "Internal Security Forces",
        "entity_type": "security",
        "short_name": "ISF",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "LRA": {
        "entity_name": "Litani River Authority",
        "entity_enum": "Litani River Authority",
        "entity_type": "river_authority",
        "short_name": "LRA",
        "governs_nationally": False,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "MEW": {
        "entity_name": "Ministry of Energy and Water",
        "entity_enum": "Ministry of Energy and Water",
        "entity_type": "ministry",
        "short_name": "MEW",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "MOBILE_OPERATOR": {
        "entity_name": "Mobile Network Operators",
        "entity_enum": "Mobile Network Operators",
        "entity_type": "operator",
        "short_name": "Mobile",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "MOE": {
        "entity_name": "Ministry of Environment",
        "entity_enum": "Ministry of Environment",
        "entity_type": "ministry",
        "short_name": "MoE",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "MOIM": {
        "entity_name": "Ministry of Interior and Municipalities",
        "entity_enum": "Ministry of Interior and Municipalities",
        "entity_type": "ministry",
        "short_name": "MoIM",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "MPWT": {
        "entity_name": "Ministry of Public Works",
        "entity_enum": "Ministry of Public Works",
        "entity_type": "ministry",
        "short_name": "MPWT",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "MUN": {
        "entity_name": "Local Municipality",
        "entity_enum": "Local Municipality",
        "entity_type": "municipality",
        "short_name": "MUN",
        "governs_nationally": False,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "MUNICIPAL_POLICE": {
        "entity_name": "Municipal Police",
        "entity_enum": "Municipal Police",
        "entity_type": "municipal_enforcement",
        "short_name": "MunPolice",
        "governs_nationally": False,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "NLWE": {
        "entity_name": "North Lebanon Water Establishment",
        "entity_enum": "North Lebanon Water Establishment",
        "entity_type": "utility",
        "short_name": "NLWE",
        "governs_nationally": False,
        "governorates": ["North Governorate", "Akkar Governorate"],
        "districts": ["Tripoli", "Zgharta", "Batroun", "Koura", "Bcharre", "Minieh-Danniyeh", "Akkar"],
        "municipalities": [],
    },
    "OGERO": {
        "entity_name": "Ogero",
        "entity_enum": "Ogero",
        "entity_type": "utility",
        "short_name": "Ogero",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
    "SLWE": {
        "entity_name": "South Lebanon Water Establishment",
        "entity_enum": "South Lebanon Water Establishment",
        "entity_type": "utility",
        "short_name": "SLWE",
        "governs_nationally": False,
        "governorates": ["South Governorate", "Nabatieh Governorate"],
        "districts": ["Sidon", "Tyre", "Jezzine", "Nabatieh", "Bint Jbeil", "Marjayoun", "Hasbaya"],
        "municipalities": [],
    },
    "TRA": {
        "entity_name": "Telecommunications Regulatory Authority",
        "entity_enum": "Telecommunications Regulatory Authority",
        "entity_type": "regulator",
        "short_name": "TRA",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
    },
}


DOMAIN_SYNONYMS = [
    ("water", ["water", "pipe", "sewer", "sewage", "wastewater", "contamination", "pressure", "meter"]),
    ("electricity", ["electricity", "power", "grid", "wire", "transformer", "streetlight", "blackout"]),
    ("telecom", ["telecom", "internet", "dsl", "fiber", "mobile", "billing", "operator", "roaming"]),
    ("roads", ["road", "pothole", "asphalt", "bridge", "tunnel", "highway", "sidewalk", "drainage"]),
    ("waste", ["waste", "garbage", "dumping", "pollution", "burning", "environment"]),
    ("safety", ["fire", "rescue", "collapse", "hazard", "accident", "traffic", "crime", "police"]),
    ("administration", ["municipal", "registry", "council", "inspection", "corruption", "permit", "form"]),
]


COMPLAINT_TYPE_SYNONYMS = {
    "water_supply": ["water_outage", "no_water", "low_pressure", "water_pressure_low"],
    "water_pipe": ["water_pipe", "pipe_leak_public", "burst_pipe", "water_leak"],
    "water_contamination": ["dirty_water", "water_contamination", "unsafe_water"],
    "wastewater_overflow": ["sewage_overflow", "public_sewer_blockage", "wastewater_overflow"],
    "electricity_outage": ["electricity_outage", "power_outage", "blackout"],
    "electricity_fault": ["power_line_fault", "transformer_fault", "sparking_wire_grid_side"],
    "electricity_meter": ["meter_bill", "meter_billing_dispute", "meter_issue"],
    "streetlight": ["streetlight", "public_lighting_grid", "street_light_fault"],
    "fixed_telecom": ["telecom_outage", "internet_outage", "dsl_fault", "fiber_fault"],
    "mobile": ["mobile_billing_complaint", "mobile_network_quality", "operator_escalation"],
    "roads": ["road_damage", "pothole", "bridge_damage", "highway_obstruction"],
    "municipal": ["local_road_damage", "sidewalk_obstruction", "public_space_obstruction"],
    "waste": ["waste_accumulation", "illegal_dumping", "open_burning"],
    "public_safety": ["public_safety", "traffic_incident", "emergency_response"],
}


STOPWORDS = {
    "and", "or", "the", "for", "with", "from", "into", "this", "that", "only", "also",
    "route", "responsible", "complaint", "complaints", "public", "private", "when",
}


ARABIZI_NOISE_TOKENS = {
    "kahraba",
    "ray7a",
    "moteur",
    "eshtirak",
    "mkashfin",
    "sando2",
    "shere3",
    "daw",
    "ta3",
    "ma3",
    "3al",
    "m2ata3een",
    "mfassol",
}

FORCED_HITL_ROUTE_MODES = {
    "human_review_gate",
    "manual_review_only",
    "human_review_user_assist",
}


def _ascii_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\([^)]*[\u0600-\u06ff][^)]*\)", "", text)
    text = text.replace("→", " to ").replace("—", " - ").replace("–", "-")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _strip_arabizi_noise(value: Any) -> str:
    text = _ascii_text(value)
    if not text:
        return ""
    # Remove Arabizi-like alphanumeric tokens (for example: 3am, 7ada, m2ata3een).
    text = re.sub(r"\b[a-z]+[2356789][a-z0-9]*\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[2356789][a-z]+[a-z0-9]*\b", " ", text, flags=re.IGNORECASE)
    for token in ARABIZI_NOISE_TOKENS:
        text = re.sub(rf"\b{re.escape(token)}\b", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" ,;.-")


def _slug(value: Any) -> str:
    text = _ascii_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_") or "unknown"


def _unique(values: list[Any], limit: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _ascii_text(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if limit and len(out) >= limit:
            break
    return out


def _confidence(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return CONFIDENCE_MAP.get(_slug(value), CONFIDENCE_MAP["unknown"])


def _truncate_sentence(text: str, limit: int = 360) -> str:
    text = _ascii_text(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return f"{cut}."


def _first_ascii(*values: Any) -> str:
    for value in values:
        text = _ascii_text(value)
        if text:
            return text
    return ""


def _enforce_forced_hitl_route_mode(doc: dict[str, Any]) -> None:
    route_mode = _slug(doc.get("route_mode", ""))
    if route_mode:
        doc["route_mode"] = route_mode
    if route_mode in FORCED_HITL_ROUTE_MODES:
        doc["hitl_always_required"] = True


def _load_dossier(path: Path, profile: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    try:
        source_file = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        source_file = f"external:data/knowledge_base/entities/{path.name}"
    data["_source_file"] = source_file
    data["_source_profile"] = profile
    return data


def _portable_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        pass
    try:
        return "../" + path.relative_to(REPO_ROOT.parent).as_posix()
    except ValueError:
        return str(path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _split_values(value: Any) -> list[str]:
    text = _ascii_text(value)
    if not text:
        return []
    parts = re.split(r"\s*[;|]\s*|\s*,\s*(?=[A-Za-z0-9_+-])", text)
    return _unique([p for p in parts if p and p.lower() not in {"nan", "none", "null", "#n/a"}])


def _compact_keywords(values: list[Any]) -> list[str]:
    keywords: list[str] = []
    for value in values:
        text = _ascii_text(value)
        if not text:
            continue
        if len(text) <= 80:
            keywords.append(text)
            continue
        terms = re.findall(r"[A-Za-z][A-Za-z0-9_+-]{2,}", text)
        for term in terms:
            if _slug(term) in STOPWORDS:
                continue
            if len(term) <= 90:
                keywords.append(term)
                continue
            # Break very long underscore-joined machine tokens into searchable parts.
            if "_" in term:
                parts = [part for part in term.split("_") if len(part) >= 3]
                keywords.extend(parts)
                continue
            keywords.append(term[:90])
    return _unique(keywords, limit=55)


def _truthy(value: Any) -> bool:
    return _slug(value) in {"true", "yes", "y", "1", "required", "hitl", "manual_review_needed"}


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    omitted_fields = {
        "examples",
        "example",
        "example_arabizi",
        "arabizi_examples",
        "sample_arabizi",
    }
    for key, value in row.items():
        if value is None:
            continue
        if key in omitted_fields or "arabizi" in key.lower():
            continue
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null", "#n/a"}:
            continue
        normalized_key = key.lower()
        preserve_raw = any(
            token in normalized_key
            for token in {
                "id",
                "url",
                "phone",
                "email",
                "endpoint",
                "registry",
                "source_profile",
                "source_ids",
                "source_id",
                "governorate",
                "district",
                "municipality",
                "entity",
                "selector",
                "confidence",
                "status",
                "date",
            }
        )
        if not preserve_raw:
            text = _strip_arabizi_noise(text)
            if not text:
                continue
        cleaned[key] = text
    return cleaned


def _row_source_ids(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("source_ids", "source_id", "source_url", "source_url_checked", "legacy_source_url", "cedarfix_source_url"):
        out.extend(_split_values(row.get(key, "")))
    return _unique(out, limit=16)


def _confidence_from_row(row: dict[str, Any], default: float = 0.78) -> float:
    for key in ("confidence_prior", "confidence", "workflow_confidence", "water_confidence", "electricity_confidence"):
        if row.get(key):
            return _confidence(row[key])
    return default


def _confidence_from_tier(tier: Any, default: float = 0.74) -> float:
    slug = _slug(tier)
    if slug.startswith("t0"):
        return 0.95
    if slug.startswith("t1"):
        return 0.88
    if slug.startswith("t2"):
        return 0.78
    if slug.startswith("t3"):
        return 0.68
    return default


def _entity_meta(entity_id: str) -> dict[str, Any]:
    if entity_id in ENTITY_MAP:
        return ENTITY_MAP[entity_id]
    if entity_id == "HITL":
        return {
            "entity_name": "Human Review Queue",
            "entity_enum": "Human Review Queue",
            "entity_type": "review",
            "short_name": "HITL",
            "governs_nationally": True,
            "governorates": [],
            "districts": [],
            "municipalities": [],
        }
    if entity_id == "BEIRUT_MUNICIPALITY":
        return {
            "entity_name": "Beirut Municipality",
            "entity_enum": "Beirut Municipality",
            "entity_type": "municipality",
            "short_name": "Beirut",
            "governs_nationally": False,
            "governorates": ["Beirut Governorate"],
            "districts": ["Beirut"],
            "municipalities": ["Beirut"],
        }
    return _entity_meta("HITL")


SELECTOR_TO_ENTITY_ID = {
    "BMLWE": "BMLWE",
    "BWE": "BWE",
    "CD": "CD",
    "CDR": "CDR",
    "CENTRAL_INSPECTION": "CENTRAL_INSPECTION",
    "CI": "CENTRAL_INSPECTION",
    "DGLAC": "DGLAC",
    "EDL": "EDL",
    "EDZ": "EDZ",
    "ISF": "ISF",
    "LRA": "LRA",
    "MEW": "MEW",
    "MOBILE_OPERATOR": "MOBILE_OPERATOR",
    "MOBILE_OP": "MOBILE_OPERATOR",
    "MOE": "MOE",
    "MOIM": "MOIM",
    "MPWT": "MPWT",
    "MOPW": "MPWT",
    "MUN": "MUN",
    "MUN_DYNAMIC": "MUN",
    "MUN_UNION_DYNAMIC": "MUN",
    "MUNICIPAL_POLICE": "MUNICIPAL_POLICE",
    "NLWE": "NLWE",
    "OGERO": "OGERO",
    "SLWE": "SLWE",
    "TRA": "TRA",
    "CIVIL_DEFENSE": "CD",
    "LEBANESE_CIVIL_DEFENSE": "CD",
    "BEIRUT_MUNICIPALITY": "BEIRUT_MUNICIPALITY",
    "HITL": "HITL",
    "HUMAN_REVIEW": "HITL",
    "HUMAN_REVIEW_QUEUE": "HITL",
}


def _selector_entity_id(selector: Any) -> str:
    text = _slug(selector).upper()
    if not text:
        return "HITL"
    if text in SELECTOR_TO_ENTITY_ID:
        return SELECTOR_TO_ENTITY_ID[text]
    if "CIVIL_DEFENSE" in text:
        return "CD"
    if "CENTRAL_INSPECTION" in text:
        return "CENTRAL_INSPECTION"
    if "MUNICIPAL_POLICE" in text:
        return "MUNICIPAL_POLICE"
    if "MOBILE" in text:
        return "MOBILE_OPERATOR"
    if "OGERO" in text:
        return "OGERO"
    if "EDZ" in text or "ZAHLE_CONCESSION" in text:
        return "EDZ"
    if "EDL" in text or "ELECTRIC" in text:
        return "EDL"
    if "MPWT" in text or "MOPW" in text or "MINISTRY_PUBLIC_WORKS" in text:
        return "MPWT"
    if "MUN" in text or "MUNICIPAL" in text:
        return "MUN"
    if "WATER_ESTABLISHMENT_BY_LOCATION" in text or text in {"WE", "WATER_ESTABLISHMENT"}:
        return "HITL"
    if "HITL" in text or "MANUAL" in text or "PRIVATE_PROPERTY" in text:
        return "HITL"
    return "HITL"


def _resolve_selector(*candidates: Any, fallback: Any = "HITL") -> str:
    for candidate in candidates:
        text = _ascii_text(candidate)
        if not text:
            continue
        probe_values = [text, *re.split(r"\s*[|;,/]\s*|\s+", text)]
        for probe in probe_values:
            if not probe:
                continue
            resolved = _selector_entity_id(probe)
            if resolved != "HITL":
                return resolved
    return _selector_entity_id(fallback)


def _is_main_entity(entity_id: Any) -> bool:
    return _selector_entity_id(entity_id) in MAIN_ENTITY_IDS


def _as_weight(value: Any, default: float = 1.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _apply_retrieval_stage_policy(docs: list[dict[str, Any]]) -> None:
    for doc in docs:
        doc_type = _slug(doc.get("doc_type", ""))
        route_mode = _slug(doc.get("route_mode", ""))
        route_authority = _slug(doc.get("route_authority", ""))
        source_profile = _slug(doc.get("source_profile", ""))
        responsibility_level = _slug(doc.get("responsibility_level", ""))
        weight = _as_weight(doc.get("retrieval_weight"), 1.0)

        stage = "stage3_evidence"
        lane = "evidence"
        priority = 4
        stage1_candidate = False
        cap_reason = ""

        if doc_type in MUNICIPAL_CONTEXT_CAP_DOC_TYPES:
            stage = "stage2_operations"
            lane = "geo_context"
            priority = 3
            stage1_candidate = False
            cap_reason = "high_volume_municipal_context"
            weight = min(weight, 0.78)
        elif doc_type in STAGE1_DISPATCH_DOC_TYPES or route_mode in STAGE1_DISPATCH_ROUTE_MODES:
            stage = "stage1_dispatch"
            lane = "dispatch"
            stage1_candidate = True
            if responsibility_level == "primary" or route_authority in {
                "authoritative",
                "authoritative_rule",
                "authoritative_map",
                "authoritative_profile",
                "guardrail",
                "project_owner_boundary",
            }:
                priority = 1
            else:
                priority = 2
        elif doc_type in STAGE2_OPERATIONS_DOC_TYPES or route_mode in STAGE2_OPERATIONS_ROUTE_MODES:
            stage = "stage2_operations"
            lane = "operations"
            priority = 3

        if doc_type in STAGE3_EVIDENCE_DOC_TYPES or route_mode in STAGE3_EVIDENCE_ROUTE_MODES:
            stage = "stage3_evidence"
            lane = "evidence"
            priority = 4
            stage1_candidate = False

        if route_mode == "contact_fallback_only":
            cap_reason = cap_reason or "fallback_contact_context_only"
            weight = min(weight, 0.65)
        if source_profile == "source_registry_entry":
            cap_reason = cap_reason or "provenance_context_only"
            weight = min(weight, 0.55)
        if source_profile == "complaint_intelligence_event":
            weight = min(weight, 0.86)

        if doc_type in {"no_contact_blocker", "complaint_intake_staging_candidate"}:
            stage = "stage1_dispatch"
            lane = "dispatch"
            priority = 1
            stage1_candidate = True
            weight = max(weight, 0.95)

        doc["retrieval_stage"] = stage
        doc["retrieval_lane"] = lane
        doc["stage1_dispatch_candidate"] = bool(stage1_candidate)
        doc["stage_priority"] = int(priority)
        doc["retrieval_weight"] = round(max(0.1, min(2.0, weight)), 3)

        if cap_reason:
            structured_fields = doc.get("structured_fields")
            if not isinstance(structured_fields, dict):
                structured_fields = {}
            structured_fields["stage1_cap_reason"] = cap_reason
            doc["structured_fields"] = structured_fields


def _partition_docs_by_stage(docs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {
        "stage1_dispatch": [],
        "stage2_operations": [],
        "stage3_evidence": [],
    }
    for doc in docs:
        stage = _ascii_text(doc.get("retrieval_stage")) or "stage3_evidence"
        buckets.setdefault(stage, []).append(doc)
    for stage in buckets:
        buckets[stage] = sorted(buckets[stage], key=lambda d: d.get("doc_id", ""))
    return buckets


def _backfill_rag_entity_dossiers(rag_dir: Path, entity_dirs: list[Path]) -> list[str]:
    target_dir = rag_dir / "dossiers" / "entities"
    target_dir.mkdir(parents=True, exist_ok=True)

    source_files: dict[str, Path] = {}
    for entity_dir in entity_dirs:
        if not entity_dir.exists():
            continue
        for path in sorted(entity_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            source_files.setdefault(path.name, path)

    copied: list[str] = []
    for name, source_path in sorted(source_files.items()):
        destination = target_dir / name
        if destination.exists():
            continue
        shutil.copy2(source_path, destination)
        copied.append(_portable_path(destination))
    return copied


def _doc_base(
    *,
    doc_id: str,
    selector: Any,
    description: str,
    doc_type: str,
    route_mode: str,
    route_authority: str,
    source_reliability: str,
    complaint_types: list[Any] | None = None,
    keywords: list[Any] | None = None,
    not_responsible_for: list[Any] | None = None,
    source_ids: list[Any] | None = None,
    source_files: list[Any] | None = None,
    confidence_prior: float = 0.78,
    responsibility_level: str = "context",
    hitl_required: bool = False,
    hitl_conditions: list[Any] | None = None,
    governorates: list[Any] | None = None,
    districts: list[Any] | None = None,
    municipalities: list[Any] | None = None,
    hotline: str | None = None,
    exact_match_terms: list[Any] | None = None,
    negative_signals: list[Any] | None = None,
    location_precision: str | None = None,
    structured_fields: dict[str, Any] | None = None,
    retrieval_weight: float = 1.0,
) -> dict[str, Any]:
    entity_id = _selector_entity_id(selector)
    meta = _entity_meta(entity_id)
    desc = _strip_arabizi_noise(description) or _ascii_text(description)
    src_files = _unique(source_files or [], limit=10)
    src_ids = _unique(source_ids or src_files, limit=20)
    normalized_route_mode = _slug(route_mode)
    forced_hitl = normalized_route_mode in FORCED_HITL_ROUTE_MODES
    keyword_values = [_strip_arabizi_noise(v) for v in [*(keywords or []), selector, doc_type, route_mode]]
    return {
        "doc_id": _slug(doc_id),
        "doc_type": _slug(doc_type),
        "route_mode": normalized_route_mode,
        "route_authority": _slug(route_authority),
        "source_reliability": _slug(source_reliability),
        "entity_name": meta["entity_name"],
        "entity_enum": meta["entity_enum"],
        "entity_type": meta["entity_type"],
        "short_name": meta["short_name"],
        "governs_nationally": bool(meta["governs_nationally"]),
        "governorates": _unique(governorates if governorates is not None else meta["governorates"], limit=20),
        "districts": _unique(districts if districts is not None else meta["districts"], limit=20),
        "municipalities": _unique(municipalities if municipalities is not None else meta["municipalities"], limit=20),
        "complaint_types": _unique(complaint_types or [_slug(doc_type)], limit=24),
        "keywords": _compact_keywords(keyword_values),
        "not_responsible_for": _unique(not_responsible_for or [], limit=24),
        "description": desc,
        "confidence_prior": round(max(0.0, min(1.0, confidence_prior)), 3),
        "hotline": hotline,
        "source_ids": src_ids,
        "source_files": src_files,
        "hitl_always_required": bool(hitl_required or forced_hitl),
        "hitl_conditions": _unique([_strip_arabizi_noise(v) for v in (hitl_conditions or [])], limit=16),
        "last_reviewed": (structured_fields or {}).get("last_checked") or (structured_fields or {}).get("last_verified"),
        "responsibility_level": _slug(responsibility_level),
        "location_precision": _ascii_text(location_precision) or None,
        "exact_match_terms": _unique([_strip_arabizi_noise(v) for v in (exact_match_terms or [])], limit=24),
        "negative_signals": _unique([_strip_arabizi_noise(v) for v in (negative_signals or [])], limit=24),
        "structured_fields": _clean_row(structured_fields or {}),
        "retrieval_weight": round(max(0.1, min(2.0, retrieval_weight)), 3),
        "source_entity_id": entity_id,
        "source_entity_aliases": _unique([selector, meta["entity_name"], meta["short_name"]], limit=8),
        "source_profile": _slug((structured_fields or {}).get("source_profile") or doc_type),
    }


def _append_unique_doc(docs: list[dict[str, Any]], doc: dict[str, Any]) -> None:
    if not doc.get("description") or len(str(doc["description"])) < 40:
        return
    existing = {d["doc_id"] for d in docs}
    base = doc["doc_id"]
    doc_id = base
    i = 2
    while doc_id in existing:
        doc_id = f"{base}_{i}"
        i += 1
    doc["doc_id"] = doc_id
    docs.append(doc)


def _merge_entities(dossiers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in dossiers:
        entity_id = _slug(item.get("entity_id")).upper()
        if entity_id:
            grouped[entity_id].append(item)

    merged: dict[str, dict[str, Any]] = {}
    confidence_rank = {"low": 1, "medium": 2, "medium_high": 3, "high": 4}
    for entity_id, items in grouped.items():
        facts: list[dict[str, Any]] = []
        fact_seen: set[tuple[str, str]] = set()
        routing_summary = {
            "primary_for_sectors": [],
            "secondary_for_sectors": [],
            "not_responsible_for": [],
            "hitl_conditions": [],
            "hitl_always_required": False,
        }
        source_ids: list[str] = []
        source_files: list[str] = []
        names: list[str] = []
        reviewed: list[str] = []
        best_conf = "unknown"

        # Prefer RAG branch wording first for entities present there, then add local KB details.
        for item in sorted(items, key=lambda x: 0 if x.get("_source_profile") == "rag_data" else 1):
            names.append(item.get("entity_name", entity_id))
            source_files.append(item.get("_source_file", ""))
            if item.get("last_reviewed"):
                reviewed.append(str(item["last_reviewed"]))
            conf = _slug(item.get("overall_confidence", "unknown"))
            if confidence_rank.get(conf, 0) > confidence_rank.get(best_conf, 0):
                best_conf = conf
            for src in item.get("sources", []) or []:
                source_ids.append(src)
            for fact in item.get("facts", []) or []:
                fact_id = str(fact.get("fact_id", ""))
                value = _ascii_text(fact.get("value", ""))
                key = (fact_id, value[:120])
                if not value or key in fact_seen:
                    continue
                fact_seen.add(key)
                fact = dict(fact)
                fact["_source_profile"] = item.get("_source_profile")
                fact["_source_file"] = item.get("_source_file")
                facts.append(fact)
                for src in fact.get("source_ids", []) or []:
                    source_ids.append(src)
            summary = item.get("routing_summary", {}) or {}
            for key in ("primary_for_sectors", "secondary_for_sectors", "not_responsible_for", "hitl_conditions"):
                routing_summary[key].extend(summary.get(key, []) or [])
            routing_summary["hitl_always_required"] = bool(
                routing_summary["hitl_always_required"] or summary.get("hitl_always_required", False)
            )

        meta = ENTITY_MAP.get(entity_id, {
            "entity_name": _ascii_text(names[0] if names else entity_id),
            "entity_enum": _ascii_text(names[0] if names else entity_id),
            "entity_type": "other",
            "short_name": entity_id,
            "governs_nationally": False,
            "governorates": [],
            "districts": [],
            "municipalities": [],
        })
        merged[entity_id] = {
            "entity_id": entity_id,
            "entity_aliases": _unique(names),
            "facts": facts,
            "routing_summary": {
                "primary_for_sectors": _unique(routing_summary["primary_for_sectors"]),
                "secondary_for_sectors": _unique(routing_summary["secondary_for_sectors"]),
                "not_responsible_for": _unique(routing_summary["not_responsible_for"]),
                "hitl_conditions": _unique(routing_summary["hitl_conditions"]),
                "hitl_always_required": routing_summary["hitl_always_required"],
            },
            "sources": _unique(source_ids),
            "source_files": _unique(source_files),
            "overall_confidence": best_conf,
            "last_reviewed": max(reviewed) if reviewed else "",
            **meta,
        }
    return dict(sorted(merged.items()))


def _sector_label(sector: str) -> str:
    label = re.split(r"\s+-\s+|\s+--\s+|\s+to\s+", _ascii_text(sector), maxsplit=1)[0]
    return label.strip() or _ascii_text(sector)


def _complaint_types_for(sector: str) -> list[str]:
    text = _slug(sector)
    types = [text]
    for key, values in COMPLAINT_TYPE_SYNONYMS.items():
        if key in text or any(token in text for token in values):
            types.extend(values)
    if "water" in text and "pipe" in text:
        types.extend(COMPLAINT_TYPE_SYNONYMS["water_pipe"])
    if "sewage" in text or "wastewater" in text or "sewer" in text:
        types.extend(COMPLAINT_TYPE_SYNONYMS["wastewater_overflow"])
    if "road" in text or "pothole" in text or "bridge" in text:
        types.extend(COMPLAINT_TYPE_SYNONYMS["roads"])
    if "internet" in text or "dsl" in text or "fiber" in text:
        types.extend(COMPLAINT_TYPE_SYNONYMS["fixed_telecom"])
    if "mobile" in text or "operator" in text or "billing" in text:
        types.extend(COMPLAINT_TYPE_SYNONYMS["mobile"])
    return _unique(types, limit=14)


def _keywords_for(entity: dict[str, Any], sector: str) -> list[str]:
    raw_words: list[str] = [entity["entity_name"], entity["short_name"], sector, *entity["entity_aliases"]]
    summary = entity["routing_summary"]
    raw_words.extend(summary.get("not_responsible_for", [])[:8])
    raw_words.extend(summary.get("hitl_conditions", [])[:8])
    for domain, terms in DOMAIN_SYNONYMS:
        if any(term in _slug(sector) for term in terms):
            raw_words.append(domain)
            raw_words.extend(terms)
    for fact in entity["facts"]:
        if fact.get("fact_type") in {"legal_responsibility", "complaint_process", "service_area", "emergency_instruction"}:
            raw_words.extend(re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", _ascii_text(fact.get("value", "")))[:16])

    keywords: list[str] = []
    for value in raw_words:
        text = _ascii_text(value)
        if not text:
            continue
        if len(text) > 80:
            for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)[:12]:
                if _slug(term) not in STOPWORDS:
                    keywords.append(_slug(term))
            continue
        keyword = _slug(text) if len(text.split()) <= 4 else text
        if _slug(keyword) not in STOPWORDS:
            keywords.append(keyword)
    return _unique(keywords, limit=45)


def _facts_for_description(entity: dict[str, Any], sector: str) -> list[str]:
    sector_tokens = {t for t in _slug(sector).split("_") if len(t) > 3}
    scored: list[tuple[int, str]] = []
    for fact in entity["facts"]:
        fact_type = fact.get("fact_type", "")
        if fact_type not in {"legal_responsibility", "complaint_process", "service_area", "emergency_instruction"}:
            continue
        value = _ascii_text(fact.get("value", ""))
        tokens = set(_slug(value).split("_"))
        score = len(sector_tokens & tokens)
        if fact_type == "legal_responsibility":
            score += 3
        elif fact_type == "complaint_process":
            score += 2
        elif fact_type == "emergency_instruction":
            score += 1
        scored.append((score, value))
    scored.sort(key=lambda x: x[0], reverse=True)
    return _unique([_truncate_sentence(value, 360) for _, value in scored if value], limit=4)


def _extract_hotline(entity: dict[str, Any]) -> str | None:
    for fact in entity["facts"]:
        if fact.get("fact_type") not in {"operational_contact", "complaint_process", "emergency_instruction"}:
            continue
        value = _ascii_text(fact.get("value", ""))
        match = re.search(r"(?:hotline|call|phone|emergency hotline)[: ]+([+0-9][0-9/+\- ]{2,20})", value, re.I)
        if match:
            return match.group(1).strip(" .;")
    return None


def _extract_hotline_from_text(value: Any) -> str | None:
    text = _ascii_text(value)
    if not text:
        return None
    match = re.search(r"(?:hotline|call|phone|customer care|emergency hotline)[:= ]+([+0-9][0-9/+\- ]{2,20})", text, re.I)
    if match:
        return match.group(1).strip(" .;")
    return None


def _description(entity: dict[str, Any], sector: str, level: str) -> str:
    summary = entity["routing_summary"]
    facts = _facts_for_description(entity, sector)
    parts = [
        f"{entity['entity_name']} ({entity['short_name']}) is a {level} routing candidate for: {_ascii_text(sector)}.",
    ]
    parts.extend(facts)
    if entity.get("governorates"):
        parts.append(f"Geographic scope: {', '.join(entity['governorates'])}.")
    if entity.get("districts"):
        parts.append(f"Districts: {', '.join(entity['districts'])}.")
    if summary.get("not_responsible_for"):
        parts.append("Not responsible for: " + "; ".join(summary["not_responsible_for"][:8]) + ".")
    if summary.get("hitl_always_required"):
        parts.append("Human review is always required for this entity's routing decisions.")
    if summary.get("hitl_conditions"):
        parts.append("Human review conditions: " + "; ".join(summary["hitl_conditions"][:8]) + ".")
    return _ascii_text(" ".join(parts))


def _base_doc(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_name": entity["entity_name"],
        "entity_enum": entity["entity_enum"],
        "entity_type": entity["entity_type"],
        "short_name": entity["short_name"],
        "governs_nationally": entity["governs_nationally"],
        "governorates": entity["governorates"],
        "districts": entity["districts"],
        "municipalities": entity["municipalities"],
        "source_entity_id": entity["entity_id"],
        "source_entity_aliases": entity["entity_aliases"],
        "source_ids": entity["sources"],
        "source_files": entity["source_files"],
        "last_reviewed": entity["last_reviewed"],
        "hitl_always_required": entity["routing_summary"].get("hitl_always_required", False),
        "hitl_conditions": entity["routing_summary"].get("hitl_conditions", []),
    }


def _build_docs(entities: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for entity_id, entity in entities.items():
        summary = entity["routing_summary"]
        sectors = [("primary", s) for s in summary.get("primary_for_sectors", [])]
        sectors.extend(("secondary", s) for s in summary.get("secondary_for_sectors", []))
        if not sectors:
            sectors.append(("primary", entity["entity_name"]))

        for level, sector in sectors:
            label = _sector_label(sector)
            conf = _confidence(entity.get("overall_confidence"))
            if level == "secondary":
                conf = max(0.45, conf - 0.08)
            doc = {
                "doc_id": f"{entity_id.lower()}-{_slug(label)}",
                "doc_type": "responsibility",
                "route_mode": "routing_candidate",
                "route_authority": "authoritative" if level == "primary" else "supporting",
                "source_reliability": "merged_verified",
                **_base_doc(entity),
                "complaint_types": _complaint_types_for(label),
                "keywords": _keywords_for(entity, label),
                "not_responsible_for": summary.get("not_responsible_for", []),
                "description": _description(entity, sector, level),
                "confidence_prior": round(conf, 3),
                "hotline": _extract_hotline(entity),
                "responsibility_level": level,
                "location_precision": "entity_service_area",
                "exact_match_terms": _unique([entity["entity_name"], entity["short_name"], label], limit=12),
                "negative_signals": summary.get("not_responsible_for", []),
                "structured_fields": {"source_profile": "merged_entity_dossier", "sector": label},
                "retrieval_weight": 1.15 if level == "primary" else 0.95,
                "source_profile": "merged",
            }
            docs.append(doc)

        if summary.get("not_responsible_for") or summary.get("hitl_conditions") or summary.get("hitl_always_required"):
            boundary_text = (
                f"Boundary and human review rules for {entity['entity_name']}. "
                f"Do not route to {entity['entity_name']} for: "
                f"{'; '.join(summary.get('not_responsible_for', [])[:12]) or 'unspecified out-of-scope cases'}. "
                f"Human review conditions: {'; '.join(summary.get('hitl_conditions', [])[:12]) or 'ambiguous ownership or insufficient evidence'}."
            )
            docs.append({
                "doc_id": f"{entity_id.lower()}-boundary-hitl",
                "doc_type": "boundary_condition",
                "route_mode": "human_review_gate",
                "route_authority": "guardrail",
                "source_reliability": "merged_verified",
                "entity_name": "Human Review Queue",
                "entity_enum": "Human Review Queue",
                "entity_type": "review",
                "short_name": "HITL",
                "governs_nationally": True,
                "governorates": entity["governorates"],
                "districts": entity["districts"],
                "municipalities": entity["municipalities"],
                "complaint_types": _unique(["boundary_condition", "ambiguous_routing", "human_review", *_complaint_types_for(entity["entity_name"])], limit=14),
                "keywords": _keywords_for(entity, boundary_text),
                "not_responsible_for": summary.get("not_responsible_for", []),
                "description": _ascii_text(boundary_text),
                "confidence_prior": 0.78 if summary.get("hitl_always_required") else 0.70,
                "hotline": None,
                "source_entity_id": entity_id,
                "source_entity_aliases": entity["entity_aliases"],
                "source_ids": entity["sources"],
                "source_files": entity["source_files"],
                "last_reviewed": entity["last_reviewed"],
                "hitl_always_required": summary.get("hitl_always_required", False),
                "hitl_conditions": summary.get("hitl_conditions", []),
                "responsibility_level": "boundary",
                "location_precision": "entity_or_case_specific",
                "exact_match_terms": _unique([entity["entity_name"], entity["short_name"], "human review", "boundary"], limit=12),
                "negative_signals": summary.get("not_responsible_for", []),
                "structured_fields": {"source_profile": "merged_entity_boundary", "source_entity_id": entity_id},
                "retrieval_weight": 1.05,
                "source_profile": "merged",
            })

    seen: set[str] = set()
    unique_docs = []
    for doc in docs:
        base_id = doc["doc_id"]
        doc_id = base_id
        i = 2
        while doc_id in seen:
            doc_id = f"{base_id}-{i}"
            i += 1
        doc["doc_id"] = doc_id
        seen.add(doc_id)
        unique_docs.append(doc)
    return sorted(unique_docs, key=lambda d: d["doc_id"])


def _discover_source_data_root() -> Path | None:
    for path in SOURCE_DATA_ROOT_CANDIDATES:
        if (path / "knowledge_base").exists():
            return path
    return None


def _read_v74_csv(filename: str) -> tuple[list[dict[str, str]], str]:
    internal = (
        "cedarfix_batch5_v74_gap_resolution_handoff/"
        f"latest_v74_gap_resolution/{filename}"
    )
    for zip_path in V74_ZIP_CANDIDATES:
        if not zip_path.exists():
            continue
        with zipfile.ZipFile(zip_path) as zf:
            try:
                with zf.open(internal) as f:
                    text = io.TextIOWrapper(f, encoding="utf-8-sig", newline="")
                    return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(text)], (
                        f"external_zip:{zip_path.name}!/{internal}"
                    )
            except KeyError:
                continue
    return [], f"missing_external_zip:{filename}"


def _build_taxonomy_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "complaint_taxonomy.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        complaint_type = row.get("complaint_type", "")
        if not complaint_type:
            continue
        selector = row.get("default_primary_entity_selector", "HITL")
        desc = (
            f"Complaint taxonomy entry {row.get('complaint_type_id')} maps category "
            f"{row.get('category')} and complaint type {complaint_type} to selector {selector}. "
            f"Minimum location precision: {row.get('minimum_location_precision') or 'not specified'}. "
            f"Routing notes: {row.get('routing_notes') or 'none'}. "
            f"Human review default: {row.get('hitl_default') or 'false'}."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"taxonomy-{row.get('complaint_type_id') or complaint_type}",
            selector=selector,
            description=desc,
            doc_type="complaint_taxonomy",
            route_mode="query_and_type_expansion",
            route_authority="supporting",
            source_reliability=row.get("status") or "seed",
            complaint_types=[complaint_type, row.get("category", ""), row.get("complaint_type_id", "")],
            keywords=[complaint_type, row.get("category", ""), row.get("minimum_location_precision", ""), row.get("routing_notes", "")],
            source_files=[_portable_path(path)],
            confidence_prior=0.72,
            responsibility_level="context",
            hitl_required=_truthy(row.get("hitl_default")),
            hitl_conditions=[row.get("routing_notes", "")] if _truthy(row.get("hitl_default")) else [],
            location_precision=row.get("minimum_location_precision"),
            exact_match_terms=[complaint_type, row.get("complaint_type_id", "")],
            structured_fields={**row, "source_profile": "complaint_taxonomy"},
            retrieval_weight=0.75,
        ))
    return docs


def _build_routing_rule_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "routing_rules.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        rule_id = row.get("rule_id", "")
        complaint_type = row.get("complaint_type", "")
        selector = row.get("primary_entity_selector", "HITL")
        desc = (
            f"Routing rule {rule_id} for complaint type {complaint_type}. "
            f"Condition: {row.get('condition')}. Primary selector: {selector}. "
            f"Secondary selector: {row.get('secondary_entity_selector') or 'none'}. "
            f"HITL required: {row.get('hitl_required')}. HITL reason: {row.get('hitl_reason') or 'none'}. "
            f"False positive risk: {row.get('false_positive_risk') or 'not specified'}. "
            f"Evidence required for production: {row.get('evidence_required_for_production') or 'not specified'}."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"routing-rule-{rule_id or complaint_type}",
            selector=selector,
            description=desc,
            doc_type="routing_rule",
            route_mode="routing_rule",
            route_authority="authoritative_rule",
            source_reliability=row.get("status") or "seed_rule",
            complaint_types=[complaint_type, row.get("complaint_type_id", "")],
            keywords=[complaint_type, row.get("condition", ""), selector, row.get("secondary_entity_selector", "")],
            not_responsible_for=[row.get("false_positive_risk", "")],
            source_ids=_row_source_ids(row),
            source_files=[_portable_path(path)],
            confidence_prior=_confidence(row.get("confidence", "medium_high")),
            responsibility_level="primary" if not _truthy(row.get("hitl_required")) else "boundary",
            hitl_required=_truthy(row.get("hitl_required")),
            hitl_conditions=[row.get("hitl_reason", ""), row.get("evidence_required_for_production", "")],
            exact_match_terms=[rule_id, complaint_type, row.get("complaint_type_id", "")],
            negative_signals=[row.get("false_positive_risk", "")],
            structured_fields={**row, "source_profile": "routing_rules"},
            retrieval_weight=1.25,
        ))
    return docs


def _build_remediation_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "remediation_workflows.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        complaint_type = row.get("complaint_type", "")
        text = " ".join(row.values())
        selector = _selector_entity_id("CD" if "fire" in _slug(text) else ("MOE" if "hazardous" in _slug(text) else "MUN"))
        desc = (
            f"Resolution workflow {row.get('workflow_id')} for {complaint_type}. "
            f"Intake: {row.get('intake_stage')}. Triage: {row.get('triage_stage')}. "
            f"Referral: {row.get('referral_stage')}. Field remediation: {row.get('field_remediation_stage')}. "
            f"Closure criteria: {row.get('closure_criteria')}. SLA policy: {row.get('official_sla_policy')}. "
            f"Deadline policy: {row.get('deadline_policy')}."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"workflow-{row.get('workflow_id') or complaint_type}",
            selector=selector,
            description=desc,
            doc_type="remediation_workflow",
            route_mode="resolution_context",
            route_authority="supporting",
            source_reliability=row.get("status") or "seed_workflow",
            complaint_types=[complaint_type, row.get("complaint_type_id", "")],
            keywords=[complaint_type, row.get("intake_stage", ""), row.get("triage_stage", ""), row.get("referral_stage", "")],
            source_ids=_row_source_ids(row),
            source_files=[_portable_path(path)],
            confidence_prior=_confidence(row.get("confidence", "medium")),
            responsibility_level="context",
            hitl_conditions=[row.get("deadline_policy", "")],
            exact_match_terms=[row.get("workflow_id", ""), complaint_type],
            structured_fields={**row, "source_profile": "remediation_workflows"},
            retrieval_weight=0.85,
        ))
    return docs


def _build_root_boundary_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "entity_boundary_conditions.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        selector = row.get("override_entity") or row.get("primary_entity") or "HITL"
        desc = (
            f"Boundary condition {row.get('bc_id')} for signal {row.get('complaint_signal')}. "
            f"Condition: {row.get('condition_description')}. Primary entity: {row.get('primary_entity')}. "
            f"Co-entity: {row.get('co_entity') or 'none'}. Override entity: {row.get('override_entity') or 'none'}. "
            f"Routing note: {row.get('routing_note')}. Human review: {row.get('hitl_required')} {row.get('hitl_reason')}."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"boundary-{row.get('bc_id')}",
            selector=selector,
            description=desc,
            doc_type="boundary_condition",
            route_mode="routing_guardrail",
            route_authority="guardrail",
            source_reliability="seed_boundary",
            complaint_types=[row.get("complaint_signal", "")],
            keywords=[row.get("complaint_signal", ""), row.get("condition_description", ""), row.get("primary_entity", ""), row.get("co_entity", "")],
            source_files=[_portable_path(path)],
            confidence_prior=0.82,
            responsibility_level="boundary" if _truthy(row.get("hitl_required")) else "primary",
            hitl_required=_truthy(row.get("hitl_required")),
            hitl_conditions=[row.get("hitl_reason", ""), row.get("routing_note", "")],
            exact_match_terms=[row.get("bc_id", ""), row.get("complaint_signal", "")],
            structured_fields={**row, "source_profile": "entity_boundary_conditions"},
            retrieval_weight=1.2,
        ))
    return docs


def _domain_dirs(source_root: Path) -> list[Path]:
    kb = source_root / "knowledge_base"
    excluded = {"arabizi", "entities", "municipalities", "channel_discovery"}
    return [p for p in sorted(kb.iterdir()) if p.is_dir() and p.name not in excluded]


def _build_domain_guardrail_docs(source_root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for directory in _domain_dirs(source_root):
        boundary = directory / "boundary_conditions.csv"
        for row in _read_csv(boundary):
            selector = row.get("default_entity") or row.get("primary_entity") or row.get("entity_id") or row.get("owner_entity_id") or "HITL"
            condition_id = row.get("condition_id") or row.get("boundary_id") or row.get("road_index_id") or row.get("coverage_id")
            desc = (
                f"{directory.name} boundary/guardrail {condition_id}. Trigger: {row.get('trigger') or row.get('condition') or row.get('routing_use')}. "
                f"Decision rule: {row.get('decision_rule') or row.get('routing_use') or row.get('notes')}. "
                f"Secondary entity: {row.get('secondary_entity') or row.get('secondary_entities') or 'none'}. "
                f"Examples: omitted for formal corpus mode. Limitations: {row.get('limitations') or row.get('notes') or 'none'}."
            )
            _append_unique_doc(docs, _doc_base(
                doc_id=f"{directory.name}-boundary-{condition_id}",
                selector=selector,
                description=desc,
                doc_type="boundary_condition",
                route_mode="routing_guardrail",
                route_authority="guardrail",
                source_reliability=row.get("verification_status") or "domain_boundary",
                complaint_types=_split_values(row.get("trigger") or row.get("condition") or row.get("routing_use") or directory.name),
                keywords=[directory.name, row.get("trigger", ""), row.get("decision_rule", ""), row.get("routing_use", "")],
                source_ids=_row_source_ids(row),
                source_files=[_portable_path(boundary)],
                confidence_prior=_confidence_from_row(row, 0.76),
                responsibility_level="boundary",
                hitl_required=_truthy(row.get("hitl_required")),
                hitl_conditions=[row.get("decision_rule", ""), row.get("notes", ""), row.get("limitations", "")],
                exact_match_terms=[condition_id, row.get("trigger", "")],
                structured_fields={**row, "source_profile": f"{directory.name}_boundary"},
                retrieval_weight=1.1,
            ))

        not_resp = directory / "not_responsible_for.csv"
        for row in _read_csv(not_resp):
            boundary_id = row.get("boundary_id") or row.get("id") or row.get("condition_id")
            desc = (
                f"{row.get('entity_id')} is not responsible for {row.get('not_responsible_for')}. "
                f"Route instead to {row.get('route_instead_to') or 'human review'} when condition applies: {row.get('condition')}. "
                f"Notes: {row.get('notes')}."
            )
            _append_unique_doc(docs, _doc_base(
                doc_id=f"{directory.name}-not-responsible-{boundary_id}",
                selector=row.get("entity_id") or "HITL",
                description=desc,
                doc_type="not_responsible_guardrail",
                route_mode="negative_boundary",
                route_authority="guardrail",
                source_reliability="domain_boundary",
                complaint_types=_split_values(row.get("not_responsible_for") or directory.name),
                keywords=[directory.name, row.get("not_responsible_for", ""), row.get("route_instead_to", ""), row.get("condition", "")],
                not_responsible_for=[row.get("not_responsible_for", "")],
                source_ids=_row_source_ids(row),
                source_files=[_portable_path(not_resp)],
                confidence_prior=_confidence_from_row(row, 0.74),
                responsibility_level="boundary",
                hitl_required=True,
                hitl_conditions=[row.get("condition", ""), row.get("notes", "")],
                exact_match_terms=[boundary_id, row.get("not_responsible_for", "")],
                negative_signals=[row.get("not_responsible_for", "")],
                structured_fields={**row, "source_profile": f"{directory.name}_not_responsible"},
                retrieval_weight=1.2,
            ))
    return docs


def _build_domain_service_docs(source_root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for directory in _domain_dirs(source_root):
        for filename, doc_type, mode, weight in [
            ("complaint_channels.csv", "complaint_channel", "complaint_intake_or_channel", 1.05),
            ("contact_points.csv", "contact_point", "contact_context", 0.75),
            ("sla_policy.csv", "sla_policy", "resolution_policy", 0.85),
            ("branch_service_areas.csv", "service_area", "geo_service_area", 1.05),
            ("water_service_catalog.csv", "service_catalog", "service_catalog", 0.9),
            ("road_class_ownership_index.csv", "road_ownership", "routing_guardrail", 1.2),
            ("waste_operator_coverage.csv", "operator_coverage", "operator_context", 1.05),
            ("irrigation_boundaries.csv", "irrigation_boundary", "routing_guardrail", 1.1),
            ("mobile_operator_channels.csv", "mobile_operator_channel", "complaint_intake_or_channel", 1.0),
            ("trusted_context.csv", "trusted_context", "supporting_context", 0.8),
        ]:
            path = directory / filename
            for row in _read_csv(path):
                row_id = (
                    row.get("channel_id") or row.get("contact_id") or row.get("sla_id") or row.get("area_id") or
                    row.get("service_id") or row.get("road_index_id") or row.get("coverage_id") or row.get("context_id") or
                    row.get("boundary_id") or row.get("id") or f"{filename}-{len(docs)}"
                )
                selector = (
                    row.get("entity_id") or row.get("owner_entity_id") or row.get("primary_responsible_entity") or
                    row.get("water_establishment_id") or row.get("electricity_entity_id") or row.get("default_entity") or "HITL"
                )
                accepted = row.get("accepted") or row.get("routing_use") or row.get("safe_use") or row.get("verification_status")
                route_mode = mode
                authority = "supporting"
                hitl = _truthy(row.get("hitl_required"))
                if doc_type == "complaint_channel" and _slug(row.get("accepted")) == "yes":
                    authority = "verified_channel"
                if "not_published" in _slug(row.get("official_sla")) or "do_not_promise" in _slug(" ".join(row.values())):
                    authority = "guardrail"
                desc = (
                    f"{directory.name} {doc_type} {row_id}. "
                    f"Entity/owner: {selector}. Complaint/service type: {row.get('complaint_type') or row.get('service_family') or row.get('service_name') or row.get('road_class_or_asset_type')}. "
                    f"Channel/contact/endpoint: {row.get('channel_type') or row.get('contact_name') or row.get('endpoint') or row.get('branch_name') or row.get('operator_or_actor') or 'not specified'}. "
                    f"Geographic context: {row.get('municipality_or_area') or row.get('municipality_scope') or row.get('coverage_area') or row.get('district_or_area') or row.get('location_hint') or 'not specified'}. "
                    f"Rule/evidence: {row.get('notes') or row.get('evidence_summary') or row.get('routing_use') or row.get('official_sla') or row.get('emergency_policy') or accepted}."
                )
                _append_unique_doc(docs, _doc_base(
                    doc_id=f"{directory.name}-{doc_type}-{row_id}",
                    selector=selector,
                    description=desc,
                    doc_type=doc_type,
                    route_mode=route_mode,
                    route_authority=authority,
                    source_reliability=row.get("verification_status") or row.get("confidence") or "domain_source",
                    complaint_types=_split_values(row.get("complaint_type") or row.get("service_family") or row.get("routing_use") or doc_type),
                    keywords=[directory.name, filename, row.get("complaint_type", ""), row.get("channel_type", ""), row.get("endpoint", ""), row.get("evidence_summary", ""), row.get("notes", "")],
                    source_ids=_row_source_ids(row),
                    source_files=[_portable_path(path)],
                    confidence_prior=_confidence_from_row(row, 0.76),
                    responsibility_level="context" if doc_type in {"contact_point", "sla_policy", "trusted_context"} else "primary",
                    hitl_required=hitl,
                    hitl_conditions=[row.get("notes", ""), row.get("limitations", ""), row.get("emergency_policy", "")],
                    governorates=[row.get("governorate") or row.get("governorate_en", "")],
                    districts=[row.get("district_or_area") or row.get("district_en", "")],
                    municipalities=[row.get("municipality_scope") or row.get("municipality_or_area", "")],
                    hotline=row.get("endpoint") if _slug(row.get("channel_type")) == "phone" else None,
                    exact_match_terms=[row_id, row.get("endpoint", ""), row.get("operator_or_actor", ""), row.get("road_name_or_ref", "")],
                    negative_signals=[row.get("limitations", "")],
                    structured_fields={**row, "source_profile": f"{directory.name}_{doc_type}"},
                    retrieval_weight=weight,
                ))
    return docs


def _build_municipality_service_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "municipalities" / "municipality_service_mappings.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        mun_name = _first_ascii(
            row.get("name_en"),
            row.get("name_ar"),
            row.get("registry_id"),
            row.get("municipality_id"),
        )
        if not mun_name:
            continue
        base_terms = [mun_name, row.get("name_ar", ""), row.get("registry_id", ""), row.get("municipality_id", "")]
        gov = [row.get("governorate_en", "")]
        district = [row.get("district_en", "")]
        mun = [mun_name]
        services = [
            ("water", row.get("water_establishment_id"), row.get("water_establishment_name"), row.get("water_notes"), row.get("water_confidence"), "water_outage;water_pipe;sewage_overflow"),
            ("electricity", row.get("electricity_entity_id"), row.get("electricity_entity_name"), row.get("electricity_notes"), row.get("electricity_confidence"), "electricity_outage;streetlight;power_line_fault"),
            ("fixed_telecom", row.get("fixed_telecom_entity_id"), row.get("fixed_telecom_entity_name"), row.get("telecom_notes"), "medium_high", "internet_outage;dsl_fault;landline_fault"),
            ("local_road", row.get("local_road_entity_id"), "Local Municipality", row.get("road_notes"), "medium_high", "local_road_damage;sidewalk_obstruction;pothole"),
            ("national_road", row.get("national_road_entity_id"), "Ministry of Public Works", row.get("road_notes"), "medium", "highway;classified_road;bridge_damage"),
        ]

        mapped_services: list[str] = []
        confidence_values: list[float] = []
        all_complaint_types: list[str] = []
        all_keywords: list[str] = [*base_terms]
        all_notes: list[str] = []

        for service, selector, entity_name, notes, conf, complaint_types in services:
            if not selector:
                continue
            mapped_services.append(f"{service} -> {entity_name or selector} ({selector})")
            confidence_values.append(_confidence(conf or "medium"))
            all_complaint_types.extend(_split_values(complaint_types))
            all_keywords.extend([service, selector, entity_name or "", notes or ""])
            if notes:
                all_notes.append(notes)

        if not mapped_services:
            continue

        notes_summary = " ".join(_unique(all_notes, limit=3))
        desc = (
            f"Municipality service bundle for {mun_name}, {row.get('district_en')}, {row.get('governorate_en')}. "
            "Use this as geo routing context and validate complaint type plus location before dispatch. "
            f"Mapped services: {'; '.join(mapped_services)}. "
            f"Notes: {notes_summary}. Source basis: {row.get('source_basis')}. Last built: {row.get('last_built')}."
        )

        _append_unique_doc(docs, _doc_base(
            doc_id=f"mun-service-bundle-{row.get('registry_id') or row.get('municipality_id')}",
            selector="MUN",
            description=desc,
            doc_type="municipality_service_map",
            route_mode="geo_service_route",
            route_authority="location_map_bundle",
            source_reliability=row.get("source_basis") or "municipality_map",
            complaint_types=_unique(all_complaint_types, limit=24),
            keywords=_unique(all_keywords, limit=64),
            source_files=[_portable_path(path)],
            confidence_prior=sum(confidence_values) / len(confidence_values),
            responsibility_level="context",
            hitl_required=True,
            hitl_conditions=[
                "Geo mapping is advisory. Confirm service type, location precision, and road class before dispatch.",
                notes_summary,
            ],
            governorates=gov,
            districts=district,
            municipalities=mun,
            exact_match_terms=[*base_terms, *mapped_services],
            location_precision="municipality",
            structured_fields={**row, "source_profile": "municipality_service_mapping_bundle", "mapped_services": "; ".join(mapped_services)},
            retrieval_weight=1.15,
        ))
    return docs


def _build_municipality_channel_docs(source_root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    mun_dir = source_root / "knowledge_base" / "municipalities"
    for filename, doc_type, mode, weight in [
        ("municipality_official_channels.csv", "municipality_channel", "complaint_intake_or_channel", 1.2),
        ("municipality_complaint_workflows.csv", "municipality_workflow", "complaint_workflow", 1.25),
        ("municipal_union_service_responsibilities.csv", "municipal_union_service", "shared_service_context", 0.95),
    ]:
        path = mun_dir / filename
        for row in _read_csv(path):
            row_id = row.get("channel_id") or row.get("workflow_id") or row.get("membership_id") or row.get("responsibility_id") or f"{filename}-{len(docs)}"
            name = _first_ascii(
                row.get("name_en"),
                row.get("municipality_name_en"),
                row.get("municipality_match_key"),
                row.get("municipality_id"),
                row.get("union_name_en"),
                row.get("union_id"),
            )
            desc = (
                f"{doc_type} {row_id} for {name}. "
                f"Channel/workflow type: {row.get('channel_type') or row.get('workflow_source_type') or row.get('service_family') or 'not specified'}. "
                f"Value or URL: {row.get('channel_value') or row.get('channel_url') or row.get('workflow_url') or row.get('source_url') or 'not specified'}. "
                f"Accepted categories: {row.get('accepted_complaint_categories') or row.get('service_responsibility') or 'not specified'}. "
                f"Evidence: {row.get('evidence_snippet') or row.get('notes') or 'not specified'}."
            )
            _append_unique_doc(docs, _doc_base(
                doc_id=f"municipality-{doc_type}-{row_id}",
                selector="MUN",
                description=desc,
                doc_type=doc_type,
                route_mode=mode,
                route_authority="verified_channel" if "verified" in _slug(row.get("verification_status") or row.get("workflow_confidence")) else "supporting",
                source_reliability=row.get("verification_status") or row.get("workflow_confidence") or row.get("confidence") or "municipal_source",
                complaint_types=_split_values(row.get("accepted_complaint_categories") or row.get("service_family") or doc_type),
                keywords=[
                    name,
                    row.get("channel_type", ""),
                    row.get("channel_value", ""),
                    row.get("accepted_complaint_categories", ""),
                    row.get("service_family", ""),
                    row.get("role_type", ""),
                    row.get("union_id", ""),
                    row.get("union_name_en", ""),
                    row.get("union_name_ar", ""),
                    row.get("operator_or_entity", ""),
                    row.get("evidence_snippet", ""),
                ],
                source_ids=_row_source_ids(row),
                source_files=[_portable_path(path)],
                confidence_prior=_confidence_from_row(row, 0.78),
                responsibility_level="primary" if doc_type in {"municipality_channel", "municipality_workflow"} else "context",
                hitl_required=not ("verified_high" in _slug(row.get("workflow_confidence")) or "verified_official" in _slug(row.get("verification_status"))),
                hitl_conditions=[row.get("notes", ""), row.get("evidence_snippet", "")],
                governorates=[row.get("governorate_en") or row.get("governorate", "")],
                districts=[row.get("district_en") or row.get("district_if_available", "")],
                municipalities=[name],
                exact_match_terms=[
                    name,
                    row.get("name_ar", ""),
                    row.get("municipality_match_key", ""),
                    row.get("union_id", ""),
                    row.get("union_name_en", ""),
                    row.get("union_name_ar", ""),
                    row_id,
                ],
                location_precision="municipality",
                structured_fields={**row, "source_profile": f"municipality_{doc_type}"},
                retrieval_weight=weight,
            ))

    # Bundle municipal union membership rows into one richer document per union.
    service_hints_by_union: dict[str, list[str]] = defaultdict(list)
    service_path = mun_dir / "municipal_union_service_responsibilities.csv"
    for row in _read_csv(service_path):
        hints = _unique(
            [
                row.get("service_family", ""),
                row.get("role_type", ""),
                row.get("member_scope", ""),
                row.get("operator_or_entity", ""),
            ],
            limit=12,
        )
        alias_keys = {
            _slug(row.get("union_id", "")),
            _slug(row.get("union_name_en", "")),
            _slug(row.get("union_name_ar", "")),
        }
        for key in {k for k in alias_keys if k}:
            service_hints_by_union[key].extend(hints)

    memberships_path = mun_dir / "municipal_union_memberships.csv"
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_csv(memberships_path):
        union_key = _slug(row.get("union_id") or row.get("union_name_en") or row.get("union_name_ar"))
        if union_key:
            grouped[union_key].append(row)

    for union_key, rows in sorted(grouped.items()):
        first = rows[0]
        union_id = _first_ascii(first.get("union_id"), union_key.upper())
        union_name = _first_ascii(first.get("union_name_en"), first.get("union_name_ar"), union_id)
        union_aliases = _unique([first.get("union_name_en", ""), first.get("union_name_ar", ""), union_id, union_name], limit=12)

        member_names = _unique([
            _first_ascii(
                row.get("member_municipality_name_en"),
                row.get("member_municipality_name_ar"),
                row.get("member_municipality_key"),
                row.get("member_municipality_id"),
                row.get("member_registry_id"),
            )
            for row in rows
        ], limit=120)
        member_ids = _unique([
            row.get("member_registry_id") or row.get("member_municipality_id")
            for row in rows
        ], limit=120)
        member_keys = _unique([row.get("member_municipality_key", "") for row in rows], limit=120)
        governorates = _unique([row.get("governorate_en", "") for row in rows], limit=8)
        districts = _unique([row.get("district_en", "") for row in rows], limit=30)
        verification_status = _unique([row.get("verification_status", "") for row in rows], limit=6)
        notes = _unique([row.get("notes", "") for row in rows], limit=4)
        confidence_values = [_confidence(row.get("confidence", "medium")) for row in rows]
        confidence_prior = sum(confidence_values) / len(confidence_values) if confidence_values else 0.78

        source_ids_raw: list[str] = []
        for row in rows:
            source_ids_raw.extend(_row_source_ids(row))

        service_hints_raw: list[str] = []
        for key in {
            union_key,
            _slug(first.get("union_id", "")),
            _slug(first.get("union_name_en", "")),
            _slug(first.get("union_name_ar", "")),
        }:
            if key:
                service_hints_raw.extend(service_hints_by_union.get(key, []))
        service_hints = _unique(service_hints_raw, limit=16)

        sample_members = "; ".join(member_names[:8]) if member_names else "not specified"
        service_hint_text = "; ".join(service_hints) if service_hints else "membership_metadata"
        desc = (
            f"Municipal union membership bundle for {union_name} ({union_id}). "
            f"This union includes {len(member_names)} municipalities across {', '.join(governorates) or 'unspecified governorates'}. "
            f"District coverage: {', '.join(districts[:12]) or 'unspecified'}. "
            f"Representative member municipalities: {sample_members}. "
            f"Service-family hints from union records: {service_hint_text}. "
            "Use membership as geo/governance context only; do not treat union membership alone as proof of dispatch ownership."
        )

        _append_unique_doc(docs, _doc_base(
            doc_id=f"municipality-municipal_union_membership-bundle-{union_id or union_key}",
            selector="MUN",
            description=desc,
            doc_type="municipal_union_membership",
            route_mode="geo_union_context",
            route_authority="geo_union_membership_bundle",
            source_reliability=verification_status[0] if verification_status else "union_membership_context",
            complaint_types=_unique([
                "municipal_union_membership",
                "inter_municipal_coordination",
                "shared_service_context",
                *service_hints,
            ], limit=24),
            keywords=_unique([
                union_name,
                union_id,
                *union_aliases,
                *governorates,
                *districts,
                *member_names[:45],
                *member_ids[:35],
                *member_keys[:35],
                *service_hints,
                *verification_status,
                *notes,
            ], limit=120),
            source_ids=_unique(source_ids_raw, limit=30),
            source_files=[_portable_path(memberships_path)],
            confidence_prior=confidence_prior,
            responsibility_level="context",
            hitl_required=True,
            hitl_conditions=[
                "Union membership does not by itself prove field-service ownership or intake authority.",
                *notes,
            ],
            governorates=governorates,
            districts=districts,
            municipalities=member_names[:60],
            exact_match_terms=_unique([
                union_id,
                union_name,
                *union_aliases,
                *member_ids[:25],
                *member_keys[:25],
            ], limit=80),
            location_precision="municipal_union",
            structured_fields={
                "source_profile": "municipality_municipal_union_membership_bundle",
                "union_id": union_id,
                "union_name": union_name,
                "union_aliases": "; ".join(union_aliases),
                "member_count": len(member_names),
                "member_registry_or_municipality_ids": "; ".join(member_ids[:80]),
                "member_match_keys": "; ".join(member_keys[:80]),
                "service_family_hints": "; ".join(service_hints),
                "verification_status": "; ".join(verification_status),
                "last_checked": max((row.get("last_checked", "") for row in rows), default=""),
                "source_file": _portable_path(memberships_path),
            },
            retrieval_weight=0.98,
        ))
    return docs


def _build_municipality_registry_profile_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "municipalities" / "national_municipality_registry.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        registry_id = _ascii_text(row.get("registry_id"))
        municipality_id = _ascii_text(row.get("municipality_id"))
        municipality_name = _first_ascii(
            row.get("name_en"),
            row.get("name_ar"),
            row.get("name_raw_en_page"),
            row.get("name_raw_ar_page"),
            registry_id,
            municipality_id,
        )
        if not municipality_name:
            continue

        governorate = _first_ascii(row.get("governorate_en"), row.get("moim_2025_governorate_ar"))
        district = _first_ascii(row.get("district_en"), row.get("moim_2025_district_ar"))

        website = _ascii_text(row.get("website"))
        form_url = _ascii_text(row.get("form_url"))
        townhall_phone = _ascii_text(row.get("townhall_phone"))
        official_website_status = _ascii_text(row.get("official_website_status"))
        complaint_form_status = _ascii_text(row.get("complaint_form_status"))
        extracted_contacts = _ascii_text(row.get("extracted_contacts"))

        desc = (
            f"Municipality registry profile for {municipality_name} "
            f"({registry_id or municipality_id or 'no_registry_id'}). "
            f"Administrative scope: district {district or 'unknown'}, governorate {governorate or 'unknown'}. "
            f"Location: lat={row.get('latitude') or 'unknown'}, lon={row.get('longitude') or 'unknown'}, has_coordinates={row.get('has_coordinates') or 'unknown'}. "
            f"Contact context: website={website or 'not_found'}, form={form_url or 'not_found'}, townhall_phone={townhall_phone or 'not_found'}. "
            f"Verification status: official_website_status={official_website_status or 'unknown'}, complaint_form_status={complaint_form_status or 'unknown'}. "
            f"Research guidance: {row.get('recommended_next_action') or row.get('reason_codes') or 'none'}."
        )

        has_verified_contact = any([
            website,
            form_url,
            townhall_phone,
        ]) and "not_found" not in _slug(official_website_status)

        _append_unique_doc(docs, _doc_base(
            doc_id=f"municipality-registry-profile-{registry_id or municipality_id}",
            selector="MUN",
            description=desc,
            doc_type="municipality_registry_profile",
            route_mode="geo_district_reference",
            route_authority="verified_channel" if has_verified_contact else "supporting",
            source_reliability=row.get("best_source_confidence") or row.get("official_website_status") or "registry_context",
            complaint_types=[
                "municipality_location_resolution",
                "municipality_contact_context",
                row.get("coverage_status", ""),
            ],
            keywords=[
                municipality_name,
                row.get("name_ar", ""),
                row.get("name_raw_en_page", ""),
                row.get("name_raw_ar_page", ""),
                registry_id,
                municipality_id,
                governorate,
                district,
                website,
                form_url,
                townhall_phone,
                extracted_contacts,
                row.get("service_scope", ""),
                row.get("reason_codes", ""),
            ],
            source_ids=_unique([
                *_row_source_ids(row),
                row.get("dglac_source_url_en", ""),
                row.get("dglac_source_url_ar", ""),
            ], limit=20),
            source_files=[_portable_path(path)],
            confidence_prior=_confidence_from_tier(row.get("research_tier"), default=0.72),
            responsibility_level="context",
            hitl_required=not has_verified_contact,
            hitl_conditions=[
                row.get("reason_codes", ""),
                "Missing verified municipality contact requires human review." if not has_verified_contact else "",
            ],
            governorates=[governorate],
            districts=[district],
            municipalities=[municipality_name],
            hotline=townhall_phone or None,
            exact_match_terms=[
                municipality_name,
                row.get("name_ar", ""),
                registry_id,
                municipality_id,
                district,
                governorate,
            ],
            location_precision="municipality",
            structured_fields={**row, "source_profile": "municipality_registry_profile"},
            retrieval_weight=0.9,
        ))
    return docs


def _build_municipality_contact_candidate_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "municipalities" / "municipality_townhall_contact_candidates_2026-06-01.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        municipality_id = _ascii_text(row.get("municipality_id"))
        municipality_name = _first_ascii(row.get("name_en"), row.get("name_ar"), municipality_id)
        if not municipality_name:
            continue

        candidate_website = _ascii_text(row.get("candidate_website"))
        candidate_email = _ascii_text(row.get("candidate_email"))
        candidate_phone = _ascii_text(row.get("candidate_phone"))
        source_confidence = _ascii_text(row.get("source_confidence"))
        promotion_rule = _ascii_text(row.get("promotion_rule"))

        desc = (
            f"Municipality contact candidate for {municipality_name} ({municipality_id}). "
            f"Candidate website={candidate_website or 'none'}, email={candidate_email or 'none'}, phone={candidate_phone or 'none'}. "
            f"Status: official_website_status={row.get('official_website_status') or 'unknown'}, complaint_form_status={row.get('complaint_form_status') or 'unknown'}, "
            f"source_confidence={source_confidence or 'unknown'}. "
            f"Promotion rule: {promotion_rule or 'candidate_only_until_official_confirmation'}."
        )

        _append_unique_doc(docs, _doc_base(
            doc_id=f"municipality-contact-candidate-{municipality_id}-{row.get('research_rank') or len(docs)}",
            selector="MUN",
            description=desc,
            doc_type="municipality_contact_candidate",
            route_mode="contact_fallback_only",
            route_authority="supporting",
            source_reliability=source_confidence or row.get("official_website_status") or "candidate_contact",
            complaint_types=[
                "municipality_contact_missing",
                "candidate_contact_review",
            ],
            keywords=[
                municipality_name,
                row.get("name_ar", ""),
                municipality_id,
                row.get("governorate_en", ""),
                row.get("district_en", ""),
                candidate_website,
                candidate_email,
                candidate_phone,
                source_confidence,
                promotion_rule,
            ],
            source_files=[_portable_path(path)],
            confidence_prior=_confidence(source_confidence or "low"),
            responsibility_level="context",
            hitl_required=True,
            hitl_conditions=[
                promotion_rule,
                "Candidate contact is non-authoritative until verified from an official municipality source.",
            ],
            governorates=[row.get("governorate_en", "")],
            districts=[row.get("district_en", "")],
            municipalities=[municipality_name],
            exact_match_terms=[
                municipality_name,
                row.get("name_ar", ""),
                municipality_id,
                candidate_phone,
                candidate_email,
                candidate_website,
            ],
            location_precision="municipality",
            structured_fields={**row, "source_profile": "municipality_contact_candidate"},
            retrieval_weight=0.58,
        ))
    return docs


def _build_municipality_discovery_queue_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "municipalities" / "municipality_channel_discovery_queue_2026-06-01.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        municipality_id = _ascii_text(row.get("municipality_id"))
        municipality_name = _first_ascii(row.get("name_en"), row.get("name_ar"), municipality_id)
        if not municipality_name:
            continue

        desc = (
            f"Municipality channel discovery queue item for {municipality_name} ({municipality_id}). "
            f"Coverage status: {row.get('coverage_status') or 'unknown'}. "
            f"Known channel types: {row.get('verified_channel_types') or 'none'}. "
            f"Current registry contact hints: website={row.get('registry_website') or 'none'}, phone={row.get('registry_phone') or 'none'}, "
            f"townhall_website={row.get('townhall_website') or 'none'}, townhall_phone={row.get('townhall_phone') or 'none'}. "
            f"Next action: {row.get('next_action') or 'manual_discovery_required'}."
        )

        _append_unique_doc(docs, _doc_base(
            doc_id=f"municipality-channel-discovery-{municipality_id}-{row.get('research_rank') or len(docs)}",
            selector="HITL",
            description=desc,
            doc_type="municipality_channel_discovery_queue",
            route_mode="human_review_user_assist",
            route_authority="manual_review_gate",
            source_reliability=row.get("official_website_status") or row.get("complaint_form_status") or "discovery_queue",
            complaint_types=[
                "municipality_contact_missing",
                "manual_review",
                "channel_discovery",
            ],
            keywords=[
                municipality_name,
                row.get("name_ar", ""),
                municipality_id,
                row.get("governorate_en", ""),
                row.get("district_en", ""),
                row.get("coverage_status", ""),
                row.get("verified_channel_types", ""),
                row.get("registry_website", ""),
                row.get("registry_phone", ""),
                row.get("townhall_phone", ""),
                row.get("next_action", ""),
            ],
            source_files=[_portable_path(path)],
            confidence_prior=0.68,
            responsibility_level="context",
            hitl_required=True,
            hitl_conditions=[
                row.get("next_action", ""),
                "No automatic channel promotion from discovery queue entries.",
            ],
            governorates=[row.get("governorate_en", "")],
            districts=[row.get("district_en", "")],
            municipalities=[municipality_name],
            exact_match_terms=[
                municipality_name,
                row.get("name_ar", ""),
                municipality_id,
                row.get("coverage_status", ""),
            ],
            location_precision="municipality",
            structured_fields={**row, "source_profile": "municipality_channel_discovery_queue"},
            retrieval_weight=0.52,
        ))
    return docs


def _build_towns_registry_reference_docs(source_root: Path) -> list[dict[str, Any]]:
    towns_path = source_root / "knowledge_base" / "municipalities" / "towns_registry.csv"
    registry_path = source_root / "knowledge_base" / "municipalities" / "national_municipality_registry.csv"
    town_rows = _read_csv(towns_path)
    registry_rows = _read_csv(registry_path)
    if not town_rows:
        return []

    registry_index: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in registry_rows:
        district_keys = {
            _slug(row.get("district_en")),
            _slug(row.get("moim_2025_district_ar")),
        }
        name_keys = {
            _slug(row.get("name_en")),
            _slug(row.get("name_ar")),
            _slug(row.get("name_raw_en_page")),
            _slug(row.get("name_raw_ar_page")),
        }
        for district_key in {k for k in district_keys if k and k != "unknown"}:
            for name_key in {k for k in name_keys if k and k != "unknown"}:
                registry_index[(name_key, district_key)].append(row)

    docs: list[dict[str, Any]] = []
    for row in town_rows:
        town_name = _first_ascii(row.get("name_en"), row.get("name_ar"))
        district = _first_ascii(row.get("caza_ar"))
        if not town_name:
            continue

        match_candidates: list[dict[str, str]] = []
        district_keys = {_slug(district)} if district else {""}
        name_keys = {_slug(row.get("name_en")), _slug(row.get("name_ar"))}
        for district_key in {k for k in district_keys if k and k != "unknown"}:
            for name_key in {k for k in name_keys if k and k != "unknown"}:
                match_candidates.extend(registry_index.get((name_key, district_key), []))

        deduped: dict[str, dict[str, str]] = {}
        for candidate in match_candidates:
            rid = _ascii_text(candidate.get("registry_id"))
            if rid:
                deduped[rid] = candidate
        candidates = list(deduped.values())

        mapping_status = "unmapped"
        mapped_registry_id = ""
        mapped_name = ""
        mapped_governorate = ""
        mapped_district = ""
        if len(candidates) == 1:
            mapping_status = "unique_match"
            mapped = candidates[0]
            mapped_registry_id = _ascii_text(mapped.get("registry_id"))
            mapped_name = _first_ascii(mapped.get("name_en"), mapped.get("name_ar"), mapped_registry_id)
            mapped_governorate = _first_ascii(mapped.get("governorate_en"), mapped.get("moim_2025_governorate_ar"))
            mapped_district = _first_ascii(mapped.get("district_en"), mapped.get("moim_2025_district_ar"))
        elif len(candidates) > 1:
            mapping_status = "ambiguous_match"

        desc = (
            f"Towns registry reference for locality {town_name} in district {district or 'unknown'}. "
            f"is_municipality={row.get('is_municipality') or 'unknown'}. "
            f"Mapping status: {mapping_status}. "
            f"Mapped municipality: {mapped_name or 'none'} ({mapped_registry_id or 'none'}). "
            f"Candidate match count: {len(candidates)}. "
            "Use for location-term normalization and query expansion, not as sole dispatch authority."
        )

        _append_unique_doc(docs, _doc_base(
            doc_id=f"towns-registry-reference-{_slug(town_name)}-{_slug(district)}",
            selector="MUN",
            description=desc,
            doc_type="town_registry_reference",
            route_mode="query_and_type_expansion",
            route_authority="supporting",
            source_reliability="towns_registry",
            complaint_types=["location_normalization", "municipality_lookup"],
            keywords=[
                town_name,
                row.get("name_ar", ""),
                row.get("name_en", ""),
                district,
                row.get("is_municipality", ""),
                mapped_name,
                mapped_registry_id,
                mapped_governorate,
                mapped_district,
                mapping_status,
            ],
            source_files=[_portable_path(towns_path)],
            confidence_prior=0.74 if mapping_status == "unique_match" else 0.6,
            responsibility_level="context",
            hitl_required=mapping_status != "unique_match",
            hitl_conditions=[
                "Ambiguous or unmapped locality requires human location confirmation." if mapping_status != "unique_match" else "",
            ],
            governorates=[mapped_governorate],
            districts=[mapped_district or district],
            municipalities=[mapped_name or town_name],
            exact_match_terms=[
                town_name,
                row.get("name_ar", ""),
                row.get("name_en", ""),
                district,
                mapped_registry_id,
                mapped_name,
            ],
            location_precision="district",
            structured_fields={
                **row,
                "source_profile": "towns_registry_reference",
                "mapping_status": mapping_status,
                "mapped_registry_id": mapped_registry_id,
                "mapped_municipality_name": mapped_name,
                "mapped_governorate": mapped_governorate,
                "mapped_district": mapped_district,
                "candidate_match_count": len(candidates),
            },
            retrieval_weight=0.5,
        ))
    return docs


def _build_municipality_resolution_bundle_docs(source_root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    alias_path = source_root / "knowledge_base" / "municipalities" / "municipality_aliases.csv"
    water_path = source_root / "knowledge_base" / "water_establishments" / "water_entity_resolution.csv"
    cd_path = source_root / "knowledge_base" / "public_safety_enforcement" / "civil_defense_entity_resolution.csv"

    if not any(path.exists() for path in (alias_path, water_path, cd_path)):
        return docs

    alias_rows = _read_csv(alias_path)
    water_rows = _read_csv(water_path)
    cd_rows = _read_csv(cd_path)

    registry_by_municipality_id: dict[str, str] = {}
    registry_by_name_key: dict[str, str] = {}
    for row in alias_rows:
        registry_id = _ascii_text(row.get("registry_id")).upper()
        if not registry_id.startswith("MUN-"):
            continue
        municipality_id = _ascii_text(row.get("municipality_id"))
        if municipality_id:
            registry_by_municipality_id[municipality_id] = registry_id
        alias_value = _ascii_text(row.get("alias_value"))
        if alias_value:
            alias_key = _slug(alias_value)
            if alias_key != "unknown":
                registry_by_name_key[alias_key] = registry_id

    for row in water_rows:
        registry_id = _ascii_text(row.get("municipality_key")).upper()
        if not registry_id.startswith("MUN-"):
            continue
        municipality_id = _ascii_text(row.get("municipality_id"))
        if municipality_id:
            registry_by_municipality_id.setdefault(municipality_id, registry_id)
        for name_key in (_ascii_text(row.get("municipality_name_en")), _ascii_text(row.get("municipality_name_ar"))):
            if name_key:
                normalized_name_key = _slug(name_key)
                if normalized_name_key != "unknown":
                    registry_by_name_key.setdefault(normalized_name_key, registry_id)

    def _bundle_key(*values: Any) -> str:
        tokens = [_ascii_text(v) for v in values if _ascii_text(v)]
        for token in tokens:
            if token.upper().startswith("MUN-"):
                return token.upper()
        for token in tokens:
            if token in registry_by_municipality_id:
                return registry_by_municipality_id[token]
        for token in tokens:
            name_key = _slug(token)
            if name_key != "unknown" and name_key in registry_by_name_key:
                return registry_by_name_key[name_key]
        for token in tokens:
            if token.isdigit():
                return token
        return _slug(tokens[0]).upper() if tokens else ""

    bundles: dict[str, dict[str, Any]] = {}

    def _ensure_bundle(bundle_id: str) -> dict[str, Any]:
        if bundle_id not in bundles:
            bundles[bundle_id] = {
                "registry_id": "",
                "municipality_id": "",
                "municipality_key": "",
                "municipality_name_en": "",
                "municipality_name_ar": "",
                "governorate": "",
                "district": "",
                "primary_alias": "",
                "aliases": [],
                "alias_types": [],
                "alias_sources": [],
                "alias_confidences": [],
                "source_ids": [],
                "notes": [],
                "water_entity_id": "",
                "water_entity_name": "",
                "water_branch_id": "",
                "water_branch_name": "",
                "water_confidences": [],
                "cd_center_id": "",
                "cd_center_name": "",
                "cd_hotline": "",
                "cd_phone": "",
                "cd_confidences": [],
                "source_files": set(),
            }
        return bundles[bundle_id]

    for row in alias_rows:
        bundle_id = _bundle_key(row.get("registry_id"), row.get("municipality_id"), row.get("alias_value"))
        if not bundle_id:
            continue
        bundle = _ensure_bundle(bundle_id)
        bundle["registry_id"] = bundle["registry_id"] or _ascii_text(row.get("registry_id"))
        bundle["municipality_id"] = bundle["municipality_id"] or _ascii_text(row.get("municipality_id"))
        alias_value = _ascii_text(row.get("alias_value"))
        if alias_value:
            bundle["aliases"].append(alias_value)
        if _truthy(row.get("is_primary")) and alias_value:
            bundle["primary_alias"] = bundle["primary_alias"] or alias_value
        alias_type = _ascii_text(row.get("alias_type"))
        if alias_type:
            bundle["alias_types"].append(alias_type)
        source_basis = _ascii_text(row.get("source_basis"))
        if source_basis:
            bundle["alias_sources"].append(source_basis)
        if _slug(row.get("language")) == "en" and alias_value and not bundle["municipality_name_en"]:
            bundle["municipality_name_en"] = alias_value
        if _slug(row.get("language")) == "ar" and alias_value and not bundle["municipality_name_ar"]:
            bundle["municipality_name_ar"] = alias_value
        if row.get("confidence"):
            bundle["alias_confidences"].append(_confidence(row["confidence"]))
        bundle["source_ids"].extend(_split_values(row.get("source")))
        bundle["source_files"].add(_portable_path(alias_path))

    for row in water_rows:
        bundle_id = _bundle_key(
            row.get("municipality_key"),
            row.get("municipality_id"),
            row.get("municipality_name_en"),
            row.get("municipality_name_ar"),
        )
        if not bundle_id:
            continue
        bundle = _ensure_bundle(bundle_id)
        bundle["registry_id"] = bundle["registry_id"] or registry_by_municipality_id.get(_ascii_text(row.get("municipality_id")), "")
        bundle["municipality_key"] = bundle["municipality_key"] or _ascii_text(row.get("municipality_key"))
        bundle["municipality_id"] = bundle["municipality_id"] or _ascii_text(row.get("municipality_id"))
        bundle["municipality_name_en"] = bundle["municipality_name_en"] or _ascii_text(row.get("municipality_name_en"))
        bundle["municipality_name_ar"] = bundle["municipality_name_ar"] or _ascii_text(row.get("municipality_name_ar"))
        bundle["governorate"] = bundle["governorate"] or _ascii_text(row.get("governorate"))
        bundle["district"] = bundle["district"] or _ascii_text(row.get("district"))
        bundle["water_entity_id"] = bundle["water_entity_id"] or _ascii_text(row.get("water_entity_id"))
        bundle["water_entity_name"] = bundle["water_entity_name"] or _ascii_text(row.get("water_entity_name"))
        bundle["water_branch_id"] = bundle["water_branch_id"] or _ascii_text(row.get("branch_service_center_id"))
        bundle["water_branch_name"] = bundle["water_branch_name"] or _ascii_text(row.get("branch_service_center_name"))
        if row.get("confidence"):
            bundle["water_confidences"].append(_confidence(row["confidence"]))
        if row.get("notes"):
            bundle["notes"].append(row["notes"])
        bundle["source_ids"].extend(_row_source_ids(row))
        bundle["source_files"].add(_portable_path(water_path))

    for row in cd_rows:
        bundle_id = _bundle_key(
            row.get("municipality_key"),
            row.get("municipality_id"),
            row.get("municipality_name_en"),
            row.get("municipality_name_ar"),
        )
        if not bundle_id:
            continue
        bundle = _ensure_bundle(bundle_id)
        bundle["registry_id"] = bundle["registry_id"] or registry_by_municipality_id.get(_ascii_text(row.get("municipality_id")), "")
        bundle["municipality_key"] = bundle["municipality_key"] or _ascii_text(row.get("municipality_key"))
        bundle["municipality_id"] = bundle["municipality_id"] or _ascii_text(row.get("municipality_id"))
        bundle["municipality_name_en"] = bundle["municipality_name_en"] or _ascii_text(row.get("municipality_name_en"))
        bundle["municipality_name_ar"] = bundle["municipality_name_ar"] or _ascii_text(row.get("municipality_name_ar"))
        bundle["governorate"] = bundle["governorate"] or _ascii_text(row.get("governorate"))
        bundle["district"] = bundle["district"] or _ascii_text(row.get("district"))
        bundle["cd_center_id"] = bundle["cd_center_id"] or _ascii_text(row.get("cd_center_id"))
        bundle["cd_center_name"] = bundle["cd_center_name"] or _first_ascii(row.get("cd_center_name_en"), row.get("cd_center_name_ar"))
        bundle["cd_hotline"] = bundle["cd_hotline"] or _ascii_text(row.get("hotline"))
        bundle["cd_phone"] = bundle["cd_phone"] or _ascii_text(row.get("phone"))
        if row.get("confidence"):
            bundle["cd_confidences"].append(_confidence(row["confidence"]))
        if row.get("notes"):
            bundle["notes"].append(row["notes"])
        bundle["source_ids"].extend(_row_source_ids(row))
        bundle["source_files"].add(_portable_path(cd_path))

    for bundle_id, bundle in sorted(bundles.items()):
        registry_id = _first_ascii(
            bundle.get("registry_id"),
            registry_by_municipality_id.get(_ascii_text(bundle.get("municipality_id")), ""),
            bundle.get("municipality_key"),
            bundle_id,
        )
        municipality_name = _first_ascii(
            bundle.get("primary_alias"),
            bundle.get("municipality_name_en"),
            bundle.get("municipality_name_ar"),
            registry_id,
            bundle.get("municipality_id"),
        )
        if not municipality_name:
            continue

        aliases = _unique(
            [
                municipality_name,
                bundle.get("municipality_name_en"),
                bundle.get("municipality_name_ar"),
                bundle.get("registry_id"),
                bundle.get("municipality_id"),
                bundle.get("municipality_key"),
                *bundle.get("aliases", []),
            ],
            limit=90,
        )

        mapped_targets: list[str] = []
        if bundle.get("water_entity_id") or bundle.get("water_entity_name"):
            mapped_targets.append(
                f"Water establishment -> {_first_ascii(bundle.get('water_entity_name'), bundle.get('water_entity_id'))}"
            )
        if bundle.get("cd_center_id") or bundle.get("cd_center_name"):
            mapped_targets.append(
                f"Civil defense center -> {_first_ascii(bundle.get('cd_center_name'), bundle.get('cd_center_id'))}"
            )
        mapped_text = "; ".join(mapped_targets) if mapped_targets else "No verified water or civil-defense mapping captured yet."
        notes_summary = "; ".join(_unique(bundle.get("notes", []), limit=4)) or "No additional routing notes captured."

        confidence_values = [
            *bundle.get("alias_confidences", []),
            *bundle.get("water_confidences", []),
            *bundle.get("cd_confidences", []),
        ]
        confidence_prior = sum(confidence_values) / len(confidence_values) if confidence_values else 0.78
        hitl_required = not bool(mapped_targets)

        desc = (
            f"Municipality resolution bundle for {municipality_name}. "
            f"Registry key: {registry_id}. District/governorate context: {bundle.get('district') or 'unspecified district'}, "
            f"{bundle.get('governorate') or 'unspecified governorate'}. "
            f"Alias count: {len(aliases)}. "
            f"Resolved downstream context: {mapped_text}. "
            f"Routing notes: {notes_summary}."
        )

        _append_unique_doc(docs, _doc_base(
            doc_id=f"municipality-resolution-bundle-{registry_id}",
            selector="MUN",
            description=desc,
            doc_type="municipality_resolution_bundle",
            route_mode="municipality_resolution_bundle",
            route_authority="location_resolution_bundle",
            source_reliability="municipality_resolution_bundle",
            complaint_types=_unique([
                "municipality_lookup",
                "geo_disambiguation",
                "water_entity_resolution" if bundle.get("water_entity_id") else "",
                "civil_defense_resolution" if bundle.get("cd_center_id") else "",
            ], limit=12),
            keywords=_unique([
                municipality_name,
                registry_id,
                bundle.get("municipality_id"),
                bundle.get("district"),
                bundle.get("governorate"),
                bundle.get("water_entity_id"),
                bundle.get("water_entity_name"),
                bundle.get("water_branch_id"),
                bundle.get("water_branch_name"),
                bundle.get("cd_center_id"),
                bundle.get("cd_center_name"),
                bundle.get("cd_hotline"),
                *aliases,
                *bundle.get("alias_types", []),
                *bundle.get("alias_sources", []),
            ], limit=120),
            source_ids=_unique(bundle.get("source_ids", []), limit=30),
            source_files=sorted(bundle.get("source_files", set())),
            confidence_prior=confidence_prior,
            responsibility_level="context",
            hitl_required=hitl_required,
            hitl_conditions=[
                "No verified municipality-to-entity mapping found; escalate to human review before dispatch." if hitl_required else "",
                notes_summary,
            ],
            governorates=[bundle.get("governorate")],
            districts=[bundle.get("district")],
            municipalities=[municipality_name],
            hotline=_first_ascii(bundle.get("cd_hotline"), bundle.get("cd_phone")) or None,
            exact_match_terms=_unique([
                registry_id,
                bundle.get("municipality_id"),
                bundle.get("municipality_key"),
                municipality_name,
                *aliases,
            ], limit=80),
            location_precision="municipality",
            structured_fields={
                "source_profile": "municipality_resolution_bundle",
                "registry_id": bundle.get("registry_id"),
                "municipality_id": bundle.get("municipality_id"),
                "municipality_key": bundle.get("municipality_key"),
                "municipality_name_en": bundle.get("municipality_name_en"),
                "municipality_name_ar": bundle.get("municipality_name_ar"),
                "alias_count": len(aliases),
                "alias_types": "; ".join(_unique(bundle.get("alias_types", []), limit=30)),
                "alias_sources": "; ".join(_unique(bundle.get("alias_sources", []), limit=30)),
                "water_entity_id": bundle.get("water_entity_id"),
                "water_entity_name": bundle.get("water_entity_name"),
                "water_branch_id": bundle.get("water_branch_id"),
                "water_branch_name": bundle.get("water_branch_name"),
                "cd_center_id": bundle.get("cd_center_id"),
                "cd_center_name": bundle.get("cd_center_name"),
                "cd_hotline": bundle.get("cd_hotline"),
                "cd_phone": bundle.get("cd_phone"),
                "governorate": bundle.get("governorate"),
                "district": bundle.get("district"),
                "source_files": "; ".join(sorted(bundle.get("source_files", set()))),
            },
            retrieval_weight=1.1 if mapped_targets else 0.86,
        ))
    return docs


def _build_required_field_profile_docs(source_root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    kb_root = source_root / "knowledge_base"
    grouped: dict[tuple[str, str, str], list[tuple[Path, dict[str, str]]]] = defaultdict(list)

    for path in sorted(kb_root.rglob("required_fields.csv")):
        sector = path.parent.name
        for row in _read_csv(path):
            entity_id = _ascii_text(row.get("entity_id")) or "HITL"
            workflow = _ascii_text(row.get("workflow_type")) or "general_intake"
            grouped[(sector, entity_id, workflow)].append((path, row))

    for (sector, entity_id, workflow), items in sorted(grouped.items()):
        requirement_ids = _unique([row.get("requirement_id", "") for _, row in items], limit=80)
        required_fields = _unique([row.get("required_field_or_document", "") for _, row in items], limit=60)
        required_for = _unique([row.get("required_for", "") for _, row in items], limit=30)
        notes = _unique([row.get("notes", "") for _, row in items], limit=8)
        source_ids = _unique([sid for _, row in items for sid in _row_source_ids(row)], limit=30)
        source_files = sorted({_portable_path(path) for path, _ in items})
        confidence_values = [_confidence(row.get("confidence", "medium")) for _, row in items]
        confidence_prior = sum(confidence_values) / len(confidence_values) if confidence_values else 0.80
        hitl_required = any("not_published" in _slug(note) or "manual" in _slug(note) for note in notes)

        desc = (
            f"Required intake fields profile for entity {entity_id} in sector {sector} workflow {workflow}. "
            f"Required fields/documents include: {'; '.join(required_fields[:16]) or 'not specified'}. "
            f"Applies to: {'; '.join(required_for[:10]) or 'general complaint intake'}. "
            f"Requirement IDs: {'; '.join(requirement_ids[:12]) or 'none captured'}. "
            f"Operational notes: {'; '.join(notes[:4]) or 'none'}."
        )

        _append_unique_doc(docs, _doc_base(
            doc_id=f"required-fields-profile-{sector}-{entity_id}-{workflow}",
            selector=_resolve_selector(entity_id, fallback="HITL"),
            description=desc,
            doc_type="required_fields_profile",
            route_mode="intake_requirements",
            route_authority="process_requirement",
            source_reliability="required_fields_profile",
            complaint_types=_unique([sector, workflow, *required_for], limit=20),
            keywords=_unique([
                sector,
                entity_id,
                workflow,
                *required_fields,
                *required_for,
                *notes,
            ], limit=110),
            source_ids=source_ids,
            source_files=source_files,
            confidence_prior=confidence_prior,
            responsibility_level="context",
            hitl_required=hitl_required,
            hitl_conditions=[
                "Some requirements are not publicly verified; keep human confirmation before strict rejection." if hitl_required else "",
                *notes,
            ],
            exact_match_terms=_unique([entity_id, workflow, *requirement_ids, *required_fields], limit=80),
            structured_fields={
                "source_profile": "required_fields_profile",
                "sector": sector,
                "entity_id": entity_id,
                "workflow_type": workflow,
                "requirement_count": len(required_fields),
                "requirement_ids": "; ".join(requirement_ids),
                "required_fields": "; ".join(required_fields),
                "required_for": "; ".join(required_for),
                "source_files": "; ".join(source_files),
            },
            retrieval_weight=0.94,
        ))
    return docs


def _build_sector_agency_policy_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "sector_agency_map.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        sector = _ascii_text(row.get("sector"))
        if not sector:
            continue
        selector = _resolve_selector(row.get("primary_entity_abbr"), fallback="HITL")
        hitl_required = _truthy(row.get("hitl_required"))
        district_aware = _truthy(row.get("district_aware"))
        desc = (
            f"Sector policy map for {sector}. Primary routing entity: {row.get('primary_entity_en')} ({row.get('primary_entity_abbr')}). "
            f"Secondary entity: {row.get('secondary_entity_en') or 'none'} ({row.get('secondary_entity_abbr') or 'none'}). "
            f"Escalation entity: {row.get('escalation_entity_en') or 'none'} ({row.get('escalation_entity_abbr') or 'none'}). "
            f"District-aware behavior: {'yes' if district_aware else 'no'}. "
            f"Routing notes: {row.get('routing_notes') or 'none'}."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"sector-policy-{sector}",
            selector=selector,
            description=desc,
            doc_type="sector_agency_policy",
            route_mode="sector_policy_map",
            route_authority="authoritative_policy",
            source_reliability="seed_policy_map",
            complaint_types=[sector, "sector_policy", "routing_policy"],
            keywords=[
                sector,
                row.get("primary_entity_abbr", ""),
                row.get("secondary_entity_abbr", ""),
                row.get("escalation_entity_abbr", ""),
                row.get("routing_notes", ""),
            ],
            source_files=[_portable_path(path)],
            confidence_prior=0.90,
            responsibility_level="context",
            hitl_required=hitl_required,
            hitl_conditions=[row.get("routing_notes", "")],
            exact_match_terms=[
                sector,
                row.get("primary_entity_en", ""),
                row.get("primary_entity_abbr", ""),
                row.get("secondary_entity_en", ""),
                row.get("escalation_entity_en", ""),
            ],
            structured_fields={**row, "source_profile": "sector_agency_map"},
            retrieval_weight=1.0,
        ))
    return docs


def _build_entity_service_area_map_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "entity_service_area_mapping.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        mapping_id = _ascii_text(row.get("mapping_id"))
        if not mapping_id:
            continue
        selector = _resolve_selector(row.get("entity_id"), row.get("entity_name"), fallback="HITL")
        desc = (
            f"Entity service-area mapping {mapping_id} for {row.get('service_family')}. "
            f"Location condition: {row.get('location_condition')}. "
            f"Join key: {row.get('municipality_registry_join_key') or 'none'}. "
            f"Mapped entity: {row.get('entity_name')} ({row.get('entity_id')}). "
            f"Routing use: {row.get('routing_use')}. Notes: {row.get('notes')}."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"entity-service-area-{mapping_id}",
            selector=selector,
            description=desc,
            doc_type="entity_service_area_map",
            route_mode="geo_service_area_map",
            route_authority="authoritative_map",
            source_reliability=row.get("confidence") or "service_area_mapping",
            complaint_types=_split_values(row.get("routing_use") or row.get("service_family")),
            keywords=[
                row.get("service_family", ""),
                row.get("location_condition", ""),
                row.get("municipality_registry_join_key", ""),
                row.get("entity_id", ""),
                row.get("entity_name", ""),
                row.get("notes", ""),
            ],
            source_ids=_row_source_ids(row),
            source_files=[_portable_path(path)],
            confidence_prior=_confidence_from_row(row, 0.88),
            responsibility_level="primary",
            hitl_conditions=[row.get("notes", "")],
            exact_match_terms=[mapping_id, row.get("entity_id", ""), row.get("entity_name", ""), row.get("service_family", "")],
            structured_fields={**row, "source_profile": "entity_service_area_mapping"},
            retrieval_weight=1.12,
        ))
    return docs


def _build_municipality_responsibility_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "municipality_responsibility_map.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        district_code = _ascii_text(row.get("district_code"))
        if not district_code:
            continue
        district_name = _first_ascii(row.get("name_en"), row.get("name_ar"), district_code)
        municipality_name = _first_ascii(row.get("municipality_en"), row.get("municipality_ar"), district_name)
        desc = (
            f"Municipality responsibility map entry {district_code}. "
            f"District/subdistrict: {district_name} in {row.get('governorate_en')}. "
            f"Mapped municipality: {municipality_name}. "
            f"Water authority hint: {row.get('water_authority_en')} ({row.get('water_authority_abbr')}). "
            f"Coordinates: {row.get('lat')}, {row.get('lon')}. Notes: {row.get('notes') or 'none'}."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"municipality-responsibility-{district_code}",
            selector="MUN",
            description=desc,
            doc_type="municipality_responsibility_map",
            route_mode="geo_district_reference",
            route_authority="district_map",
            source_reliability="district_mapping",
            complaint_types=["municipality_responsibility", "location_disambiguation", "water_authority_hint"],
            keywords=[
                district_code,
                district_name,
                municipality_name,
                row.get("governorate_en", ""),
                row.get("water_authority_abbr", ""),
                row.get("water_authority_en", ""),
                row.get("notes", ""),
            ],
            source_files=[_portable_path(path)],
            confidence_prior=0.90,
            responsibility_level="context",
            governorates=[row.get("governorate_en")],
            districts=[district_name],
            municipalities=[municipality_name],
            location_precision="district",
            exact_match_terms=[district_code, district_name, municipality_name, row.get("water_authority_abbr", "")],
            structured_fields={**row, "source_profile": "municipality_responsibility_map"},
            retrieval_weight=0.98,
        ))
    return docs


def _build_cdr_project_service_area_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "roads_public_works" / "cdr_project_service_areas.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        project_area_id = _ascii_text(row.get("project_area_id"))
        if not project_area_id:
            continue
        selector = _resolve_selector(row.get("primary_entity_id"), fallback="CDR")
        hitl_required = _truthy(row.get("hitl_required"))
        desc = (
            f"CDR project service-area boundary {project_area_id}: {row.get('project_name')}. "
            f"Sector/subsector: {row.get('sector')} / {row.get('subsector')}. "
            f"Area hint: {row.get('service_area_hint')}. "
            f"Primary/secondary entities: {row.get('primary_entity_id')} / {row.get('secondary_entity_ids') or 'none'}. "
            f"Routing use: {row.get('routing_use')}. Limitations: {row.get('limitations')}."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"cdr-project-area-{project_area_id}",
            selector=selector,
            description=desc,
            doc_type="cdr_project_service_area",
            route_mode="cdr_project_boundary",
            route_authority="project_owner_boundary",
            source_reliability=row.get("verification_status") or row.get("confidence") or "cdr_project_registry",
            complaint_types=_unique([
                *_split_values(row.get("sector")),
                *_split_values(row.get("subsector")),
                *_split_values(row.get("routing_use")),
            ], limit=20),
            keywords=[
                row.get("project_name", ""),
                row.get("project_aliases", ""),
                row.get("sector", ""),
                row.get("subsector", ""),
                row.get("municipality_or_area", ""),
                row.get("service_area_hint", ""),
                row.get("primary_entity_id", ""),
                row.get("secondary_entity_ids", ""),
                row.get("contractor_if_public", ""),
                row.get("limitations", ""),
            ],
            source_ids=_row_source_ids(row),
            source_files=[_portable_path(path)],
            confidence_prior=_confidence_from_row(row, 0.84),
            responsibility_level="boundary" if hitl_required else "context",
            hitl_required=hitl_required,
            hitl_conditions=[row.get("routing_use", ""), row.get("limitations", ""), row.get("notes", "")],
            governorates=[row.get("governorate_en")],
            districts=[row.get("district_en")],
            municipalities=[row.get("municipality_or_area")],
            exact_match_terms=[project_area_id, row.get("project_name", ""), row.get("project_aliases", "")],
            negative_signals=[row.get("limitations", "")],
            structured_fields={**row, "source_profile": "cdr_project_service_areas"},
            retrieval_weight=1.12,
        ))
    return docs


def _build_waste_site_registry_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "waste_environment" / "waste_site_registry.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        site_id = _ascii_text(row.get("site_id"))
        if not site_id:
            continue
        selector = _resolve_selector(row.get("primary_routing_entity"), fallback="MUN")
        hitl_required = _truthy(row.get("hitl_required"))
        desc = (
            f"Waste-site registry entry {site_id}: {row.get('site_name')} ({row.get('site_type')}). "
            f"Location context: {row.get('municipality_or_area')}, {row.get('district_en')}, {row.get('governorate_en')}. "
            f"Primary/secondary routing entities: {row.get('primary_routing_entity')} / {row.get('secondary_entities') or 'none'}. "
            f"Risk indicators: environmental={row.get('environmental_risk')}, emergency={row.get('emergency_risk')}. "
            f"Routing use: {row.get('routing_use')}. Limitations: {row.get('limitations')}."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"waste-site-registry-{site_id}",
            selector=selector,
            description=desc,
            doc_type="waste_site_registry",
            route_mode="waste_site_context",
            route_authority="site_context",
            source_reliability=row.get("verification_status") or row.get("confidence") or "waste_site_registry",
            complaint_types=_unique([
                *_split_values(row.get("site_type")),
                *_split_values(row.get("routing_use")),
                _ascii_text(row.get("environmental_risk")),
                _ascii_text(row.get("emergency_risk")),
            ], limit=20),
            keywords=[
                row.get("site_name", ""),
                row.get("site_type", ""),
                row.get("location_hint", ""),
                row.get("municipality_or_area", ""),
                row.get("operator_if_public", ""),
                row.get("primary_routing_entity", ""),
                row.get("secondary_entities", ""),
                row.get("routing_use", ""),
                row.get("limitations", ""),
                row.get("environmental_risk", ""),
                row.get("emergency_risk", ""),
            ],
            source_ids=_row_source_ids(row),
            source_files=[_portable_path(path)],
            confidence_prior=_confidence_from_row(row, 0.78),
            responsibility_level="boundary" if hitl_required else "context",
            hitl_required=hitl_required,
            hitl_conditions=[row.get("routing_use", ""), row.get("limitations", ""), row.get("notes", "")],
            governorates=[row.get("governorate_en")],
            districts=[row.get("district_en")],
            municipalities=[row.get("municipality_or_area")],
            exact_match_terms=[site_id, row.get("site_name", ""), row.get("municipality_or_area", "")],
            negative_signals=[row.get("limitations", "")],
            structured_fields={**row, "source_profile": "waste_site_registry"},
            retrieval_weight=1.03,
        ))
    return docs


def _build_source_registry_docs(source_root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    kb_root = source_root / "knowledge_base"
    seen_source_ids: set[str] = set()
    for path in sorted(kb_root.rglob("source_registry.csv")):
        registry_scope = path.parent.name
        for row in _read_csv(path):
            source_id = _ascii_text(row.get("source_id")) or f"SRC-{_slug(row.get('title')).upper()}"
            source_key = source_id.upper()
            if source_key in seen_source_ids:
                continue
            seen_source_ids.add(source_key)

            selector = _resolve_selector(source_id, row.get("primary_use"), row.get("notes"), fallback="HITL")
            desc = (
                f"Source registry entry {source_id}: {row.get('title')}. "
                f"Publisher/type: {row.get('publisher')} / {row.get('source_type')}. "
                f"Reliability tier: {row.get('reliability_tier')}. "
                f"Primary use: {row.get('primary_use')}. "
                f"URL: {row.get('url')}. Notes: {row.get('notes')}."
            )
            _append_unique_doc(docs, _doc_base(
                doc_id=f"source-registry-{source_id}",
                selector=selector,
                description=desc,
                doc_type="source_registry_entry",
                route_mode="source_provenance",
                route_authority="provenance_context",
                source_reliability=row.get("reliability_tier") or "source_registry",
                complaint_types=_unique([
                    row.get("source_type", ""),
                    *_split_values(row.get("primary_use")),
                    "source_provenance",
                ], limit=14),
                keywords=[
                    source_id,
                    row.get("title", ""),
                    row.get("publisher", ""),
                    row.get("source_type", ""),
                    row.get("reliability_tier", ""),
                    row.get("primary_use", ""),
                    row.get("scheme_note", ""),
                    registry_scope,
                ],
                source_ids=[source_id, row.get("url", "")],
                source_files=[_portable_path(path)],
                confidence_prior=_confidence_from_tier(row.get("reliability_tier"), 0.74),
                responsibility_level="context",
                exact_match_terms=[source_id, row.get("title", ""), row.get("publisher", ""), row.get("url", "")],
                structured_fields={
                    **row,
                    "source_profile": "source_registry_entry",
                    "source_registry_scope": registry_scope,
                },
                retrieval_weight=0.55,
            ))
    return docs


def _build_data_entity_fact_docs(source_root: Path) -> list[dict[str, Any]]:
    entity_dir = source_root / "knowledge_base" / "entities"
    docs: list[dict[str, Any]] = []

    if not entity_dir.exists():
        return docs

    mode_by_fact_type = {
        "legal_responsibility": ("entity_legal_fact", "entity_legal_scope", "authoritative_profile", "primary", 1.2),
        "service_area": ("entity_service_area_fact", "geo_service_area", "authoritative_map", "primary", 1.15),
        "operational_contact": ("entity_contact_fact", "contact_context", "verified_channel", "context", 0.92),
        "complaint_process": ("entity_process_fact", "complaint_workflow", "process_requirement", "context", 1.0),
        "deadline_or_sla": ("entity_deadline_policy_fact", "resolution_policy", "policy_context", "context", 0.96),
        "emergency_instruction": ("entity_emergency_fact", "emergency_instruction", "guardrail", "boundary", 1.12),
    }

    for path in sorted(entity_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue

        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            continue

        if not isinstance(payload, dict):
            continue

        entity_id = _selector_entity_id(payload.get("entity_id") or path.stem)
        if not _is_main_entity(entity_id):
            continue

        routing_summary = payload.get("routing_summary") if isinstance(payload.get("routing_summary"), dict) else {}
        entity_sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
        primary_sectors = routing_summary.get("primary_for_sectors") if isinstance(routing_summary.get("primary_for_sectors"), list) else []
        not_responsible_for = routing_summary.get("not_responsible_for") if isinstance(routing_summary.get("not_responsible_for"), list) else []
        shared_hitl_conditions = routing_summary.get("hitl_conditions") if isinstance(routing_summary.get("hitl_conditions"), list) else []
        facts = payload.get("facts") if isinstance(payload.get("facts"), list) else []

        for idx, fact in enumerate(facts, start=1):
            if not isinstance(fact, dict):
                continue

            fact_id = _ascii_text(fact.get("fact_id")) or f"{entity_id}-F{idx:03d}"
            fact_type = _slug(fact.get("fact_type") or "entity_fact")
            fact_value = _ascii_text(fact.get("value"))
            if not fact_value:
                continue

            doc_type, route_mode, route_authority, responsibility_level, weight = mode_by_fact_type.get(
                fact_type,
                ("entity_fact", "entity_fact_context", "supporting", "context", 0.9),
            )
            notes = _ascii_text(fact.get("notes"))
            human_review_reason = _ascii_text(fact.get("human_review_reason"))
            hitl_required = bool(fact.get("human_review_required")) or bool(routing_summary.get("hitl_always_required"))
            confidence_prior = _confidence(fact.get("confidence") or payload.get("overall_confidence") or "medium")
            hotline = _extract_hotline_from_text(fact_value)

            _append_unique_doc(docs, _doc_base(
                doc_id=f"data-entity-fact-{entity_id}-{fact_id}",
                selector=entity_id,
                description=(
                    f"Entity fact from data folder for {payload.get('entity_name') or entity_id}: "
                    f"{fact_id} ({fact_type}). {fact_value}"
                ),
                doc_type=doc_type,
                route_mode=route_mode,
                route_authority=route_authority,
                source_reliability=fact.get("confidence") or payload.get("overall_confidence") or "entity_fact",
                complaint_types=_unique([
                    fact_type,
                    *[_ascii_text(s) for s in primary_sectors],
                ], limit=24),
                keywords=_unique([
                    entity_id,
                    payload.get("entity_name", ""),
                    payload.get("entity_type", ""),
                    fact_id,
                    fact_type,
                    *[_ascii_text(s) for s in primary_sectors],
                    notes,
                    human_review_reason,
                    fact_value,
                ], limit=120),
                not_responsible_for=not_responsible_for if fact_type == "legal_responsibility" else [],
                source_ids=_unique([
                    *[v for v in (fact.get("source_ids") or []) if isinstance(v, str)],
                    *[v for v in entity_sources if isinstance(v, str)],
                ], limit=28),
                source_files=[_portable_path(path)],
                confidence_prior=confidence_prior,
                responsibility_level=responsibility_level,
                hitl_required=hitl_required,
                hitl_conditions=_unique([
                    human_review_reason,
                    notes,
                    *[v for v in shared_hitl_conditions if isinstance(v, str)],
                ], limit=16),
                hotline=hotline,
                exact_match_terms=_unique([
                    fact_id,
                    entity_id,
                    payload.get("entity_name", ""),
                    *[_ascii_text(s) for s in primary_sectors],
                ], limit=30),
                negative_signals=not_responsible_for if fact_type == "legal_responsibility" else [],
                structured_fields={
                    "source_profile": "data_entities_fact",
                    "main_entity_only": True,
                    "entity_id": entity_id,
                    "entity_name": payload.get("entity_name", ""),
                    "entity_type": payload.get("entity_type", ""),
                    "parent_ministry": payload.get("parent_ministry", ""),
                    "fact_id": fact_id,
                    "fact_type": fact_type,
                    "fact_confidence": fact.get("confidence", ""),
                    "human_review_required": bool(fact.get("human_review_required")),
                    "human_review_reason": human_review_reason,
                    "last_reviewed": payload.get("last_reviewed", ""),
                },
                retrieval_weight=weight,
            ))

    return docs


def _build_public_entity_profile_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "public_entities_extended.csv"
    docs: list[dict[str, Any]] = []
    for row in _read_csv(path):
        entity_id = _selector_entity_id(row.get("entity_id"))
        if not _is_main_entity(entity_id):
            continue
        complaint_domains = _split_values(row.get("complaint_domains"))
        not_responsible = _split_values(row.get("not_responsible_for"))
        default_use = _ascii_text(row.get("default_use_in_routing"))
        hitl_required = "hitl" in _slug(default_use)
        desc = (
            f"Primary entity profile for {row.get('entity_name_en')} ({entity_id}). "
            f"Routing role: {row.get('routing_role')}. Scope: {row.get('geographic_scope')}. "
            f"Responsibilities: {row.get('responsibilities_summary')}. "
            f"Default routing behavior: {default_use}. "
            f"Out-of-scope boundaries: {'; '.join(not_responsible[:10]) or 'none captured'}."
        )
        authority = "authoritative_profile" if "verified" in _slug(row.get("production_status")) else "supporting_profile"
        _append_unique_doc(docs, _doc_base(
            doc_id=f"primary-entity-profile-{entity_id}",
            selector=entity_id,
            description=desc,
            doc_type="primary_entity_profile",
            route_mode="entity_profile",
            route_authority=authority,
            source_reliability=row.get("confidence") or "entity_profile",
            complaint_types=_unique([*complaint_domains, row.get("entity_type", "")], limit=20),
            keywords=_unique([
                entity_id,
                row.get("entity_name_en"),
                row.get("entity_name_ar"),
                row.get("routing_role"),
                row.get("geographic_scope"),
                row.get("canonical_id_in_routing"),
                row.get("parent_body"),
                row.get("official_email"),
                row.get("emergency_hotline"),
                row.get("non_emergency_phone"),
                *complaint_domains,
            ], limit=110),
            not_responsible_for=not_responsible,
            source_ids=_row_source_ids(row),
            source_files=[_portable_path(path)],
            confidence_prior=_confidence_from_row(row, 0.88),
            responsibility_level="primary",
            hitl_required=hitl_required,
            hitl_conditions=[
                row.get("conflict_note", ""),
                "Default use references HITL gating." if hitl_required else "",
            ],
            hotline=_first_ascii(row.get("emergency_hotline"), row.get("non_emergency_phone")) or None,
            exact_match_terms=_unique([
                entity_id,
                row.get("entity_name_en"),
                row.get("entity_name_ar"),
                row.get("canonical_id_in_routing"),
                *complaint_domains,
            ], limit=80),
            structured_fields={
                **row,
                "source_profile": "primary_entity_profile",
                "main_entity_only": True,
            },
            retrieval_weight=1.14,
        ))
    return docs


def _build_ground_truth_main_entity_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "knowledge_base" / "lebanese_public_entities_ground_truth.json"
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return []

    docs: list[dict[str, Any]] = []
    meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
    version = _ascii_text(meta.get("version")) or "ground_truth"
    entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}

    for entity_id, payload in entities.items():
        if not isinstance(payload, dict):
            continue
        selector = _selector_entity_id(entity_id)
        if not _is_main_entity(selector):
            continue

        responsibilities = payload.get("responsibilities") if isinstance(payload.get("responsibilities"), list) else []
        not_responsible = payload.get("not_responsible_for") if isinstance(payload.get("not_responsible_for"), list) else []
        hitl_conditions = payload.get("hitl_conditions") if isinstance(payload.get("hitl_conditions"), list) else []
        routing_rule = _ascii_text(payload.get("routing_rule"))
        official_contact = payload.get("official_contact") if isinstance(payload.get("official_contact"), dict) else {}
        contact_bits = [
            _ascii_text(official_contact.get("hotline")),
            _ascii_text(official_contact.get("customer_care")),
            _ascii_text(official_contact.get("phone")),
            _ascii_text(payload.get("emergency_hotline")),
        ]

        desc = (
            f"Ground-truth profile for primary entity {payload.get('name_en') or selector} ({selector}). "
            f"Coverage: {payload.get('coverage') or payload.get('coverage_governorates') or 'not specified'}. "
            f"Responsibilities: {'; '.join(_unique(responsibilities, limit=6)) or 'not specified'}. "
            f"Routing rule: {routing_rule or 'none provided'}. "
            f"Out-of-scope boundaries: {'; '.join(_unique(not_responsible, limit=8)) or 'none provided'}."
        )

        _append_unique_doc(docs, _doc_base(
            doc_id=f"ground-truth-entity-{selector}",
            selector=selector,
            description=desc,
            doc_type="ground_truth_entity_profile",
            route_mode="entity_ground_truth_profile",
            route_authority="authoritative_profile",
            source_reliability="ground_truth_v2",
            complaint_types=_unique([
                payload.get("type", ""),
                "primary_entity_ground_truth",
            ], limit=12),
            keywords=_unique([
                selector,
                payload.get("abbr", ""),
                payload.get("name_en", ""),
                payload.get("name_ar", ""),
                payload.get("type", ""),
                payload.get("coverage", ""),
                payload.get("parent_ministry", ""),
                payload.get("parent_oversight", ""),
                routing_rule,
                *responsibilities,
            ], limit=120),
            not_responsible_for=not_responsible,
            source_files=[_portable_path(path)],
            confidence_prior=0.93,
            responsibility_level="primary",
            hitl_required=bool(payload.get("default_hitl_required")),
            hitl_conditions=_unique([
                *hitl_conditions,
                payload.get("hitl_reason", ""),
            ], limit=14),
            hotline=_first_ascii(*contact_bits) or None,
            exact_match_terms=_unique([
                selector,
                payload.get("abbr", ""),
                payload.get("name_en", ""),
                payload.get("name_ar", ""),
            ], limit=24),
            structured_fields={
                "source_profile": "ground_truth_entity_profile",
                "ground_truth_version": version,
                "main_entity_only": True,
                "entity_id": selector,
                "entity_type": payload.get("type"),
                "coverage": payload.get("coverage"),
                "coverage_governorates": "; ".join(_unique(payload.get("coverage_governorates", []), limit=15)),
                "routing_rule": routing_rule,
                "default_hitl_required": payload.get("default_hitl_required"),
            },
            retrieval_weight=1.2,
        ))

    water_map = data.get("water_authority_by_governorate") if isinstance(data.get("water_authority_by_governorate"), dict) else {}
    for governorate, entity_value in sorted(water_map.items()):
        selector = _selector_entity_id(entity_value)
        if not _is_main_entity(selector):
            continue
        desc = (
            f"Ground-truth water authority map: governorate {governorate} routes to primary water entity {selector}. "
            "Use this as the governorate-level primary rule before municipality-level exceptions."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"ground-truth-water-map-{governorate}-{selector}",
            selector=selector,
            description=desc,
            doc_type="ground_truth_water_authority_map",
            route_mode="geo_primary_rule",
            route_authority="authoritative_map",
            source_reliability="ground_truth_v2",
            complaint_types=["WATER", "water_authority_mapping", "primary_routing_rule"],
            keywords=[governorate, selector, "water_authority_by_governorate", version],
            source_files=[_portable_path(path)],
            confidence_prior=0.94,
            responsibility_level="primary",
            governorates=[governorate],
            location_precision="governorate",
            exact_match_terms=[governorate, selector],
            structured_fields={
                "source_profile": "ground_truth_water_authority_map",
                "ground_truth_version": version,
                "main_entity_only": True,
                "governorate": governorate,
                "mapped_entity": selector,
            },
            retrieval_weight=1.16,
        ))

    routing_rules = data.get("routing_rules") if isinstance(data.get("routing_rules"), dict) else {}
    for sector, rule_obj in sorted(routing_rules.items()):
        if not isinstance(rule_obj, dict):
            continue

        hitl_conditions = []
        if isinstance(rule_obj.get("hitl_required_if"), list):
            hitl_conditions = [str(v) for v in rule_obj.get("hitl_required_if", [])]
        elif rule_obj.get("hitl_required_if"):
            hitl_conditions = _split_values(rule_obj.get("hitl_required_if"))

        for rule_key, raw_value in rule_obj.items():
            if not isinstance(raw_value, str):
                continue
            if not (rule_key == "primary" or rule_key.endswith("_primary")):
                continue

            candidates: list[str] = []
            if _slug(raw_value) == "gps_selected_rwe":
                candidates.extend(_selector_entity_id(v) for v in water_map.values())
            else:
                for token in re.findall(r"[A-Z][A-Z_]{1,30}", raw_value.upper()):
                    if _is_main_entity(token):
                        candidates.append(_selector_entity_id(token))
                resolved = _resolve_selector(raw_value, fallback="HITL")
                if _is_main_entity(resolved):
                    candidates.append(resolved)

            for selector in _unique(candidates, limit=6):
                if not _is_main_entity(selector):
                    continue
                desc = (
                    f"Ground-truth primary routing rule for sector {sector}: {rule_key} -> {raw_value}. "
                    f"Primary main entity: {selector}. "
                    f"HITL conditions: {'; '.join(_unique(hitl_conditions, limit=8)) or 'none specified'}"
                )
                _append_unique_doc(docs, _doc_base(
                    doc_id=f"ground-truth-primary-rule-{sector}-{rule_key}-{selector}",
                    selector=selector,
                    description=desc,
                    doc_type="ground_truth_primary_rule",
                    route_mode="sector_primary_rule",
                    route_authority="authoritative_rule",
                    source_reliability="ground_truth_v2",
                    complaint_types=[sector, "primary_routing_rule"],
                    keywords=[sector, rule_key, raw_value, selector, *hitl_conditions],
                    source_files=[_portable_path(path)],
                    confidence_prior=0.94,
                    responsibility_level="primary",
                    hitl_required=bool(rule_obj.get("hitl_required")) or bool(hitl_conditions),
                    hitl_conditions=hitl_conditions,
                    exact_match_terms=[sector, rule_key, raw_value, selector],
                    structured_fields={
                        "source_profile": "ground_truth_primary_rule",
                        "ground_truth_version": version,
                        "main_entity_only": True,
                        "sector": sector,
                        "rule_key": rule_key,
                        "rule_value": raw_value,
                        "primary_entity": selector,
                    },
                    retrieval_weight=1.22,
                ))

    return docs


def _build_complaint_intelligence_event_docs(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "complaint_intelligence" / "normalized" / "municipal_official_process_seed.jsonl"
    docs: list[dict[str, Any]] = []
    for event in _read_jsonl(path):
        event_id = _ascii_text(event.get("event_id"))
        if not event_id:
            continue
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        issue = event.get("issue") if isinstance(event.get("issue"), dict) else {}
        location = event.get("location") if isinstance(event.get("location"), dict) else {}
        entities = event.get("entities") if isinstance(event.get("entities"), dict) else {}
        lifecycle = event.get("lifecycle") if isinstance(event.get("lifecycle"), dict) else {}
        resolution = event.get("resolution") if isinstance(event.get("resolution"), dict) else {}
        labels = event.get("labels_for_cedarfix") if isinstance(event.get("labels_for_cedarfix"), dict) else {}

        selector = _resolve_selector(
            labels.get("routing_entity"),
            entities.get("expected_responsible"),
            entities.get("resolver_entity"),
            fallback="HITL",
        )
        issue_type = _ascii_text(issue.get("issue_type")) or "municipal_process_event"
        sector = _ascii_text(issue.get("sector")) or "other"
        source_name = _ascii_text(source.get("source_name")) or "unknown_source"
        municipality = _first_ascii(location.get("municipality"), location.get("free_text"), "unknown_municipality")
        district = _ascii_text(location.get("district"))
        governorate = _ascii_text(location.get("governorate"))
        issue_keywords_raw = issue.get("keywords")
        if isinstance(issue_keywords_raw, list):
            issue_keywords = [_ascii_text(item) for item in issue_keywords_raw]
        else:
            issue_keywords = _split_values(issue_keywords_raw)

        hitl_required = bool(labels.get("hitl_required")) or bool(event.get("review_required"))
        desc = (
            f"Complaint intelligence event {event_id} from {source_name}. "
            f"Issue type: {issue_type} in sector {sector}. "
            f"Location context: {municipality}{', ' + district if district else ''}{', ' + governorate if governorate else ''}. "
            f"Routing label: {labels.get('routing_entity') or entities.get('expected_responsible') or 'unknown'}. "
            f"Resolution summary: {event.get('summary') or resolution.get('action_taken') or 'not provided'}."
        )

        _append_unique_doc(docs, _doc_base(
            doc_id=f"complaint-intelligence-event-{event_id}",
            selector=selector,
            description=desc,
            doc_type="official_process_event",
            route_mode="historical_case_context",
            route_authority="evidence_case",
            source_reliability=event.get("source_confidence") or resolution.get("evidence_confidence") or "event_record",
            complaint_types=_unique([
                sector,
                issue_type,
                _ascii_text(resolution.get("evidence_type")),
                "municipal_process_event",
            ], limit=16),
            keywords=_unique([
                event_id,
                sector,
                issue_type,
                municipality,
                district,
                governorate,
                source_name,
                source.get("platform", ""),
                labels.get("routing_entity", ""),
                labels.get("hitl_reason", ""),
                *issue_keywords,
            ], limit=100),
            source_ids=_unique([
                source.get("source_id", ""),
                source.get("target_id", ""),
                source.get("source_url", ""),
                source.get("public_url", ""),
            ], limit=20),
            source_files=[_portable_path(path)],
            confidence_prior=_confidence(
                _first_ascii(
                    resolution.get("evidence_confidence"),
                    event.get("source_confidence"),
                    "medium",
                )
            ),
            responsibility_level="context",
            hitl_required=hitl_required,
            hitl_conditions=[labels.get("hitl_reason", ""), "Historical case evidence is contextual and must be checked against current ownership."],
            governorates=[governorate],
            districts=[district],
            municipalities=[municipality],
            location_precision=location.get("precision"),
            exact_match_terms=[event_id, issue_type, municipality, source_name],
            structured_fields={
                "source_profile": "complaint_intelligence_event",
                "event_id": event_id,
                "source_id": source.get("source_id"),
                "source_name": source_name,
                "platform": source.get("platform"),
                "language": event.get("language"),
                "status": lifecycle.get("status"),
                "evidence_type": resolution.get("evidence_type"),
                "source_confidence": event.get("source_confidence"),
                "routing_entity": labels.get("routing_entity"),
                "hitl_required_label": labels.get("hitl_required"),
                "hitl_reason": labels.get("hitl_reason"),
                "eval_candidate": labels.get("eval_candidate"),
                "captured_at": event.get("captured_at"),
                "published_at": event.get("published_at"),
            },
            retrieval_weight=0.92 if _truthy(labels.get("eval_candidate")) else 0.86,
        ))
    return docs


def _build_v74_gap_resolution_docs(source_root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []

    summary_rows, summary_file = _read_v74_csv("coverage_summary_v74_gap_resolution.csv")
    if summary_rows:
        desc = "Batch 5 v74 municipality contact gap-resolution summary. " + " ".join(
            f"{r.get('metric')}: {r.get('value')} ({r.get('notes')})." for r in summary_rows
        )
        _append_unique_doc(docs, _doc_base(
            doc_id="v74-gap-resolution-coverage-summary",
            selector="HITL",
            description=desc,
            doc_type="coverage_audit",
            route_mode="audit_context",
            route_authority="supporting_audit",
            source_reliability="handoff_validation",
            complaint_types=["municipality_contact_coverage", "manual_review"],
            keywords=["v74", "gap resolution", "municipality contact coverage", "no auto route"],
            source_files=[summary_file],
            confidence_prior=0.84,
            responsibility_level="context",
            hitl_required=True,
            hitl_conditions=["Coverage/contact rows do not authorize auto-routing."],
            structured_fields={"source_profile": "v74_gap_resolution_summary", "rows": len(summary_rows)},
            retrieval_weight=0.7,
        ))

    fallback_rows, fallback_file = _read_v74_csv("cedarfix_v74_gap_resolution_current_contact_fallbacks_cumulative.csv")
    for row in fallback_rows:
        name = row.get("municipality_name_en") or row.get("municipality_name_ar") or row.get("municipality_id")
        desc = (
            f"Municipality contact fallback for {name}, {row.get('governorate')}. "
            f"Contact phone: {row.get('contact_phone') or 'not captured'}. Source: {row.get('source_title') or row.get('source_url')}. "
            f"Decision: {row.get('decision_class') or row.get('decision')}. Reason: {row.get('reason')}. "
            "This is contact_fallback_only, not a verified complaint intake route and not auto-route permission."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"v74-contact-fallback-{row.get('coverage_universe_id')}-{_slug(row.get('contact_phone'))}",
            selector="MUN",
            description=desc,
            doc_type="municipality_contact_fallback",
            route_mode="contact_fallback_only",
            route_authority="fallback_only_not_auto_route",
            source_reliability=row.get("decision_class") or "contact_fallback",
            complaint_types=["municipality_contact", "contact_fallback"],
            keywords=[name, row.get("municipality_name_ar", ""), row.get("governorate", ""), row.get("source_title", ""), row.get("contact_phone", "")],
            source_ids=_row_source_ids(row),
            source_files=[fallback_file],
            confidence_prior=_confidence_from_row(row, 0.70),
            responsibility_level="context",
            hitl_required=True,
            hitl_conditions=["Do not auto-route; verify complaint intake separately.", row.get("reason", "")],
            governorates=[row.get("governorate", "")],
            districts=[row.get("district_if_available", "")],
            municipalities=[name],
            hotline=row.get("contact_phone") or None,
            exact_match_terms=[name, row.get("municipality_name_ar", ""), row.get("coverage_universe_id", ""), row.get("municipality_id", "")],
            location_precision="municipality",
            structured_fields={**row, "source_profile": "v74_contact_fallback"},
            retrieval_weight=0.65,
        ))

    staging_rows, staging_file = _read_v74_csv("cedarfix_v74_gap_resolution_new_complaint_review_staging_candidates.csv")
    for row in staging_rows:
        name = row.get("municipality_name_en") or row.get("municipality_name_ar") or row.get("municipality_id")
        desc = (
            f"Scoped municipality complaint-intake staging candidate for {name}. "
            f"Evidence: {row.get('complaint_intake_evidence') or row.get('evidence_snippet')}. "
            f"Recommended use: {row.get('recommended_use')}. Reason: {row.get('reason')}. "
            "Manual review is required before production or auto-route."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"v74-staging-candidate-{row.get('coverage_universe_id')}",
            selector="HITL",
            description=desc,
            doc_type="complaint_intake_staging_candidate",
            route_mode="manual_review_only",
            route_authority="staging_not_production",
            source_reliability=row.get("decision_class") or "staging_candidate",
            complaint_types=["building_safety", "cracked_building", "unsafe_building", "municipal_complaint_intake"],
            keywords=[name, "cracked building", "unsafe building", row.get("source_title", ""), row.get("evidence_snippet", "")],
            source_ids=_row_source_ids(row),
            source_files=[staging_file],
            confidence_prior=_confidence_from_row(row, 0.72),
            responsibility_level="boundary",
            hitl_required=True,
            hitl_conditions=[row.get("reason", ""), "Scoped candidate only; not generic complaint intake."],
            governorates=[row.get("governorate", "")],
            districts=[row.get("district_if_available", "")],
            municipalities=[name],
            exact_match_terms=[name, row.get("municipality_name_ar", ""), "cracked buildings", "unsafe buildings"],
            location_precision="municipality",
            structured_fields={**row, "source_profile": "v74_staging_candidate"},
            retrieval_weight=0.9,
        ))

    no_contact_rows, no_contact_file = _read_v74_csv("cedarfix_v74_gap_resolution_no_contact_remaining.csv")
    for row in no_contact_rows:
        name = row.get("municipality_name_en") or row.get("municipality_name_ar") or row.get("municipality_id")
        desc = (
            f"No usable contact or complaint endpoint found for {name}, {row.get('governorate')}. "
            f"Evidence: {row.get('evidence_snippet')}. Recommended next action: {row.get('recommended_next_action')}. "
            "Do not fabricate a route or phone number; send to human review/user assist."
        )
        _append_unique_doc(docs, _doc_base(
            doc_id=f"v74-no-contact-{row.get('coverage_universe_id')}",
            selector="HITL",
            description=desc,
            doc_type="no_contact_blocker",
            route_mode="human_review_user_assist",
            route_authority="blocker",
            source_reliability=row.get("v74_status") or "no_contact_adjudicated",
            complaint_types=["municipality_contact_missing", "manual_review"],
            keywords=[name, row.get("municipality_name_ar", ""), row.get("governorate", ""), "no contact", "do not fabricate"],
            source_ids=_row_source_ids(row),
            source_files=[no_contact_file],
            confidence_prior=0.86,
            responsibility_level="boundary",
            hitl_required=True,
            hitl_conditions=[row.get("recommended_next_action", ""), "No usable contact/endpoint found."],
            governorates=[row.get("governorate", "")],
            municipalities=[name],
            exact_match_terms=[name, row.get("municipality_name_ar", ""), row.get("coverage_universe_id", "")],
            location_precision="municipality",
            structured_fields={**row, "source_profile": "v74_no_contact_blocker"},
            retrieval_weight=1.0,
        ))

    validation_rows, validation_file = _read_v74_csv("v74_gap_resolution_validation_checks.csv")
    if validation_rows:
        desc = "v74 validation checks: " + " ".join(
            f"{r.get('check')}={r.get('status')} ({r.get('details')})." for r in validation_rows
        )
        _append_unique_doc(docs, _doc_base(
            doc_id="v74-gap-resolution-validation-checks",
            selector="HITL",
            description=desc,
            doc_type="validation_audit",
            route_mode="audit_context",
            route_authority="supporting_audit",
            source_reliability="validation_pass",
            complaint_types=["municipality_contact_coverage", "validation"],
            keywords=["v74", "validation", "no auto route", "strict promotion guard"],
            source_files=[validation_file],
            confidence_prior=0.82,
            responsibility_level="context",
            hitl_required=True,
            hitl_conditions=["Validation confirms no auto-route promotions in v74."],
            structured_fields={"source_profile": "v74_validation_checks", "rows": len(validation_rows)},
            retrieval_weight=0.65,
        ))
    return docs


def _build_structured_docs(rag_dir: Path) -> list[dict[str, Any]]:
    source_root = _discover_source_data_root()
    if source_root is None:
        return []
    docs: list[dict[str, Any]] = []
    for builder in [
        _build_taxonomy_docs,
        _build_routing_rule_docs,
        _build_data_entity_fact_docs,
        _build_remediation_docs,
        _build_root_boundary_docs,
        _build_domain_guardrail_docs,
        _build_domain_service_docs,
        _build_municipality_service_docs,
        _build_municipality_channel_docs,
        _build_municipality_registry_profile_docs,
        _build_municipality_contact_candidate_docs,
        _build_municipality_discovery_queue_docs,
        _build_towns_registry_reference_docs,
        _build_municipality_resolution_bundle_docs,
        _build_sector_agency_policy_docs,
        _build_entity_service_area_map_docs,
        _build_municipality_responsibility_docs,
        _build_required_field_profile_docs,
        _build_cdr_project_service_area_docs,
        _build_waste_site_registry_docs,
        _build_source_registry_docs,
        _build_complaint_intelligence_event_docs,
        _build_v74_gap_resolution_docs,
    ]:
        docs.extend(builder(source_root))
    return sorted(docs, key=lambda d: d["doc_id"])


def _discover_entity_dirs(values: list[str] | None) -> list[Path]:
    candidates = [Path(v).resolve() for v in values or []]
    candidates.extend(DEFAULT_ENTITY_DIR_CANDIDATES)
    out: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path.exists() and path not in seen:
            out.append(path)
            seen.add(path)
    if out:
        return out
    for path in FALLBACK_ENTITY_DIR_CANDIDATES:
        if path.exists() and path not in seen:
            out.append(path)
            seen.add(path)
    return out


def _discover_rag_dossier_files(rag_dir: Path) -> list[Path]:
    """Accept either the RAG Data root or a direct dossier directory."""
    candidates = [rag_dir]
    if rag_dir == DEFAULT_RAG_DIR or (rag_dir / "source").exists():
        candidates.insert(0, rag_dir / "source" / "rag_dossiers")
    if rag_dir != DEFAULT_RAG_DOSSIER_DIR:
        candidates.append(DEFAULT_RAG_DOSSIER_DIR)

    files: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if not candidate.exists():
            continue
        for path in sorted(candidate.glob("*.json")):
            resolved = path.resolve()
            if resolved in seen or path.name.startswith("_"):
                continue
            seen.add(resolved)
            files.append(path)
    return files


def compile_docs(rag_dir: Path, entity_dirs: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    dossiers: list[dict[str, Any]] = []
    rag_dossier_files = _discover_rag_dossier_files(rag_dir)
    for path in rag_dossier_files:
        dossiers.append(_load_dossier(path, "rag_data"))

    for entity_dir in entity_dirs:
        for path in sorted(entity_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            dossiers.append(_load_dossier(path, "entity_kb"))

    entities = _merge_entities(dossiers)
    entity_docs = _build_docs(entities)
    structured_docs = _build_structured_docs(rag_dir)
    all_docs = [*entity_docs, *structured_docs]
    for doc in all_docs:
        _enforce_forced_hitl_route_mode(doc)
    _apply_retrieval_stage_policy(all_docs)
    docs = sorted(all_docs, key=lambda d: d["doc_id"])
    manifest = {
        "compiled_at": datetime.now(tz=timezone.utc).isoformat(),
        "rag_dir": _portable_path(rag_dir),
        "rag_dossier_files": [_portable_path(p) for p in rag_dossier_files],
        "entity_dirs": [_portable_path(p) for p in entity_dirs],
        "source_dossier_count": len(dossiers),
        "advanced_dossier_path": _portable_path(DEFAULT_ADVANCED_DOSSIER),
        "advanced_dossier_doc_count": len(structured_docs),
        "entity_count": len(entities),
        "doc_count": len(docs),
        "doc_types": dict(Counter(d.get("doc_type", "unknown") for d in docs)),
        "route_modes": dict(Counter(d.get("route_mode", "unknown") for d in docs)),
        "retrieval_stages": dict(Counter(d.get("retrieval_stage", "unknown") for d in docs)),
        "retrieval_lanes": dict(Counter(d.get("retrieval_lane", "unknown") for d in docs)),
        "stage1_dispatch_candidate_count": sum(1 for d in docs if bool(d.get("stage1_dispatch_candidate"))),
        "docs_by_entity": dict(Counter(d["source_entity_id"] for d in docs)),
        "docs_by_routing_entity": dict(Counter(d["entity_enum"] for d in docs)),
        "responsibility_levels": dict(Counter(d["responsibility_level"] for d in docs)),
    }
    return docs, manifest, structured_docs


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile CedarFix routing knowledge for RAG.")
    parser.add_argument(
        "--rag-dir",
        default=str(DEFAULT_RAG_DIR),
        help="RAG Data root or a directory containing RAG dossier JSON files.",
    )
    parser.add_argument("--entity-dir", action="append", help="Optional entity KB directory. May be passed multiple times.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSONL path.")
    parser.add_argument(
        "--production-json",
        default=str(DEFAULT_PRODUCTION_JSON),
        help="Output single-file JSON array path for production packaging.",
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Output manifest JSON path.")
    args = parser.parse_args()

    rag_dir = Path(args.rag_dir).resolve()
    entity_dirs = _discover_entity_dirs(args.entity_dir)
    output = Path(args.output).resolve()
    production_json = Path(args.production_json).resolve()
    manifest_path = Path(args.manifest).resolve()

    backfilled_rag_entities = _backfill_rag_entity_dossiers(rag_dir, entity_dirs)

    docs, manifest, structured_docs = compile_docs(rag_dir, entity_dirs)
    stage_buckets = _partition_docs_by_stage(docs)

    DEFAULT_ADVANCED_DOSSIER.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_ADVANCED_DOSSIER.open("w", encoding="utf-8", newline="\n") as f:
        for doc in structured_docs:
            f.write(json.dumps(doc, ensure_ascii=True, sort_keys=True) + "\n")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=True, sort_keys=True) + "\n")

    production_json.parent.mkdir(parents=True, exist_ok=True)
    production_json.write_text(
        json.dumps(docs, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    stage_outputs = {
        "stage1_dispatch": DEFAULT_STAGE1_OUTPUT,
        "stage2_operations": DEFAULT_STAGE2_OUTPUT,
        "stage3_evidence": DEFAULT_STAGE3_OUTPUT,
    }
    for stage, stage_path in stage_outputs.items():
        stage_path.parent.mkdir(parents=True, exist_ok=True)
        with stage_path.open("w", encoding="utf-8", newline="\n") as f:
            for doc in stage_buckets.get(stage, []):
                f.write(json.dumps(doc, ensure_ascii=True, sort_keys=True) + "\n")

    manifest["rag_dossier_backfill_count"] = len(backfilled_rag_entities)
    manifest["rag_dossier_backfilled_files"] = backfilled_rag_entities
    manifest["compiled_jsonl_output"] = _portable_path(output)
    manifest["production_json_output"] = _portable_path(production_json)
    manifest["production_json_doc_count"] = len(docs)
    manifest["stage_partition_outputs"] = {
        stage: _portable_path(path) for stage, path in stage_outputs.items()
    }
    manifest["stage_partition_counts"] = {
        stage: len(stage_buckets.get(stage, [])) for stage in stage_outputs
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Compiled {len(docs)} RAG routing documents from {manifest['entity_count']} entities.")
    print(f"Backfilled {len(backfilled_rag_entities)} missing RAG entity dossiers.")
    print(f"Wrote {DEFAULT_ADVANCED_DOSSIER}")
    print(f"Wrote {output}")
    print(f"Wrote {production_json}")
    print(f"Wrote {DEFAULT_STAGE1_OUTPUT}")
    print(f"Wrote {DEFAULT_STAGE2_OUTPUT}")
    print(f"Wrote {DEFAULT_STAGE3_OUTPUT}")
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()

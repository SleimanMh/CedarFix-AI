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
DEFAULT_MANIFEST = DEFAULT_RAG_DIR / "compiled" / "routing_knowledge_manifest.json"

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


def _ascii_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\([^)]*[\u0600-\u06ff][^)]*\)", "", text)
    text = text.replace("→", " to ").replace("—", " - ").replace("–", "-")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
        keywords.extend(term for term in terms if _slug(term) not in STOPWORDS)
    return _unique(keywords, limit=55)


def _truthy(value: Any) -> bool:
    return _slug(value) in {"true", "yes", "y", "1", "required", "hitl", "manual_review_needed"}


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if value is None:
            continue
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null", "#n/a"}:
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
    desc = _ascii_text(description)
    src_files = _unique(source_files or [], limit=10)
    src_ids = _unique(source_ids or src_files, limit=20)
    return {
        "doc_id": _slug(doc_id),
        "doc_type": _slug(doc_type),
        "route_mode": _slug(route_mode),
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
        "keywords": _compact_keywords([*(keywords or []), selector, doc_type, route_mode]),
        "not_responsible_for": _unique(not_responsible_for or [], limit=24),
        "description": desc,
        "confidence_prior": round(max(0.0, min(1.0, confidence_prior)), 3),
        "hotline": hotline,
        "source_ids": src_ids,
        "source_files": src_files,
        "hitl_always_required": bool(hitl_required),
        "hitl_conditions": _unique(hitl_conditions or [], limit=16),
        "last_reviewed": (structured_fields or {}).get("last_checked") or (structured_fields or {}).get("last_verified"),
        "responsibility_level": _slug(responsibility_level),
        "location_precision": _ascii_text(location_precision) or None,
        "exact_match_terms": _unique(exact_match_terms or [], limit=24),
        "negative_signals": _unique(negative_signals or [], limit=24),
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
                f"Examples: {row.get('examples') or 'none'}. Limitations: {row.get('limitations') or row.get('notes') or 'none'}."
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
                keywords=[directory.name, row.get("trigger", ""), row.get("decision_rule", ""), row.get("examples", ""), row.get("routing_use", "")],
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
        mun_name = row.get("name_en") or row.get("name_ar") or row.get("municipality_id")
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
        for service, selector, entity_name, notes, conf, complaint_types in services:
            if not selector:
                continue
            desc = (
                f"Municipality service map for {mun_name}, {row.get('district_en')}, {row.get('governorate_en')}. "
                f"For {service} complaints, mapped entity is {entity_name or selector} ({selector}). "
                f"Notes: {notes}. Source basis: {row.get('source_basis')}. Last built: {row.get('last_built')}."
            )
            _append_unique_doc(docs, _doc_base(
                doc_id=f"mun-service-{row.get('registry_id') or row.get('municipality_id')}-{service}",
                selector=selector,
                description=desc,
                doc_type="municipality_service_map",
                route_mode="geo_service_route",
                route_authority="location_map",
                source_reliability=row.get("source_basis") or "municipality_map",
                complaint_types=_split_values(complaint_types),
                keywords=[service, selector, entity_name, notes, *base_terms],
                source_files=[_portable_path(path)],
                confidence_prior=_confidence(conf or "medium"),
                responsibility_level="primary" if service != "national_road" else "secondary",
                hitl_required="HITL" in _ascii_text(notes).upper() or service == "national_road",
                hitl_conditions=[notes or "", "Use exact municipality/GPS and road class when applicable."],
                governorates=gov,
                districts=district,
                municipalities=mun,
                exact_match_terms=base_terms,
                location_precision="municipality",
                structured_fields={**row, "source_profile": "municipality_service_mapping", "service": service},
                retrieval_weight=1.35 if service in {"water", "electricity", "fixed_telecom"} else 1.2,
            ))
    return docs


def _build_municipality_channel_docs(source_root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    mun_dir = source_root / "knowledge_base" / "municipalities"
    for filename, doc_type, mode, weight in [
        ("municipality_official_channels.csv", "municipality_channel", "complaint_intake_or_channel", 1.2),
        ("municipality_complaint_workflows.csv", "municipality_workflow", "complaint_workflow", 1.25),
        ("municipal_union_service_responsibilities.csv", "municipal_union_service", "shared_service_context", 0.95),
        ("municipal_union_memberships.csv", "municipal_union_membership", "geo_union_context", 0.8),
    ]:
        path = mun_dir / filename
        for row in _read_csv(path):
            row_id = row.get("channel_id") or row.get("workflow_id") or row.get("membership_id") or row.get("responsibility_id") or f"{filename}-{len(docs)}"
            name = row.get("name_en") or row.get("municipality_name_en") or row.get("municipality_match_key") or row.get("municipality_id") or row.get("union_name_en")
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
                keywords=[name, row.get("channel_type", ""), row.get("channel_value", ""), row.get("accepted_complaint_categories", ""), row.get("evidence_snippet", "")],
                source_ids=_row_source_ids(row),
                source_files=[_portable_path(path)],
                confidence_prior=_confidence_from_row(row, 0.78),
                responsibility_level="primary" if doc_type in {"municipality_channel", "municipality_workflow"} else "context",
                hitl_required=not ("verified_high" in _slug(row.get("workflow_confidence")) or "verified_official" in _slug(row.get("verification_status"))),
                hitl_conditions=[row.get("notes", ""), row.get("evidence_snippet", "")],
                governorates=[row.get("governorate_en") or row.get("governorate", "")],
                districts=[row.get("district_en") or row.get("district_if_available", "")],
                municipalities=[name],
                exact_match_terms=[name, row.get("name_ar", ""), row.get("municipality_match_key", ""), row_id],
                location_precision="municipality",
                structured_fields={**row, "source_profile": f"municipality_{doc_type}"},
                retrieval_weight=weight,
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
        _build_remediation_docs,
        _build_root_boundary_docs,
        _build_domain_guardrail_docs,
        _build_domain_service_docs,
        _build_municipality_service_docs,
        _build_municipality_channel_docs,
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
    docs = sorted([*entity_docs, *structured_docs], key=lambda d: d["doc_id"])
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
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Output manifest JSON path.")
    args = parser.parse_args()

    rag_dir = Path(args.rag_dir).resolve()
    entity_dirs = _discover_entity_dirs(args.entity_dir)
    output = Path(args.output).resolve()
    manifest_path = Path(args.manifest).resolve()

    docs, manifest, structured_docs = compile_docs(rag_dir, entity_dirs)
    DEFAULT_ADVANCED_DOSSIER.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_ADVANCED_DOSSIER.open("w", encoding="utf-8", newline="\n") as f:
        for doc in structured_docs:
            f.write(json.dumps(doc, ensure_ascii=True, sort_keys=True) + "\n")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=True, sort_keys=True) + "\n")

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Compiled {len(docs)} RAG routing documents from {manifest['entity_count']} entities.")
    print(f"Wrote {DEFAULT_ADVANCED_DOSSIER}")
    print(f"Wrote {output}")
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()

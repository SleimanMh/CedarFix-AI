"""IEP-3 calibrated routing engine.

Reads sector_agency_map.csv to determine primary routing entity.
Produces a routing decision with confidence and SHAP-style top-3 feature
explanations for every complaint.

Routing logic
-------------
1. If issue_type contains a direct sector signal, use it.
2. Otherwise, fall back to IEP-1 routing_sector.
3. Look up primary_entity_abbr from sector_agency_map.
4. Apply HITL gate: sectors with hitl_required=true always produce
   routing_confidence <= 0.60 and set needs_hitl=True.
5. Priority score: base 50 + sector urgency bonus + drift penalty.

The calibration output for each decision is stored in shap_top3.
"""
from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECTOR_MAP_PATH = ROOT / "data" / "knowledge_base" / "sector_agency_map.csv"

# Routing confidence by sector (calibrated from batch7+8 eval set)
_SECTOR_CONFIDENCE: dict[str, float] = {
    "ROADS": 0.83,
    "WATER": 0.81,
    "ELECTRICITY": 0.55,   # always HITL
    "WASTE": 0.79,
    "FLOODING": 0.76,
    "SAFETY": 0.52,        # always HITL
    "TELECOM": 0.58,       # HITL until classifier matures
    "OTHER": 0.40,
}

# Priority bonus by sector urgency
_SECTOR_URGENCY: dict[str, float] = {
    "FLOODING": 30.0,
    "SAFETY": 35.0,
    "ELECTRICITY": 20.0,
    "WATER": 15.0,
    "ROADS": 10.0,
    "WASTE": 5.0,
    "TELECOM": 5.0,
    "OTHER": 0.0,
}


@lru_cache(maxsize=1)
def _load_sector_map() -> dict[str, dict]:
    """Load sector_agency_map.csv once and cache."""
    if not SECTOR_MAP_PATH.exists():
        return {}
    with SECTOR_MAP_PATH.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return {row["sector"]: row for row in rows}


def _pick_sector(routing_sector: str | None, issue_type: str | None) -> str:
    """Resolve the best sector from IEP-1 signals."""
    if routing_sector and routing_sector not in ("", "OTHER", "UNKNOWN"):
        return routing_sector.upper()

    if issue_type:
        it = issue_type.lower()
        if "flood" in it or "drain" in it or "rain" in it:
            return "FLOODING"
        if "elect" in it or "kahraba" in it or "power" in it:
            return "ELECTRICITY"
        if "water" in it or "may" in it or "mie" in it:
            return "WATER"
        if "road" in it or "tari" in it or "jora" in it or "street" in it:
            return "ROADS"
        if "waste" in it or "zbele" in it or "garbage" in it:
            return "WASTE"
        if "safety" in it or "khouf" in it or "7ariki" in it:
            return "SAFETY"
        if "telecom" in it or "internet" in it or "phone" in it:
            return "TELECOM"

    return "OTHER"


def route(
    complaint_id: str,
    routing_sector: str | None,
    issue_type: str | None,
    issue_type_confidence: float | None,
    drift_score: int | None,
    gps_lat: float | None,
    gps_lon: float | None,
) -> dict:
    """Produce a routing decision for one complaint.

    Returns a dict with:
        routing_sector      str
        routing_entity      str   (primary_entity_abbr)
        routing_confidence  float
        priority_score      float  (0–100)
        hitl_required       bool
        hitl_reason         str | None
        shap_top3           dict  (feature → contribution)
    """
    sector = _pick_sector(routing_sector, issue_type)
    sector_map = _load_sector_map()
    sector_row = sector_map.get(sector) or sector_map.get("OTHER", {})

    entity = sector_row.get("primary_entity_abbr", "") or ""
    hitl_required = sector_row.get("hitl_required", "false").lower() == "true"

    base_conf = _SECTOR_CONFIDENCE.get(sector, 0.50)

    # Confidence penalties
    conf = base_conf
    if drift_score and drift_score >= 2:
        conf = max(0.30, conf - 0.15)
    if issue_type_confidence is not None and issue_type_confidence < 0.50:
        conf = max(0.25, conf - 0.10)

    if hitl_required:
        conf = min(conf, 0.60)

    # Priority score
    urgency_bonus = _SECTOR_URGENCY.get(sector, 0.0)
    priority = 50.0 + urgency_bonus
    if drift_score and drift_score >= 2:
        priority = max(0.0, priority - 10.0)
    if gps_lat is not None and gps_lon is not None:
        priority = min(100.0, priority + 5.0)  # GPS grounding bonus

    hitl_reason: str | None = None
    if hitl_required:
        hitl_reason = f"sector_{sector.lower()}_always_requires_hitl"
    elif conf < 0.65:
        hitl_required = True
        hitl_reason = "routing_confidence_below_threshold"

    shap_top3 = {
        "sector_signal": round(base_conf * 0.5, 3),
        "issue_type_conf": round((issue_type_confidence or 0.5) * 0.3, 3),
        "drift_penalty": round(-(0.15 if (drift_score or 0) >= 2 else 0.0), 3),
    }

    return {
        "routing_sector": sector,
        "routing_entity": entity,
        "routing_confidence": round(conf, 4),
        "priority_score": round(priority, 2),
        "hitl_required": hitl_required,
        "hitl_reason": hitl_reason,
        "shap_top3": shap_top3,
    }

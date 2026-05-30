"""
route_complaint.py
CedarFix — end-to-end complaint routing engine.

Entry point:
    from src.route_complaint import route
    result = route("zbele 3am tetrak b jiwar l baladiye ta3 zahle")

Or from CLI:
    python src/route_complaint.py "zbele ma ndafat men l shere3 b jounieh"
    python src/route_complaint.py --demo

Pipeline:
    1. Classify complaint category via Arabizi vocab keyword matching
    2. Match location string to municipality_id via alias lookup (+ GPS fallback)
    3. Look up service mappings (water / electricity / road entities for that municipality)
    4. Apply routing rules (complaint_taxonomy → routing_rules → resolved entity IDs)
    5. Apply HITL gates (RR-GATE rules)
    6. Return a RouteResult with entity, secondary, hitl_required, confidence, reason
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent

KB = ROOT / "data" / "knowledge_base"
MUN_DIR = KB / "municipalities"

# ---------------------------------------------------------------------------
# Load-time data (loaded once on import)
# ---------------------------------------------------------------------------

def _load_vocab() -> dict[str, str]:
    """
    variant_string → sector from arabizi_vocabulary.json.
    Structure: {sectors: {SECTOR: {issue_type_keywords: {issue: [variant, ...]}}}}
    Indexes both full phrases AND individual significant words.
    """
    vpath = KB / "arabizi_vocabulary.json"
    if not vpath.exists():
        return {}
    data = json.loads(vpath.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for sector_name, sector_data in data.get("sectors", {}).items():
        for issue_type, variants in sector_data.get("issue_type_keywords", {}).items():
            for v in variants:
                phrase = v.strip().lower()
                # Index full phrase
                out[phrase] = sector_name
                # Index each significant word (len > 2)
                for word in phrase.split():
                    if len(word) > 2 and word not in out:
                        out[word] = sector_name

    # Supplement: Arabizi/transliterated keywords missing from vocab JSON
    _VOCAB_SUPPLEMENT: dict[str, str] = {
        # SAFETY — accidents, incidents, gunshots
        "7adis": "SAFETY", "7aades": "SAFETY", "7awadis": "SAFETY",
        "dawshra": "SAFETY", "dawshara": "SAFETY", "ta2bi2": "SAFETY",
        "masalla7": "SAFETY", "sila7": "SAFETY",
        # SAFETY — sidewalk/road obstruction
        "msakkra": "SAFETY", "msakker": "SAFETY",
        # TELECOM
        "internet": "TELECOM", "wifi": "TELECOM", "ogero": "TELECOM",
        "khatt": "TELECOM", "shabake": "TELECOM", "netwrok": "TELECOM",
        "net": "TELECOM", "signal": "TELECOM",
        # ENVIRONMENT (not in vocab)
        "tawasokh": "ENVIRONMENT", "ta22okh": "ENVIRONMENT",
        "7ar2": "ENVIRONMENT", "7arrak": "ENVIRONMENT",
        "dawshe": "ENVIRONMENT",
    }
    for k, v in _VOCAB_SUPPLEMENT.items():
        if k not in out:  # don't overwrite existing vocab entries
            out[k] = v

    return out


def _load_taxonomy() -> dict[str, dict]:
    """complaint_type_id → row dict."""
    path = KB / "complaint_taxonomy.csv"
    if not path.exists():
        return {}
    return {r["complaint_type_id"]: r
            for r in csv.DictReader(open(path, encoding="utf-8"))}


def _load_routing_rules() -> list[dict]:
    path = KB / "routing_rules.csv"
    if not path.exists():
        return []
    return list(csv.DictReader(open(path, encoding="utf-8")))


def _load_aliases() -> dict[str, str]:
    """normalised alias string → municipality_id."""
    path = MUN_DIR / "municipality_aliases.csv"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        alias = _normalize_name(r["alias_value"])
        if alias:
            out[alias] = r["municipality_id"]
    return out


def _load_service_mappings() -> dict[str, dict]:
    """municipality_id → service mapping row."""
    path = MUN_DIR / "municipality_service_mappings.csv"
    if not path.exists():
        return {}
    return {r["municipality_id"]: r
            for r in csv.DictReader(open(path, encoding="utf-8"))}


def _load_registry() -> dict[str, dict]:
    """municipality_id → registry row (for name/lat/lon lookup)."""
    path = MUN_DIR / "national_municipality_registry.csv"
    if not path.exists():
        return {}
    return {r["municipality_id"]: r
            for r in csv.DictReader(open(path, encoding="utf-8"))}


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

_ARABIC_ARTICLES = re.compile(r"^(ال|al[ -]?)", re.IGNORECASE)
_PUNCT = re.compile(r"[^a-z0-9\u0600-\u06ff\s]")
_SPACES = re.compile(r"\s+")

def _normalize_name(s: str) -> str:
    s = s.strip().lower()
    s = _ARABIC_ARTICLES.sub("", s)
    s = _PUNCT.sub(" ", s)
    s = _SPACES.sub(" ", s).strip()
    return s


def _arabizi_tokens(text: str) -> list[str]:
    """Split text into lowercase tokens, keeping digits and Arabic chars."""
    return re.findall(r"[\w\u0600-\u06ff]+", text.lower())


# ---------------------------------------------------------------------------
# English + Arabic script keyword tables (in-code fallback when Arabizi fails)
# ---------------------------------------------------------------------------

_EN_KEYWORDS: dict[str, str] = {
    # WASTE
    "garbage": "WASTE", "trash": "WASTE", "waste": "WASTE", "rubbish": "WASTE",
    "litter": "WASTE", "dump": "WASTE", "dumpster": "WASTE", "bins": "WASTE",
    "sanitation": "WASTE", "recycling": "WASTE", "landfill": "WASTE",
    "collected": "WASTE", "collection": "WASTE", "pile": "WASTE", "piling": "WASTE",
    # ROADS
    "road": "ROADS", "pothole": "ROADS", "pavement": "ROADS", "asphalt": "ROADS",
    "sidewalk": "ROADS", "manhole": "ROADS", "roadblock": "ROADS",
    "street": "ROADS", "cracked": "ROADS", "paving": "ROADS",
    "paved": "ROADS", "unpaved": "ROADS",
    # WATER
    "water": "WATER", "pipe": "WATER", "leak": "WATER", "leaking": "WATER",
    "sewage": "WATER", "plumbing": "WATER",
    "faucet": "WATER", "tap": "WATER",
    # ELECTRICITY
    "electricity": "ELECTRICITY", "power": "ELECTRICITY", "outage": "ELECTRICITY",
    "blackout": "ELECTRICITY", "electric": "ELECTRICITY", "lights": "ELECTRICITY",
    "edl": "ELECTRICITY", "generator": "ELECTRICITY", "transformer": "ELECTRICITY",
    # FLOODING
    "flood": "FLOODING", "flooding": "FLOODING", "flooded": "FLOODING",
    "overflow": "FLOODING", "rainwater": "FLOODING", "stormwater": "FLOODING",
    "inundated": "FLOODING", "drain": "FLOODING", "drains": "FLOODING",
    "drainage": "FLOODING", "submerged": "FLOODING",
    # SAFETY — only clear emergencies, not generic adjectives
    "fire": "SAFETY", "emergency": "SAFETY", "collapse": "SAFETY",
    "collapsed": "SAFETY", "explosion": "SAFETY", "gas leak": "SAFETY",
    "injury": "SAFETY", "injured": "SAFETY", "armed": "SAFETY",
    "shooting": "SAFETY", "ambulance": "SAFETY",
    "obstruction": "SAFETY", "blocking": "SAFETY",  # blocking sidewalk/path
    "accident": "SAFETY", "crash": "SAFETY",
    # TELECOM
    "internet": "TELECOM", "wifi": "TELECOM", "network": "TELECOM",
    "telecom": "TELECOM", "ogero": "TELECOM", "broadband": "TELECOM",
    "connection": "TELECOM", "disconnected": "TELECOM",
    "4g": "TELECOM", "5g": "TELECOM", "coverage": "TELECOM",
    "telephone": "TELECOM", "landline": "TELECOM",
    # ENVIRONMENT
    "pollution": "ENVIRONMENT", "polluted": "ENVIRONMENT", "contamination": "ENVIRONMENT",
    "burning": "ENVIRONMENT", "smoke": "ENVIRONMENT", "noise": "ENVIRONMENT",
    "quarry": "ENVIRONMENT", "deforestation": "ENVIRONMENT", "odor": "ENVIRONMENT",
    # OTHER — administrative/unclear complaints
    "respond": "OTHER", "response": "OTHER", "request": "OTHER",
    "unclear": "OTHER", "complaint": "OTHER", "ignored": "OTHER",
    "administrative": "OTHER", "municipality": "OTHER", "permit": "OTHER",
    "unresponsive": "OTHER", "follow": "OTHER",
}

_AR_KEYWORDS: dict[str, str] = {
    # WASTE — standard + dialectal
    "زبالة": "WASTE", "نفايات": "WASTE", "القمامة": "WASTE", "نفايه": "WASTE",
    "قمامة": "WASTE", "جمع": "WASTE", "مكب": "WASTE", "نفاية": "WASTE",
    # ROADS — include common dialectal/informal forms
    "طريق": "ROADS", "حفرة": "ROADS", "أسفلت": "ROADS", "اسفلت": "ROADS",
    "رصيف": "ROADS", "تشقق": "ROADS", "بالوعة": "ROADS",
    "تالف": "ROADS", "شارع": "ROADS", "جسر": "ROADS",
    "جورة": "ROADS",  # Lebanese dialect for pothole
    "ردم": "ROADS",   # rubble/fill blocking road
    "مسكر": "ROADS",  # blocked
    # WATER
    "مياه": "WATER", "ماء": "WATER", "أنابيب": "WATER", "تسرب": "WATER",
    "الحنفية": "WATER", "مجاري": "WATER", "ماي": "WATER",
    # ELECTRICITY — standard + dialectal كهربا (no hamza)
    "كهرباء": "ELECTRICITY", "كهربا": "ELECTRICITY", "كهربائي": "ELECTRICITY",
    "تيار": "ELECTRICITY", "انقطاع": "ELECTRICITY",
    "عداد": "ELECTRICITY", "مولد": "ELECTRICITY", "ترانسفورمر": "ELECTRICITY",
    "شرطان": "ELECTRICITY",  # electrical wires (dialectal)
    "ضو": "ELECTRICITY",     # light (dialectal ضو instead of ضوء)
    # FLOODING
    "فيضان": "FLOODING", "فياضان": "FLOODING",
    "غرق": "FLOODING", "طفح": "FLOODING",
    # SAFETY
    "حريق": "SAFETY", "حرائق": "SAFETY", "انهيار": "SAFETY", "خطر": "SAFETY",
    "غاز": "SAFETY", "إسعاف": "SAFETY", "مسلح": "SAFETY", "إطفاء": "SAFETY",
    "جريح": "SAFETY", "مصاب": "SAFETY", "انفجار": "SAFETY",
    "حادث": "SAFETY",  # accident
    # TELECOM
    "إنترنت": "TELECOM", "انترنت": "TELECOM", "شبكة": "TELECOM",
    "أوجيرو": "TELECOM", "اوجيرو": "TELECOM", "اتصالات": "TELECOM",
    "خط": "TELECOM",
    # ENVIRONMENT
    "تلوث": "ENVIRONMENT", "حرق": "ENVIRONMENT", "مرمى": "ENVIRONMENT",
    "ضجيج": "ENVIRONMENT", "دخان": "ENVIRONMENT", "روائح": "ENVIRONMENT",
}

# Arabic definite article prefix (ال) — strip before keyword lookup
_AR_ARTICLE = re.compile(r"^ال")


# ---------------------------------------------------------------------------
# Sector detection via vocab
# ---------------------------------------------------------------------------

def detect_sector(text: str, vocab: dict[str, str]) -> tuple[str, float]:
    """
    Returns (sector, confidence_score).
    Tries multi-word phrases first (greedy left-to-right), then single tokens.
    Also normalises Arabizi q↔2 substitution (7ariq / 7ari2 both = حريق).
    Confidence = matched_hits / total_tokens.
    """
    text_lower = text.lower()
    tokens = _arabizi_tokens(text_lower)
    hits: dict[str, int] = {}
    matched_positions: set[int] = set()

    def _lookup(key: str) -> Optional[str]:
        """Try key, then q↔2 variant."""
        sec = vocab.get(key)
        if sec:
            return sec
        if key.endswith("2"):
            return vocab.get(key[:-1] + "q")
        if key.endswith("q"):
            return vocab.get(key[:-1] + "2")
        return None

    # Pass 1: try 4/3/2-word phrases (greedy)
    for n in (4, 3, 2):
        for i in range(len(tokens) - n + 1):
            if i in matched_positions:
                continue
            phrase = " ".join(tokens[i:i + n])
            sec = _lookup(phrase)
            if sec:
                hits[sec] = hits.get(sec, 0) + 1
                for j in range(i, i + n):
                    matched_positions.add(j)

    # Pass 2: single tokens not already matched
    for i, tok in enumerate(tokens):
        if i in matched_positions:
            continue
        sec = _lookup(tok)
        if sec:
            hits[sec] = hits.get(sec, 0) + 1

    # Pass 3: English + Arabic script keywords (if Arabizi produced nothing or weak)
    for tok in tokens:
        sec_en = _EN_KEYWORDS.get(tok)
        if sec_en:
            hits[sec_en] = hits.get(sec_en, 0) + 1
        # Arabic: try with and without ال definite article
        sec_ar = _AR_KEYWORDS.get(tok)
        if sec_ar:
            hits[sec_ar] = hits.get(sec_ar, 0) + 2  # Arabic script = stronger signal
        elif tok.startswith("ال"):
            stripped = _AR_ARTICLE.sub("", tok)
            sec_ar2 = _AR_KEYWORDS.get(stripped)
            if sec_ar2:
                hits[sec_ar2] = hits.get(sec_ar2, 0) + 2

    if not hits:
        return "UNKNOWN", 0.0

    # SAFETY always wins when any clear safety keyword matched
    # (fire/collapse/explosion/gas-leak/armed etc. always route to CD, never MUN)
    if "SAFETY" in hits:
        score = hits["SAFETY"] / max(len(tokens), 1)
        return "SAFETY", round(score, 3)

    best_sector = max(hits, key=hits.__getitem__)
    score = hits[best_sector] / max(len(tokens), 1)
    return best_sector, round(score, 3)


# ---------------------------------------------------------------------------
# National road detection (classified/inter-city → MPWT, not MUN)
# ---------------------------------------------------------------------------

_NATIONAL_ROAD_RE = re.compile(
    r"\b(bein|dawli|duali|autoroute|autostrad|highway|tari2 dawli|tari2 3aam|tari2 3am|ta3 l dawle|ta2 l dawle)\b",
    re.IGNORECASE,
)

def _detect_national_road(text: str) -> bool:
    """True if text signals a classified or inter-city road (→ MPWT, not MUN)."""
    return bool(_NATIONAL_ROAD_RE.search(text))


# ---------------------------------------------------------------------------
# Complaint type matching (sector → best complaint_type_id)
# ---------------------------------------------------------------------------

SECTOR_TO_CATEGORY: dict[str, list[str]] = {
    "WASTE":       ["waste_sanitation"],
    "ROADS":       ["roads_public_works", "public_projects"],
    "WATER":       ["water"],
    "ELECTRICITY": ["electricity"],
    "TELECOM":     ["telecom"],
    "FLOODING":    ["drainage_flooding"],
    "SAFETY":      ["public_safety"],
    "OTHER":       ["ambiguous", "administrative", "environment", "municipal_enforcement"],
}

def pick_complaint_type(sector: str, taxonomy: dict[str, dict]) -> Optional[str]:
    """Return first CT id matching one of the sector's categories."""
    cats = set(SECTOR_TO_CATEGORY.get(sector, []))
    for ct_id, row in taxonomy.items():
        if row.get("category", "") in cats:
            return ct_id
    return None


# ---------------------------------------------------------------------------
# Location lookup
# ---------------------------------------------------------------------------

def resolve_location(text: str, aliases: dict[str, str],
                     registry: dict[str, dict]) -> tuple[Optional[str], str]:
    """
    Returns (municipality_id, method).
    Tries every substring of the text against the alias index.
    """
    tokens = text.split()
    # Try 3-gram, 2-gram, 1-gram substrings
    for n in (4, 3, 2, 1):
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i + n])
            norm = _normalize_name(phrase)
            if norm in aliases:
                return aliases[norm], f"alias_match:{phrase!r}"
    return None, "not_found"


def resolve_location_gps(lat: float, lon: float,
                          registry: dict[str, dict],
                          radius_km: float = 5.0) -> Optional[str]:
    """Find nearest municipality by Haversine distance."""
    best_id = None
    best_dist = float("inf")
    for mid, row in registry.items():
        try:
            rlat = float(row["latitude"])
            rlon = float(row["longitude"])
        except (ValueError, KeyError):
            continue
        d = _haversine(lat, lon, rlat, rlon)
        if d < best_dist:
            best_dist = d
            best_id = mid
    if best_dist <= radius_km:
        return best_id
    return None


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Entity resolver: replaces selector tokens with concrete IDs
# ---------------------------------------------------------------------------

def resolve_entity(selector: str, mun_id: Optional[str],
                   service_map: Optional[dict]) -> str:
    """
    MUN_DYNAMIC → municipality_id (or MUN if unknown)
    MUN_UNION_DYNAMIC → MUN_UNION (not resolvable without union member data)
    RWA_DYNAMIC / WATER_ESTABLISHMENT_BY_LOCATION → water_establishment_id from service_map
    ELECTRICITY_DYNAMIC → electricity_entity_id from service_map (EDL or EDZ)
    All other selectors (CD, EDL, OGERO, ISF, MPWT, etc.) → returned as-is.
    """
    if selector in ("MUN_DYNAMIC", "MUN"):
        return mun_id or "MUN"
    if selector in ("MUN_UNION_DYNAMIC", "MUN_UNION"):
        if service_map:
            return service_map.get("union_id", "MUN_UNION")
        return "MUN_UNION"
    if selector in ("RWA_DYNAMIC", "WATER_ESTABLISHMENT_BY_LOCATION"):
        if service_map:
            return service_map.get("water_establishment_id", "RWA_DYNAMIC")
        return "RWA_DYNAMIC"
    if selector == "ELECTRICITY_DYNAMIC":
        if service_map:
            return service_map.get("electricity_entity_id", "EDL")
        return "EDL"
    return selector


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RouteResult:
    primary_entity: str                  # e.g. "MUN-54111", "BMLWE", "EDL"
    secondary_entity: str = ""           # e.g. "MPWT", ""
    hitl_required: bool = False
    hitl_reason: str = ""
    sector: str = ""
    complaint_type_id: str = ""
    complaint_type: str = ""
    municipality_id: Optional[str] = None
    municipality_name: str = ""
    location_method: str = ""
    confidence: str = "low"
    reason: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "primary_entity": self.primary_entity,
            "secondary_entity": self.secondary_entity,
            "hitl_required": self.hitl_required,
            "hitl_reason": self.hitl_reason,
            "sector": self.sector,
            "complaint_type_id": self.complaint_type_id,
            "complaint_type": self.complaint_type,
            "municipality_id": self.municipality_id,
            "municipality_name": self.municipality_name,
            "location_method": self.location_method,
            "confidence": self.confidence,
            "reason": self.reason,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Main routing function
# ---------------------------------------------------------------------------

# Module-level singletons (loaded once)
_VOCAB: dict[str, str] | None = None
_TAXONOMY: dict[str, dict] | None = None
_RULES: list[dict] | None = None
_ALIASES: dict[str, str] | None = None
_SERVICE_MAP: dict[str, dict] | None = None
_REGISTRY: dict[str, dict] | None = None


def _ensure_loaded():
    global _VOCAB, _TAXONOMY, _RULES, _ALIASES, _SERVICE_MAP, _REGISTRY
    if _VOCAB is None:
        _VOCAB = _load_vocab()
        _TAXONOMY = _load_taxonomy()
        _RULES = _load_routing_rules()
        _ALIASES = _load_aliases()
        _SERVICE_MAP = _load_service_mappings()
        _REGISTRY = _load_registry()


def route(
    complaint_text: str,
    location_text: Optional[str] = None,
    gps_lat: Optional[float] = None,
    gps_lon: Optional[float] = None,
) -> RouteResult:
    """
    Route a citizen complaint to the responsible entity.

    Args:
        complaint_text: The raw text (Arabizi, Arabic, or English).
        location_text:  Optional separate location string (e.g. "zahle" or "jounieh").
                        If None, location is extracted from complaint_text.
        gps_lat/lon:    Optional GPS coordinates (takes precedence over text location).
    """
    _ensure_loaded()

    result = RouteResult(primary_entity="HITL")
    search_text = complaint_text
    if location_text:
        search_text = complaint_text + " " + location_text

    # Step 1 — Sector detection
    sector, sec_conf = detect_sector(complaint_text, _VOCAB)
    result.sector = sector

    if sector == "UNKNOWN" or sec_conf == 0.0:
        result.hitl_required = True
        result.hitl_reason = "sector_not_detected"
        result.confidence = "low"
        result.reason = "No known Arabizi/Arabic keywords matched. Cannot auto-classify sector."
        result.warnings.append("HITL_GATE: sector unknown")
        return result

    # Step 2 — Location resolution
    mun_id: Optional[str] = None
    location_method = "not_found"

    if gps_lat is not None and gps_lon is not None:
        mun_id = resolve_location_gps(gps_lat, gps_lon, _REGISTRY)
        location_method = "gps" if mun_id else "gps_out_of_range"
    
    if mun_id is None:
        mun_id, location_method = resolve_location(search_text, _ALIASES, _REGISTRY)

    result.municipality_id = mun_id
    result.location_method = location_method

    if mun_id:
        reg_row = _REGISTRY.get(mun_id, {})
        result.municipality_name = reg_row.get("name_en") or reg_row.get("name_ar") or mun_id

    service_map = _SERVICE_MAP.get(mun_id) if mun_id else None

    # Step 3 — Pick complaint type
    ct_id = pick_complaint_type(sector, _TAXONOMY)
    # National road override: inter-city/classified road signals → CT-ROAD-002 (MPWT)
    if sector == "ROADS" and _detect_national_road(complaint_text):
        national_ct = next(
            (cid for cid, row in _TAXONOMY.items()
             if row.get("complaint_type_id", cid) == "CT-ROAD-002"
             or row.get("complaint_type", "") == "classified_or_main_road_damage"),
            None,
        )
        if national_ct:
            ct_id = national_ct
    taxonomy_row = _TAXONOMY.get(ct_id, {}) if ct_id else {}
    result.complaint_type_id = ct_id or ""
    result.complaint_type = taxonomy_row.get("complaint_type", "")

    # Step 4 — Find matching routing rule
    matched_rule: Optional[dict] = None
    for rule in _RULES:
        if rule.get("complaint_type_id") == ct_id and not rule["rule_id"].startswith("RR-GATE"):
            matched_rule = rule
            break
    # Fallback: match by sector category
    if not matched_rule and ct_id:
        category = taxonomy_row.get("category", "")
        for rule in _RULES:
            if not rule["rule_id"].startswith("RR-GATE") and rule.get("complaint_type_id", "").startswith(ct_id[:7]):
                matched_rule = rule
                break

    # Step 5 — Resolve entities
    if matched_rule:
        primary_sel = matched_rule.get("entity_id_canonical") or matched_rule.get("primary_entity_selector", "HITL")
        secondary_sel = matched_rule.get("secondary_entity_selector", "")
        rule_hitl = matched_rule.get("hitl_required", "false").lower() == "true"
        rule_hitl_reason = matched_rule.get("hitl_reason", "")
        confidence_raw = matched_rule.get("confidence", "medium")
    else:
        primary_sel = taxonomy_row.get("default_primary_entity_selector", "HITL")
        secondary_sel = ""
        rule_hitl = taxonomy_row.get("hitl_default", "false").lower() == "true"
        rule_hitl_reason = "no matching routing rule — taxonomy default"
        confidence_raw = "low"

    # Map confidence
    conf_map = {"medium_high": "high", "medium": "medium", "low": "low", "high": "high"}
    confidence = conf_map.get(confidence_raw, "medium")

    result.primary_entity = resolve_entity(primary_sel, mun_id, service_map)

    # Secondary entity — extract only the first concrete selector token
    # Raw values look like: "MUN_UNION_DYNAMIC if verified shared service; MPWT"
    # or "CIVIL_DEFENSE/ISF for immediate public danger" → take first slash/space token
    sec_first = secondary_sel.split(";")[0].split(" if ")[0].strip()
    if sec_first:
        sec_tok = re.split(r"[/ ]", sec_first)[0].strip()
        result.secondary_entity = resolve_entity(sec_tok, mun_id, service_map) if sec_tok else ""
    else:
        result.secondary_entity = ""

    # Step 6 — HITL gates
    hitl_required = rule_hitl
    hitl_reasons = []
    if rule_hitl:
        hitl_reasons.append(rule_hitl_reason)

    # Gate: no location
    if mun_id is None and sector not in ("SAFETY",):
        hitl_required = True
        hitl_reasons.append("location_missing — cannot resolve dynamic entity")
        result.warnings.append("HITL_GATE: no location found in text")
        confidence = "low"

    # Gate: emergency sector always routes to CD first
    if sector == "SAFETY":
        result.primary_entity = "CD"
        result.secondary_entity = result.secondary_entity or "ISF"
        hitl_required = True
        hitl_reasons.append("emergency_first — civil defense always primary")
        confidence = "high"

    # Gate: electricity needs location to pick EDL vs EDZ
    if sector == "ELECTRICITY" and mun_id and service_map:
        result.primary_entity = service_map.get("electricity_entity_id", "EDL")
        confidence = "high" if service_map.get("electricity_confidence", "") == "high" else "medium"

    # Gate: water needs location to pick water authority
    if sector == "WATER" and mun_id and service_map:
        result.primary_entity = service_map.get("water_establishment_id", "RWA_DYNAMIC")
        confidence = "high" if service_map.get("water_confidence", "").startswith("medium") else "medium"

    result.hitl_required = hitl_required
    result.hitl_reason = "; ".join(hitl_reasons) if hitl_reasons else ""
    result.confidence = confidence

    reason_parts = [f"sector={sector}"]
    if ct_id:
        reason_parts.append(f"type={result.complaint_type}")
    if mun_id:
        reason_parts.append(f"location={result.municipality_name}({location_method})")
    if matched_rule:
        reason_parts.append(f"rule={matched_rule['rule_id']}")
    result.reason = " | ".join(reason_parts)

    return result


# ---------------------------------------------------------------------------
# CLI / demo
# ---------------------------------------------------------------------------

DEMO_CASES = [
    ("zbele ma ndafat men l shere3 b jounieh",
     None, None, None,
     "Expected: MUN (Jounieh), no HITL"),
    ("fi may weskha 3am tetla3 men l 7anafeye b zahle",
     None, None, None,
     "Expected: BWE (Bekaa Water), Zahle district"),
    ("kahraba ma fi b kfarfila",
     None, None, None,
     "Expected: EDL, Kfarfila"),
    ("fi 7ariq b makab zbele ta3 l balad",
     None, None, None,
     "Expected: CD, HITL=true (emergency/fire)"),
    ("internet 3am y2atte3 3al shamal",
     None, None, None,
     "Expected: OGERO, North region"),
    ("tari2 meksour bein baalbek w hermel",
     None, None, None,
     "Expected: MPWT (national road), HITL for road owner ambiguity"),
]


def _print_result(res: RouteResult, note: str = ""):
    print(f"  Primary:    {res.primary_entity}")
    print(f"  Secondary:  {res.secondary_entity or '—'}")
    print(f"  HITL:       {res.hitl_required}" + (f" ({res.hitl_reason})" if res.hitl_reason else ""))
    print(f"  Sector:     {res.sector}")
    print(f"  Type:       {res.complaint_type or '—'}")
    print(f"  Location:   {res.municipality_name or '?'} [{res.location_method}]")
    print(f"  Confidence: {res.confidence}")
    print(f"  Reason:     {res.reason}")
    if res.warnings:
        print(f"  Warnings:   {'; '.join(res.warnings)}")
    if note:
        print(f"  Note:       {note}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        print("=== CedarFix Route Demo ===\n")
        for text, loc, lat, lon, note in DEMO_CASES:
            print(f"INPUT: {text!r}")
            res = route(text, loc, lat, lon)
            _print_result(res, note)
            print()
    elif len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        print(f"Routing: {text!r}\n")
        res = route(text)
        _print_result(res)
        print()
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("Usage:")
        print("  python src/route_complaint.py \"zbele ma ndafat b jounieh\"")
        print("  python src/route_complaint.py --demo")

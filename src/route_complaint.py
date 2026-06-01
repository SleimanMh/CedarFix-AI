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
WATER_DIR = KB / "water_establishments"

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
        municipality_id = r.get("municipality_id", "").strip() or r.get("registry_id", "").strip()
        if not municipality_id:
            continue
        alias = _normalize_name(r["alias_value"])
        if alias:
            out[alias] = municipality_id
    registry_path = MUN_DIR / "national_municipality_registry.csv"
    if registry_path.exists():
        for r in csv.DictReader(open(registry_path, encoding="utf-8")):
            municipality_id = r.get("municipality_id", "").strip() or r.get("registry_id", "").strip()
            if not municipality_id:
                continue
            for col in ("name_en", "name_ar", "name_raw_en_page", "name_raw_ar_page", "dglac_detail_name"):
                raw_alias = r.get(col, "")
                alias = _normalize_name(raw_alias)
                if alias and alias not in out:
                    out[alias] = municipality_id
                for part in re.split(r"[-–+]", raw_alias):
                    part_alias = _normalize_name(part)
                    if part_alias and len(part_alias) > 2 and part_alias not in out:
                        out[part_alias] = municipality_id
    return out


def _load_service_mappings() -> dict[str, dict]:
    """municipality_id → service mapping row."""
    path = MUN_DIR / "municipality_service_mappings.csv"
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        key = r.get("municipality_id", "").strip() or r.get("registry_id", "").strip()
        if key:
            out[key] = r
    return out


def _load_water_resolution() -> dict[str, dict]:
    """municipality_id → canonical water-establishment resolver row."""
    path = WATER_DIR / "water_entity_resolution.csv"
    if not path.exists():
        return {}
    return {r["municipality_id"]: r
            for r in csv.DictReader(open(path, encoding="utf-8"))}


def _load_registry() -> dict[str, dict]:
    """municipality_id → registry row (for name/lat/lon lookup)."""
    path = MUN_DIR / "national_municipality_registry.csv"
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        key = r.get("municipality_id", "").strip() or r.get("registry_id", "").strip()
        if key:
            out[key] = r
    return out


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

_ARABIC_ARTICLES = re.compile(r"^(ال|al[ -]?)", re.IGNORECASE)
_PUNCT = re.compile(r"[^a-z0-9\u0600-\u06ff\s]")
_SPACES = re.compile(r"\s+")

def _normalize_name(s: str) -> str:
    s = s.strip().lower()
    s = (
        s.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
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
    "irrigation": "WATER", "canal": "WATER", "agricultural": "WATER",
    "farm": "WATER", "well": "WATER", "tanker": "WATER",
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
    "ري": "WATER", "قناة": "WATER", "زراعي": "WATER", "زراعية": "WATER",
    "بئر": "WATER", "آبار": "WATER", "صهريج": "WATER",
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
    "نهر": "ENVIRONMENT", "الليطاني": "ENVIRONMENT", "مصنع": "ENVIRONMENT",
    "مصانع": "ENVIRONMENT",
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

_ROAD_BRIDGE_RE = re.compile(
    r"\b(bridge|jeser|jisr|overpass|viaduct)\b|جسر",
    re.IGNORECASE,
)

_ROAD_SIDEWALK_RE = re.compile(
    r"\b(sidewalk|pavement|raseef|rasif|pedestrian path)\b|رصيف",
    re.IGNORECASE,
)

_ROAD_BLOCKED_RE = re.compile(
    r"\b(blocked|blocking|closed|debris|rubble|rdem|msakker|msakkra|landslide|rockfall|tree blocking)\b|"
    r"مسكر|مقفلة|ردم|انهيار|صخور|شجرة واقعة",
    re.IGNORECASE,
)

_ROAD_STORM_SNOW_RE = re.compile(
    r"\b(snow|talj|storm|flooded road|road flooded|icy|ice|landslide after rain)\b|ثلج|جليد|طريق غرقانة",
    re.IGNORECASE,
)

_ROAD_SIGN_BARRIER_RE = re.compile(
    r"\b(barrier|guardrail|sign|traffic sign|missing sign|safety rail|7ajez|hajez|dangerous curve|cliff)\b|"
    r"حاجز|اشارة|إشارة|درابزين|منعطف خطر",
    re.IGNORECASE,
)

_ROAD_CDR_PROJECT_RE = re.compile(
    r"\b(cdr|council for development|majles el inmaa|active project|public works project|worksite|werche|contractor)\b|"
    r"مجلس الانماء|مجلس الإنماء|مشروع|ورشة|متعهد",
    re.IGNORECASE,
)

_ROAD_LOCAL_RE = re.compile(
    r"\b(local road|internal road|tari2 dekhle|tari2 fer3iye|neighborhood street|hayy|alley|dead end)\b|"
    r"طريق داخلية|طريق فرعية|شارع الحي|زقاق",
    re.IGNORECASE,
)

def _detect_national_road(text: str) -> bool:
    """True if text signals a classified or inter-city road (→ MPWT, not MUN)."""
    return bool(_NATIONAL_ROAD_RE.search(text))


def _road_complaint_type_override(text: str) -> Optional[str]:
    if _ROAD_CDR_PROJECT_RE.search(text):
        return "CT-PROJ-002" if re.search(r"\b(cdr|majles|council for development)\b|مجلس الانماء|مجلس الإنماء", text, re.IGNORECASE) else "CT-PROJ-003"
    if _ROAD_BRIDGE_RE.search(text):
        return "CT-ROAD-003"
    if _ROAD_STORM_SNOW_RE.search(text):
        return "CT-ROAD-006"
    if _ROAD_BLOCKED_RE.search(text):
        return "CT-ROAD-005"
    if _ROAD_SIGN_BARRIER_RE.search(text):
        return "CT-ROAD-007"
    if _ROAD_SIDEWALK_RE.search(text):
        return "CT-ROAD-004"
    if _detect_national_road(text):
        return "CT-ROAD-002"
    return "CT-ROAD-001"


_TELECOM_BILLING_RE = re.compile(
    r"\b(fattoure|fawatir|7sab|billing|bill|invoice|khassam|overcharge|roaming|wrong charge)\b|"
    r"فاتورة|فواتير|حساب|خصم|رومينغ|تجوال",
    re.IGNORECASE,
)

_BILLING_REGULATORY_RE = re.compile(
    r"\b(TRA|hiye2|regulator|regulatory|consumer protection|shakkait|shikwe|complaint|dispute|"
    r"escalat|not resolved|unresolved|ma hajou|ma 7allou|ma hallou)\b|"
    r"هيئة|شكوى|شكيت|نزاع|ما حلو|ما حلوا",
    re.IGNORECASE,
)

def _detect_billing_regulatory(text: str) -> bool:
    """True if text signals a billing dispute or escalated operator complaint (→ TRA, not OGERO)."""
    return bool(_BILLING_REGULATORY_RE.search(text))


_MOBILE_NETWORK_RE = re.compile(
    r"\b(mobile|alfa|touch|4g|5g|3g|lte|coverage|shabake mobile|signal mobile|shabake alfa|shabake touch"
    r"|network alfa|network touch|mobile network|cell|cellular)\b",
    re.IGNORECASE,
)

def _detect_mobile_complaint(text: str) -> bool:
    """True if text signals a mobile operator network complaint (→ TRA, not OGERO)."""
    return bool(_MOBILE_NETWORK_RE.search(text))


_TELECOM_LANDLINE_RE = re.compile(
    r"\b(landline|fixed line|telephone line|khatt arde|khat arde|tel arde|phone line)\b|"
    r"خط ارضي|خط أرضي|تلفون ارضي|هاتف ارضي",
    re.IGNORECASE,
)

_TELECOM_FIXED_INTERNET_RE = re.compile(
    r"\b(ogero|dsl|vdsl|fiber|fibre|fixed internet|home internet|internet line|broadband|wifi|router)\b|"
    r"اوجيرو|أوجيرو|دي اس ال|فايبر|انترنت البيت|واي فاي|راوتر",
    re.IGNORECASE,
)

_TELECOM_CABLE_CUT_RE = re.compile(
    r"\b(telecom cable|internet cable|phone cable|cable cut|wire cut|ma2tou3|ma2tu3|makto3|cut cable)\b|"
    r"كابل مقطوع|كابل الانترنت|كابل الهاتف|سلك مقطوع",
    re.IGNORECASE,
)

_TELECOM_CABINET_RE = re.compile(
    r"\b(telecom cabinet|ogero cabinet|cabinet|distribution box|box open|kabinet|sando2 ogero)\b|"
    r"كابينة|كبينه|صندوق اوجيرو|علبة الاتصالات",
    re.IGNORECASE,
)

_TELECOM_UNRESPONSIVE_RE = re.compile(
    r"\b(ogero ma 3am tred|ogero not answering|not responding|no response|service desk|support ticket)\b|"
    r"اوجيرو ما عم ترد|ما عم يردوا|لا جواب",
    re.IGNORECASE,
)

_TELECOM_PRIVATE_CPE_RE = re.compile(
    r"\b(router password|wifi password|my router|inside my house|device issue|phone setting|modem setting|"
    r"private router|home router|laptop|mobile phone only)\b|"
    r"كلمة سر الواي فاي|راوتر البيت|جهازي|لابتوب|موبايل بس",
    re.IGNORECASE,
)

_TELECOM_PRIVATE_ISP_RE = re.compile(
    r"\b(private isp|local isp|cable provider|neighborhood internet|satellite internet|starlink|provider taba3 l hay)\b|"
    r"انترنت خاص|مزود خاص|انترنت الحي|ستارلينك",
    re.IGNORECASE,
)

_TELECOM_STRONG_RE = re.compile(
    r"\b(ogero|dsl|vdsl|fiber|fibre|landline|fixed line|khatt arde|khat arde|telecom cabinet|"
    r"ogero cabinet|telecom cable|internet cable|phone cable|router password|private router|home router|"
    r"private isp|local isp|satellite internet|starlink|alfa|touch|4g|5g|lte)\b|"
    r"اوجيرو|أوجيرو|خط ارضي|خط أرضي|كابينة|كابل الانترنت|ألفا|تاتش",
    re.IGNORECASE,
)


def _telecom_complaint_type_override(text: str) -> Optional[str]:
    mobile = _detect_mobile_complaint(text)
    billing = bool(_TELECOM_BILLING_RE.search(text))
    regulatory = _detect_billing_regulatory(text)
    if regulatory or (mobile and billing):
        return "CT-TEL-010"
    if mobile:
        return "CT-TEL-005"
    if _TELECOM_CABLE_CUT_RE.search(text):
        return "CT-TEL-003"
    if _TELECOM_CABINET_RE.search(text):
        return "CT-TEL-004"
    if _TELECOM_UNRESPONSIVE_RE.search(text):
        return "CT-TEL-008"
    if _TELECOM_LANDLINE_RE.search(text):
        return "CT-TEL-002"
    if re.search(r"\b(cutting|cuts|disconnect|intermittent|slow|weak|y2atte3|byo2ta3|ma fi internet)\b", text, re.IGNORECASE):
        return "CT-TEL-006"
    return "CT-TEL-001"


# ---------------------------------------------------------------------------
# Water-establishment routing guardrails
# ---------------------------------------------------------------------------

_WATER_DIRTY_RE = re.compile(
    r"\b(dirty|brown|red|yellow|smell|smells|smelly|odor|polluted|contaminat|unsafe|salty|muddy|turbid|"
    r"weskh|weskha|wisikh|wsikha|3akra|hamra|7amra|ri7a|mloo7a|mle7a|mdaradra)\b|"
    r"وسخة|ملوث|ملوثة|عكرة|حمراء|ريحة|رائحة|مالحة|وحلة|غير نظيفة",
    re.IGNORECASE,
)

_WATER_SEWAGE_RE = re.compile(
    r"\b(sewage|wastewater|black water|manhole|sewer|sarf|majrour|majareer|tasrif|fecal|"
    r"majrour|majroura|faydan|fayda)\b|"
    r"مجاري|صرف|مجارير|مجرور|مياه سوداء|بالوعة",
    re.IGNORECASE,
)

_WATER_PIPE_LEAK_RE = re.compile(
    r"\b(pipe|main|network|leak|leaking|burst|broken pipe|public pipe|water main|"
    r"shreet|masrabe|maftou7|kasr|ma2sour|nabbour)\b|"
    r"تسرب|ماسورة|انبوب|أنبوب|شبكة|خط مياه|مكسور|مفتوح",
    re.IGNORECASE,
)

_WATER_LOW_PRESSURE_RE = re.compile(
    r"\b(low pressure|weak pressure|pressure|da3if|da3ife|daghet|wate|ma byetla3|ma 3am ytla3)\b|"
    r"ضغط|ضعيف|ما عم تطلع|لا تصل",
    re.IGNORECASE,
)

_WATER_BILLING_RE = re.compile(
    r"\b(bill|billing|invoice|meter|subscription|subscribe|new connection|connection request|"
    r"fatura|fetoura|fawatir|3addad|ishtirak|ishtiراك|customer number|payment|pay)\b|"
    r"فاتورة|فواتير|عداد|اشتراك|مشترك|دفع|تسديد|رقم آلي|رسم",
    re.IGNORECASE,
)

_WATER_IRRIGATION_RE = re.compile(
    r"\b(irrigation|canal|agricultural water|farm water|ray|reyy|zira3|zira3iye|mazra3a|"
    r"qasimiy|qasimiya|ras al ain|litani)\b|"
    r"(^|\s)(ري|قناة|زراعي|زراعية|القاسمية|رأس العين|الليطاني)(\s|$)",
    re.IGNORECASE,
)

_WATER_LRA_RE = re.compile(
    r"\b(litani|qaraoun|qasimiya|qasimiy|ras al ain|collective irrigation|canal)\b|"
    r"الليطاني|القرعون|القاسمية|رأس العين|قناة",
    re.IGNORECASE,
)

_WATER_PRIVATE_PLUMBING_RE = re.compile(
    r"\b(apartment|inside my house|inside the house|inside building|building tank|roof tank|"
    r"rooftop tank|private pump|internal pipe|heater|landlord|bathroom|kitchen sink|"
    r"sha22a|beit|binaye|khazzan|motore|motor|dakhel|sakhane|plumbing)\b|"
    r"داخل البيت|داخل الشقة|خزان|مضخة خاصة|موتور|سخان|مالك|حمام|مطبخ",
    re.IGNORECASE,
)

_WATER_PUBLIC_NETWORK_RE = re.compile(
    r"\b(street|road|public|neighborhood|area|whole building|multiple homes|many houses|"
    r"meter|main|network|manhole|shared|hayy|shere3|tari2|3imara|3amm)\b|"
    r"شارع|حي|منطقة|عام|شبكة|عداد|عدة بيوت|كل الحي|بالطريق",
    re.IGNORECASE,
)

_WATER_PRIVATE_WELL_RE = re.compile(
    r"\b(private well|well|groundwater|bir|bi2r|abbar|2abar|license|permit)\b|"
    r"بئر|آبار|ابار|جوفية|رخصة",
    re.IGNORECASE,
)

_WATER_TANKER_DISPUTE_RE = re.compile(
    r"\b(water truck|truck|tanker|cistern|citerne|vendor|delivery|price|cost|expensive|"
    r"sayyara may|citerna|tank)\b|"
    r"صهريج|سيارة مي|بائع|سعر|كلفة|غالي|توصيل",
    re.IGNORECASE,
)

_WATER_HOME_EMERGENCY_RE = re.compile(
    r"\b(entering home|inside home|basement flooding|trapped|collapse|electrical hazard|"
    r"electrical wires|electric wires|touching electrical|touching wires|sewage entering|"
    r"flooding my house|sardab|ghare2|khatir)\b|"
    r"داخل البيت|غرق|خطر|قبو|سرداب|انهيار",
    re.IGNORECASE,
)

# FLOODING-specific patterns (distinct from the WATER sector)
_FLOODING_INDOOR_RE = re.compile(
    r"\b(entering home|inside home|inside the house|inside building|basement|sardab|"
    r"ghare2 l beit|ghare2 baytna|ghare2 bbeit|beit ghare2|flooded house|flooding my house|"
    r"trapped inside|water inside|water entered|roof leak|ceiling water|water coming in|"
    r"3am yod5ol may|may dakhel|l may dakhel|l may 3am yod5ol)\b|"
    r"داخل البيت|داخل المنزل|سرداب|غرق|المي دخل|المي عم يدخل|قبو|الطابق السفلي",
    re.IGNORECASE,
)

_FLOODING_IMMEDIATE_DANGER_RE = re.compile(
    r"\b(trapped|collapse|collapse risk|car submerged|cars submerged|road closed flooding|"
    r"wires in water|electrical in water|electrical wire flooded|generator flooded|"
    r"محاصر|cars sinking|people trapped|rescue|ambulance|7areje|stuck|ma2sour|ma2soure|"
    r"istinja|iste3ane|isti3ane|help|nazle|nazleh)\b|"
    r"محاصر|انهيار|سيارات غارقة|أسلاك كهربائية|طلب إنقاذ|إسعاف|استنجاد",
    re.IGNORECASE,
)

_FLOODING_INFRASTRUCTURE_RE = re.compile(
    r"\b(sewage overflow|sewer backed up|sewer flooded|drain blocked|drain overflow|"
    r"stormwater|storm drain|drainage pipe|mazra3e ghare2a|mazra3a gharet|"
    r"masrafe masduude|masrafe tafe2e|sarf mesdoud|sarf ta2e2|baleou3 mesdoud|"
    r"road flooded|street flooded|tari2 ghare2|street under water|under water)\b|"
    r"مجرور|بالوعة مسدودة|طريق غارقة|مياه عارمة|فيضان صرف",
    re.IGNORECASE,
)


def _water_complaint_type_override(text: str) -> Optional[str]:
    """Pick a more precise water/drainage complaint type than the sector default."""
    if _WATER_SEWAGE_RE.search(text):
        return "CT-DRAIN-004"
    if _WATER_IRRIGATION_RE.search(text):
        return "CT-WATER-006"
    if _WATER_BILLING_RE.search(text):
        return "CT-WATER-005"
    if _WATER_DIRTY_RE.search(text):
        return "CT-WATER-002"
    if _WATER_LOW_PRESSURE_RE.search(text):
        return "CT-WATER-004"
    if _WATER_PIPE_LEAK_RE.search(text):
        return "CT-WATER-003"
    return None


def _is_private_plumbing_issue(text: str) -> bool:
    if not _WATER_PRIVATE_PLUMBING_RE.search(text):
        return False
    if _WATER_PUBLIC_NETWORK_RE.search(text):
        return False
    if _WATER_LOW_PRESSURE_RE.search(text) and not re.search(
        r"\b(internal|inside|apartment|bathroom|kitchen|heater|landlord|private pump|plumbing|"
        r"dakhel|sha22a|sakhane)\b|داخل|شقة|سخان|حمام|مطبخ",
        text,
        re.IGNORECASE,
    ):
        return False
    return True


def _is_private_source_issue(text: str) -> bool:
    return bool(_WATER_PRIVATE_WELL_RE.search(text) or _WATER_TANKER_DISPUTE_RE.search(text))


_ENV_RIVER_RE = re.compile(
    r"\b(river|stream|litani|qaraoun|basin|nahr)\b|نهر|الليطاني|القرعون",
    re.IGNORECASE,
)

_ENV_INDUSTRIAL_RE = re.compile(
    r"\b(factory|industrial|plant|workshop|chemical|oil|tannery|ma3mal|masna3)\b|"
    r"مصنع|مصانع|صناعي|كيميائي|نفط|زيت",
    re.IGNORECASE,
)

_ENV_QUARRY_RE = re.compile(
    r"\b(quarry|crusher|ksara|stone crusher|dust from crusher)\b|كسارة|مقلع|كسارات",
    re.IGNORECASE,
)

_ENV_AIR_RE = re.compile(
    r"\b(smoke|air pollution|bad smell|odor|odour|dkhan|ri7a|burning smell)\b|دخان|ريحة|رائحة|تلوث هوا",
    re.IGNORECASE,
)

_WASTE_FIRE_RE = re.compile(
    r"\b(landfill fire|dump fire|trash fire|garbage fire|burning garbage|makab fire|nar b makab|7ari2 zbele)\b|"
    r"حريق مكب|مكب عم يحترق|زبالة عم تحترق",
    re.IGNORECASE,
)

_WASTE_HAZARDOUS_RE = re.compile(
    r"\b(hazardous|medical waste|hospital waste|chemical waste|toxic|syringe|needles|dead animals|industrial waste)\b|"
    r"نفايات طبية|نفايات خطرة|كيميائي|سامة|ابر|إبر",
    re.IGNORECASE,
)

_WASTE_ILLEGAL_DUMP_RE = re.compile(
    r"\b(illegal dumping|dumped|ramye zbele|thrown trash|public land dump|random dump)\b|"
    r"رمية زبالة|رمي نفايات|مكب عشوائي",
    re.IGNORECASE,
)

_WASTE_BIN_RE = re.compile(
    r"\b(bin|bins|dumpster|container|konteiner|overflowing|feyed|fayid)\b|حاوية|كونتينر|فايض",
    re.IGNORECASE,
)

_WASTE_SWEEPING_RE = re.compile(
    r"\b(street sweeping|sweeping|clean street|street cleaning|tandeef|bado tandeef)\b|كنس|تنظيف الشارع",
    re.IGNORECASE,
)

_SAFETY_FIRE_RE = re.compile(r"\b(fire|7ari2|7ariq|burning|explosion|gas leak)\b|حريق|انفجار|غاز", re.IGNORECASE)
_SAFETY_COLLAPSE_RE = re.compile(r"\b(collapse|collapsing|building crack|bina m2ashar|structural risk)\b|انهيار|مبنى متصدع", re.IGNORECASE)
_SAFETY_CRIME_RE = re.compile(r"\b(crime|threat|armed|shooting|assault|theft|weapon|sila7|tahdid)\b|تهديد|مسلح|سلاح|سرقة|اعتداء", re.IGNORECASE)
_SAFETY_ACCIDENT_RE = re.compile(r"\b(accident|crash|7adis|injury|injured|ambulance|blocked traffic)\b|حادث|جريح|مصاب|اسعاف|إسعاف", re.IGNORECASE)
_SAFETY_TREE_POLE_RE = re.compile(r"\b(dangerous tree|falling tree|dangerous pole|pole falling|3amoud|shajra)\b|شجرة واقعة|عمود واقع|عامود", re.IGNORECASE)
_SAFETY_ANIMAL_RE = re.compile(r"\b(stray dog|stray dogs|aggressive dog|rabid|kleb|kalb)\b|كلاب|كلب شرس|كلاب شاردة", re.IGNORECASE)
_SAFETY_IMMEDIATE_RE = re.compile(
    r"\b(now|immediate|urgent|trapped|people trapped|injury|injured|children|near homes|public danger|life danger|khatar|3ajel)\b|"
    r"عاجل|محاصرين|جريح|مصاب|خطر|حد البيوت",
    re.IGNORECASE,
)

_MUNI_PARKING_RE = re.compile(
    r"\b(illegal parking|parked|parking|car blocking|vehicle blocking|sayara msakkra|sayara mesakra)\b|"
    r"سيارة مسكرة|ركن مخالف|وقوف مخالف",
    re.IGNORECASE,
)

_MUNI_NOISE_RE = re.compile(
    r"\b(noise|loud music|generator noise|construction noise|dawshra|dawshe|ta2bi2|disturbance)\b|"
    r"ضجة|ازعاج|إزعاج|موسيقى عالية",
    re.IGNORECASE,
)

_MUNI_OBSTRUCTION_RE = re.compile(
    r"\b(public space obstruction|sidewalk obstruction|vendor blocking|stall blocking|bsata|kiosk|encroachment)\b|"
    r"بسطة|اشغال رصيف|إشغال رصيف|تعدي على الرصيف",
    re.IGNORECASE,
)

_MUNI_CONSTRUCTION_RE = re.compile(
    r"\b(illegal construction|building without permit|construction without permit|bala rekhsse|bala rukhsa|unlicensed building)\b|"
    r"بلا رخصة|بناء مخالف|تعدي بناء",
    re.IGNORECASE,
)

_MUNI_PERMIT_RE = re.compile(
    r"\b(municipal permit|license request|shop license|building permit|permit status|rekhsit|rukhsa|ro5sa)\b|"
    r"رخصة|ترخيص|رخصة محل",
    re.IGNORECASE,
)

_ADMIN_NO_RESPONSE_RE = re.compile(
    r"\b(municipality not responding|municipality ignored|baladiye ma 3am tred|no response from municipality|not answering)\b|"
    r"البلدية ما عم ترد|البلدية لا ترد|ما حدا رد",
    re.IGNORECASE,
)

_ADMIN_CORRUPTION_RE = re.compile(
    r"\b(corruption|bribe|bribery|misconduct|public employee refused|fasad|rashwe|negligence|abuse of power)\b|"
    r"فساد|رشوة|مخالفة موظف|سوء استعمال السلطة|اهمال",
    re.IGNORECASE,
)

_ADMIN_STATUS_RE = re.compile(
    r"\b(request status|application status|tracking number|registration number|form id|wen sar talab|talab l baladiye|dglac)\b|"
    r"رقم التسجيل|رقم الطلب|وين صار الطلب|المديرية العامة للإدارات",
    re.IGNORECASE,
)

_ADMIN_PUBLIC_BODY_RE = re.compile(
    r"\b(public administration complaint|complaint against administration|central inspection|cib|edara 3amme|taftish markazi)\b|"
    r"إدارة عامة|ادارة عامة|التفتيش المركزي|شكوى على ادارة",
    re.IGNORECASE,
)

_ELECTRIC_EXPOSED_RE = re.compile(
    r"exposed|bare wire|open wire|wire exposed|mkashaf|mkashfin|mkaashfin|shortan|shertan|"
    r"مكشوف|مكشوفين|شرطان|اسلاك مكشوفه|أسلاك مكشوفة",
    re.IGNORECASE,
)

_ELECTRIC_SPARK_RE = re.compile(
    r"spark|sparking|yshar2et|sharara|burning wire|electric box|power box|sando2|sandou2|"
    r"شرارة|يشرقط|كهربا عم تشرقط|صندوق الكهربا|علبة الكهربا",
    re.IGNORECASE,
)

_ELECTRIC_STREETLIGHT_RE = re.compile(
    r"street\s*light|streetlight|public light|daw l shere3|daw el shere3|daw l tari2|"
    r"ضو الشارع|انارة الشارع|إنارة الشارع|عامود الانارة|عمود الانارة",
    re.IGNORECASE,
)

_ELECTRIC_TRANSFORMER_RE = re.compile(
    r"transformer|transfo|transformateur|substation|محول|ترانس|ترانسفورمر|محطة كهربا",
    re.IGNORECASE,
)

_ELECTRIC_METER_RE = re.compile(
    r"meter|counter|compteur|subscription number|bill|billing|facture|3added|3addad|"
    r"عداد|كونتور|فاتورة|اشتراك",
    re.IGNORECASE,
)

_ELECTRIC_GENERATOR_RE = re.compile(
    r"generator|private generator|moteur|moteur l eshtirak|moteur el eshtirak|moualed|moualad|"
    r"مولد|موتور|اشتراك المولد|صاحب المولد",
    re.IGNORECASE,
)

_ELECTRIC_INTERNAL_RE = re.compile(
    r"inside (my )?(house|home|building|apartment)|breaker|fuse|internal wiring|building panel|"
    r"جوا البيت|داخل البيت|قاطع|فيوز|تابلو|كهربا البيت|اسلاك البيت",
    re.IGNORECASE,
)

_ELECTRIC_FIRE_DANGER_RE = re.compile(
    r"fire|smoke|burn|burning|explosion|electrocution|shock|danger|khatar|7ari2|7ariq|"
    r"yehtereq|ye7tere2|yi7tere2|3am yehtereq|"
    r"حريق|دخان|عم يحترق|انفجار|تكهرب|خطر",
    re.IGNORECASE,
)

_ELECTRIC_STRONG_RE = re.compile(
    r"generator|private generator|moteur|moualed|moualad|street\s*light|streetlight|"
    r"exposed|bare wire|spark|sparking|transformer|transfo|transformateur|substation|"
    r"breaker|fuse|internal wiring|building panel|"
    r"مولد|موتور|ضو الشارع|انارة الشارع|إنارة الشارع|مكشوف|شرطان|شرارة|محول|ترانسفورمر",
    re.IGNORECASE,
)


def _environment_complaint_type_override(text: str) -> Optional[str]:
    if _ENV_QUARRY_RE.search(text):
        return "CT-ENV-004"
    if _ENV_RIVER_RE.search(text):
        return "CT-ENV-003"
    if _ENV_INDUSTRIAL_RE.search(text):
        return "CT-ENV-002"
    if _ENV_AIR_RE.search(text):
        return "CT-ENV-001"
    return "CT-ENV-001"


def _waste_complaint_type_override(text: str) -> Optional[str]:
    if _WASTE_FIRE_RE.search(text):
        return "CT-WASTE-004"
    if _WASTE_HAZARDOUS_RE.search(text):
        return "CT-WASTE-005"
    if _WASTE_SWEEPING_RE.search(text):
        return "CT-WASTE-006"
    if _WASTE_ILLEGAL_DUMP_RE.search(text):
        return "CT-WASTE-002"
    if _WASTE_BIN_RE.search(text):
        return "CT-WASTE-003"
    return "CT-WASTE-001"


def _safety_complaint_type_override(text: str) -> Optional[str]:
    if _SAFETY_FIRE_RE.search(text):
        return "CT-SAFE-001"
    if _SAFETY_COLLAPSE_RE.search(text):
        return "CT-SAFE-002"
    if _SAFETY_CRIME_RE.search(text):
        return "CT-SAFE-003"
    if _SAFETY_ACCIDENT_RE.search(text):
        return "CT-SAFE-004"
    if _SAFETY_TREE_POLE_RE.search(text):
        return "CT-SAFE-005"
    if _SAFETY_ANIMAL_RE.search(text):
        return "CT-SAFE-006"
    return None


def _municipal_enforcement_complaint_type_override(text: str) -> Optional[str]:
    if _MUNI_PARKING_RE.search(text):
        return "CT-MUNI-001"
    if _MUNI_NOISE_RE.search(text):
        return "CT-MUNI-002"
    if _MUNI_OBSTRUCTION_RE.search(text):
        return "CT-MUNI-003"
    if _MUNI_CONSTRUCTION_RE.search(text):
        return "CT-MUNI-004"
    if _MUNI_PERMIT_RE.search(text):
        return "CT-MUNI-005"
    return None


def _administrative_complaint_type_override(text: str) -> Optional[str]:
    if _ADMIN_CORRUPTION_RE.search(text):
        return "CT-ADMIN-002"
    if _ADMIN_PUBLIC_BODY_RE.search(text):
        return "CT-ADMIN-004"
    if _ADMIN_STATUS_RE.search(text):
        return "CT-ADMIN-003"
    if _ADMIN_NO_RESPONSE_RE.search(text):
        return "CT-ADMIN-001"
    return None


def _electricity_complaint_type_override(text: str) -> Optional[str]:
    if _ELECTRIC_GENERATOR_RE.search(text):
        return "CT-ELEC-007"
    if _ELECTRIC_STREETLIGHT_RE.search(text):
        return "CT-ELEC-004"
    if _ELECTRIC_EXPOSED_RE.search(text):
        return "CT-ELEC-002"
    if _ELECTRIC_SPARK_RE.search(text):
        return "CT-ELEC-003"
    if _ELECTRIC_TRANSFORMER_RE.search(text):
        return "CT-ELEC-005"
    if _ELECTRIC_METER_RE.search(text):
        return "CT-ELEC-006"
    return "CT-ELEC-001"


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
    "ENVIRONMENT": ["environment"],
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
    if selector in ("MUNICIPAL_POLICE_DYNAMIC", "MUNICIPAL_POLICE"):
        return "MUNICIPAL_POLICE"
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
    hitl_reason_codes: list[str] = field(default_factory=list)
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
            "hitl_reason_codes": self.hitl_reason_codes,
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
_WATER_RESOLUTION: dict[str, dict] | None = None
_REGISTRY: dict[str, dict] | None = None


def _ensure_loaded():
    global _VOCAB, _TAXONOMY, _RULES, _ALIASES, _SERVICE_MAP, _WATER_RESOLUTION, _REGISTRY
    if _VOCAB is None:
        _VOCAB = _load_vocab()
        _TAXONOMY = _load_taxonomy()
        _RULES = _load_routing_rules()
        _ALIASES = _load_aliases()
        _SERVICE_MAP = _load_service_mappings()
        _WATER_RESOLUTION = _load_water_resolution()
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
    if sector == "SAFETY" and (
        _MUNI_PARKING_RE.search(complaint_text)
        or _MUNI_NOISE_RE.search(complaint_text)
        or _MUNI_OBSTRUCTION_RE.search(complaint_text)
    ) and not (
        _SAFETY_FIRE_RE.search(complaint_text)
        or _SAFETY_COLLAPSE_RE.search(complaint_text)
        or _SAFETY_CRIME_RE.search(complaint_text)
        or _SAFETY_ACCIDENT_RE.search(complaint_text)
    ):
        sector = "OTHER"
        sec_conf = max(sec_conf, 0.25)
    elif sector in {"UNKNOWN", "OTHER"} and (
        _ADMIN_NO_RESPONSE_RE.search(complaint_text)
        or _ADMIN_CORRUPTION_RE.search(complaint_text)
        or _ADMIN_STATUS_RE.search(complaint_text)
        or _ADMIN_PUBLIC_BODY_RE.search(complaint_text)
        or _MUNI_PARKING_RE.search(complaint_text)
        or _MUNI_NOISE_RE.search(complaint_text)
        or _MUNI_OBSTRUCTION_RE.search(complaint_text)
        or _MUNI_CONSTRUCTION_RE.search(complaint_text)
        or _MUNI_PERMIT_RE.search(complaint_text)
    ):
        sector = "OTHER"
        sec_conf = max(sec_conf, 0.25)
    elif sector not in {"SAFETY"} and (
        _SAFETY_FIRE_RE.search(complaint_text)
        or _SAFETY_COLLAPSE_RE.search(complaint_text)
        or _SAFETY_CRIME_RE.search(complaint_text)
        or _SAFETY_ACCIDENT_RE.search(complaint_text)
        or _SAFETY_TREE_POLE_RE.search(complaint_text)
        or _SAFETY_ANIMAL_RE.search(complaint_text)
    ):
        sector = "SAFETY"
        sec_conf = max(sec_conf, 0.25)
    elif sector not in {"SAFETY"} and (
        _WATER_SEWAGE_RE.search(complaint_text)
        or _WATER_PRIVATE_WELL_RE.search(complaint_text)
        or (
            _WATER_PIPE_LEAK_RE.search(complaint_text)
            and re.search(r"\b(water|maye?|miyah|network|main|pipe)\b|مياه|ماء|ماي", complaint_text, re.IGNORECASE)
        )
    ):
        sector = "WATER"
        sec_conf = max(sec_conf, 0.25)
    elif sector not in {"SAFETY"} and _ELECTRIC_STRONG_RE.search(complaint_text):
        sector = "ELECTRICITY"
        sec_conf = max(sec_conf, 0.25)
    elif sector not in {"SAFETY"} and _TELECOM_STRONG_RE.search(complaint_text):
        sector = "TELECOM"
        sec_conf = max(sec_conf, 0.25)
    elif sector not in {"SAFETY"} and (
        _WASTE_FIRE_RE.search(complaint_text)
        or _WASTE_HAZARDOUS_RE.search(complaint_text)
        or _WASTE_ILLEGAL_DUMP_RE.search(complaint_text)
        or _WASTE_BIN_RE.search(complaint_text)
        or _WASTE_SWEEPING_RE.search(complaint_text)
    ):
        sector = "WASTE"
        sec_conf = max(sec_conf, 0.25)
    elif sector not in {"SAFETY"} and (
        _ROAD_BRIDGE_RE.search(complaint_text)
        or _ROAD_SIDEWALK_RE.search(complaint_text)
        or _ROAD_CDR_PROJECT_RE.search(complaint_text)
        or _ROAD_SIGN_BARRIER_RE.search(complaint_text)
    ):
        sector = "ROADS"
        sec_conf = max(sec_conf, 0.25)
    elif sector in {"UNKNOWN", "OTHER", "ENVIRONMENT"} and (
        _ENV_RIVER_RE.search(complaint_text)
        or _ENV_INDUSTRIAL_RE.search(complaint_text)
        or _ENV_QUARRY_RE.search(complaint_text)
        or _ENV_AIR_RE.search(complaint_text)
    ):
        sector = "ENVIRONMENT"
        sec_conf = max(sec_conf, 0.25)
    result.sector = sector

    if sector == "UNKNOWN" or sec_conf == 0.0:
        result.hitl_required = True
        result.hitl_reason = "sector_not_detected"
        result.hitl_reason_codes = ["sector_not_detected"]
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
    water_resolution = _WATER_RESOLUTION.get(mun_id) if mun_id and _WATER_RESOLUTION else None

    # Step 3 — Pick complaint type
    ct_id = pick_complaint_type(sector, _TAXONOMY)
    if sector == "ROADS":
        road_ct = _road_complaint_type_override(complaint_text)
        if road_ct and road_ct in _TAXONOMY:
            ct_id = road_ct
    # Telecom subtype override: fixed Ogero faults, mobile network, and regulatory escalation.
    if sector == "TELECOM":
        tel_ct = _telecom_complaint_type_override(complaint_text)
        if tel_ct and tel_ct in _TAXONOMY:
            ct_id = tel_ct
    # Water subtype override: the WATER sector default is outage, so inspect the
    # text for billing, dirty water, public pipe, low pressure, sewage, and irrigation.
    if sector == "WASTE":
        waste_ct = _waste_complaint_type_override(complaint_text)
        if waste_ct and waste_ct in _TAXONOMY:
            ct_id = waste_ct
    elif sector == "SAFETY":
        safe_ct = _safety_complaint_type_override(complaint_text)
        if safe_ct and safe_ct in _TAXONOMY:
            ct_id = safe_ct
    elif sector == "WATER":
        water_ct = _water_complaint_type_override(complaint_text)
        if water_ct and water_ct in _TAXONOMY:
            ct_id = water_ct
    elif sector == "ELECTRICITY":
        elec_ct = _electricity_complaint_type_override(complaint_text)
        if elec_ct and elec_ct in _TAXONOMY:
            ct_id = elec_ct
    elif sector == "FLOODING" and _WATER_SEWAGE_RE.search(complaint_text):
        if "CT-DRAIN-004" in _TAXONOMY:
            ct_id = "CT-DRAIN-004"
    elif sector == "ENVIRONMENT":
        env_ct = _environment_complaint_type_override(complaint_text)
        if env_ct and env_ct in _TAXONOMY:
            ct_id = env_ct
    elif sector == "OTHER":
        admin_ct = _administrative_complaint_type_override(complaint_text)
        muni_ct = _municipal_enforcement_complaint_type_override(complaint_text)
        other_ct = admin_ct or muni_ct
        if other_ct and other_ct in _TAXONOMY:
            ct_id = other_ct
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
    hitl_reasons: list[str] = []
    hitl_reason_codes: list[str] = []

    def add_hitl(code: str, reason: str) -> None:
        nonlocal hitl_required
        hitl_required = True
        if code and code not in hitl_reason_codes:
            hitl_reason_codes.append(code)
        if reason and reason not in hitl_reasons:
            hitl_reasons.append(reason)

    def clear_hitl() -> None:
        nonlocal hitl_required
        hitl_required = False
        hitl_reasons.clear()
        hitl_reason_codes.clear()

    if rule_hitl:
        add_hitl("routing_rule_hitl", rule_hitl_reason)

    # Gate: no location
    # Exceptions: SAFETY (emergency, nationwide), and national regulators that don't need location (TRA, CENTRAL_INSPECTION)
    _location_not_needed = primary_sel in ("TRA", "CENTRAL_INSPECTION", "CDR") or sector == "SAFETY"
    if mun_id is None and not _location_not_needed:
        add_hitl("missing_location", "location_missing - cannot resolve dynamic entity")
        result.warnings.append("HITL_GATE: no location found in text")
        confidence = "low"

    # Public-safety guardrails from the public_safety_enforcement KB shard.
    if sector == "SAFETY":
        if ct_id == "CT-SAFE-003":
            result.primary_entity = "ISF"
            result.secondary_entity = "CD_IF_RESCUE_OR_FIRE"
            add_hitl("law_enforcement_safety", "law_enforcement_safety - threat crime or weapon reports need ISF first")
            confidence = "high"
        elif ct_id == "CT-SAFE-004":
            result.primary_entity = "ISF"
            result.secondary_entity = "CD_IF_INJURY_OR_RESCUE"
            add_hitl("traffic_accident_boundary", "traffic_accident_boundary - ISF for traffic/security control and Civil Defense if rescue or injury")
            confidence = "high"
        elif ct_id == "CT-SAFE-002":
            if _SAFETY_IMMEDIATE_RE.search(complaint_text) or re.search(r"\b(collapse|collapsing|trapped)\b|انهيار|محاصرين", complaint_text, re.IGNORECASE):
                result.primary_entity = "CD"
                result.secondary_entity = mun_id or "MUN"
                add_hitl("collapse_emergency", "collapse_emergency - Civil Defense first for active collapse or trapped-person risk")
                confidence = "high"
            else:
                result.primary_entity = mun_id or "MUN"
                result.secondary_entity = "CD_IF_IMMEDIATE_DANGER"
                add_hitl("building_safety_boundary", "building_safety_boundary - municipality/building safety review unless active rescue danger")
                confidence = "medium" if mun_id else "low"
        elif ct_id == "CT-SAFE-005":
            if _SAFETY_IMMEDIATE_RE.search(complaint_text):
                result.primary_entity = "CD"
                result.secondary_entity = mun_id or "MUN"
                add_hitl("falling_asset_emergency", "falling_asset_emergency - Civil Defense first when tree or pole is actively falling or endangering people")
                confidence = "high"
            else:
                result.primary_entity = mun_id or "MUN"
                result.secondary_entity = "EDL_OR_MPWT_OR_CD_BY_ASSET"
                add_hitl("dangerous_asset_boundary", "dangerous_asset_boundary - confirm whether tree pole road asset or electrical asset owns the hazard")
                confidence = "medium" if mun_id else "low"
        elif ct_id == "CT-SAFE-006":
            result.primary_entity = mun_id or "MUN"
            result.secondary_entity = "MUNICIPAL_POLICE_OR_ISF_IF_ATTACKING"
            add_hitl("stray_animals_public_risk", "stray_animals_public_risk - confirm public danger and local handling path")
            confidence = "medium" if mun_id else "low"
        else:
            result.primary_entity = "CD"
            result.secondary_entity = result.secondary_entity or "ISF"
            add_hitl("emergency_first", "emergency_first - Civil Defense first for fire rescue explosion gas or active life-safety danger")
            confidence = "high"

    # Municipal enforcement and administrative guardrails.
    if sector == "OTHER":
        if ct_id in {"CT-MUNI-001", "CT-MUNI-002", "CT-MUNI-003"}:
            result.primary_entity = "MUNICIPAL_POLICE"
            result.secondary_entity = "ISF_IF_THREAT_OR_MAJOR_TRAFFIC" if ct_id != "CT-MUNI-002" else "ISF_IF_THREAT_OR_VIOLENCE"
            if ct_id == "CT-MUNI-002":
                add_hitl("noise_enforcement_boundary", "noise_enforcement_boundary - local noise starts municipal but threats or violence need ISF")
            confidence = "medium" if mun_id else "low"
        elif ct_id == "CT-MUNI-004":
            result.primary_entity = mun_id or "MUN"
            result.secondary_entity = "URBAN_PLANNING_OR_ISF_IF_ACTIVE_DANGER"
            add_hitl("illegal_construction_boundary", "illegal_construction_boundary - confirm permit parcel municipality and danger level")
            confidence = "medium" if mun_id else "low"
        elif ct_id == "CT-MUNI-005":
            result.primary_entity = mun_id or "MUN"
            result.secondary_entity = "DGLAC_IF_FORM_OR_REGISTRY_ISSUE"
            confidence = "medium" if mun_id else "low"
        elif ct_id == "CT-ADMIN-001":
            result.primary_entity = mun_id or "MUN"
            result.secondary_entity = "CENTRAL_INSPECTION_OR_MOIM_IF_ESCALATION"
            confidence = "medium" if mun_id else "low"
        elif ct_id in {"CT-ADMIN-002", "CT-ADMIN-004"}:
            result.primary_entity = "CENTRAL_INSPECTION"
            result.secondary_entity = "ISF_IF_CRIMINAL_THREAT;MOIM_IF_MUNICIPAL_GOVERNANCE"
            add_hitl("oversight_complaint_boundary", "oversight_complaint_boundary - administrative misconduct complaints need evidence and privacy review")
            confidence = "medium"
        elif ct_id == "CT-ADMIN-003":
            if re.search(r"\b(dglac|registration number|form id)\b|رقم التسجيل|المديرية العامة", complaint_text, re.IGNORECASE):
                result.primary_entity = "DGLAC"
                result.secondary_entity = mun_id or "MUN"
            else:
                result.primary_entity = mun_id or "MUN"
                result.secondary_entity = "DGLAC_IF_CENTRAL_FORM"
            confidence = "medium" if result.primary_entity == "DGLAC" or mun_id else "low"

    # Roads/public-works guardrails from the roads_public_works KB shard.
    if sector == "ROADS":
        if ct_id == "CT-PROJ-002":
            result.primary_entity = "CDR"
            result.secondary_entity = "MUN_OR_MPWT_BY_ASSET"
            add_hitl("cdr_project_boundary", "cdr_project_boundary - verify active CDR project before project-owner routing")
            confidence = "medium"
        elif ct_id == "CT-PROJ-003":
            result.primary_entity = mun_id or "HITL"
            result.secondary_entity = "MPWT_OR_CDR_BY_PROJECT_OWNER"
            add_hitl("worksite_owner_boundary", "worksite_owner_boundary - verify municipality MPWT CDR or contractor owner")
            confidence = "medium" if mun_id else "low"
        elif ct_id in {"CT-ROAD-002", "CT-ROAD-003"} or (_detect_national_road(complaint_text) and not _ROAD_LOCAL_RE.search(complaint_text)):
            result.primary_entity = "MPWT"
            result.secondary_entity = mun_id or "MUN_IF_LOCAL_ROAD"
            add_hitl("road_class_boundary", "road_class_boundary - confirm national/classified road versus local municipal road")
            confidence = "medium"
        elif ct_id in {"CT-ROAD-005", "CT-ROAD-006", "CT-ROAD-007"}:
            result.primary_entity = mun_id or "HITL"
            result.secondary_entity = "MPWT_OR_CD_IF_MAIN_ROAD_OR_DANGER"
            add_hitl("road_safety_boundary", "road_safety_boundary - blocked storm unsafe road may need MPWT or Civil Defense depending road class and danger")
            confidence = "medium" if mun_id else "low"
        elif result.secondary_entity in {"MUN_UNION", "MUN_UNION_DYNAMIC"}:
            result.secondary_entity = ""

    # Waste/environment guardrails from the waste_environment KB shard.
    if sector == "WASTE":
        if ct_id == "CT-WASTE-004":
            result.primary_entity = "CD"
            result.secondary_entity = mun_id or "MUN;MOE"
            add_hitl("waste_fire_emergency", "waste_fire_emergency - Civil Defense first then municipality/MOE follow-up")
            confidence = "high"
        elif ct_id == "CT-WASTE-005":
            result.primary_entity = "MOE"
            result.secondary_entity = mun_id or "MUN"
            add_hitl("hazardous_waste_boundary", "hazardous_waste_boundary - confirm hazardous/medical/industrial waste and local containment")
            confidence = "medium"
        elif ct_id == "CT-WASTE-002" and (_ENV_INDUSTRIAL_RE.search(complaint_text) or _WASTE_HAZARDOUS_RE.search(complaint_text)):
            result.primary_entity = "MOE"
            result.secondary_entity = mun_id or "MUN"
            add_hitl("illegal_dumping_environmental_boundary", "illegal_dumping_environmental_boundary - possible MOE environmental enforcement case")
            confidence = "medium"
        elif result.secondary_entity in {"MUN_UNION", "MUN_UNION_DYNAMIC"}:
            result.secondary_entity = ""

    if sector == "ENVIRONMENT":
        if ct_id in {"CT-ENV-002", "CT-ENV-003", "CT-ENV-004"}:
            result.primary_entity = "MOE"
            result.secondary_entity = mun_id or "MUN"
            add_hitl("environmental_evidence_boundary", "environmental_evidence_boundary - source/evidence and exact location needed for regulatory complaint")
            confidence = "medium"
        elif ct_id == "CT-ENV-001" and _ENV_INDUSTRIAL_RE.search(complaint_text):
            result.primary_entity = "MOE"
            result.secondary_entity = mun_id or "MUN"
            add_hitl("industrial_air_pollution_boundary", "industrial_air_pollution_boundary - industrial source points to MOE with municipal context")
            confidence = "medium"

    # Gate: electricity needs location to pick EDL vs EDZ
    if sector == "ELECTRICITY" and mun_id and service_map:
        result.primary_entity = service_map.get("electricity_entity_id", "EDL")
        confidence = "high" if service_map.get("electricity_confidence", "") == "high" else "medium"

    # Electricity-specific guardrails from the electricity KB shard.
    if sector == "ELECTRICITY":
        if _ELECTRIC_GENERATOR_RE.search(complaint_text):
            result.primary_entity = "HITL"
            result.secondary_entity = "PRIVATE_GENERATOR_OR_LOCAL_REGULATOR"
            add_hitl("private_generator_boundary", "private_generator_boundary - confirm generator versus public grid and local regulatory path")
            confidence = "medium"
            result.warnings.append("ELECTRICITY_BOUNDARY: private generator issues are not EDL/EDZ grid faults by default")

        elif _ELECTRIC_INTERNAL_RE.search(complaint_text) and not (_ELECTRIC_EXPOSED_RE.search(complaint_text) or _ELECTRIC_SPARK_RE.search(complaint_text)):
            result.primary_entity = "HITL"
            result.secondary_entity = "PRIVATE_PROPERTY_OR_ELECTRICIAN"
            add_hitl("internal_wiring_boundary", "internal_wiring_boundary - confirm private wiring versus public grid asset")
            confidence = "medium"
            result.warnings.append("ELECTRICITY_BOUNDARY: internal building wiring is not ordinary utility dispatch")

        elif ct_id == "CT-ELEC-004" and not (_ELECTRIC_EXPOSED_RE.search(complaint_text) or _ELECTRIC_SPARK_RE.search(complaint_text)):
            result.primary_entity = mun_id or "MUN"
            result.secondary_entity = "EDL_OR_EDZ_IF_GRID_SUPPLY_ISSUE"
            confidence = "medium" if mun_id else "low"
            result.warnings.append("ELECTRICITY_BOUNDARY: streetlight fixture outage defaults to municipality unless grid hazard is visible")

        if _ELECTRIC_EXPOSED_RE.search(complaint_text) or _ELECTRIC_SPARK_RE.search(complaint_text):
            utility_entity = result.primary_entity if result.primary_entity not in {"HITL", "MUN"} else "EDL_OR_EDZ_BY_LOCATION"
            result.primary_entity = utility_entity
            result.secondary_entity = "CD"
            add_hitl("electrical_public_hazard", "electrical_public_hazard - exposed or sparking public electrical asset")
            confidence = "medium" if confidence == "low" else confidence
            result.warnings.append("ELECTRICITY_EMERGENCY: call Civil Defense 125 if there is immediate public danger")

        if _ELECTRIC_TRANSFORMER_RE.search(complaint_text) and _ELECTRIC_FIRE_DANGER_RE.search(complaint_text):
            utility_entity = result.primary_entity if result.primary_entity not in {"HITL", "CD"} else "EDL_OR_EDZ_BY_LOCATION"
            result.primary_entity = "CD"
            result.secondary_entity = utility_entity
            add_hitl("transformer_fire_emergency", "transformer_fire_emergency - Civil Defense first then utility isolation")
            confidence = "high"

        has_electrical_hazard = bool(
            _ELECTRIC_EXPOSED_RE.search(complaint_text)
            or _ELECTRIC_SPARK_RE.search(complaint_text)
            or (_ELECTRIC_TRANSFORMER_RE.search(complaint_text) and _ELECTRIC_FIRE_DANGER_RE.search(complaint_text))
        )
        if not has_electrical_hazard and result.secondary_entity in {"CD", "CIVIL_DEFENSE", "ISF"}:
            result.secondary_entity = ""

        if mun_id is None and result.primary_entity in {"EDL", "EDZ", "EDL_OR_EDZ_BY_LOCATION"}:
            result.primary_entity = "HITL"
            result.secondary_entity = "CD;EDL_OR_EDZ_BY_LOCATION" if result.secondary_entity == "CD" else "EDL_OR_EDZ_BY_LOCATION"
            add_hitl("missing_location", "location_missing - electricity entity depends on EDL versus EDZ location")
            confidence = "low"

    # Telecom-specific guardrails from the telecom KB shard.
    if sector == "TELECOM":
        mobile = _detect_mobile_complaint(complaint_text)
        billing = bool(_TELECOM_BILLING_RE.search(complaint_text))
        regulatory = _detect_billing_regulatory(complaint_text)

        if _TELECOM_PRIVATE_CPE_RE.search(complaint_text) and not re.search(r"\b(ogero|dsl|vdsl|fiber|fibre|line)\b", complaint_text, re.IGNORECASE):
            result.primary_entity = "HITL"
            result.secondary_entity = "PRIVATE_CPE_OR_HOME_NETWORK"
            add_hitl("private_cpe_boundary", "private_cpe_boundary - confirm Ogero line fault versus private router/device issue")
            confidence = "medium"
            result.warnings.append("TELECOM_BOUNDARY: private router/device issues are not Ogero infrastructure by default")

        elif _TELECOM_PRIVATE_ISP_RE.search(complaint_text):
            result.primary_entity = "HITL"
            result.secondary_entity = "PRIVATE_ISP_OR_RESELLER"
            add_hitl("private_isp_boundary", "private_isp_boundary - confirm Ogero last-mile fault versus private ISP/reseller")
            confidence = "medium"
            result.warnings.append("TELECOM_BOUNDARY: private ISP/satellite complaints need provider confirmation before Ogero routing")

        elif mobile and (billing or regulatory):
            result.primary_entity = "TRA"
            result.secondary_entity = "MOBILE_OPERATOR_FIRST"
            confidence = "high" if regulatory else "medium"
            result.warnings.append("TELECOM_BOUNDARY: TRA is escalation/regulator; user should identify Alfa/Touch/provider history when available")

        elif mobile:
            result.primary_entity = "TRA"
            result.secondary_entity = "MOBILE_OPERATOR_FIRST"
            confidence = "medium"
            result.warnings.append("TELECOM_BOUNDARY: mobile network issues are not Ogero fixed-line faults")

        elif regulatory:
            result.primary_entity = "TRA"
            result.secondary_entity = "OGERO_OR_OPERATOR_FIRST"
            confidence = "medium"
            result.warnings.append("TELECOM_BOUNDARY: TRA is an escalation route after provider non-response or regulatory dispute")

        elif result.primary_entity == "OGERO":
            if result.secondary_entity in {"MUN_DYNAMIC", "MUN", "MUN_UNION"} and not (_TELECOM_CABLE_CUT_RE.search(complaint_text) or _TELECOM_CABINET_RE.search(complaint_text)):
                result.secondary_entity = ""
            if _TELECOM_CABLE_CUT_RE.search(complaint_text) or _TELECOM_CABINET_RE.search(complaint_text):
                result.secondary_entity = result.secondary_entity or "MUN_IF_PUBLIC_OBSTRUCTION"
                result.warnings.append("TELECOM_BOUNDARY: public Ogero cable/cabinet damage may need exact street location and municipal public-space coordination")

        if mun_id is None and result.primary_entity == "OGERO" and ct_id in {"CT-TEL-001", "CT-TEL-002", "CT-TEL-003", "CT-TEL-004", "CT-TEL-006", "CT-TEL-007", "CT-TEL-008", "CT-TEL-009"}:
            result.primary_entity = "HITL"
            result.secondary_entity = "OGERO"
            add_hitl("missing_location_or_line", "location_or_line_missing - fixed telecom fault needs municipality exact location or line/account details")
            confidence = "low"

    # Gate: water needs location to pick water authority. Prefer the canonical
    # water resolver shard because it carries source IDs and branch hints.
    if sector == "WATER" and mun_id:
        if water_resolution:
            result.primary_entity = water_resolution.get("water_entity_id", "RWA_DYNAMIC")
            confidence = conf_map.get(water_resolution.get("confidence", ""), "medium")
            branch_name = water_resolution.get("branch_service_center_name", "")
            branch_phone = water_resolution.get("branch_service_center_phone", "")
            if branch_name:
                branch_note = f"WATER_RESOLUTION: branch_hint={branch_name}"
                if branch_phone:
                    branch_note += f" phone={branch_phone}"
                result.warnings.append(branch_note)
        elif service_map:
            result.primary_entity = service_map.get("water_establishment_id", "RWA_DYNAMIC")
            confidence = "high" if service_map.get("water_confidence", "").startswith("medium") else "medium"

    # Water-specific guardrails from the water_establishments KB.
    if sector == "WATER":
        if _is_private_plumbing_issue(complaint_text):
            result.primary_entity = "PRIVATE_PROPERTY_OR_BUILDING_MANAGEMENT"
            result.secondary_entity = ""
            clear_hitl()
            confidence = "medium"
            result.warnings.append("WATER_BOUNDARY: private plumbing/tank/pump issue unless public-network evidence is provided")

        elif _WATER_PRIVATE_WELL_RE.search(complaint_text):
            result.primary_entity = "MEW" if re.search(r"\b(license|permit)\b|رخصة", complaint_text, re.IGNORECASE) else "HITL"
            result.secondary_entity = "MOE"
            code = "private_well_license" if result.primary_entity == "MEW" else "private_well_unclear_authority"
            add_hitl(code, "private_well_or_groundwater_boundary - confirm public network vs private source and public-health risk")
            confidence = "medium"
            result.warnings.append("WATER_BOUNDARY: private well/groundwater issue is not ordinary WE network dispatch")

        elif _WATER_TANKER_DISPUTE_RE.search(complaint_text) and not re.search(
            r"\b(no water|water cut|outage|mafi may|ma fi may|2ata3|ata3|public network|network)\b|انقطع|ما في مي",
            complaint_text,
            re.IGNORECASE,
        ):
            result.primary_entity = "PRIVATE_WATER_VENDOR_OR_CONSUMER_DISPUTE"
            result.secondary_entity = ""
            clear_hitl()
            confidence = "medium"
            result.warnings.append("WATER_BOUNDARY: private tanker/vendor dispute; ask if public network outage is also involved")

        elif _WATER_LRA_RE.search(complaint_text) and _WATER_IRRIGATION_RE.search(complaint_text):
            result.primary_entity = "HITL"
            result.secondary_entity = "LRA"
            add_hitl("irrigation_lra_overlap", "irrigation_litani_boundary - confirm LRA/Qasimiya/Ras Al Ain asset owner")
            confidence = "medium"
            result.warnings.append("WATER_BOUNDARY: LRA may be primary for Litani/Qasimiya/Ras Al Ain irrigation assets")

        elif _WATER_SEWAGE_RE.search(complaint_text):
            add_hitl("sewage_public_health", "sewage_or_wastewater_public_health_boundary")
            confidence = "medium" if confidence == "low" else confidence

        elif _WATER_DIRTY_RE.search(complaint_text):
            add_hitl("dirty_water_public_health", "dirty_water_public_health_check - ask source, color/smell, photos, and whether multiple homes are affected")
            result.secondary_entity = result.secondary_entity or "MOE"
            confidence = "medium" if confidence == "low" else confidence

        elif ct_id == "CT-WATER-006":
            add_hitl("irrigation_asset_unclear", "irrigation_asset_boundary - confirm WE versus LRA/project/private asset")
            confidence = "medium" if confidence == "low" else confidence

        if _WATER_HOME_EMERGENCY_RE.search(complaint_text) and (_WATER_SEWAGE_RE.search(complaint_text) or _WATER_PIPE_LEAK_RE.search(complaint_text)):
            result.secondary_entity = result.primary_entity if result.primary_entity not in {"HITL", "CD"} else result.secondary_entity
            result.primary_entity = "CD"
            add_hitl("water_emergency_first", "water_emergency_first - flooding/sewage entering home or collapse/electrical risk")
            confidence = "high"

        if mun_id is None and result.primary_entity == "RWA_DYNAMIC":
            result.primary_entity = "HITL"
            result.secondary_entity = "WATER_ESTABLISHMENT_BY_LOCATION"
            add_hitl("missing_location", "location_missing - water establishment depends on municipality or GPS")

    if sector == "ENVIRONMENT" and ct_id == "CT-ENV-003":
        add_hitl("river_pollution", "river_or_stream_pollution_boundary - confirm source, water body, and responsible authority")

    # ── FLOODING HITL gate ───────────────────────────────────────────────────
    # Flooding escalation has three levels; only the top two are safety emergencies
    # that unconditionally require HITL regardless of routing rules.
    #  1. Immediate danger (trapped/wires in water) → CD primary, HITL=True
    #  2. Indoor flooding  (water entered home/basement) → CD primary, HITL=True
    #  3. Infrastructure flooding (blocked drain/road) → keep rule-derived entity,
    #     add HITL only if routing rule already requires it or location is unknown.
    if sector == "FLOODING":
        if _FLOODING_IMMEDIATE_DANGER_RE.search(complaint_text):
            result.primary_entity = "CD"
            result.secondary_entity = "ISF;MUN"
            add_hitl("flooding_immediate_danger",
                     "flooding_immediate_danger - trapped persons/vehicles or electrical in water requires Civil Defense dispatch")
            confidence = "high"
        elif _FLOODING_INDOOR_RE.search(complaint_text):
            prev = result.primary_entity
            result.primary_entity = "CD"
            result.secondary_entity = prev if prev not in {"CD", "HITL", ""} else (mun_id or "MUN")
            add_hitl("flooding_indoor_emergency",
                     "flooding_indoor_emergency - water entering home or basement is a life-safety risk requiring Civil Defense")
            confidence = "high"
        else:
            # Infrastructure/road flooding: keep rule-derived entity; add HITL if
            # location is missing or routing rules flag it.
            if _FLOODING_INFRASTRUCTURE_RE.search(complaint_text) or result.primary_entity in {"HITL", ""}:
                if result.primary_entity in {"HITL", ""}:
                    result.primary_entity = mun_id or "MUN"
            if mun_id is None:
                add_hitl("flooding_missing_location",
                         "flooding_location_missing - cannot dispatch drain/road flooding without municipality")
                confidence = "low"
    # ────────────────────────────────────────────────────────────────────────

    result.hitl_required = hitl_required
    result.hitl_reason = "; ".join(hitl_reasons) if hitl_reasons else ""
    result.hitl_reason_codes = hitl_reason_codes
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

"""
Structured text extractor for English complaint text.

Phase 1: Rule-based keyword/regex extraction.
Phase 2: Replace with Qwen2.5 / Llama structured JSON generation.

AI Engineer 1 owns this file.
"""

import re
from typing import Dict, List, Optional, Tuple

from cedarfix_shared.schemas import (
    ComplaintType,
    LocationJSON,
    ReconciliationStatus,
    SeverityLevel,
    SignalsJSON,
    TextUnderstandingResult,
)

# ---------------------------------------------------------------------------
# Category hierarchy: issue_type → (category, subcategory)
# ---------------------------------------------------------------------------

ISSUE_HIERARCHY: Dict[ComplaintType, Tuple[str, str]] = {
    ComplaintType.POTHOLE:          ("roads",       "pothole"),
    ComplaintType.ROAD_DAMAGE:      ("roads",       "road_damage"),
    ComplaintType.FLOODING:         ("drainage",    "flooding"),
    ComplaintType.WASTE:            ("sanitation",  "waste_accumulation"),
    ComplaintType.ELECTRICITY:      ("electricity", "outage"),
    ComplaintType.TRAFFIC_LIGHT:    ("roads",       "traffic_light"),
    ComplaintType.WATER_PIPE:       ("water",       "pipe_leak"),
    ComplaintType.WATER_OUTAGE:     ("water",       "water_outage"),
    ComplaintType.SIDEWALK:         ("roads",       "sidewalk_damage"),
    ComplaintType.STREETLIGHT:      ("electricity", "streetlight"),
    ComplaintType.TRAFFIC_INCIDENT: ("roads",       "traffic_incident"),
    ComplaintType.PUBLIC_SAFETY:    ("other",       "public_safety"),
    ComplaintType.OTHER:            ("other",       "other"),
}

# Semantic descriptors used downstream for cross-modal text/image validation.
# Keep this aligned with the image-side descriptor vocabulary.
ISSUE_DESCRIPTORS: Dict[ComplaintType, Tuple[str, str, str]] = {
    ComplaintType.POTHOLE:          ("transportation", "road_surface",    "damage"),
    ComplaintType.ROAD_DAMAGE:      ("transportation", "road_surface",    "damage"),
    ComplaintType.FLOODING:         ("environment",    "drainage_system", "overflow"),
    ComplaintType.WASTE:            ("environment",    "public_space",    "accumulation"),
    ComplaintType.ELECTRICITY:      ("utilities",      "electrical_line", "outage"),
    ComplaintType.TRAFFIC_LIGHT:    ("transportation", "traffic_signal",  "damage"),
    ComplaintType.WATER_PIPE:       ("utilities",      "water_pipe",      "damage"),
    ComplaintType.WATER_OUTAGE:     ("utilities",      "water_supply",    "outage"),
    ComplaintType.SIDEWALK:         ("transportation", "sidewalk",        "damage"),
    ComplaintType.STREETLIGHT:      ("transportation", "street_light",    "damage"),
    ComplaintType.TRAFFIC_INCIDENT: ("transportation", "road_surface",    "blockage"),
    ComplaintType.PUBLIC_SAFETY:    ("safety",         "public_space",    "other"),
    ComplaintType.OTHER:            ("other",          "other",           "other"),
}

# ---------------------------------------------------------------------------
# Keyword maps (English — Phase 1)
# TODO Phase 2: replace with fine-tuned classifier
# ---------------------------------------------------------------------------

ISSUE_KEYWORDS: Dict[ComplaintType, List[str]] = {
    ComplaintType.POTHOLE: [
        "pothole", "hole in road", "road hole", "pit in road",
        "crater in road", "dip in road", "large hole", "deep hole",
    ],
    ComplaintType.ROAD_DAMAGE: [
        "road damage", "broken road", "cracked road", "road crack",
        "damaged asphalt", "asphalt crack", "pavement crack", "street damage",
        "road broken", "damaged road", "road deterioration",
    ],
    ComplaintType.FLOODING: [
        "flood", "flooding", "water on road", "standing water",
        "road flooded", "street flooded", "inundation", "waterlogged",
        "overflow", "submerged", "water accumulation",
    ],
    ComplaintType.WASTE: [
        "garbage", "waste", "trash", "rubbish", "litter",
        "pile of garbage", "waste accumulation", "dumpster overflow",
        "refuse", "solid waste",
    ],
    ComplaintType.ELECTRICITY: [
        "electricity", "power cut", "power outage", "no power",
        "blackout", "electric issue", "electrical problem",
        "no electricity", "power failure",
    ],
    ComplaintType.TRAFFIC_LIGHT: [
        "traffic light", "traffic signal", "signal broken",
        "signal not working", "stoplight", "red light broken",
        "traffic lamp", "broken signal",
    ],
    ComplaintType.WATER_PIPE: [
        "pipe leak", "water leak", "broken pipe", "water pipe",
        "burst pipe", "leaking pipe", "water main", "pipe burst",
        "water gushing", "water waste", "wasted water", "water loss",
        "water is wasting", "water being wasted",
    ],
    ComplaintType.WATER_OUTAGE: [
        "water outage", "no water", "water cut", "water cutoff",
        "water supply cut", "no running water", "water not available",
        "water disconnected", "water supply issue", "water shortage",
        "ma fi may", "mayo ma3na",
    ],
    ComplaintType.SIDEWALK: [
        "sidewalk", "pavement broken", "footpath", "walkway broken",
        "sidewalk damaged", "cracked pavement", "broken sidewalk",
        "damaged footpath",
    ],
    ComplaintType.STREETLIGHT: [
        "streetlight", "street light", "lamp post", "street lamp",
        "light not working", "broken light", "no lighting",
        "dark street", "lamp broken",
    ],
    ComplaintType.TRAFFIC_INCIDENT: [
        "accident", "car accident", "road accident", "traffic accident",
        "crash", "collision", "vehicle crash", "car crash",
        "congestion", "traffic jam", "traffic block", "road blocked",
        "blocked road", "road closure", "road closed", "traffic incident",
        "traffic problem", "traffic issue", "heavy traffic",
    ],
    ComplaintType.PUBLIC_SAFETY: [
        "unsafe", "dangerous structure", "falling debris", "risk to life",
        "public hazard", "structural collapse", "unsafe building",
        "falling wall", "dangerous building", "public safety",
        "safety hazard", "fire hazard", "open manhole", "exposed wire",
    ],
}

SEVERITY_KEYWORDS: Dict[SeverityLevel, List[str]] = {
    SeverityLevel.CRITICAL: [
        "completely blocked", "emergency", "collapsing", "collapse",
        "danger of life", "accident", "severe flooding", "dangerous",
        "critical", "severe", "fatal", "life threatening",
    ],
    SeverityLevel.HIGH: [
        "large", "major", "significant", "deep pothole", "very deep",
        "causing accident", "traffic jam", "major issue", "big hole",
        "serious", "heavy flooding",
    ],
    SeverityLevel.MEDIUM: [
        "medium", "moderate", "causing traffic", "traffic",
        "noticeable", "multiple", "several",
    ],
    SeverityLevel.LOW: [
        "small", "minor", "slight", "little", "tiny",
    ],
}

PUBLIC_SAFETY_KEYWORDS = [
    "dangerous", "danger", "accident", "injury", "hurt",
    "risk", "hazard", "unsafe", "falling", "collapse", "emergency",
]
TRAFFIC_KEYWORDS = [
    "traffic", "congestion", "blocked", "slow", "jam", "delay", "queue",
]
EMERGENCY_KEYWORDS = [
    "emergency", "urgent", "immediately", "asap", "critical",
    "risk of", "now",
]
CORRUPTION_KEYWORDS = [
    "corruption", "no action", "ignored", "reported before",
    "no one came", "never fixed", "wasta",
]
URGENCY_KEYWORDS = [
    "urgent", "immediately", "asap", "dangerous", "emergency",
    "critical", "risk of", "please fix", "need immediate",
]

# ---------------------------------------------------------------------------
# Location patterns — Lebanese city / area names
# TODO Phase 2: replace with spaCy NER → CAMeL-Lab Arabic NER
# ---------------------------------------------------------------------------

_LOCATION_PATTERN = re.compile(
    r"\b("
    r"hamra|cola|jounieh|tripoli|sidon|tyre|sur|baabda|ashrafieh|verdun|"
    r"bourj hammoud|dekwaneh|sin el fil|jdeideh|antelias|dbayeh|kaslik|"
    r"jbeil|byblos|zalka|dora|nahr el mott|metn|kesrouan|batroun|koura|"
    r"zgharta|mina|minyeh|nabatieh|marjayoun|hasbaya|bint jbeil|"
    r"aley|chouf|deir el qamar|beiteddine|saida|beirut|downtown|gemmayzeh|"
    r"mar mikhael|geitawi|badaro|tallet el khayat|ras beirut|"
    r"dahr el baydar|zahle|chtaura|bekaa|baalbek|hermel|aanjar"
    r")\b",
    re.IGNORECASE,
)

DISTRICT_MAP: Dict[str, str] = {
    "hamra": "Beirut",        "cola": "Beirut",         "ashrafieh": "Beirut",
    "verdun": "Beirut",       "badaro": "Beirut",        "downtown": "Beirut",
    "gemmayzeh": "Beirut",    "mar mikhael": "Beirut",   "geitawi": "Beirut",
    "ras beirut": "Beirut",   "tallet el khayat": "Beirut",
    "bourj hammoud": "Metn",  "dekwaneh": "Metn",        "sin el fil": "Metn",
    "jdeideh": "Metn",        "antelias": "Metn",        "dora": "Metn",
    "zalka": "Metn",          "nahr el mott": "Metn",
    "kaslik": "Kesrouan",     "jounieh": "Kesrouan",     "dbayeh": "Kesrouan",
    "jbeil": "Byblos",        "byblos": "Byblos",
    "tripoli": "North Lebanon", "mina": "North Lebanon", "minyeh": "North Lebanon",
    "batroun": "Batroun",     "koura": "Koura",          "zgharta": "Zgharta",
    "sidon": "Sidon",         "saida": "Sidon",
    "tyre": "Tyre",           "sur": "Tyre",
    "nabatieh": "Nabatieh",   "marjayoun": "Marjayoun",
    "hasbaya": "Hasbaya",     "bint jbeil": "Bint Jbeil",
    "aley": "Aley",           "chouf": "Chouf",
    "deir el qamar": "Chouf", "beiteddine": "Chouf",
    "metn": "Metn",           "kesrouan": "Kesrouan",
    "baabda": "Baabda",       "beirut": "Beirut",
    "dahr el baydar": "Aley", "zahle": "Bekaa",
    "chtaura": "Bekaa",       "bekaa": "Bekaa",
    "baalbek": "Baalbek",     "hermel": "Hermel",
    "aanjar": "Bekaa",
}

GOVERNORATE_MAP: Dict[str, str] = {
    "Beirut":        "Beirut Governorate",
    "Metn":          "Mount Lebanon",
    "Kesrouan":      "Mount Lebanon",
    "Byblos":        "Mount Lebanon",
    "Baabda":        "Mount Lebanon",
    "Aley":          "Mount Lebanon",
    "Chouf":         "Mount Lebanon",
    "North Lebanon": "North Lebanon Governorate",
    "Batroun":       "North Lebanon Governorate",
    "Koura":         "North Lebanon Governorate",
    "Zgharta":       "North Lebanon Governorate",
    "Sidon":         "South Lebanon Governorate",
    "Tyre":          "South Lebanon Governorate",
    "Nabatieh":      "Nabatieh Governorate",
    "Marjayoun":     "Nabatieh Governorate",
    "Hasbaya":       "Nabatieh Governorate",
    "Bint Jbeil":    "Nabatieh Governorate",
    "Bekaa":         "Bekaa Governorate",
    "Baalbek":       "Baalbek-Hermel Governorate",
    "Hermel":        "Baalbek-Hermel Governorate",
}


# ---------------------------------------------------------------------------
# StructuredExtractor
# ---------------------------------------------------------------------------

class StructuredExtractor:
    """
    Produces a structured TextUnderstandingResult from raw English complaint text.

    Phase 1: rule-based keyword scoring + regex.
    TODO Phase 2: replace body of `extract()` with a call to
                  Qwen2.5 / Llama with a structured JSON output prompt.
    """

    def extract(self, complaint_id: str, text: str) -> TextUnderstandingResult:
        normalized = self._normalize(text)
        issue_type, type_conf = self._classify_issue_type(normalized)
        category, subcategory = ISSUE_HIERARCHY[issue_type]
        semantic_domain, physical_component, failure_mode = ISSUE_DESCRIPTORS.get(
            issue_type, ("other", "other", "other")
        )
        location = self._extract_location(normalized)
        severity = self._estimate_severity(normalized)
        signals = self._extract_signals(normalized)
        urgency_kws = self._extract_urgency_keywords(normalized)
        summary = self._generate_summary(subcategory, location.normalized, normalized)

        # Location confidence boosts overall confidence
        loc_boost = 0.3 if location.normalized else 0.0
        overall_conf = round(type_conf * 0.7 + loc_boost, 3)

        return TextUnderstandingResult(
            complaint_id=complaint_id,
            original_text=text,
            normalized_text=normalized,
            language="english",
            summary=summary,
            category=category,
            subcategory=subcategory,
            issue_type=issue_type,
            location=location,
            severity=severity,
            signals=signals,
            urgency_keywords=urgency_kws,
            confidence=min(overall_conf, 0.95),
            semantic_domain=semantic_domain,
            physical_component=physical_component,
            failure_mode=failure_mode,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalize(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def _classify_issue_type(self, text: str) -> Tuple[ComplaintType, float]:
        """
        Score each issue type by counting how many of its keywords appear in the text.
        Returns best type and normalised confidence.
        """
        text_lower = text.lower()
        scores: Dict[ComplaintType, int] = {}
        for issue_type, keywords in ISSUE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[issue_type] = score
        if not scores:
            return ComplaintType.OTHER, 0.4
        best = max(scores, key=scores.get)
        total = sum(scores.values())
        conf = min(scores[best] / max(total, 1) + 0.15, 0.95)
        return best, round(conf, 3)

    def _extract_location(self, text: str) -> LocationJSON:
        matches = _LOCATION_PATTERN.findall(text)
        if not matches:
            return LocationJSON(raw="", normalized="", confidence=0.0)
        # De-duplicate while preserving first-seen order
        seen: Dict[str, None] = {}
        for m in matches:
            seen[m.lower()] = None
        unique = list(seen.keys())
        raw_str = ", ".join(m.title() for m in unique)
        primary = unique[0]
        district = DISTRICT_MAP.get(primary)
        governorate = GOVERNORATE_MAP.get(district) if district else None
        return LocationJSON(
            raw=raw_str,
            normalized=primary.title(),
            district=district,
            governorate=governorate,
            confidence=0.74,
        )

    def _estimate_severity(self, text: str) -> SeverityLevel:
        text_lower = text.lower()
        for level in (
            SeverityLevel.CRITICAL,
            SeverityLevel.HIGH,
            SeverityLevel.MEDIUM,
        ):
            if any(kw in text_lower for kw in SEVERITY_KEYWORDS[level]):
                return level
        return SeverityLevel.LOW

    def _extract_signals(self, text: str) -> SignalsJSON:
        tl = text.lower()
        return SignalsJSON(
            public_safety_risk=any(kw in tl for kw in PUBLIC_SAFETY_KEYWORDS),
            traffic_impact=any(kw in tl for kw in TRAFFIC_KEYWORDS),
            corruption_signal=any(kw in tl for kw in CORRUPTION_KEYWORDS),
            emergency_signal=any(kw in tl for kw in EMERGENCY_KEYWORDS),
        )

    def _extract_urgency_keywords(self, text: str) -> List[str]:
        tl = text.lower()
        return [kw for kw in URGENCY_KEYWORDS if kw in tl]

    def _generate_summary(
        self,
        subcategory: str,
        location: str,
        text: str,
    ) -> str:
        label = subcategory.replace("_", " ")
        if location:
            return f"{label.capitalize()} reported in {location}"
        words = text.split()
        truncated = " ".join(words[:12])
        return truncated + ("..." if len(words) > 12 else "")

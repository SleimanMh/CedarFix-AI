"""
Location Normalizer — shared module used by IEP-1 and the routing engine.

Resolution priority (highest → lowest):
  1. GPS coordinates  → reverse_geocode (external API abstraction)
  2. Text mention     → lookup in LB_LOCATIONS seed table
  3. user_hint field  → same text lookup
  4. LLM extracted    → no extra resolution (IEP-1 already ran it)
  5. none             → empty result, confidence = 0

The seed table (LB_LOCATIONS) is intentionally small (~100 entries covering
the most common complaint areas). Replace/extend with a full PostgreSQL
lb_locations table when available.

Output always matches LocationJSON schema:
  {raw, normalized, municipality, district, governorate,
   latitude, longitude, confidence, source}
"""

from __future__ import annotations

import os
from difflib import SequenceMatcher
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Seed data — common Lebanese locations
# (name_en, name_ar, aliases, municipality, district, governorate, lat, lng)
# ---------------------------------------------------------------------------

LB_LOCATIONS: list[dict] = [
    # ── Beirut neighbourhoods ────────────────────────────────────────────────
    {"name": "Hamra",         "ar": "حمرا",     "aliases": ["hamra", "el hamra", "al hamra"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.8938, "lng": 35.4881},
    {"name": "Verdun",        "ar": "فردان",     "aliases": ["verdun", "rue verdun"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.8836, "lng": 35.4904},
    {"name": "Ashrafieh",     "ar": "الأشرفية",  "aliases": ["ashrafieh", "ashrafiyet", "achrafieh"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.8892, "lng": 35.5125},
    {"name": "Gemmayzeh",     "ar": "الجميزة",   "aliases": ["gemmayzeh", "gemmayze"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.8959, "lng": 35.5133},
    {"name": "Mar Mikhael",   "ar": "مار مخايل", "aliases": ["mar mikhael", "mar mikhail", "armenia street"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.8981, "lng": 35.5194},
    {"name": "Corniche",      "ar": "الكورنيش",  "aliases": ["corniche", "corniche beirut", "ain el mreisseh"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.8978, "lng": 35.4762},
    {"name": "Downtown Beirut", "ar": "وسط بيروت", "aliases": ["downtown", "centre ville", "solidere", "martyr square"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.8959, "lng": 35.5018},
    {"name": "Cola",          "ar": "كولا",      "aliases": ["cola", "cola intersection", "dawra cola"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.8698, "lng": 35.4932},
    {"name": "Bourj Hammoud", "ar": "برج حمود",  "aliases": ["bourj hammoud", "burj hammoud"],
     "municipality": "Bourj Hammoud", "district": "Metn", "governorate": "Mount Lebanon Governorate",
     "lat": 33.8906, "lng": 35.5439},
    {"name": "Zarif",         "ar": "الظريف",    "aliases": ["zarif", "el zarif"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.8806, "lng": 35.5006},
    {"name": "Ras Beirut",    "ar": "رأس بيروت", "aliases": ["ras beirut", "AUB area", "bliss"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.9000, "lng": 35.4788},
    {"name": "Badaro",        "ar": "بدارو",     "aliases": ["badaro"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.8734, "lng": 35.5119},
    {"name": "Tallet el Khayat", "ar": "تلة الخياط", "aliases": ["tallet el khayat", "tallet khayat"],
     "municipality": "Beirut", "district": "Beirut", "governorate": "Beirut Governorate",
     "lat": 33.8747, "lng": 35.4984},
    # ── Mount Lebanon ────────────────────────────────────────────────────────
    {"name": "Jounieh",       "ar": "جونية",     "aliases": ["jounieh", "jouniyeh"],
     "municipality": "Jounieh", "district": "Keserwan", "governorate": "Mount Lebanon Governorate",
     "lat": 33.9811, "lng": 35.6175},
    {"name": "Jdeideh",       "ar": "الجديدة",   "aliases": ["jdeideh", "jdeide", "el jdeideh"],
     "municipality": "Jdeideh", "district": "Metn", "governorate": "Mount Lebanon Governorate",
     "lat": 33.9003, "lng": 35.5753},
    {"name": "Dekwaneh",      "ar": "الدكوانة",  "aliases": ["dekwaneh", "dkwaneh"],
     "municipality": "Dekwaneh", "district": "Metn", "governorate": "Mount Lebanon Governorate",
     "lat": 33.9003, "lng": 35.5656},
    {"name": "Sin el Fil",    "ar": "سن الفيل",  "aliases": ["sin el fil", "sinn el fil", "sinelfil"],
     "municipality": "Sin el Fil", "district": "Metn", "governorate": "Mount Lebanon Governorate",
     "lat": 33.8867, "lng": 35.5511},
    {"name": "Baabda",        "ar": "بعبدا",     "aliases": ["baabda"],
     "municipality": "Baabda", "district": "Baabda", "governorate": "Mount Lebanon Governorate",
     "lat": 33.8356, "lng": 35.5442},
    {"name": "Aley",          "ar": "عاليه",     "aliases": ["aley", "aaley"],
     "municipality": "Aley", "district": "Aley", "governorate": "Mount Lebanon Governorate",
     "lat": 33.8115, "lng": 35.5997},
    {"name": "Byblos",        "ar": "جبيل",      "aliases": ["byblos", "jbeil", "jbail"],
     "municipality": "Jbeil", "district": "Jbeil", "governorate": "Mount Lebanon Governorate",
     "lat": 34.1228, "lng": 35.6508},
    {"name": "Antelias",      "ar": "انطلياس",   "aliases": ["antelias", "anteliyas"],
     "municipality": "Antelias", "district": "Metn", "governorate": "Mount Lebanon Governorate",
     "lat": 33.9161, "lng": 35.5978},
    {"name": "Dbayeh",        "ar": "ضبية",       "aliases": ["dbayeh", "dbaye"],
     "municipality": "Dbayeh", "district": "Metn", "governorate": "Mount Lebanon Governorate",
     "lat": 33.9306, "lng": 35.5936},
    {"name": "Choueifat",     "ar": "الشويفات",  "aliases": ["choueifat", "shweifat"],
     "municipality": "Choueifat", "district": "Baabda", "governorate": "Mount Lebanon Governorate",
     "lat": 33.8264, "lng": 35.4811},
    {"name": "Khalde",        "ar": "خلدة",       "aliases": ["khalde", "khaldeh"],
     "municipality": "Khalde", "district": "Baabda", "governorate": "Mount Lebanon Governorate",
     "lat": 33.7986, "lng": 35.4797},
    # ── North Lebanon ────────────────────────────────────────────────────────
    {"name": "Tripoli",       "ar": "طرابلس",    "aliases": ["tripoli", "trablus", "trablos"],
     "municipality": "Tripoli", "district": "Tripoli", "governorate": "North Governorate",
     "lat": 34.4366, "lng": 35.8497},
    {"name": "Zgharta",       "ar": "زغرتا",     "aliases": ["zgharta", "zghorta"],
     "municipality": "Zgharta", "district": "Zgharta", "governorate": "North Governorate",
     "lat": 34.4056, "lng": 35.8897},
    {"name": "Batroun",       "ar": "البترون",   "aliases": ["batroun", "batrun"],
     "municipality": "Batroun", "district": "Batroun", "governorate": "North Governorate",
     "lat": 34.2553, "lng": 35.6586},
    {"name": "Chekka",        "ar": "شكا",        "aliases": ["chekka", "chikka"],
     "municipality": "Chekka", "district": "Batroun", "governorate": "North Governorate",
     "lat": 34.3131, "lng": 35.7297},
    # ── South Lebanon ────────────────────────────────────────────────────────
    {"name": "Sidon",         "ar": "صيدا",       "aliases": ["sidon", "saida", "sayda"],
     "municipality": "Sidon", "district": "Sidon", "governorate": "South Governorate",
     "lat": 33.5572, "lng": 35.3725},
    {"name": "Tyre",          "ar": "صور",        "aliases": ["tyre", "sour", "sur"],
     "municipality": "Tyre", "district": "Tyre", "governorate": "South Governorate",
     "lat": 33.2742, "lng": 35.2031},
    {"name": "Nabatieh",      "ar": "النبطية",   "aliases": ["nabatieh", "nabatiye"],
     "municipality": "Nabatieh", "district": "Nabatieh", "governorate": "Nabatieh Governorate",
     "lat": 33.3772, "lng": 35.4836},
    {"name": "Bint Jbeil",    "ar": "بنت جبيل",  "aliases": ["bint jbeil", "bint jbayl"],
     "municipality": "Bint Jbeil", "district": "Bint Jbeil", "governorate": "Nabatieh Governorate",
     "lat": 33.1206, "lng": 35.4342},
    # ── Bekaa ────────────────────────────────────────────────────────────────
    {"name": "Zahle",         "ar": "زحلة",       "aliases": ["zahle", "zahleh", "zahle city"],
     "municipality": "Zahle", "district": "Zahle", "governorate": "Bekaa Governorate",
     "lat": 33.8497, "lng": 35.9017},
    {"name": "Baalbek",       "ar": "بعلبك",     "aliases": ["baalbek", "baalbeck", "baalbak"],
     "municipality": "Baalbek", "district": "Baalbek", "governorate": "Baalbek-Hermel Governorate",
     "lat": 34.0042, "lng": 36.2111},
    {"name": "Chtaura",       "ar": "شتورا",     "aliases": ["chtaura", "chtoura", "chtura"],
     "municipality": "Chtaura", "district": "Zahle", "governorate": "Bekaa Governorate",
     "lat": 33.8097, "lng": 35.8544},
    {"name": "Rayak",         "ar": "رياق",       "aliases": ["rayak", "riyak"],
     "municipality": "Rayak", "district": "Zahle", "governorate": "Bekaa Governorate",
     "lat": 33.8547, "lng": 35.9886},
    # ── Akkar ────────────────────────────────────────────────────────────────
    {"name": "Halba",         "ar": "حلبا",       "aliases": ["halba", "halbe"],
     "municipality": "Halba", "district": "Akkar", "governorate": "Akkar Governorate",
     "lat": 34.5522, "lng": 36.0783},
]

# Build an alias → location lookup for O(1) exact matches
_ALIAS_INDEX: dict[str, dict] = {}
for _loc in LB_LOCATIONS:
    for _alias in _loc["aliases"]:
        _ALIAS_INDEX[_alias.lower()] = _loc
    _ALIAS_INDEX[_loc["name"].lower()] = _loc


# ---------------------------------------------------------------------------
# Text-based lookup
# ---------------------------------------------------------------------------

def _fuzzy_score(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def lookup_text(text: str, min_score: float = 0.80) -> Optional[dict]:
    """
    Find the best matching Lebanese location for a free-text string.
    Returns the location dict or None.
    """
    text_lower = text.lower().strip()

    # 1. Exact alias match
    if text_lower in _ALIAS_INDEX:
        return _ALIAS_INDEX[text_lower]

    # 2. Substring match (text contains a known alias)
    for alias, loc in _ALIAS_INDEX.items():
        if alias in text_lower:
            return loc

    # 3. Fuzzy match
    best_score = 0.0
    best_loc: Optional[dict] = None
    for alias, loc in _ALIAS_INDEX.items():
        score = _fuzzy_score(text_lower, alias)
        if score > best_score:
            best_score = score
            best_loc = loc

    if best_score >= min_score:
        return best_loc
    return None


# ---------------------------------------------------------------------------
# Reverse geocoding abstraction (optional external call)
# ---------------------------------------------------------------------------

NOMINATIM_URL = os.getenv("NOMINATIM_URL", "")  # empty = disabled
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
GOOGLE_GEOCODING_URL = os.getenv(
    "GOOGLE_GEOCODING_URL",
    "https://maps.googleapis.com/maps/api/geocode/json",
)


def _google_admin_components(data: dict) -> Optional[dict]:
    results = data.get("results") or []
    if not results:
        return None

    result = results[0]
    components = result.get("address_components") or []

    def pick(*types: str) -> str:
        for comp in components:
            comp_types = set(comp.get("types") or [])
            if any(t in comp_types for t in types):
                return comp.get("long_name") or ""
        return ""

    geometry = result.get("geometry") or {}
    loc = geometry.get("location") or {}
    municipality = pick("locality", "postal_town", "administrative_area_level_3", "sublocality")
    district = pick("administrative_area_level_2")
    governorate = pick("administrative_area_level_1")

    return {
        "normalized": result.get("formatted_address", ""),
        "municipality": municipality,
        "district": district,
        "governorate": governorate,
        "display_name": result.get("formatted_address", ""),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "source": "google_maps",
    }


async def _google_geocode(params: dict) -> Optional[dict]:
    if not GOOGLE_MAPS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(
                GOOGLE_GEOCODING_URL,
                params={
                    **params,
                    "key": GOOGLE_MAPS_API_KEY,
                    "language": "en",
                    "region": "lb",
                },
            )
            r.raise_for_status()
            data = r.json()
            if data.get("status") not in ("OK", "ZERO_RESULTS"):
                return None
            return _google_admin_components(data)
    except Exception:
        return None


async def reverse_geocode(lat: float, lng: float) -> Optional[dict]:
    """
    Call Google Maps when configured, then self-hosted Nominatim if configured.
    Returns a dict with municipality, district, governorate, display_name.
    Falls back to None gracefully if not configured or network fails.
    """
    google = await _google_geocode({"latlng": f"{lat},{lng}"})
    if google and (google.get("municipality") or google.get("district") or google.get("governorate")):
        return google

    if not NOMINATIM_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(
                f"{NOMINATIM_URL}/reverse",
                params={
                    "lat": lat, "lon": lng,
                    "format": "jsonv2",
                    "accept-language": "en",
                    "addressdetails": "1",
                },
                headers={"User-Agent": "CedarFix/1.0"},
            )
            r.raise_for_status()
            data = r.json()
            addr = data.get("address", {})
            return {
                "municipality": addr.get("city") or addr.get("town") or addr.get("village") or "",
                "district":     addr.get("county") or "",
                "governorate":  addr.get("state") or "",
                "display_name": data.get("display_name", ""),
                "source":       "reverse_geocode",
            }
    except Exception:
        return None


async def geocode_text(text: str) -> Optional[dict]:
    """
    Resolve a free-form location string with Google Maps when configured.
    Falls back to the local Lebanon seed lookup when Google is unavailable.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return None

    google = await _google_geocode({"address": f"{cleaned}, Lebanon"})
    if google and (google.get("municipality") or google.get("district") or google.get("governorate")):
        return google

    loc = lookup_text(cleaned)
    if loc:
        return {
            "normalized": loc.get("name"),
            "municipality": loc.get("municipality"),
            "district": loc.get("district"),
            "governorate": loc.get("governorate"),
            "display_name": loc.get("name"),
            "lat": loc.get("lat"),
            "lng": loc.get("lng"),
            "source": "text_lookup",
        }
    return None


# ---------------------------------------------------------------------------
# Main normalizer
# ---------------------------------------------------------------------------

def _loc_to_result(loc: dict, raw: str, source: str, confidence: float) -> dict:
    return {
        "raw": raw,
        "normalized": loc["name"],
        "municipality": loc.get("municipality"),
        "district": loc.get("district"),
        "governorate": loc.get("governorate"),
        "latitude": loc.get("lat"),
        "longitude": loc.get("lng"),
        "confidence": round(confidence, 2),
        "source": source,
    }


async def normalize_location(
    *,
    raw_text: str = "",
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    user_hint: Optional[str] = None,
    llm_extracted_district: Optional[str] = None,
    llm_extracted_governorate: Optional[str] = None,
    llm_confidence: float = 0.0,
) -> dict:
    """
    Resolve a location to its canonical Lebanese administrative unit.

    Priority:
      1. GPS + reverse geocoding (highest)
      2. raw_text lookup
      3. user_hint lookup
      4. LLM extracted district/governorate (pass-through)
      5. None (empty result)

    Returns a dict matching LocationJSON fields.
    """
    # 1. GPS path
    if lat is not None and lng is not None:
        geo = await reverse_geocode(lat, lng)
        if geo and (geo.get("municipality") or geo.get("district") or geo.get("governorate")):
            normalized = geo.get("municipality") or geo.get("district") or geo.get("display_name") or f"{lat},{lng}"
            return {
                "raw": raw_text or f"{lat},{lng}",
                "normalized": normalized,
                "municipality": geo.get("municipality"),
                "district": geo.get("district"),
                "governorate": geo.get("governorate"),
                "latitude": lat,
                "longitude": lng,
                "confidence": 0.92,
                "source": geo.get("source") or "reverse_geocode",
            }
        # GPS coords available but no geocoder — try seed match by proximity
        best = _find_nearest_seed(lat, lng)
        if best:
            return {
                "raw": raw_text or f"{lat},{lng}",
                "normalized": best["name"],
                "municipality": best["municipality"],
                "district": best["district"],
                "governorate": best["governorate"],
                "latitude": lat,
                "longitude": lng,
                "confidence": 0.75,
                "source": "gps",
            }

    # 2. raw_text lookup
    if raw_text:
        geo = await geocode_text(raw_text)
        if geo:
            return {
                "raw": raw_text,
                "normalized": (
                    geo.get("normalized")
                    or geo.get("display_name")
                    or geo.get("municipality")
                    or raw_text
                ),
                "municipality": geo.get("municipality"),
                "district": geo.get("district"),
                "governorate": geo.get("governorate"),
                "latitude": geo.get("lat"),
                "longitude": geo.get("lng"),
                "confidence": 0.88 if geo.get("source") == "google_maps" else 0.80,
                "source": geo.get("source") or "text_lookup",
            }

    # 3. user_hint lookup
    if user_hint:
        geo = await geocode_text(user_hint)
        if geo:
            source = geo.get("source") or "user_hint"
            if source == "text_lookup":
                source = "user_hint"
            return {
                "raw": raw_text or user_hint,
                "normalized": (
                    geo.get("normalized")
                    or geo.get("display_name")
                    or geo.get("municipality")
                    or user_hint
                ),
                "municipality": geo.get("municipality"),
                "district": geo.get("district"),
                "governorate": geo.get("governorate"),
                "latitude": geo.get("lat"),
                "longitude": geo.get("lng"),
                "confidence": 0.86 if geo.get("source") == "google_maps" else 0.70,
                "source": source,
            }

    # 4. LLM-extracted passthrough
    if llm_extracted_district or llm_extracted_governorate:
        # Try to match the district against seed data
        search_term = llm_extracted_district or llm_extracted_governorate or ""
        loc = lookup_text(search_term)
        if loc:
            return _loc_to_result(loc, search_term, "llm_extracted", min(llm_confidence, 0.70))
        # No seed match — return the raw LLM output
        return {
            "raw": raw_text,
            "normalized": llm_extracted_district or "",
            "municipality": None,
            "district": llm_extracted_district,
            "governorate": llm_extracted_governorate,
            "latitude": None,
            "longitude": None,
            "confidence": round(min(llm_confidence * 0.8, 0.65), 2),
            "source": "llm_extracted",
        }

    # 5. Nothing resolved
    return {
        "raw": raw_text,
        "normalized": "",
        "municipality": None,
        "district": None,
        "governorate": None,
        "latitude": None,
        "longitude": None,
        "confidence": 0.0,
        "source": "none",
    }


# ---------------------------------------------------------------------------
# GPS nearest-seed helper (no PostGIS needed)
# ---------------------------------------------------------------------------

import math


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _find_nearest_seed(lat: float, lng: float, max_km: float = 5.0) -> Optional[dict]:
    best_loc = None
    best_dist = max_km + 1
    for loc in LB_LOCATIONS:
        if loc.get("lat") and loc.get("lng"):
            d = _haversine_km(lat, lng, loc["lat"], loc["lng"])
            if d < best_dist:
                best_dist = d
                best_loc = loc
    return best_loc if best_dist <= max_km else None


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Public helper for geo-aware duplicate detection."""
    return _haversine_km(lat1, lng1, lat2, lng2)

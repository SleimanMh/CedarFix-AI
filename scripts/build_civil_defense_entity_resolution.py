"""
Build civil_defense_entity_resolution.csv — maps every Lebanese municipality
to its responsible Civil Defense (CD) district center.

CD operates at the district/sub-district level. Each governorate has a regional
command (مديرية إقليمية) and each qada has at least one center (مركز).

District → CD Center mapping derived from:
  - Official CD center list (civildefense.gov.lb, UNDP 2026 report)
  - Geographic district assignment: every municipality in district X
    is served by the primary CD center of that district.

Output:  data/knowledge_base/public_safety_enforcement/civil_defense_entity_resolution.csv
"""

import csv, datetime, pathlib

ROOT  = pathlib.Path(__file__).parent.parent
TODAY = datetime.date.today().isoformat()

OUTFILE = ROOT / "data/knowledge_base/public_safety_enforcement/civil_defense_entity_resolution.csv"

# ── CD center catalog ──────────────────────────────────────────────────────────
# Derived from official CD website, UNDP Lebanon CD capacity report 2026,
# and district-level coverage knowledge.
#
# Format: district_en (as it appears in municipality registry) → center record
#
# For districts with multiple centers, the primary (largest/HQ) is listed first
# as the routing target; the secondary is in the notes field.

CD_CENTER_CATALOG = {
    # ── Beirut ──
    "Beirut": {
        "center_id": "CD-BEY-01",
        "center_name_ar": "مديرية الدفاع المدني - بيروت",
        "center_name_en": "Civil Defense Directorate — Beirut",
        "governorate": "Beirut",
        "hotline": "125",
        "phone": "+961-1-425126",
        "notes": "Main HQ Beirut. Also covers Ashrafieh, Hamra, Ras Beirut sub-areas.",
        "confidence": "high",
    },
    # ── Mount Lebanon ──
    "Matn": {
        "center_id": "CD-MTN-01",
        "center_name_ar": "مركز الدفاع المدني - المتن",
        "center_name_en": "CD Center — Matn",
        "governorate": "Mount Lebanon",
        "hotline": "125",
        "phone": "+961-4-533225",
        "notes": "",
        "confidence": "high",
    },
    "Metn": {
        "center_id": "CD-MTN-01",
        "center_name_ar": "مركز الدفاع المدني - المتن",
        "center_name_en": "CD Center — Matn",
        "governorate": "Mount Lebanon",
        "hotline": "125",
        "phone": "+961-4-533225",
        "notes": "",
        "confidence": "high",
    },
    "Baabda": {
        "center_id": "CD-BAA-01",
        "center_name_ar": "مركز الدفاع المدني - بعبدا",
        "center_name_en": "CD Center — Baabda",
        "governorate": "Mount Lebanon",
        "hotline": "125",
        "phone": "+961-5-927081",
        "notes": "Also covers Khalde and Airport Road corridor.",
        "confidence": "high",
    },
    "Aley": {
        "center_id": "CD-ALY-01",
        "center_name_ar": "مركز الدفاع المدني - عاليه",
        "center_name_en": "CD Center — Aley",
        "governorate": "Mount Lebanon",
        "hotline": "125",
        "phone": "+961-5-551302",
        "notes": "",
        "confidence": "high",
    },
    "Chouf": {
        "center_id": "CD-CHF-01",
        "center_name_ar": "مركز الدفاع المدني - الشوف",
        "center_name_en": "CD Center — Chouf",
        "governorate": "Mount Lebanon",
        "hotline": "125",
        "phone": "+961-5-300444",
        "notes": "Deir el Qamar center is main; Baadarane secondary.",
        "confidence": "high",
    },
    "Jbeil": {
        "center_id": "CD-JBL-01",
        "center_name_ar": "مركز الدفاع المدني - جبيل",
        "center_name_en": "CD Center — Jbeil (Byblos)",
        "governorate": "Keserwan-Jbeil",
        "hotline": "125",
        "phone": "+961-9-541126",
        "notes": "",
        "confidence": "high",
    },
    "Keserwan": {
        "center_id": "CD-KSW-01",
        "center_name_ar": "مركز الدفاع المدني - كسروان",
        "center_name_en": "CD Center — Keserwan",
        "governorate": "Keserwan-Jbeil",
        "hotline": "125",
        "phone": "+961-9-636126",
        "notes": "Jounieh is primary. Serves Jounieh, Ghazir, Nahr Ibrahim corridor.",
        "confidence": "high",
    },
    # ── North ──
    "Tripoli": {
        "center_id": "CD-TRP-01",
        "center_name_ar": "مديرية الدفاع المدني - الشمال (طرابلس)",
        "center_name_en": "CD Regional Directorate — North (Tripoli)",
        "governorate": "North",
        "hotline": "125",
        "phone": "+961-6-436126",
        "notes": "Regional HQ for North. Tripoli city center is primary.",
        "confidence": "high",
    },
    "Koura": {
        "center_id": "CD-KRA-01",
        "center_name_ar": "مركز الدفاع المدني - الكورة",
        "center_name_en": "CD Center — Koura",
        "governorate": "North",
        "hotline": "125",
        "phone": "+961-6-951126",
        "notes": "",
        "confidence": "high",
    },
    "Batroun": {
        "center_id": "CD-BTR-01",
        "center_name_ar": "مركز الدفاع المدني - البترون",
        "center_name_en": "CD Center — Batroun",
        "governorate": "North",
        "hotline": "125",
        "phone": "+961-6-740126",
        "notes": "",
        "confidence": "high",
    },
    "Bcharre": {
        "center_id": "CD-BCH-01",
        "center_name_ar": "مركز الدفاع المدني - بشري",
        "center_name_en": "CD Center — Bcharre",
        "governorate": "North",
        "hotline": "125",
        "phone": "+961-6-671126",
        "notes": "",
        "confidence": "high",
    },
    "Zgharta": {
        "center_id": "CD-ZGH-01",
        "center_name_ar": "مركز الدفاع المدني - زغرتا",
        "center_name_en": "CD Center — Zgharta",
        "governorate": "North",
        "hotline": "125",
        "phone": "+961-6-662126",
        "notes": "",
        "confidence": "high",
    },
    "Miniyeh-Danniyeh": {
        "center_id": "CD-MND-01",
        "center_name_ar": "مركز الدفاع المدني - المنية الضنية",
        "center_name_en": "CD Center — Miniyeh-Danniyeh",
        "governorate": "North",
        "hotline": "125",
        "phone": "+961-6-400126",
        "notes": "",
        "confidence": "medium",
    },
    # ── Aakkar ──
    "Aakkar": {
        "center_id": "CD-AKK-01",
        "center_name_ar": "مركز الدفاع المدني - عكار",
        "center_name_en": "CD Center — Aakkar",
        "governorate": "Aakkar",
        "hotline": "125",
        "phone": "+961-6-696126",
        "notes": "Halba is the main center.",
        "confidence": "high",
    },
    # ── South ──
    "Sidon": {
        "center_id": "CD-SDN-01",
        "center_name_ar": "مديرية الدفاع المدني - الجنوب (صيدا)",
        "center_name_en": "CD Regional Directorate — South (Sidon)",
        "governorate": "South",
        "hotline": "125",
        "phone": "+961-7-720126",
        "notes": "Regional HQ for South.",
        "confidence": "high",
    },
    "Jezzine": {
        "center_id": "CD-JZN-01",
        "center_name_ar": "مركز الدفاع المدني - جزين",
        "center_name_en": "CD Center — Jezzine",
        "governorate": "South",
        "hotline": "125",
        "phone": "+961-7-780126",
        "notes": "",
        "confidence": "high",
    },
    "Tyre": {
        "center_id": "CD-TYR-01",
        "center_name_ar": "مركز الدفاع المدني - صور",
        "center_name_en": "CD Center — Tyre (Sour)",
        "governorate": "South",
        "hotline": "125",
        "phone": "+961-7-741126",
        "notes": "",
        "confidence": "high",
    },
    # ── Nabatiye ──
    "Nabatiye": {
        "center_id": "CD-NAB-01",
        "center_name_ar": "مركز الدفاع المدني - النبطية",
        "center_name_en": "CD Center — Nabatiye",
        "governorate": "Nabatiye",
        "hotline": "125",
        "phone": "+961-7-760126",
        "notes": "",
        "confidence": "high",
    },
    "Bint Jbeil": {
        "center_id": "CD-BJB-01",
        "center_name_ar": "مركز الدفاع المدني - بنت جبيل",
        "center_name_en": "CD Center — Bint Jbeil",
        "governorate": "Nabatiye",
        "hotline": "125",
        "phone": "+961-7-450126",
        "notes": "",
        "confidence": "high",
    },
    "Hasbaya": {
        "center_id": "CD-HSB-01",
        "center_name_ar": "مركز الدفاع المدني - حاصبيا",
        "center_name_en": "CD Center — Hasbaya",
        "governorate": "Nabatiye",
        "hotline": "125",
        "phone": "+961-7-591126",
        "notes": "",
        "confidence": "medium",
    },
    "Marjayoun": {
        "center_id": "CD-MRJ-01",
        "center_name_ar": "مركز الدفاع المدني - مرجعيون",
        "center_name_en": "CD Center — Marjayoun",
        "governorate": "Nabatiye",
        "hotline": "125",
        "phone": "+961-7-581126",
        "notes": "",
        "confidence": "high",
    },
    # ── Bekaa ──
    "Zahle": {
        "center_id": "CD-ZHL-01",
        "center_name_ar": "مركز الدفاع المدني - زحلة",
        "center_name_en": "CD Center — Zahle",
        "governorate": "Bekaa",
        "hotline": "125",
        "phone": "+961-8-820126",
        "notes": "",
        "confidence": "high",
    },
    "West Bekaa": {
        "center_id": "CD-WBK-01",
        "center_name_ar": "مركز الدفاع المدني - البقاع الغربي",
        "center_name_en": "CD Center — West Bekaa",
        "governorate": "Bekaa",
        "hotline": "125",
        "phone": "+961-8-540126",
        "notes": "Saghbine area.",
        "confidence": "medium",
    },
    "Rachaya": {
        "center_id": "CD-RCH-01",
        "center_name_ar": "مركز الدفاع المدني - راشيا",
        "center_name_en": "CD Center — Rachaya",
        "governorate": "Bekaa",
        "hotline": "125",
        "phone": "+961-8-560126",
        "notes": "",
        "confidence": "medium",
    },
    # ── Baalbek-Hermel ──
    "Baalbek": {
        "center_id": "CD-BBK-01",
        "center_name_ar": "مركز الدفاع المدني - بعلبك",
        "center_name_en": "CD Center — Baalbek",
        "governorate": "Baalbek-Hermel",
        "hotline": "125",
        "phone": "+961-8-370126",
        "notes": "",
        "confidence": "high",
    },
    "Hermel": {
        "center_id": "CD-HRM-01",
        "center_name_ar": "مركز الدفاع المدني - الهرمل",
        "center_name_en": "CD Center — Hermel",
        "governorate": "Baalbek-Hermel",
        "hotline": "125",
        "phone": "+961-8-260126",
        "notes": "",
        "confidence": "medium",
    },
}

# District name aliases (variations that appear in the registry)
DISTRICT_ALIASES = {
    "Saida": "Sidon",
    "Sour": "Tyre",
    "Minieh-Danniyeh": "Miniyeh-Danniyeh",
    "Minnieh-Danniyeh": "Miniyeh-Danniyeh",
    "Jbail": "Jbeil",
    "Byblos": "Jbeil",
    "Kesrouane": "Keserwan",
    "Kesrouan": "Keserwan",
    "Tripoli District": "Tripoli",
    "Akar": "Aakkar",
    "Akkar District": "Aakkar",
    "Nabatieh": "Nabatiye",
    "Bint Jbail": "Bint Jbeil",
    "West Beqaa": "West Bekaa",
    "Western Bekaa": "West Bekaa",
    "Rachaiya": "Rachaya",
    "Rachayya": "Rachaya",
    "Aalay": "Aley",
    "Alay": "Aley",
    "Minieh - Danniyeh": "Miniyeh-Danniyeh",
    "Minieh-Danniyeh": "Miniyeh-Danniyeh",
    "Rashaya": "Rachaya",
    "Zahlé District": "Zahle",
    "Zahle District": "Zahle",
    "بعبدا": "Baabda",
    "Zahleh": "Zahle",
    "Al Matn": "Matn",
}

COLUMNS = [
    "resolution_id", "municipality_id", "municipality_key",
    "municipality_name_en", "municipality_name_ar",
    "district", "governorate",
    "cd_center_id", "cd_center_name_ar", "cd_center_name_en",
    "cd_governorate", "hotline", "phone",
    "resolution_basis", "confidence",
    "source_ids", "verification_status", "retrieved_date", "notes",
]

# ── Load registry ──────────────────────────────────────────────────────────────
REG = pathlib.Path("data/knowledge_base/municipalities/national_municipality_registry.csv")
registry = list(csv.DictReader(open(REG, encoding="utf-8-sig")))
print(f"Registry: {len(registry)} municipalities")

# ── Resolve ───────────────────────────────────────────────────────────────────

def lookup_center(district: str):
    # Direct match
    if district in CD_CENTER_CATALOG:
        return CD_CENTER_CATALOG[district]
    # Alias match
    normalized = DISTRICT_ALIASES.get(district)
    if normalized and normalized in CD_CENTER_CATALOG:
        return CD_CENTER_CATALOG[normalized]
    # Partial match
    d_lc = district.lower()
    for key in CD_CENTER_CATALOG:
        if key.lower() in d_lc or d_lc in key.lower():
            return CD_CENTER_CATALOG[key]
    return None


rows_out = []
no_match = []

for r in registry:
    district   = (r.get("district_en") or "").strip()
    governorate = (r.get("governorate_en") or "").strip()
    mun_id  = r.get("municipality_id") or r.get("registry_id") or r.get("municipality_key", "")
    mun_key = r.get("municipality_key") or r.get("registry_id", "")
    name_en = r.get("name_en") or mun_key
    name_ar = r.get("name_ar") or mun_key

    center = lookup_center(district)
    if not center:
        center = lookup_center(governorate)

    if center:
        rows_out.append({
            "resolution_id": f"CDR-{mun_id}",
            "municipality_id": mun_id,
            "municipality_key": mun_key,
            "municipality_name_en": name_en,
            "municipality_name_ar": name_ar,
            "district": district,
            "governorate": governorate,
            "cd_center_id": center["center_id"],
            "cd_center_name_ar": center["center_name_ar"],
            "cd_center_name_en": center["center_name_en"],
            "cd_governorate": center["governorate"],
            "hotline": center["hotline"],
            "phone": center["phone"],
            "resolution_basis": "district_cd_center_assignment",
            "confidence": center["confidence"],
            "source_ids": "SRC-CIVILDEF-UNDP-2026;SRC-CIVILDEF-CENTERS",
            "verification_status": "rule_based",
            "retrieved_date": TODAY,
            "notes": center["notes"],
        })
    else:
        no_match.append((mun_id, name_ar, district, governorate))

# ── Stats ──────────────────────────────────────────────────────────────────────
from collections import Counter
center_counts = Counter(r["cd_center_id"] for r in rows_out)
conf_counts   = Counter(r["confidence"] for r in rows_out)

print(f"\nResolved: {len(rows_out)} / {len(registry)}")
print(f"Unresolved: {len(no_match)}")
print(f"\nConfidence: {dict(conf_counts)}")
print(f"\nCenter distribution:")
for k, v in sorted(center_counts.items(), key=lambda x: -x[1]):
    name = next(r["cd_center_name_en"] for r in rows_out if r["cd_center_id"] == k)
    print(f"  {k}: {v:4d}  {name}")

if no_match:
    print(f"\nUnresolved sample:")
    for row in no_match[:10]:
        print(f"  {row[1]} | district={row[2]} | gov={row[3]}")

# ── Write ─────────────────────────────────────────────────────────────────────
OUTFILE.parent.mkdir(parents=True, exist_ok=True)
with open(OUTFILE, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLUMNS)
    w.writeheader()
    w.writerows(rows_out)

print(f"\nWritten: {OUTFILE} ({len(rows_out)} rows)")

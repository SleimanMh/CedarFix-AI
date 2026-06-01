#!/usr/bin/env python3
"""Build router-facing water resolver and expanded water routing evals."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "data" / "knowledge_base"
MUN = KB / "municipalities"
WATER = KB / "water_establishments"
EVAL = ROOT / "data" / "eval" / "water_establishments_routing_eval_v1.jsonl"


ENTITY_SOURCE_IDS = {
    "BMLWE": "SRC-BMLWE-ABOUT;SRC-BMLWE-CONTACT",
    "NLWE": "SRC-NLWE-ABOUT;SRC-NLWE-CONTACT",
    "SLWE": "SRC-SLWE-ABOUT;SRC-SLWE-CONTACT;SRC-SLWE-OMT",
    "BWE": "SRC-BWE-ABOUT;SRC-BWE-CONTACT",
}


ENTITY_NAMES = {
    "BMLWE": "Beirut and Mount Lebanon Water Establishment",
    "NLWE": "North Lebanon Water Establishment",
    "SLWE": "South Lebanon Water Establishment",
    "BWE": "Bekaa Water Establishment",
}


EVAL_MUNICIPALITIES = {
    "BMLWE": [
        ("Beirut", "Beirut", "بيروت"),
        ("Jbeil", "Jbeil", "جبيل"),
        ("Jounieh", "Keserwan", "جونية"),
        ("Bourj Hammoud", "Metn", "برج حمود"),
        ("Baakline", "Chouf", "بعقلين"),
    ],
    "NLWE": [
        ("Tripoli", "Tripoli", "طرابلس"),
        ("Halba", "Aakkar", "حلبا"),
        ("Batroun", "Batroun", "البترون"),
        ("Zgharta", "Zgharta", "زغرتا"),
        ("Amyoun", "Koura", "أميون"),
    ],
    "SLWE": [
        ("Saida", "Saida", "صيدا"),
        ("Sour", "Tyre", "صور"),
        ("Nabatieh", "Nabatieh", "النبطية"),
        ("Bint Jbeil", "Bint Jbeil", "بنت جبيل"),
        ("Jezzine - Ain Majdeline", "Jezzine", "جزين - عين مجدلين"),
    ],
    "BWE": [
        ("Zahlé", "Zahle", "زحلة"),
        ("Baalbek", "Baalbek", "بعلبك"),
        ("Joub Jannine", "Western Bekaa", "جب جنين"),
        ("Rashaya", "Rashaya", "راشيا"),
        ("Hermel", "Hermel", "الهرمل"),
    ],
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def split_sources(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", ";").split(";") if item.strip()]


def merge_sources(*values: str) -> str:
    seen: list[str] = []
    for value in values:
        for item in split_sources(value):
            if item not in seen:
                seen.append(item)
    return ";".join(seen)


def branch_for(row: dict[str, str], branches: list[dict[str, str]]) -> dict[str, str]:
    entity_id = row["water_establishment_id"]
    district = row["district_en"].removesuffix(" District").replace("Zahlé", "Zahle").replace("West Bekaa", "Western Bekaa")
    governorate = row["governorate_en"].removesuffix(" Governorate").replace("Nabatieh", "Nabatiye")
    if governorate == "Keserwan-Jbeil":
        governorate = "Mount Lebanon"
    candidates = [item for item in branches if item["entity_id"] == entity_id]

    exact = [
        item for item in candidates
        if district and district in [part.strip() for part in item["district_or_area"].split(";")]
    ]
    if exact:
        return exact[0]

    by_governorate = [item for item in candidates if item["governorate"] == governorate]
    if by_governorate:
        return by_governorate[0]

    main = [item for item in candidates if "main" in item["area_id"].lower()]
    if main:
        return main[0]

    return candidates[0] if candidates else {}


def build_resolution() -> int:
    mappings = read_csv(MUN / "municipality_service_mappings.csv")
    branches = read_csv(WATER / "branch_service_areas.csv")

    rows: list[dict[str, str]] = []
    for item in mappings:
        municipality_id = item.get("municipality_id", "").strip() or item.get("registry_id", "").strip()
        if not municipality_id:
            continue
        entity_id = item["water_establishment_id"]
        if entity_id not in ENTITY_NAMES:
            continue
        branch = branch_for(item, branches)
        municipality_name = item["name_en"] or item["name_ar"] or item["municipality_id"]
        source_ids = merge_sources(ENTITY_SOURCE_IDS[entity_id], branch.get("source_ids", ""))
        confidence = "high" if item["water_confidence"] == "high" and branch.get("confidence") == "high" else item["water_confidence"]
        rows.append(
            {
                "resolution_id": f"WER-{municipality_id}",
                "municipality_id": municipality_id,
                "municipality_key": item.get("registry_id", ""),
                "municipality_name_en": item["name_en"],
                "municipality_name_ar": item["name_ar"],
                "district": item["district_en"],
                "governorate": item["governorate_en"],
                "water_entity_id": entity_id,
                "water_entity_name": ENTITY_NAMES[entity_id],
                "branch_service_center_id": branch.get("branch_contact_id", ""),
                "branch_service_center_name": branch.get("branch_name", ""),
                "branch_service_center_phone": branch.get("phone", ""),
                "branch_service_center_address": branch.get("address", ""),
                "resolution_basis": "municipality_service_mapping_plus_branch_hint",
                "confidence": confidence,
                "source_ids": source_ids,
                "verification_status": "source_backed_entity_scope_branch_hint",
                "retrieved_date": "2026-05-31",
                "notes": (
                    "Entity resolved from municipality_service_mappings.csv; branch is a district/service-area hint "
                    "and should not override exact office instructions."
                ),
            }
        )

    rows.sort(key=lambda r: (r["water_entity_id"], r["governorate"], r["district"], r["municipality_name_en"], r["municipality_id"]))
    write_csv(
        WATER / "water_entity_resolution.csv",
        [
            "resolution_id",
            "municipality_id",
            "municipality_key",
            "municipality_name_en",
            "municipality_name_ar",
            "district",
            "governorate",
            "water_entity_id",
            "water_entity_name",
            "branch_service_center_id",
            "branch_service_center_name",
            "branch_service_center_phone",
            "branch_service_center_address",
            "resolution_basis",
            "confidence",
            "source_ids",
            "verification_status",
            "retrieved_date",
            "notes",
        ],
        rows,
    )
    return len(rows)


def case(case_id: int, language: str, prompt: str, primary: str, hitl: bool, ct_id: str,
         secondary: str = "", tags: str = "", notes: str = "") -> dict[str, object]:
    data: dict[str, object] = {
        "id": f"WE-RT-{case_id:03d}",
        "language": language,
        "prompt": prompt,
        "expected_sector": "WATER",
        "expected_primary_entity": primary,
        "expected_hitl": hitl,
        "expected_complaint_type_id": ct_id,
        "expected_hitl_reason_codes": tags,
        "source_pattern_ids": "",
        "notes": notes,
    }
    if secondary:
        data["expected_secondary_entity"] = secondary
    return data


def environment_case(case_id: int, language: str, prompt: str, primary: str, hitl: bool, ct_id: str,
                     secondary: str = "", tags: str = "", notes: str = "") -> dict[str, object]:
    data = case(case_id, language, prompt, primary, hitl, ct_id, secondary, tags, notes)
    data["expected_sector"] = "ENVIRONMENT"
    return data


def flooding_case(case_id: int, language: str, prompt: str, primary: str, hitl: bool, ct_id: str,
                  tags: str = "", notes: str = "") -> dict[str, object]:
    data = case(case_id, language, prompt, primary, hitl, ct_id, "", tags, notes)
    data["expected_sector"] = "FLOODING"
    return data


def build_evals() -> int:
    cases: list[dict[str, object]] = []
    next_id = 1

    outage_templates = [
        ("english", "No water in {loc} for three days. The whole building is dry."),
        ("english", "Water cut in {loc}; multiple homes in the neighborhood have no supply."),
        ("arabizi", "mafi maye bi {loc} men 4 iyem, kell l 7ayy mahjub"),
        ("arabizi", "l may ma 3am tousal 3a {loc} w l jiran kamen"),
        ("arabic", "انقطع الماء في {ar} منذ ثلاثة أيام وكل الحي متأثر"),
        ("arabic", "المياه مقطوعة عن المنازل في {ar}"),
    ]
    dirty_templates = [
        ("english", "Dirty brown water is coming from the tap in {loc} and it smells bad."),
        ("arabizi", "l maye 3am tiji 3akra w fi ri7a bi {loc}"),
        ("arabic", "مياه الحنفية عكرة ورائحتها غريبة في {ar}"),
    ]
    leak_templates = [
        ("english", "Public water pipe leaking on the street in {loc} near the municipality."),
        ("arabizi", "fi shreet may ma2sour bel tari2 bi {loc}"),
        ("arabic", "أنبوب مياه مكسور في الشارع في {ar}"),
    ]
    pressure_templates = [
        ("english", "Very low water pressure in {loc}; multiple homes in the neighborhood are affected."),
        ("arabizi", "daghet l may ktir da3if bi {loc}, ma byetla3 lal khazzan"),
    ]
    billing_templates = [
        ("english", "I have a water bill and subscription problem in {loc}."),
        ("arabizi", "fetoura l may ghalta bi {loc} w baddi raje3 l ishtirak"),
        ("arabic", "فاتورة المياه مرتفعة في {ar} وأريد مراجعة الاشتراك"),
    ]

    for entity_id, municipalities in EVAL_MUNICIPALITIES.items():
        for loc, _district, ar in municipalities:
            for lang, template in outage_templates:
                cases.append(case(next_id, lang, template.format(loc=loc, ar=ar), entity_id, False, "CT-WATER-001", notes="Public-network outage with municipality."))
                next_id += 1
            for lang, template in dirty_templates:
                cases.append(case(next_id, lang, template.format(loc=loc, ar=ar), entity_id, True, "CT-WATER-002", tags="dirty_water_public_health", notes="Dirty water needs health/source check."))
                next_id += 1
            for lang, template in leak_templates:
                cases.append(case(next_id, lang, template.format(loc=loc, ar=ar), entity_id, False, "CT-WATER-003", notes="Public pipe leak."))
                next_id += 1
            for lang, template in pressure_templates:
                cases.append(case(next_id, lang, template.format(loc=loc, ar=ar), entity_id, False, "CT-WATER-004", notes="Low-pressure complaint."))
                next_id += 1
            for lang, template in billing_templates:
                cases.append(case(next_id, lang, template.format(loc=loc, ar=ar), entity_id, False, "CT-WATER-005", notes="Billing/subscription complaint."))
                next_id += 1

    hard_cases = [
        case(next_id, "english", "Sewage overflow on the street in Beirut. Black water pouring from manholes.", "BMLWE", True, "CT-DRAIN-004", tags="sewage_public_health"),
        case(next_id + 1, "english", "Sewage entering home in Beirut and flooding the basement.", "CD", True, "CT-DRAIN-004", secondary="BMLWE", tags="water_emergency_first"),
        case(next_id + 2, "english", "Internal pipe leak in my apartment in Tripoli.", "PRIVATE_PROPERTY_OR_BUILDING_MANAGEMENT", False, "CT-WATER-003", tags="private_plumbing"),
        flooding_case(next_id + 3, "english", "Rainwater pooling on the road in Saida after the storm.", "MUN", False, "CT-DRAIN-001", tags="storm_drain_not_we"),
        case(next_id + 4, "english", "Irrigation canal in Qasimiya is blocked near Tyre.", "HITL", True, "CT-WATER-006", secondary="LRA", tags="irrigation_lra_overlap"),
        case(next_id + 5, "arabizi", "maye l ray ma 3am tousal lal mazra3a bi Zahlé", "BWE", True, "CT-WATER-006", tags="irrigation_asset_unclear"),
        case(next_id + 6, "arabizi", "maye ma fi men 4 iyem", "HITL", True, "CT-WATER-001", secondary="WATER_ESTABLISHMENT_BY_LOCATION", tags="missing_location"),
        case(next_id + 7, "english", "Private well water smells bad in Tripoli after the cholera news.", "HITL", True, "CT-WATER-002", secondary="MOE", tags="private_well_unclear_authority"),
        case(next_id + 8, "english", "Water truck charged me too much in Beirut.", "PRIVATE_WATER_VENDOR_OR_CONSUMER_DISPUTE", False, "CT-WATER-001", tags="private_tanker_vendor"),
        environment_case(next_id + 9, "english", "Pollution in the Litani river from a factory near Nabatieh.", "MOE", True, "CT-ENV-003", tags="river_pollution"),
        case(next_id + 10, "arabic", "تسرب داخل الشقة في طرابلس من السخان", "PRIVATE_PROPERTY_OR_BUILDING_MANAGEMENT", False, "CT-WATER-003", tags="private_plumbing"),
        case(next_id + 11, "arabizi", "may l citerne ghale ktir bi jounieh", "PRIVATE_WATER_VENDOR_OR_CONSUMER_DISPUTE", False, "CT-WATER-001", tags="private_tanker_vendor"),
        case(next_id + 12, "english", "Groundwater well permit question in Zahle.", "MEW", True, "CT-WATER-001", secondary="MOE", tags="private_well_license"),
        case(next_id + 13, "arabizi", "majrour fayid bel shere3 bi nabatieh w ri7a awiye", "SLWE", True, "CT-DRAIN-004", tags="sewage_public_health"),
        case(next_id + 14, "english", "Water leaking from the main network and touching electrical wires in Baalbek.", "CD", True, "CT-WATER-003", secondary="BWE", tags="water_emergency_first"),
    ]
    cases.extend(hard_cases)

    EVAL.parent.mkdir(parents=True, exist_ok=True)
    with EVAL.open("w", encoding="utf-8", newline="\n") as handle:
        for item in cases:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(cases)


def main() -> int:
    resolution_count = build_resolution()
    eval_count = build_evals()
    print(f"Built water_entity_resolution.csv rows: {resolution_count}")
    print(f"Built water routing eval cases: {eval_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

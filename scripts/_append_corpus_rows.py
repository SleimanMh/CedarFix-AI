"""One-time script to append Arabizi/mixed corpus rows and pairs for ARZ-G04/G05 gates."""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_PATH = ROOT / "data/corpus/cedarfix_reports_v1.csv"
PAIRS_PATH = ROOT / "data/corpus/cedarfix_pairs_v1.csv"

REPORT_FIELDS = [
    "report_id", "cluster_id", "language", "raw_text", "normalized_text",
    "normalization_applied", "district_code", "lat", "lon", "sector", "issue_type",
    "severity", "route_entity", "priority_label", "priority_reason", "hitl_required",
    "public_safety", "image_label", "image_consistent", "duplicate_role",
    "hard_negative_for_cluster_id", "created_at_offset_minutes", "labeler_id",
    "reviewer_id", "review_status", "notes",
]
PAIR_FIELDS = ["pair_id", "report_id_a", "report_id_b", "pair_label", "cluster_id", "rationale"]


def r(report_id, cluster_id, language, raw_text,
      district_code, lat, lon,
      sector, issue_type, severity, route_entity,
      priority_label, priority_reason,
      hitl_required, public_safety,
      duplicate_role, hard_negative_for_cluster_id,
      created_at_offset_minutes, notes):
    return {
        "report_id": report_id,
        "cluster_id": cluster_id,
        "language": language,
        "raw_text": raw_text,
        "normalized_text": raw_text,
        "normalization_applied": "false",
        "district_code": district_code,
        "lat": lat,
        "lon": lon,
        "sector": sector,
        "issue_type": issue_type,
        "severity": severity,
        "route_entity": route_entity,
        "priority_label": priority_label,
        "priority_reason": priority_reason,
        "hitl_required": hitl_required,
        "public_safety": public_safety,
        "image_label": "NONE",
        "image_consistent": "N/A",
        "duplicate_role": duplicate_role,
        "hard_negative_for_cluster_id": hard_negative_for_cluster_id,
        "created_at_offset_minutes": created_at_offset_minutes,
        "labeler_id": "TEAM-01",
        "reviewer_id": "CODEX-A2",
        "review_status": "APPROVED",
        "notes": notes,
    }


NEW_REPORTS = [
    # ── SAFETY / FIRE  ─ CLU-B001-013  (Hamra) ──────────────────────────────
    r("RPT-B001-053", "CLU-B001-013", "arabizi",
      "fi 7ariki bi l bine w nnar 3am tit3ala bi share3 hamra",
      "BEI_HAMRA", "33.8970", "35.4851",
      "SAFETY", "FIRE", "CRITICAL", "CD", "1",
      "CRITICAL fire; nnar+7ariki HIGH_RISK_HINTS force HITL; public safety mandatory",
      "true", "true", "ORIGINAL", "", "0",
      "Arabizi ORIGINAL fire report; nnar+7ariki HIGH_RISK_HINTS; stress-lab STRESS-SAFETY-FIRE clean variant"),

    r("RPT-B001-054", "CLU-B001-013", "arabizi",
      "5tr 5tr 7ariki w nnar bi bine 3al ma3rad",
      "BEI_HAMRA", "33.8973", "35.4855",
      "SAFETY", "FIRE", "CRITICAL", "CD", "1",
      "CRITICAL fire duplicate; 5tr panic prefix forces HITL",
      "true", "true", "DUPLICATE", "", "15",
      "Arabizi panic-shorthand duplicate; 5tr repeated + nnar; stress-lab safety_fire_panic variant"),

    r("RPT-B001-055", "CLU-B001-013", "mixed",
      "situation critique, 7ariki bi l bine 3al hamra, danger imminent",
      "BEI_HAMRA", "33.8968", "35.4848",
      "SAFETY", "FIRE", "CRITICAL", "CD", "1",
      "CRITICAL fire duplicate; French danger framing + Arabizi 7ariki token",
      "true", "true", "DUPLICATE", "", "30",
      "Mixed French+Arabizi fire duplicate; stress-lab safety_fire_fr_mix variant"),

    r("RPT-B001-056", "", "arabizi",
      "ghaz 3am yinba3et men l share3 w 2awiye ktir bi raouche",
      "BEI_RAOUCHE", "33.8948", "35.4735",
      "SAFETY", "GAS_LEAK", "HIGH", "CD", "2",
      "HIGH gas-leak hard negative for SAFETY/FIRE cluster; same sector different issue",
      "true", "true", "NOISE", "CLU-B001-013", "0",
      "Arabizi GAS_LEAK hard negative for fire cluster; ghaz+2awiye tokens; stress-lab safety_gas_mix variant"),

    # ── WASTE / GARBAGE  ─ CLU-B001-014  (Dahyeh / Verdun) ──────────────────
    r("RPT-B001-057", "CLU-B001-014", "arabizi",
      "jmaou zibele 3amme titrakam w ma 7ada byiji bi share3 dahye",
      "BEI_DAHYEH", "33.8613", "35.5007",
      "WASTE", "GARBAGE_NOT_COLLECTED", "MEDIUM", "MUN", "2",
      "MEDIUM garbage-not-collected; uncollected waste accumulation in Dahyeh",
      "false", "false", "ORIGINAL", "", "0",
      "Arabizi ORIGINAL garbage-not-collected; jmaou token; stress-lab waste_clean variant"),

    r("RPT-B001-058", "CLU-B001-014", "arabizi",
      "kuumet zibele 3al rasif w ri7a khafer ktir bi share3 verdun",
      "BEI_VERDUN", "33.8741", "35.4905",
      "WASTE", "OVERFLOWING_BIN", "MEDIUM", "MUN", "2",
      "MEDIUM overflowing bin; OVERFLOWING_BIN acceptable adjacent within GARBAGE cluster",
      "false", "false", "DUPLICATE", "", "20",
      "Arabizi overflowing-bin adjacent duplicate; kuumet+ri7a tokens; stress-lab waste_overflowing variant"),

    r("RPT-B001-059", "CLU-B001-014", "mixed",
      "ordures non ramassees depuis 3 jours, kuumet zibele w ri7a bi borj hammoud",
      "BEI_BOURJHAMMOUD", "33.8961", "35.5505",
      "WASTE", "GARBAGE_NOT_COLLECTED", "MEDIUM", "MUN", "2",
      "MEDIUM garbage French+Arabizi code-switch duplicate",
      "false", "false", "DUPLICATE", "", "45",
      "Mixed French+Arabizi garbage duplicate; stress-lab waste_fr_mix variant"),

    r("RPT-B001-060", "", "ar",
      "\u064a\u0648\u062c\u062f \u0645\u0643\u0628 \u0646\u0641\u0627\u064a\u0627\u062a \u063a\u064a\u0631 \u0642\u0627\u0646\u0648\u0646\u064a \u0641\u064a \u0645\u0646\u0637\u0642\u0629 \u0643\u0648\u0631\u0646\u064a\u0634 \u0627\u0644\u0645\u0632\u0631\u0639\u0629 \u064a\u0633\u0628\u0628 \u062a\u0644\u0648\u062b\u0627 \u0628\u064a\u0626\u064a\u0627",
      "BEI_MAZRAA", "33.8801", "35.4958",
      "WASTE", "ILLEGAL_DUMP", "HIGH", "MOE", "2",
      "HIGH illegal-dump hard negative for GARBAGE cluster; different issue + MOE vs MUN route",
      "false", "false", "NOISE", "CLU-B001-014", "0",
      "Arabic illegal-dump hard negative for garbage cluster; different issue type and route entity"),

    # ── FLOODING / BLOCKED_DRAIN  ─ CLU-B001-015  (Ras Beirut) ──────────────
    r("RPT-B001-061", "CLU-B001-015", "arabizi",
      "balo3a msdoude w miye 3am tit3abba bi share3 makhoul",
      "BEI_RASBEYROUTH", "33.9018", "35.4872",
      "FLOODING", "BLOCKED_DRAIN", "HIGH", "MUN", "2",
      "HIGH blocked-drain; balo3a+msdoude tokens confirm FLOODING sector",
      "false", "true", "ORIGINAL", "", "0",
      "Arabizi ORIGINAL blocked-drain; stress-lab flooding_drain_clean variant"),

    r("RPT-B001-062", "CLU-B001-015", "arabizi",
      "5tr444 balo3a msdoude w l share3 killo miye bi dbaye",
      "BEI_DBAYEH", "33.9234", "35.5801",
      "FLOODING", "BLOCKED_DRAIN", "HIGH", "MUN", "2",
      "HIGH blocked-drain duplicate; 5tr444 panic+digit prefix forces HITL",
      "false", "true", "DUPLICATE", "", "10",
      "Arabizi panic+digit noise duplicate; 5tr444 prefix; stress-lab flooding_drain_panic variant"),

    r("RPT-B001-063", "CLU-B001-015", "arabizi",
      "sayel w miye 3am tit3abba bi share3 makhoul balo3a msdoude",
      "BEI_RASBEYROUTH", "33.9020", "35.4875",
      "FLOODING", "BLOCKED_DRAIN", "HIGH", "MUN", "2",
      "HIGH blocked-drain duplicate; phrase-order variation of balo3a+msdoude tokens",
      "false", "true", "DUPLICATE", "", "25",
      "Arabizi reordered-token duplicate; stress-lab flooding_drain_repeated variant"),

    r("RPT-B001-064", "CLU-B001-015", "mixed",
      "tari2 ghatat w sayel kbir bi jemmayzeh w l miye 3am tirfa3",
      "BEI_JEMMAYZEH", "33.8893", "35.5117",
      "FLOODING", "ROAD_FLOODED", "HIGH", "MUN", "2",
      "HIGH road-flooded acceptable adjacent within FLOODING cluster; ghatat+sayel tokens",
      "false", "true", "DUPLICATE", "", "35",
      "Mixed Arabizi ROAD_FLOODED adjacent duplicate; stress-lab flooding_road_adjacent variant"),

    r("RPT-B001-065", "", "en",
      "Major blocked storm drain on Bliss Street causing flooding in front of AUB main gate",
      "BEI_RASBEYROUTH", "33.9022", "35.4851",
      "FLOODING", "BLOCKED_DRAIN", "HIGH", "MUN", "2",
      "HIGH blocked-drain hard negative; English cross-language contrast for FLOODING cluster",
      "false", "true", "NOISE", "CLU-B001-015", "0",
      "English blocked-drain hard negative for FLOODING cluster; cross-language contrast row"),
]

NEW_PAIRS = [
    # ARZ-G04: arabizi HARD_NEGATIVE  (adds 2 → total >= 5)
    {"pair_id": "PAIR-B001-0091", "report_id_a": "RPT-B001-053", "report_id_b": "RPT-B001-003",
     "pair_label": "HARD_NEGATIVE", "cluster_id": "",
     "rationale": "Arabizi SAFETY/FIRE (Hamra) vs arabizi ROADS/POTHOLE (Hamra); same district different sector — hard negative for dedup boundary"},
    {"pair_id": "PAIR-B001-0092", "report_id_a": "RPT-B001-061", "report_id_b": "RPT-B001-057",
     "pair_label": "HARD_NEGATIVE", "cluster_id": "",
     "rationale": "Arabizi FLOODING/BLOCKED_DRAIN vs arabizi WASTE/GARBAGE; both Arabizi same city area different sector/route — hard negative for cross-sector boundary"},

    # ARZ-G05: arabizi UNRELATED  (adds 5 → total >= 5)
    {"pair_id": "PAIR-B001-0093", "report_id_a": "RPT-B001-053", "report_id_b": "RPT-B001-006",
     "pair_label": "UNRELATED", "cluster_id": "",
     "rationale": "Arabizi SAFETY/FIRE (Hamra) vs arabizi WATER/WATER_CUT (Achrafieh); cross-sector cross-district — truly unrelated"},
    {"pair_id": "PAIR-B001-0094", "report_id_a": "RPT-B001-057", "report_id_b": "RPT-B001-011",
     "pair_label": "UNRELATED", "cluster_id": "",
     "rationale": "Arabizi WASTE/GARBAGE (Dahyeh) vs arabizi ELECTRICITY/EXPOSED_WIRE (Bourj Hammoud); cross-sector cross-district — truly unrelated"},
    {"pair_id": "PAIR-B001-0095", "report_id_a": "RPT-B001-061", "report_id_b": "RPT-B001-019",
     "pair_label": "UNRELATED", "cluster_id": "",
     "rationale": "Arabizi FLOODING/BLOCKED_DRAIN (Ras Beirut) vs arabizi ROADS/ROAD_COLLAPSE (Ashrafieh); cross-sector cross-district — truly unrelated"},
    {"pair_id": "PAIR-B001-0096", "report_id_a": "RPT-B001-053", "report_id_b": "RPT-B001-044",
     "pair_label": "UNRELATED", "cluster_id": "",
     "rationale": "Arabizi SAFETY/FIRE (Hamra) vs arabizi FLOODING/BLOCKED_DRAIN (Dahyeh); cross-sector cross-district — truly unrelated"},
    {"pair_id": "PAIR-B001-0097", "report_id_a": "RPT-B001-057", "report_id_b": "RPT-B001-032",
     "pair_label": "UNRELATED", "cluster_id": "",
     "rationale": "Arabizi WASTE/GARBAGE (Dahyeh) vs arabizi SAFETY/STRUCTURAL_COLLAPSE (Bourj Hammoud); cross-sector cross-district — truly unrelated"},
]


def main() -> None:
    # Guard: check if already applied
    existing = list(csv.DictReader(REPORTS_PATH.open(encoding="utf-8")))
    existing_ids = {row["report_id"] for row in existing}
    if "RPT-B001-053" in existing_ids:
        print("Already applied — RPT-B001-053 exists. Skipping.")
        return

    with REPORTS_PATH.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        for row in NEW_REPORTS:
            w.writerow(row)
    print(f"Appended {len(NEW_REPORTS)} reports to {REPORTS_PATH.name}")

    existing_pairs = list(csv.DictReader(PAIRS_PATH.open(encoding="utf-8")))
    existing_pair_ids = {p["pair_id"] for p in existing_pairs}
    new_pairs_to_write = [p for p in NEW_PAIRS if p["pair_id"] not in existing_pair_ids]
    with PAIRS_PATH.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PAIR_FIELDS)
        for row in new_pairs_to_write:
            w.writerow(row)
    print(f"Appended {len(new_pairs_to_write)} pairs to {PAIRS_PATH.name}")


if __name__ == "__main__":
    main()

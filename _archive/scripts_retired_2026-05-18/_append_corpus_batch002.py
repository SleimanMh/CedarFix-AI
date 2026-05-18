"""Batch 002: append 15 Arabizi/mixed rows + 3 clusters to reach ARZ-G01 (>=40 rows)."""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_PATH = ROOT / "data/corpus/cedarfix_reports_v1.csv"
PAIRS_PATH = ROOT / "data/corpus/cedarfix_pairs_v1.csv"
CLUSTERS_PATH = ROOT / "data/corpus/cedarfix_clusters_v1.csv"

REPORT_FIELDS = [
    "report_id", "cluster_id", "language", "raw_text", "normalized_text",
    "normalization_applied", "district_code", "lat", "lon", "sector", "issue_type",
    "severity", "route_entity", "priority_label", "priority_reason", "hitl_required",
    "public_safety", "image_label", "image_consistent", "duplicate_role",
    "hard_negative_for_cluster_id", "created_at_offset_minutes", "labeler_id",
    "reviewer_id", "review_status", "notes",
]
PAIR_FIELDS = ["pair_id", "report_id_a", "report_id_b", "pair_label", "cluster_id", "rationale"]
CLUSTER_FIELDS = [
    "cluster_id", "sector", "issue_type", "district_code", "severity",
    "route_entity", "hitl_required", "public_safety", "report_count",
    "centroid_lat", "centroid_lon", "created_at_reference",
    "cluster_description", "canonical_report_id", "notes",
]


def rpt(report_id, cluster_id, language, raw_text,
        district_code, lat, lon,
        sector, issue_type, severity, route_entity,
        priority_label, priority_reason,
        hitl_required, public_safety,
        duplicate_role, hard_negative_for_cluster_id,
        created_at_offset_minutes, notes):
    return {
        "report_id": report_id, "cluster_id": cluster_id, "language": language,
        "raw_text": raw_text, "normalized_text": raw_text, "normalization_applied": "false",
        "district_code": district_code, "lat": lat, "lon": lon,
        "sector": sector, "issue_type": issue_type, "severity": severity,
        "route_entity": route_entity, "priority_label": priority_label,
        "priority_reason": priority_reason, "hitl_required": hitl_required,
        "public_safety": public_safety, "image_label": "NONE", "image_consistent": "N/A",
        "duplicate_role": duplicate_role, "hard_negative_for_cluster_id": hard_negative_for_cluster_id,
        "created_at_offset_minutes": created_at_offset_minutes,
        "labeler_id": "TEAM-01", "reviewer_id": "CODEX-A2", "review_status": "APPROVED",
        "notes": notes,
    }


NEW_REPORTS = [
    # ── CLU-B002-001  ROADS / POTHOLE  Achrafieh ─────────────────────────────
    rpt("RPT-B001-066", "CLU-B002-001", "arabizi",
        "fi 7ufra kbire bi share3 armeniye w l tire2 ghayet min l zaman",
        "BEI_ACHRAFIEH", "33.8938", "35.5117",
        "ROADS", "POTHOLE", "HIGH", "CDR", "2",
        "HIGH pothole; 7ufra token confirmed; persistent defect ghayet long-standing",
        "false", "false", "ORIGINAL", "", "0",
        "Arabizi ORIGINAL pothole; 7ufra token; CLU-B002-001"),

    rpt("RPT-B001-067", "CLU-B002-001", "arabizi",
        "l 7ufra bi armeniye kbire ktir w bi terji3 t2a3 3jelatna",
        "BEI_ACHRAFIEH", "33.8941", "35.5120",
        "ROADS", "POTHOLE", "HIGH", "CDR", "2",
        "HIGH pothole duplicate; same 7ufra location t2a3 3jelatna tire-damage risk",
        "false", "false", "DUPLICATE", "", "12",
        "Arabizi pothole duplicate; t2a3 3jelatna colloquial Lebanese; CLU-B002-001"),

    rpt("RPT-B001-068", "CLU-B002-001", "mixed",
        "route completement abimee, 7ufra w kasaret bi share3 sursok achrafieh",
        "BEI_ACHRAFIEH", "33.8935", "35.5112",
        "ROADS", "ROAD_DAMAGED", "HIGH", "CDR", "2",
        "HIGH road-damaged adjacent duplicate; French route + Arabizi 7ufra token",
        "false", "false", "DUPLICATE", "", "25",
        "Mixed French+Arabizi road-damaged duplicate; route abimee framing; CLU-B002-001"),

    # ── CLU-B002-002  WATER / WATER_CUT  Tarik Jdide ─────────────────────────
    rpt("RPT-B001-069", "CLU-B002-002", "arabizi",
        "miye 2at3a men 3 t3yam w ma 7ada byiji bi share3 el khandaq el ghamik",
        "BEI_TARIK_JDIDE", "33.8813", "35.4985",
        "WATER", "WATER_CUT", "HIGH", "BWE", "2",
        "HIGH water cut; miye 2at3a confirmed; 3 days unresolved forces HITL review",
        "false", "true", "ORIGINAL", "", "0",
        "Arabizi ORIGINAL water-cut; miye 2at3a; 3 t3yam duration; CLU-B002-002"),

    rpt("RPT-B001-070", "CLU-B002-002", "arabizi",
        "lissa miye mat3a w l nas killon yishtikou bi hay el tarik jdide",
        "BEI_TARIK_JDIDE", "33.8817", "35.4989",
        "WATER", "WATER_CUT", "HIGH", "BWE", "2",
        "HIGH water-cut duplicate; lissa mat3a still-cut + community complaint scale",
        "false", "true", "DUPLICATE", "", "20",
        "Arabizi water-cut duplicate; lissa mat3a + nas killon community signal; CLU-B002-002"),

    rpt("RPT-B001-071", "CLU-B002-002", "mixed",
        "eau coupee depuis 2 jours, miye mat3a w ma fi jawab bi share3 bliss el mazraa",
        "BEI_MAZRAA", "33.8801", "35.4958",
        "WATER", "WATER_CUT", "HIGH", "BWE", "2",
        "HIGH water-cut adjacent; French eau coupee + Arabizi miye mat3a cross-language",
        "false", "true", "DUPLICATE", "", "40",
        "Mixed French+Arabizi water-cut adjacent; eau coupee + miye mat3a bilingual; CLU-B002-002"),

    # ── CLU-B002-003  ELECTRICITY / POWER_OUTAGE  Hamra / Sanayeh ────────────
    rpt("RPT-B001-072", "CLU-B002-003", "arabizi",
        "kahraba mat3a men imbere7 w ma fi schedule 3la l app bi share3 makdissi hamra",
        "BEI_HAMRA", "33.8972", "35.4847",
        "ELECTRICITY", "POWER_OUTAGE", "MEDIUM", "EDL", "2",
        "MEDIUM power outage; kahraba mat3a token; no-schedule frustration via app",
        "false", "false", "ORIGINAL", "", "0",
        "Arabizi ORIGINAL power-outage; kahraba mat3a token; CLU-B002-003"),

    rpt("RPT-B001-073", "CLU-B002-003", "arabizi",
        "mat3a l kahraba w l moulid kharban 3enna bi share3 jeanne d arc",
        "BEI_HAMRA", "33.8969", "35.4850",
        "ELECTRICITY", "POWER_OUTAGE", "MEDIUM", "EDL", "2",
        "MEDIUM power-outage duplicate; moulid kharban generator-down; kahraba mat3a",
        "false", "false", "DUPLICATE", "", "15",
        "Arabizi power-outage duplicate; moulid kharban colloquial generator-failure; CLU-B002-003"),

    rpt("RPT-B001-074", "CLU-B002-003", "mixed",
        "panne depuis 20h, kahraba mat3a w ma fi masliye bi share3 hamra sanayeh",
        "BEI_SANAYEH", "33.8942", "35.4877",
        "ELECTRICITY", "POWER_OUTAGE", "MEDIUM", "EDL", "2",
        "MEDIUM power-outage adjacent; French panne + Arabizi kahraba mat3a bilingual",
        "false", "false", "DUPLICATE", "", "30",
        "Mixed French+Arabizi power-outage; panne depuis + kahraba mat3a; CLU-B002-003"),

    # ── Standalone rows  (balance WASTE, FLOODING, SAFETY) ───────────────────
    rpt("RPT-B001-075", "", "arabizi",
        "jmaou zibele w l masoul ma bada yiji bala haje bi share3 sin el fil",
        "BEI_SINELFILE", "33.9092", "35.5507",
        "WASTE", "GARBAGE_NOT_COLLECTED", "MEDIUM", "MUN", "2",
        "MEDIUM garbage not collected; jmaou zibele token; contractor absent",
        "false", "false", "NOISE", "CLU-B001-014", "0",
        "Arabizi WASTE hard-negative; Sin el Fil district; jmaou zibele token"),

    rpt("RPT-B001-076", "", "arabizi",
        "fi shahin zibele mhattout bi 7aret el nahr w ri7a khafer ktir",
        "BEI_KARANTINA", "33.8975", "35.5265",
        "WASTE", "OVERFLOWING_BIN", "MEDIUM", "MUN", "2",
        "MEDIUM overflowing bin; shahin+ri7a khafer token pair confirms WASTE",
        "false", "false", "NOISE", "CLU-B001-014", "0",
        "Arabizi WASTE overflowing-bin; Karantina district; shahin zibele token"),

    rpt("RPT-B001-077", "", "arabizi",
        "balo3a msdoude bi share3 sursok w l miye 3am tit2elle3 men l ardiye",
        "BEI_ACHRAFIEH", "33.8930", "35.5108",
        "FLOODING", "BLOCKED_DRAIN", "HIGH", "MUN", "2",
        "HIGH blocked-drain; balo3a msdoude + ardiye tokens; water seeping up",
        "false", "true", "NOISE", "CLU-B001-015", "0",
        "Arabizi FLOODING blocked-drain; balo3a msdoude; Achrafieh Sursok"),

    rpt("RPT-B001-078", "", "arabizi",
        "l share3 ghatat bil miye bi el patriarkat w ma fi 7ada byemsha",
        "BEI_PATRIARCAT", "33.8855", "35.4990",
        "FLOODING", "ROAD_FLOODED", "HIGH", "MUN", "2",
        "HIGH road-flooded; ghatat bil miye token; no pedestrian passage",
        "false", "true", "NOISE", "CLU-B001-015", "0",
        "Arabizi FLOODING road-flooded; ghatat bil miye; Patriarcat district"),

    rpt("RPT-B001-079", "", "arabizi",
        "bne shabbe bi 2eshr derej w hajra nzal men l jdar bi share3 badaro",
        "BEI_BADARO", "33.8870", "35.5170",
        "SAFETY", "STRUCTURAL_DAMAGE", "HIGH", "CD", "2",
        "HIGH structural damage; bne shabbe + hajra nzal debris-fall confirms SAFETY",
        "true", "true", "NOISE", "CLU-B001-013", "0",
        "Arabizi SAFETY structural-damage; hajra nzal debris signal; Badaro district"),

    rpt("RPT-B001-080", "", "arabizi",
        "nnar 3am tit3ala bi mokhzen bi share3 el sodeco w l nar kbire ktir",
        "BEI_SODECO", "33.8854", "35.5140",
        "SAFETY", "FIRE", "CRITICAL", "CD", "1",
        "CRITICAL fire; nnar+nar HIGH_RISK_HINTS double-confirm SAFETY/FIRE; HITL mandatory",
        "true", "true", "NOISE", "CLU-B001-013", "0",
        "Arabizi SAFETY fire; nnar + nar double-token; Sodeco district; Batch 002"),
]

NEW_CLUSTERS = [
    {
        "cluster_id": "CLU-B002-001", "sector": "ROADS", "issue_type": "POTHOLE",
        "district_code": "BEI_ACHRAFIEH", "severity": "HIGH",
        "route_entity": "CDR", "hitl_required": "false", "public_safety": "false",
        "report_count": "2", "centroid_lat": "33.8938", "centroid_lon": "35.5117",
        "created_at_reference": "RPT-B001-066",
        "cluster_description": "Persistent large pothole on Rue Armenienne, Achrafieh — 2 arabizi reports; tire-damage risk",
        "canonical_report_id": "RPT-B001-066",
        "notes": "Batch 002 ROADS cluster; 7ufra token coverage",
    },
    {
        "cluster_id": "CLU-B002-002", "sector": "WATER", "issue_type": "WATER_CUT",
        "district_code": "BEI_TARIK_JDIDE", "severity": "HIGH",
        "route_entity": "BWE", "hitl_required": "false", "public_safety": "true",
        "report_count": "2", "centroid_lat": "33.8813", "centroid_lon": "35.4985",
        "created_at_reference": "RPT-B001-069",
        "cluster_description": "72-hour water cut, Khandaq el Ghamik / Tarik Jdide — community-scale impact; miye 2at3a",
        "canonical_report_id": "RPT-B001-069",
        "notes": "Batch 002 WATER cluster; miye 2at3a + mat3a token coverage",
    },
    {
        "cluster_id": "CLU-B002-003", "sector": "ELECTRICITY", "issue_type": "POWER_OUTAGE",
        "district_code": "BEI_HAMRA", "severity": "MEDIUM",
        "route_entity": "EDL", "hitl_required": "false", "public_safety": "false",
        "report_count": "2", "centroid_lat": "33.8970", "centroid_lon": "35.4849",
        "created_at_reference": "RPT-B001-072",
        "cluster_description": "Unscheduled power outage, Makdissi / Hamra — kahraba mat3a + moulid kharban; EDL no-schedule",
        "canonical_report_id": "RPT-B001-072",
        "notes": "Batch 002 ELECTRICITY cluster; kahraba mat3a token coverage",
    },
]


def main() -> None:
    # Guard
    existing = list(csv.DictReader(REPORTS_PATH.open(encoding="utf-8")))
    if any(r["report_id"] == "RPT-B001-066" for r in existing):
        print("Already applied — RPT-B001-066 exists. Skipping.")
        return

    with REPORTS_PATH.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        for row in NEW_REPORTS:
            w.writerow(row)
    print(f"Appended {len(NEW_REPORTS)} reports to {REPORTS_PATH.name}")

    with CLUSTERS_PATH.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CLUSTER_FIELDS)
        for row in NEW_CLUSTERS:
            w.writerow(row)
    print(f"Appended {len(NEW_CLUSTERS)} clusters to {CLUSTERS_PATH.name}")


if __name__ == "__main__":
    main()

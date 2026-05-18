import argparse
import csv
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS_PATH = ROOT / "data" / "corpus" / "cedarfix_reports_v1.csv"
PAIRS_PATH = ROOT / "data" / "corpus" / "cedarfix_pairs_v1.csv"
OOV_QUEUE_PATH = ROOT / "data" / "corpus" / "arabizi_oov_review_queue_v1.csv"
OUTPUT_PATH = ROOT / "data" / "eval" / "arabizi_benchmark_v0_regression.csv"
SHA_PATH = ROOT / "data" / "eval" / "arabizi_benchmark_v0_regression.sha256"

FIELDNAMES = [
    "case_id",
    "case_type",
    "source_id",
    "report_id_a",
    "report_id_b",
    "cluster_id",
    "language_a",
    "language_b",
    "lat_a",
    "lon_a",
    "lat_b",
    "lon_b",
    "raw_text_a",
    "raw_text_b",
    "expected_normalized_text_a",
    "expected_normalized_text_b",
    "expected_sector",
    "expected_issue_type",
    "expected_severity",
    "expected_route_entity",
    "expected_pair_label",
    "expected_hitl_required",
    "expected_drift_score_min",
    "expected_behavior",
    "notes",
]

SELECTED_PAIR_IDS = {
    "PAIR-B001-0002",  # English-Arabizi pothole duplicate
    "PAIR-B001-0004",  # Arabic-Arabizi pothole duplicate
    "PAIR-B001-0006",  # Arabizi-French pothole duplicate
    "PAIR-B001-0018",  # Arabizi hard negative, electricity cluster
    "PAIR-B001-0042",  # English-Arabizi flooding duplicate
    "PAIR-B001-0089",  # Mixed-language exposed-wire duplicate
    "PAIR-B001-0090",  # Mixed-language water-cut duplicate
}

ADVERSARIAL_CASES = [
    {
        "case_id": "ADV-B001-001",
        "case_type": "ADVERSARIAL",
        "source_id": "manual:digit_omission_repeated_letters",
        "language_a": "arabizi",
        "raw_text_a": "fi hofraaaaaa 3al share3 l 7amra jemb l virgin",
        "expected_normalized_text_a": "في حفرة على شارع الحمرا بجانب الفيرجن",
        "expected_sector": "ROADS",
        "expected_issue_type": "POTHOLE",
        "expected_severity": "MEDIUM",
        "expected_route_entity": "MUN",
        "expected_hitl_required": "false",
        "expected_drift_score_min": "1",
        "expected_behavior": "Normalize repeated letters and tolerate omitted 7 in hofra without losing POTHOLE signal",
        "notes": "Regression for hofra/7ofra and elongation handling; not training data.",
    },
    {
        "case_id": "ADV-B001-002",
        "case_type": "ADVERSARIAL",
        "source_id": "manual:repeated_digit_high_risk",
        "language_a": "arabizi",
        "raw_text_a": "5tr444444 silk kahraba 3al ard bi borj 7ammoud",
        "expected_normalized_text_a": "خطر، سلك كهرباء على الأرض في برج حمود",
        "expected_sector": "ELECTRICITY",
        "expected_issue_type": "EXPOSED_WIRE",
        "expected_severity": "CRITICAL",
        "expected_route_entity": "EDL",
        "expected_hitl_required": "true",
        "expected_drift_score_min": "2",
        "expected_behavior": "Collapse repeated danger shorthand and force HITL for exposed-wire safety risk",
        "notes": "Regression for 5tr444444 noise handling and high-risk OOV/HITL behavior.",
    },
    {
        "case_id": "ADV-B001-003",
        "case_type": "ADVERSARIAL",
        "source_id": "manual:no_space_tokenization",
        "language_a": "arabizi",
        "raw_text_a": "fishare3l7amra fi jora kbire",
        "expected_normalized_text_a": "في شارع الحمرا في حفرة كبيرة",
        "expected_sector": "ROADS",
        "expected_issue_type": "POTHOLE",
        "expected_severity": "MEDIUM",
        "expected_route_entity": "MUN",
        "expected_hitl_required": "false",
        "expected_drift_score_min": "2",
        "expected_behavior": "Tokenizer should not crash on fused words; prediction may lower confidence but keeps ROADS/POTHOLE",
        "notes": "Regression for no-space user input common in mobile typing.",
    },
    {
        "case_id": "ADV-B001-004",
        "case_type": "ADVERSARIAL",
        "source_id": "manual:french_code_switch_transformer",
        "language_a": "mixed",
        "raw_text_a": "transformateur m7arrak bi borj 7ammoud w fi ri7et 7ar2",
        "expected_normalized_text_a": "محول كهرباء شغال في برج حمود وفي رائحة حريق",
        "expected_sector": "ELECTRICITY",
        "expected_issue_type": "TRANSFORMER_FAULT",
        "expected_severity": "HIGH",
        "expected_route_entity": "EDL",
        "expected_hitl_required": "true",
        "expected_drift_score_min": "2",
        "expected_behavior": "Detect French-origin transformer token, code mix, and electricity HITL policy",
        "notes": "Regression for transformateur mapping to TRANSFORMER_FAULT rather than EXPOSED_WIRE.",
    },
    {
        "case_id": "ADV-B001-005",
        "case_type": "ADVERSARIAL",
        "source_id": "manual:unknown_risk_modifier",
        "language_a": "arabizi",
        "raw_text_a": "fi jora kbire 3al tari2 w l wad3 m5atra ktir",
        "expected_normalized_text_a": "في حفرة كبيرة على الطريق والوضع خطير كثير",
        "expected_sector": "ROADS",
        "expected_issue_type": "POTHOLE",
        "expected_severity": "HIGH",
        "expected_route_entity": "MUN",
        "expected_hitl_required": "true",
        "expected_drift_score_min": "2",
        "expected_behavior": "Known jora should preserve POTHOLE signal while unknown risk modifier raises drift/HITL",
        "notes": "Demo-grade Arabizi drift case; system survives unknown meaningful token.",
    },
    {
        "case_id": "ADV-B001-006",
        "case_type": "ADVERSARIAL",
        "source_id": "manual:sanitation_ambiguity",
        "language_a": "arabizi",
        "raw_text_a": "may ws5a w ri7et sarif 3al tari2 bi bliss",
        "expected_normalized_text_a": "مياه وسخة ورائحة صرف صحي على الطريق في بليس",
        "expected_sector": "WATER",
        "expected_issue_type": "SEWAGE_OVERFLOW",
        "expected_severity": "HIGH",
        "expected_route_entity": "BMLWE",
        "expected_hitl_required": "true",
        "expected_drift_score_min": "1",
        "expected_behavior": "Prefer WATER/SEWAGE_OVERFLOW and force review because dirty water vs sewage wording affects public-health routing",
        "notes": "Regression for sanitation ambiguity rather than simple dirty-water keywording.",
    },
    {
        "case_id": "ADV-B001-007",
        "case_type": "PAIR_ADVERSARIAL",
        "source_id": "manual:near_border_non_merge",
        "report_id_a": "ADV-GEO-A",
        "report_id_b": "ADV-GEO-B",
        "cluster_id": "ADV-GEO-001",
        "language_a": "arabizi",
        "language_b": "ar",
        "lat_a": "33.889700",
        "lon_a": "35.480000",
        "lat_b": "33.891510",
        "lon_b": "35.480000",
        "raw_text_a": "fi hofra kbire 3al share3 l 7amra",
        "raw_text_b": "حفرة كبيرة على شارع آخر قريب من الحمرا",
        "expected_normalized_text_a": "في حفرة كبيرة على شارع الحمرا",
        "expected_normalized_text_b": "حفرة كبيرة على شارع آخر قريب من الحمرا",
        "expected_sector": "ROADS",
        "expected_issue_type": "POTHOLE",
        "expected_severity": "MEDIUM",
        "expected_route_entity": "MUN",
        "expected_pair_label": "HARD_NEGATIVE",
        "expected_hitl_required": "false",
        "expected_drift_score_min": "1",
        "expected_behavior": "Near-border semantic duplicate candidate should not auto-merge when geography indicates a different physical pothole",
        "notes": "201m north-south offset at Beirut latitude; tests IEP-2 boundary discipline.",
    },
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def blank_row() -> dict[str, str]:
    return {field: "" for field in FIELDNAMES}


def add_hash(path: Path, sha_path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    sha_path.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def oov_drift_min_by_report() -> dict[str, int]:
    """Return per-report minimum drift score based on non-promoted OOV tokens.

    Tokens with decision=ADD_TO_VOCAB are excluded: they have been promoted to
    the vocabulary and are no longer OOV, so they must not inflate the expected
    minimum drift score after a vocabulary bump.
    """
    if not OOV_QUEUE_PATH.exists():
        return {}
    result: dict[str, int] = {}
    for row in read_csv(OOV_QUEUE_PATH):
        if row.get("decision") == "ADD_TO_VOCAB":
            continue  # token promoted to vocab — no longer counts as OOV drift
        risk_hint = row["risk_hint"]
        score = 2 if risk_hint in {"SAFETY_LEXICAL_HINT", "HIGH_IMPACT_CONTEXT", "HITL_CONTEXT"} else 1
        for report_id in row["report_ids"].split("|"):
            if report_id:
                result[report_id] = max(result.get(report_id, 0), score)
    return result


def report_case(index: int, report: dict[str, str], drift_by_report: dict[str, int]) -> dict[str, str]:
    row = blank_row()
    row.update(
        {
            "case_id": f"BENCH-B001-REPORT-{index:03d}",
            "case_type": "REPORT",
            "source_id": report["report_id"],
            "report_id_a": report["report_id"],
            "cluster_id": report["cluster_id"],
            "language_a": report["language"],
            "lat_a": report["lat"],
            "lon_a": report["lon"],
            "raw_text_a": report["raw_text"],
            "expected_normalized_text_a": report["normalized_text"],
            "expected_sector": report["sector"],
            "expected_issue_type": report["issue_type"],
            "expected_severity": report["severity"],
            "expected_route_entity": report["route_entity"],
            "expected_hitl_required": report["hitl_required"].lower(),
            "expected_drift_score_min": str(drift_by_report.get(report["report_id"], 0)),
            "expected_behavior": "Preserve reviewed corpus labels and meaning-equivalent normalization",
            "notes": "Frozen B001 Arabizi/mixed corpus row; use for regression, not final F1 claims.",
        }
    )
    return row


def pair_case(index: int, pair: dict[str, str], reports_by_id: dict[str, dict[str, str]]) -> dict[str, str]:
    report_a = reports_by_id[pair["report_id_a"]]
    report_b = reports_by_id[pair["report_id_b"]]
    row = blank_row()
    row.update(
        {
            "case_id": f"BENCH-B001-PAIR-{index:03d}",
            "case_type": "PAIR",
            "source_id": pair["pair_id"],
            "report_id_a": pair["report_id_a"],
            "report_id_b": pair["report_id_b"],
            "cluster_id": pair["cluster_id"],
            "language_a": report_a["language"],
            "language_b": report_b["language"],
            "lat_a": report_a["lat"],
            "lon_a": report_a["lon"],
            "lat_b": report_b["lat"],
            "lon_b": report_b["lon"],
            "raw_text_a": report_a["raw_text"],
            "raw_text_b": report_b["raw_text"],
            "expected_normalized_text_a": report_a["normalized_text"],
            "expected_normalized_text_b": report_b["normalized_text"],
            "expected_sector": report_a["sector"],
            "expected_issue_type": report_a["issue_type"],
            "expected_severity": report_a["severity"],
            "expected_route_entity": report_a["route_entity"],
            "expected_pair_label": pair["pair_label"],
            "expected_hitl_required": report_a["hitl_required"].lower(),
            "expected_drift_score_min": "0",
            "expected_behavior": pair["rationale"],
            "notes": "Frozen B001 pair case stressing cross-language or hard-negative fusion.",
        }
    )
    return row


def adversarial_case(case: dict[str, str]) -> dict[str, str]:
    row = blank_row()
    row.update(case)
    return row


def build_rows() -> list[dict[str, str]]:
    reports = read_csv(REPORTS_PATH)
    pairs = read_csv(PAIRS_PATH)
    reports_by_id = {row["report_id"]: row for row in reports}
    drift_by_report = oov_drift_min_by_report()

    rows: list[dict[str, str]] = []
    arabizi_reports = [row for row in reports if row["language"] in {"arabizi", "mixed"}]
    for index, report in enumerate(arabizi_reports, start=1):
        rows.append(report_case(index, report, drift_by_report))

    selected_pairs = [row for row in pairs if row["pair_id"] in SELECTED_PAIR_IDS]
    for index, pair in enumerate(selected_pairs, start=1):
        rows.append(pair_case(index, pair, reports_by_id))

    for case in ADVERSARIAL_CASES:
        rows.append(adversarial_case(case))

    return rows


def write_rows(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze the CedarFix B001 Arabizi regression benchmark.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing benchmark and hash intentionally.")
    args = parser.parse_args()

    if (OUTPUT_PATH.exists() or SHA_PATH.exists()) and not args.force:
        print("ERROR: benchmark already exists. Use --force only for an intentional new benchmark version/hash.")
        return 1

    rows = build_rows()
    write_rows(rows, OUTPUT_PATH)
    digest = add_hash(OUTPUT_PATH, SHA_PATH)
    print(f"OK: wrote {len(rows)} benchmark cases to {OUTPUT_PATH}")
    print(f"OK: sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

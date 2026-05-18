import csv
import hashlib
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "data" / "eval" / "arabizi_benchmark_v0_regression.csv"
SHA_PATH = ROOT / "data" / "eval" / "arabizi_benchmark_v0_regression.sha256"
REPORTS_PATH = ROOT / "data" / "corpus" / "cedarfix_reports_v1.csv"
PAIRS_PATH = ROOT / "data" / "corpus" / "cedarfix_pairs_v1.csv"
OOV_QUEUE_PATH = ROOT / "data" / "corpus" / "arabizi_oov_review_queue_v1.csv"

REQUIRED_COLUMNS = {
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
}

VALID_CASE_TYPES = {"REPORT", "PAIR", "ADVERSARIAL", "PAIR_ADVERSARIAL"}
VALID_LANGUAGES = {"arabizi", "mixed", "ar", "en", "fr", ""}
VALID_PAIR_LABELS = {"DUPLICATE", "RELATED", "HARD_NEGATIVE", "UNRELATED", ""}
VALID_HITL = {"true", "false", ""}
CASE_ID_RE = re.compile(r"^(BENCH-B001-(REPORT|PAIR)-\d{3}|ADV-B001-\d{3})$")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def add_error(errors: list[str], code: str, message: str) -> None:
    errors.append(f"{code}: {message}")


def verify_sha(errors: list[str]) -> None:
    if not BENCHMARK_PATH.exists():
        add_error(errors, "BENCHMARK_MISSING", f"{BENCHMARK_PATH} does not exist")
        return
    if not SHA_PATH.exists():
        add_error(errors, "SHA_MISSING", f"{SHA_PATH} does not exist")
        return

    actual = hashlib.sha256(BENCHMARK_PATH.read_bytes()).hexdigest()
    expected_line = SHA_PATH.read_text(encoding="utf-8").strip()
    parts = expected_line.split()
    if len(parts) != 2:
        add_error(errors, "SHA_FORMAT", "SHA file must contain '<sha256>  arabizi_benchmark_v0_regression.csv'")
        return
    expected_hash, expected_name = parts
    if expected_name != BENCHMARK_PATH.name:
        add_error(errors, "SHA_FILENAME", f"SHA file references {expected_name}, expected {BENCHMARK_PATH.name}")
    if expected_hash != actual:
        add_error(errors, "SHA_MISMATCH", f"Benchmark hash mismatch: expected {expected_hash}, actual {actual}")


def expected_drift_min_by_report_from_oov_queue() -> dict[str, int]:
    """Mirror benchmark build logic so stale drift expectations fail validation."""

    if not OOV_QUEUE_PATH.exists():
        return {}

    result: dict[str, int] = {}
    for row in read_csv(OOV_QUEUE_PATH):
        if row.get("decision") == "ADD_TO_VOCAB":
            continue
        risk_hint = row["risk_hint"]
        score = 2 if risk_hint in {"SAFETY_LEXICAL_HINT", "HIGH_IMPACT_CONTEXT", "HITL_CONTEXT"} else 1
        for report_id in row["report_ids"].split("|"):
            if report_id:
                result[report_id] = max(result.get(report_id, 0), score)
    return result


def validate() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    verify_sha(errors)
    if errors:
        return finish(errors, warnings)

    rows = read_csv(BENCHMARK_PATH)
    reports = read_csv(REPORTS_PATH)
    pairs = read_csv(PAIRS_PATH)
    reports_by_id = {row["report_id"]: row for row in reports}
    pairs_by_id = {row["pair_id"]: row for row in pairs}
    drift_min_by_report = expected_drift_min_by_report_from_oov_queue()

    if not rows:
        add_error(errors, "EMPTY_BENCHMARK", f"No rows in {BENCHMARK_PATH}")
        return finish(errors, warnings)

    missing_cols = REQUIRED_COLUMNS - set(rows[0].keys())
    if missing_cols:
        add_error(errors, "BENCHMARK_COLUMNS", f"Missing columns: {sorted(missing_cols)}")

    case_ids = set()
    report_cases = []
    pair_cases = []
    adversarial_cases = []
    pair_adversarial_cases = []

    for row in rows:
        case_id = row["case_id"]
        case_type = row["case_type"]
        if case_id in case_ids:
            add_error(errors, "DUPLICATE_CASE", f"Duplicate case_id={case_id}")
        case_ids.add(case_id)
        if not CASE_ID_RE.match(case_id):
            add_error(errors, "CASE_ID", f"{case_id} has invalid format")
        if case_type not in VALID_CASE_TYPES:
            add_error(errors, "CASE_TYPE", f"{case_id} invalid case_type={case_type}")
        if row["language_a"] not in VALID_LANGUAGES or row["language_b"] not in VALID_LANGUAGES:
            add_error(errors, "LANGUAGE", f"{case_id} has invalid language fields")
        if row["expected_pair_label"] not in VALID_PAIR_LABELS:
            add_error(errors, "PAIR_LABEL", f"{case_id} invalid expected_pair_label={row['expected_pair_label']}")
        if row["expected_hitl_required"].lower() not in VALID_HITL:
            add_error(errors, "HITL", f"{case_id} invalid expected_hitl_required={row['expected_hitl_required']}")
        try:
            drift_min = int(row["expected_drift_score_min"] or "0")
        except ValueError:
            add_error(errors, "DRIFT_SCORE", f"{case_id} expected_drift_score_min must be int 0-3")
            drift_min = 0
        if drift_min < 0 or drift_min > 3:
            add_error(errors, "DRIFT_SCORE", f"{case_id} expected_drift_score_min={drift_min} outside 0-3")

        if case_type in {"REPORT", "ADVERSARIAL"}:
            if not row["raw_text_a"] or not row["expected_normalized_text_a"]:
                add_error(errors, "TEXT", f"{case_id} requires raw_text_a and expected_normalized_text_a")
            if not row["expected_sector"] or not row["expected_issue_type"]:
                add_error(errors, "EXPECTED_LABELS", f"{case_id} requires expected_sector and expected_issue_type")
        if case_type in {"PAIR", "PAIR_ADVERSARIAL"}:
            if not row["raw_text_a"] or not row["raw_text_b"]:
                add_error(errors, "PAIR_TEXT", f"{case_id} requires raw_text_a and raw_text_b")
            if row["expected_pair_label"] not in {"DUPLICATE", "RELATED", "HARD_NEGATIVE", "UNRELATED"}:
                add_error(errors, "PAIR_EXPECTED_LABEL", f"{case_id} requires concrete expected_pair_label")

        if case_type == "REPORT":
            report_cases.append(row)
            report = reports_by_id.get(row["source_id"])
            if not report:
                add_error(errors, "SOURCE_REPORT", f"{case_id} source report missing: {row['source_id']}")
            else:
                if report["language"] not in {"arabizi", "mixed"}:
                    add_error(errors, "SOURCE_REPORT_LANGUAGE", f"{case_id} source report is not arabizi/mixed")
                if row["expected_normalized_text_a"] != report["normalized_text"]:
                    add_error(errors, "SOURCE_NORMALIZATION", f"{case_id} expected normalization differs from corpus")
                if row["expected_issue_type"] != report["issue_type"]:
                    add_error(errors, "SOURCE_ISSUE_TYPE", f"{case_id} expected issue differs from corpus")
                if row["expected_severity"] != report["severity"]:
                    add_error(errors, "SOURCE_SEVERITY", f"{case_id} expected severity differs from corpus")
                if row["expected_sector"] != report["sector"]:
                    add_error(errors, "SOURCE_SECTOR", f"{case_id} expected sector differs from corpus")
                if row["expected_route_entity"] != report["route_entity"]:
                    add_error(errors, "SOURCE_ROUTE_ENTITY", f"{case_id} expected route_entity differs from corpus")
                if row["expected_hitl_required"].lower() != report["hitl_required"].lower():
                    add_error(errors, "SOURCE_HITL", f"{case_id} expected hitl_required differs from corpus")
                expected_drift_min = drift_min_by_report.get(report["report_id"], 0)
                if int(row["expected_drift_score_min"] or "0") != expected_drift_min:
                    add_error(
                        errors,
                        "SOURCE_DRIFT_MIN",
                        (
                            f"{case_id} expected_drift_score_min={row['expected_drift_score_min']} "
                            f"but non-promoted OOV queue implies {expected_drift_min}"
                        ),
                    )
        elif case_type == "PAIR":
            pair_cases.append(row)
            pair = pairs_by_id.get(row["source_id"])
            if not pair:
                add_error(errors, "SOURCE_PAIR", f"{case_id} source pair missing: {row['source_id']}")
            else:
                if row["expected_pair_label"] != pair["pair_label"]:
                    add_error(errors, "SOURCE_PAIR_LABEL", f"{case_id} expected pair label differs from corpus")
                report_a = reports_by_id.get(pair["report_id_a"])
                report_b = reports_by_id.get(pair["report_id_b"])
                if report_a and row["expected_normalized_text_a"] != report_a["normalized_text"]:
                    add_error(errors, "PAIR_NORM_A", f"{case_id} expected_normalized_text_a differs from corpus")
                if report_b and row["expected_normalized_text_b"] != report_b["normalized_text"]:
                    add_error(errors, "PAIR_NORM_B", f"{case_id} expected_normalized_text_b differs from corpus")
        elif case_type == "ADVERSARIAL":
            adversarial_cases.append(row)
        elif case_type == "PAIR_ADVERSARIAL":
            pair_adversarial_cases.append(row)

    if len(report_cases) != 14:
        add_error(errors, "REPORT_CASE_COUNT", f"Expected 14 Arabizi/mixed REPORT cases, found {len(report_cases)}")
    if len(adversarial_cases) < 6:
        add_error(errors, "ADVERSARIAL_COUNT", f"Expected at least 6 ADVERSARIAL cases, found {len(adversarial_cases)}")
    if len(pair_adversarial_cases) < 1:
        add_error(errors, "PAIR_ADVERSARIAL_COUNT", "Expected at least 1 PAIR_ADVERSARIAL case")
    if len(pair_cases) < 6:
        add_error(errors, "PAIR_CASE_COUNT", f"Expected at least 6 PAIR cases, found {len(pair_cases)}")

    duplicate_cross_language = [
        row
        for row in pair_cases
        if row["expected_pair_label"] == "DUPLICATE" and row["language_a"] != row["language_b"]
    ]
    hard_negatives = [
        row
        for row in pair_cases + pair_adversarial_cases
        if row["expected_pair_label"] == "HARD_NEGATIVE"
    ]
    if len(duplicate_cross_language) < 4:
        add_error(errors, "CROSS_LANGUAGE_DUPLICATES", "Benchmark needs at least 4 cross-language duplicate cases")
    if not hard_negatives:
        add_error(errors, "HARD_NEGATIVE_CASES", "Benchmark needs at least one hard-negative pair case")

    return finish(errors, warnings)


def finish(errors: list[str], warnings: list[str]) -> int:
    for warning in warnings:
        print(f"WARNING {warning}")
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        print(f"FAILED: {len(errors)} errors, {len(warnings)} warnings")
        return 1
    print(f"OK: Arabizi benchmark validation passed with {len(warnings)} warnings")
    return 0


if __name__ == "__main__":
    sys.exit(validate())

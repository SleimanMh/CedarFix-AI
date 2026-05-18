import csv
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "data" / "corpus" / "arabizi_oov_review_queue_v1.csv"
REPORTS_PATH = ROOT / "data" / "corpus" / "cedarfix_reports_v1.csv"

CANDIDATE_ID_RE = re.compile(r"^OOV-(B\d{3})-\d{3}$")
TOKEN_RE = re.compile(r"^[a-z0-9]+$")

REQUIRED_COLUMNS = {
    "candidate_id",
    "batch",
    "normalized_token",
    "raw_variants",
    "frequency",
    "report_count",
    "report_ids",
    "example_report_id",
    "example_text",
    "proposed_sector",
    "proposed_issue_type",
    "risk_hint",
    "suggested_action",
    "reviewer_id",
    "review_status",
    "decision",
    "notes",
}

VALID_REVIEW_STATUSES = {"PENDING_REVIEW", "REVIEWED", "NEEDS_CONTEXT", "DISPUTED"}
VALID_ACTIONS = {
    "ADD_TO_VOCAB",
    "ADD_TO_STOPLIST",
    "KEEP_MODEL_ONLY",
    "REJECT_NOISE",
    "NEEDS_MORE_EXAMPLES",
    "",
}
VALID_RISK_HINTS = {"SAFETY_LEXICAL_HINT", "HIGH_IMPACT_CONTEXT", "HITL_CONTEXT", "LANGUAGE_DRIFT"}

ISSUE_TYPES_BY_SECTOR = {
    "ROADS": {
        "POTHOLE",
        "ROAD_COLLAPSE",
        "ROAD_BLOCKED",
        "ROAD_CRACK",
        "MISSING_MANHOLE",
        "BROKEN_SIDEWALK",
        "ROAD_DAMAGE",
        "ROAD_CLOSED",
    },
    "WATER": {"WATER_CUT", "PIPE_LEAK", "SEWAGE_OVERFLOW", "DIRTY_WATER", "LOW_PRESSURE", "NO_SUPPLY"},
    "ELECTRICITY": {"EXPOSED_WIRE", "POWER_OUTAGE", "STREET_LIGHT", "TRANSFORMER_FAULT", "VOLTAGE_FLUCTUATION"},
    "WASTE": {"GARBAGE_NOT_COLLECTED", "ILLEGAL_DUMP", "OVERFLOWING_BIN", "BURNING_WASTE", "DAMAGED_BIN"},
    "FLOODING": {"ROAD_FLOODED", "HOUSE_FLOODED", "BLOCKED_DRAIN", "FLASH_FLOOD", "STANDING_WATER", "BASEMENT_FLOODED"},
    "SAFETY": {"STRUCTURAL_COLLAPSE", "FIRE", "GAS_LEAK", "EXPOSED_HAZARD", "ARMED_INCIDENT", "INJURY", "SUSPICIOUS"},
    "OTHER": {"UNCLASSIFIED"},
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def add_error(errors: list[str], code: str, message: str) -> None:
    errors.append(f"{code}: {message}")


def validate() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not QUEUE_PATH.exists():
        add_error(errors, "QUEUE_MISSING", f"{QUEUE_PATH} does not exist; run scripts/analyze_arabizi_oov.py")
        return finish(errors, warnings)

    rows = read_csv(QUEUE_PATH)
    reports = read_csv(REPORTS_PATH)
    report_by_id = {row["report_id"]: row for row in reports}

    if not rows:
        warnings.append("EMPTY_QUEUE: no OOV candidates found; acceptable only if Arabizi coverage is intentionally small")
        return finish(errors, warnings)

    cols = set(rows[0].keys())
    missing_cols = REQUIRED_COLUMNS - cols
    if missing_cols:
        add_error(errors, "QUEUE_COLUMNS", f"Missing columns: {sorted(missing_cols)}")

    candidate_ids = set()
    token_keys = set()
    for row in rows:
        candidate_id = row["candidate_id"]
        batch = row["batch"]
        token = row["normalized_token"]
        review_status = row["review_status"]
        suggested_action = row["suggested_action"]
        decision = row["decision"]

        match = CANDIDATE_ID_RE.match(candidate_id)
        if not match:
            add_error(errors, "CANDIDATE_ID", f"{candidate_id} must match OOV-BNNN-NNN")
        elif batch != match.group(1):
            add_error(errors, "CANDIDATE_BATCH", f"{candidate_id} has batch={batch}, expected {match.group(1)}")

        if candidate_id in candidate_ids:
            add_error(errors, "DUPLICATE_CANDIDATE", f"Duplicate candidate_id={candidate_id}")
        candidate_ids.add(candidate_id)

        token_key = (batch, token)
        if token_key in token_keys:
            add_error(errors, "DUPLICATE_TOKEN", f"{batch} token {token!r} appears more than once")
        token_keys.add(token_key)

        if not TOKEN_RE.match(token):
            add_error(errors, "TOKEN_FORMAT", f"{candidate_id} normalized_token={token!r} must be lowercase a-z/0-9")
        if token != token.lower():
            add_error(errors, "TOKEN_CASE", f"{candidate_id} normalized_token must be lowercase")
        if not row["raw_variants"].strip():
            add_error(errors, "RAW_VARIANTS", f"{candidate_id} has empty raw_variants")
        if row["risk_hint"] not in VALID_RISK_HINTS:
            add_error(errors, "RISK_HINT", f"{candidate_id} invalid risk_hint={row['risk_hint']}")
        if review_status not in VALID_REVIEW_STATUSES:
            add_error(errors, "REVIEW_STATUS", f"{candidate_id} invalid review_status={review_status}")
        if suggested_action not in VALID_ACTIONS - {""}:
            add_error(errors, "SUGGESTED_ACTION", f"{candidate_id} invalid suggested_action={suggested_action}")
        if decision not in VALID_ACTIONS:
            add_error(errors, "DECISION", f"{candidate_id} invalid decision={decision}")

        try:
            frequency = int(row["frequency"])
            report_count = int(row["report_count"])
        except ValueError:
            add_error(errors, "COUNTS", f"{candidate_id} frequency/report_count must be integers")
            continue
        if frequency < report_count or report_count < 1:
            add_error(errors, "COUNTS", f"{candidate_id} has frequency={frequency}, report_count={report_count}")

        report_ids = [item for item in row["report_ids"].split("|") if item]
        if len(set(report_ids)) != report_count:
            add_error(errors, "REPORT_COUNT", f"{candidate_id} report_count does not match report_ids")
        for report_id in report_ids:
            report = report_by_id.get(report_id)
            if not report:
                add_error(errors, "REPORT_ID", f"{candidate_id} references unknown report {report_id}")
            elif report["language"] not in {"arabizi", "mixed"}:
                add_error(errors, "REPORT_LANGUAGE", f"{candidate_id} references non-Arabizi report {report_id}")
        if row["example_report_id"] not in report_by_id:
            add_error(errors, "EXAMPLE_REPORT", f"{candidate_id} example_report_id missing")

        sector = row["proposed_sector"]
        issue_type = row["proposed_issue_type"]
        if sector and sector not in ISSUE_TYPES_BY_SECTOR:
            add_error(errors, "PROPOSED_SECTOR", f"{candidate_id} invalid proposed_sector={sector}")
        if issue_type and (not sector or issue_type not in ISSUE_TYPES_BY_SECTOR.get(sector, set())):
            add_error(errors, "PROPOSED_ISSUE", f"{candidate_id} invalid proposed issue {sector}/{issue_type}")

        reviewer_id = row["reviewer_id"].strip()
        if review_status == "REVIEWED":
            if not reviewer_id or reviewer_id == "UNASSIGNED":
                add_error(errors, "REVIEWED_WITHOUT_REVIEWER", f"{candidate_id} reviewed without reviewer_id")
            if not decision:
                add_error(errors, "REVIEWED_WITHOUT_DECISION", f"{candidate_id} reviewed without decision")
            if decision == "ADD_TO_VOCAB" and (not sector or not issue_type):
                add_error(errors, "VOCAB_ACCEPTANCE_TARGET", f"{candidate_id} ADD_TO_VOCAB requires sector and issue_type")
        elif review_status == "PENDING_REVIEW":
            if decision:
                add_error(errors, "PENDING_WITH_DECISION", f"{candidate_id} is pending review but already has decision={decision}")
        elif review_status == "DISPUTED" and not row["notes"].strip():
            add_error(errors, "DISPUTED_WITHOUT_NOTES", f"{candidate_id} is disputed without notes")

    return finish(errors, warnings)


def finish(errors: list[str], warnings: list[str]) -> int:
    for warning in warnings:
        print(f"WARNING {warning}")
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        print(f"FAILED: {len(errors)} errors, {len(warnings)} warnings")
        return 1
    print(f"OK: Arabizi OOV queue validation passed with {len(warnings)} warnings")
    return 0


if __name__ == "__main__":
    sys.exit(validate())

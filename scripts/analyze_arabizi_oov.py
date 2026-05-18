import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.shared.arabizi_lexical_policy import (  # noqa: E402
    CONNECTORISH_SUFFIXES,
    HIGH_RISK_HINTS,
    IGNORED_OOV_TOKENS,
    PROPER_OR_ENTITY_TOKENS,
    STOPWORDS,
)

REPORTS_PATH = ROOT / "data" / "corpus" / "cedarfix_reports_v1.csv"
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "corpus" / "arabizi_oov_review_queue_v1.csv"

TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
ARABIZI_MARKER_RE = re.compile(r"[235789]")
PAIR_RE = re.compile(r"^RPT-(B\d{3})-\d{3}$")
OOV_ID_RE = re.compile(r"^OOV-(B\d{3})-(\d{3})$")

FIELDNAMES = [
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
]

def normalise_token(token: str) -> str:
    token = token.lower().strip()
    token = re.sub(r"[^a-z0-9]", "", token)
    token = re.sub(r"[0146]+$", "", token)
    token = re.sub(r"([a-z0-9])\1{3,}", r"\1\1", token)
    return token


def tokenize(text: str) -> list[str]:
    return [normalise_token(match.group(0)) for match in TOKEN_RE.finditer(text)]


def load_reports() -> list[dict[str, str]]:
    with REPORTS_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def iter_vocab_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_vocab_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_vocab_strings(item)


def load_known_tokens() -> set[str]:
    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8-sig"))
    known: set[str] = set()
    for text in iter_vocab_strings(vocab.get("arabizi_notes", {})):
        known.update(token for token in tokenize(text) if token)
    for sector in vocab.get("sectors", {}).values():
        for section in ("issue_type_keywords", "sample_complaints", "catch_all_phrases", "issue_type_aliases"):
            for text in iter_vocab_strings(sector.get(section, {})):
                known.update(token for token in tokenize(text) if token)
    return known | STOPWORDS | PROPER_OR_ENTITY_TOKENS


def looks_like_meaningful_oov(token: str) -> bool:
    if not token or len(token) < 3:
        return False
    if token in IGNORED_OOV_TOKENS:
        return False
    if token.isdigit():
        return False
    if len(token) <= 4 and token.endswith(CONNECTORISH_SUFFIXES):
        return False
    if ARABIZI_MARKER_RE.search(token):
        return True
    if re.search(r"(gh|kh|sh|ou|aw|ay|iy|ee|aa)", token):
        return True
    return len(token) >= 5


def dominant(values: list[str]) -> tuple[str, float]:
    counts = Counter(v for v in values if v)
    if not counts:
        return "", 0.0
    value, count = counts.most_common(1)[0]
    return value, count / len(values)


def batch_from_report_id(report_id: str) -> str:
    match = PAIR_RE.match(report_id)
    return match.group(1) if match else "BUNK"


def risk_hint_for(token: str, reports: list[dict[str, str]]) -> str:
    if token in HIGH_RISK_HINTS or any(hint in token for hint in HIGH_RISK_HINTS):
        return "SAFETY_LEXICAL_HINT"
    if any(row["severity"] == "CRITICAL" or row["public_safety"].lower() == "true" for row in reports):
        return "HIGH_IMPACT_CONTEXT"
    if any(row["hitl_required"].lower() == "true" for row in reports):
        return "HITL_CONTEXT"
    return "LANGUAGE_DRIFT"


def suggested_action_for(token: str, frequency: int, issue_share: float, risk_hint: str) -> str:
    if risk_hint in {"SAFETY_LEXICAL_HINT", "HIGH_IMPACT_CONTEXT"}:
        return "ADD_TO_VOCAB"
    if frequency >= 2 and issue_share >= 0.60:
        return "ADD_TO_VOCAB"
    if frequency >= 2:
        return "KEEP_MODEL_ONLY"
    return "NEEDS_MORE_EXAMPLES"


def build_queue(min_count: int) -> list[dict[str, str]]:
    reports = [row for row in load_reports() if row["language"] in {"arabizi", "mixed"}]
    known_tokens = load_known_tokens()

    occurrences: dict[str, list[tuple[str, str, dict[str, str]]]] = defaultdict(list)
    for row in reports:
        raw_text = row["raw_text"]
        for raw_token in TOKEN_RE.findall(raw_text.lower()):
            token = normalise_token(raw_token)
            if token in known_tokens or not looks_like_meaningful_oov(token):
                continue
            occurrences[token].append((raw_token, raw_text, row))

    rows: list[dict[str, str]] = []
    grouped_by_batch: dict[str, list[tuple[str, list[tuple[str, str, dict[str, str]]]]]] = defaultdict(list)
    for token, token_occurrences in occurrences.items():
        report_ids = {row["report_id"] for _, _, row in token_occurrences}
        if len(token_occurrences) < min_count:
            continue
        batch = sorted({batch_from_report_id(report_id) for report_id in report_ids})[0]
        grouped_by_batch[batch].append((token, token_occurrences))

    for batch, batch_items in sorted(grouped_by_batch.items()):
        for index, (token, token_occurrences) in enumerate(
            sorted(batch_items, key=lambda item: (-len(item[1]), item[0])),
            start=1,
        ):
            rows_for_token = [row for _, _, row in token_occurrences]
            first_raw, first_text, first_row = token_occurrences[0]
            sectors = [row["sector"] for row in rows_for_token]
            issue_types = [row["issue_type"] for row in rows_for_token]
            proposed_sector, sector_share = dominant(sectors)
            proposed_issue_type, issue_share = dominant(issue_types)
            if sector_share < 0.60:
                proposed_sector = ""
            if issue_share < 0.60:
                proposed_issue_type = ""

            risk_hint = risk_hint_for(token, rows_for_token)
            report_ids = sorted({row["report_id"] for row in rows_for_token})
            raw_variants = sorted({raw for raw, _, _ in token_occurrences})
            rows.append(
                {
                    "candidate_id": f"OOV-{batch}-{index:03d}",
                    "batch": batch,
                    "normalized_token": token,
                    "raw_variants": "|".join(raw_variants),
                    "frequency": str(len(token_occurrences)),
                    "report_count": str(len(report_ids)),
                    "report_ids": "|".join(report_ids),
                    "example_report_id": first_row["report_id"],
                    "example_text": first_text,
                    "proposed_sector": proposed_sector,
                    "proposed_issue_type": proposed_issue_type,
                    "risk_hint": risk_hint,
                    "suggested_action": suggested_action_for(token, len(token_occurrences), issue_share, risk_hint),
                    "reviewer_id": "UNASSIGNED",
                    "review_status": "PENDING_REVIEW",
                    "decision": "",
                    "notes": f"Generated from raw variant {first_raw!r}; review before changing vocabulary.",
                }
            )
    return rows


def read_existing_reviews(output_path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not output_path.exists():
        return {}
    with output_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {
        (row.get("batch", ""), row.get("normalized_token", "")): row
        for row in rows
        if row.get("batch") and row.get("normalized_token")
    }


def read_existing_review_rows(output_path: Path) -> list[dict[str, str]]:
    if not output_path.exists():
        return []
    with output_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def next_candidate_ids(existing_rows: list[dict[str, str]]) -> dict[str, int]:
    next_by_batch: dict[str, int] = defaultdict(lambda: 1)
    for row in existing_rows:
        match = OOV_ID_RE.match(row.get("candidate_id", ""))
        if not match:
            continue
        batch, index = match.group(1), int(match.group(2))
        next_by_batch[batch] = max(next_by_batch[batch], index + 1)
    return next_by_batch


def sort_key(row: dict[str, str]) -> tuple[str, int, str]:
    match = OOV_ID_RE.match(row.get("candidate_id", ""))
    if match:
        return match.group(1), int(match.group(2)), row.get("normalized_token", "")
    return row.get("batch", ""), 999_999, row.get("normalized_token", "")


def preserve_review_state(rows: list[dict[str, str]], output_path: Path) -> list[dict[str, str]]:
    existing_rows = read_existing_review_rows(output_path)
    existing_by_token = {
        (row.get("batch", ""), row.get("normalized_token", "")): row
        for row in existing_rows
        if row.get("batch") and row.get("normalized_token")
    }
    next_id_by_batch = next_candidate_ids(existing_rows)
    preserved: list[dict[str, str]] = []
    generated_keys: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["batch"], row["normalized_token"])
        generated_keys.add(key)
        existing = existing_by_token.get(key)
        if existing and existing.get("review_status") != "PENDING_REVIEW":
            row = {
                **row,
                "candidate_id": existing.get("candidate_id", row["candidate_id"]),
                "proposed_sector": existing.get("proposed_sector", row["proposed_sector"]),
                "proposed_issue_type": existing.get("proposed_issue_type", row["proposed_issue_type"]),
                "suggested_action": existing.get("suggested_action", row["suggested_action"]),
                "reviewer_id": existing.get("reviewer_id", row["reviewer_id"]),
                "review_status": existing.get("review_status", row["review_status"]),
                "decision": existing.get("decision", row["decision"]),
                "notes": existing.get("notes", row["notes"]),
            }
        elif not existing:
            batch = row["batch"]
            row = {**row, "candidate_id": f"OOV-{batch}-{next_id_by_batch[batch]:03d}"}
            next_id_by_batch[batch] += 1
        preserved.append(row)

    for existing in existing_rows:
        key = (existing.get("batch", ""), existing.get("normalized_token", ""))
        if key in generated_keys:
            continue
        if existing.get("review_status") == "PENDING_REVIEW":
            continue
        preserved.append({field: existing.get(field, "") for field in FIELDNAMES})

    return sorted(preserved, key=sort_key)


def write_queue(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> int:
    cases = {
        "5tr444444": "5tr",
        "mniiiii7": "mnii7",
        "jora!!!": "jora",
        "M5ATRA": "m5atra",
    }
    failures = []
    for raw, expected in cases.items():
        actual = normalise_token(raw)
        if actual != expected:
            failures.append(f"{raw!r}: expected {expected!r}, got {actual!r}")
    if failures:
        for failure in failures:
            print(f"ERROR SELF_TEST: {failure}")
        return 1
    print("OK: Arabizi OOV analyzer self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build CedarFix Arabizi OOV/drift review queue.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--min-count", type=int, default=1)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.min_count < 1:
        print("ERROR: --min-count must be >= 1")
        return 1

    rows = preserve_review_state(build_queue(args.min_count), args.output)
    write_queue(rows, args.output)
    print(f"OK: wrote {len(rows)} Arabizi OOV candidates to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

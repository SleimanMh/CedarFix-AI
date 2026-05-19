"""
promote_arabizi_candidates.py

Safely promotes reviewed Arabizi candidates into the production vocabulary.

The script is intentionally conservative:
  - dry-run is the default
  - approved rows must have a reviewer_id and a concrete promotion_target
  - issue_type keys are mapped to the lowercase production vocabulary schema
  - unknown issue types are rejected, never auto-created
  - a temporary vocabulary is validated before production is touched
  - apply mode writes a timestamped backup before replacing production
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BANK_PATH = ROOT / "data/knowledge_base/arabizi/arabizi_candidate_bank.csv"
DEFAULT_STOPLIST_PATH = ROOT / "data/knowledge_base/arabizi/arabizi_reliability_layer.json"
DEFAULT_VOCAB_PATH = ROOT / "data/knowledge_base/arabizi_vocabulary.json"
DEFAULT_AUDIT_PATH = ROOT / "data/knowledge_base/arabizi/arabizi_reviewed_changes.csv"
VALIDATE_SCRIPT = ROOT / "scripts/validate_arabizi_vocabulary.py"

VALID_SECTORS = {"ROADS", "WATER", "ELECTRICITY", "WASTE", "FLOODING", "SAFETY"}
PROMOTE_DECISIONS = {"APPROVE", "PROMOTE_TO_CORE"}


def utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_stoplist(path: Path) -> frozenset[str]:
    if not path.exists():
        return frozenset()
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        terms: set[str] = set()
        for row in data.get("stoplist", []):
            terms.add((row.get("term") or "").strip().lower())
            terms.add((row.get("normalized_term") or "").strip().lower())
        terms.discard("")
        return frozenset(terms)
    with open(path, encoding="utf-8") as f:
        terms = set()
        for row in csv.DictReader(f):
            terms.add((row.get("term") or "").strip().lower())
            terms.add((row.get("normalized_term") or "").strip().lower())
        terms.discard("")
        return frozenset(terms)


def load_candidates(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"candidate bank not found: {path}")
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_vocab(path: Path) -> dict:
    return json.loads(read_text(path))


def write_vocab(path: Path, vocab: dict) -> None:
    path.write_text(json.dumps(vocab, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_promotion_target(raw: str) -> tuple[str, str] | None:
    target = raw.strip().replace(".", "/")
    if not target or "/" not in target:
        return None
    sector, issue_type = [part.strip() for part in target.split("/", 1)]
    if not sector or not issue_type:
        return None
    return sector.upper(), issue_type.lower()


def run_vocab_validator(vocab_path: Path) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT), "--vocab-path", str(vocab_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.returncode == 0, f"{result.stdout}{result.stderr}".strip()


def next_change_id(audit_path: Path) -> int:
    if not audit_path.exists():
        return 1
    with open(audit_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return 1
    last = rows[-1].get("change_id", "CHG-0000")
    try:
        return int(last.split("-")[-1]) + 1
    except (ValueError, IndexError):
        return len(rows) + 1


def append_audit(audit_path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    fieldnames = [
        "change_id",
        "batch_id",
        "date",
        "action",
        "term",
        "sector",
        "issue_type",
        "old_value",
        "new_value",
        "reason",
        "reviewer_id",
        "decision",
        "created_at",
        "before_vocab_hash",
        "after_vocab_hash",
    ]
    write_header = not audit_path.exists() or audit_path.stat().st_size == 0
    with open(audit_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def build_changes(
    candidates: list[dict[str, str]],
    vocab: dict,
    stoplist: frozenset[str],
    verbose: bool = False,
) -> tuple[dict, list[dict[str, str]], list[str], int]:
    updated_vocab = json.loads(json.dumps(vocab, ensure_ascii=False))
    skipped: list[str] = []
    change_rows: list[dict[str, str]] = []
    token_count = 0

    production_tokens: dict[str, dict[str, set[str]]] = {}
    for sector, sector_data in updated_vocab.get("sectors", {}).items():
        production_tokens[sector] = {}
        for issue_type, tokens in sector_data.get("issue_type_keywords", {}).items():
            production_tokens[sector][issue_type] = {str(token).lower() for token in tokens}

    eligible = [
        row
        for row in candidates
        if row.get("review_status", "").strip().upper() == "APPROVED"
        and row.get("decision", "").strip().upper() in PROMOTE_DECISIONS
    ]

    for row in eligible:
        cid = row.get("candidate_id", "").strip() or "<missing-id>"
        reviewer = row.get("reviewer_id", "").strip()
        if not reviewer:
            skipped.append(f"{cid}: APPROVED promotion row missing reviewer_id")
            continue

        target = parse_promotion_target(row.get("promotion_target", ""))
        if target is None:
            skipped.append(f"{cid}: missing/invalid promotion_target")
            continue

        sector, issue_type = target
        if sector not in VALID_SECTORS:
            skipped.append(f"{cid}: invalid promotion sector={sector}")
            continue
        if sector not in updated_vocab.get("sectors", {}):
            skipped.append(f"{cid}: sector {sector} not in vocabulary")
            continue
        if issue_type not in updated_vocab["sectors"][sector].get("issue_type_keywords", {}):
            skipped.append(f"{cid}: issue_type {sector}/{issue_type} is not in production taxonomy")
            continue

        if row.get("sector", "").strip().upper() == "ALL" or row.get("issue_type", "").strip().upper() == "ALL":
            skipped.append(f"{cid}: ALL sector/issue_type rows cannot be promoted to production")
            continue

        variants = [variant.strip() for variant in row.get("variants", "").split(";") if variant.strip()]
        if not variants:
            skipped.append(f"{cid}: no variants to promote")
            continue

        blocked = [variant for variant in variants if variant.lower() in stoplist]
        if blocked:
            skipped.append(f"{cid}: stoplist variants blocked: {blocked}")
            continue

        existing = production_tokens[sector][issue_type]
        new_tokens = [variant for variant in variants if variant.lower() not in existing]
        if not new_tokens:
            skipped.append(f"{cid}: all variants already in vocabulary")
            continue

        if verbose:
            print(f"  PROMOTE {cid} -> {sector}/{issue_type}: {new_tokens}")

        keyword_list = updated_vocab["sectors"][sector]["issue_type_keywords"][issue_type]
        keyword_list.extend(new_tokens)
        existing.update(token.lower() for token in new_tokens)
        token_count += len(new_tokens)
        change_rows.append(
            {
                "candidate_id": cid,
                "term": ";".join(new_tokens),
                "sector": sector,
                "issue_type": issue_type,
                "old_value": "(not in vocab)",
                "new_value": ";".join(new_tokens),
                "reason": f"Approved by {reviewer}; candidate_id={cid}",
                "reviewer_id": reviewer,
                "decision": "PROMOTE_TO_CORE",
            }
        )

    if not eligible:
        skipped.append("no APPROVED + promotion-decision rows found")

    return updated_vocab, change_rows, skipped, token_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote approved Arabizi candidates to vocabulary.")
    parser.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    parser.add_argument("--apply", action="store_true", help="Write validated changes to vocabulary")
    parser.add_argument("--verbose", action="store_true", help="Print each token added")
    parser.add_argument("--candidate-bank", type=Path, default=DEFAULT_BANK_PATH)
    parser.add_argument("--vocab-path", type=Path, default=DEFAULT_VOCAB_PATH)
    parser.add_argument("--review-log", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--stoplist-path", type=Path, default=DEFAULT_STOPLIST_PATH)
    args = parser.parse_args()

    dry = not args.apply
    if args.apply and args.dry_run:
        print("FATAL: use either --dry-run or --apply, not both")
        sys.exit(2)

    try:
        candidates = load_candidates(args.candidate_bank)
        vocab = load_vocab(args.vocab_path)
        stoplist = load_stoplist(args.stoplist_path)
    except Exception as exc:
        print(f"FATAL: {exc}")
        sys.exit(1)

    before_text = read_text(args.vocab_path)
    before_hash = sha256_text(before_text)
    updated_vocab, pending_audit_rows, skipped, token_count = build_changes(
        candidates, vocab, stoplist, verbose=args.verbose
    )

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(json.dumps(updated_vocab, ensure_ascii=False, indent=2) + "\n")

    validator_ok, validator_output = run_vocab_validator(tmp_path)
    tmp_path.unlink(missing_ok=True)

    print(f"\n[{'DRY RUN' if dry else 'APPLY'}] Promotion summary")
    print(f"  Candidate rows: {len(candidates)}")
    print(f"  Tokens to add:  {token_count}")
    print(f"  Skipped:        {len(skipped)}")
    for reason in skipped:
        print(f"    - {reason}")
    print(f"  Temp validator: {'OK' if validator_ok else 'FAILED'}")
    if validator_output and not validator_ok:
        print(validator_output)

    if not validator_ok:
        print("FATAL: candidate promotion would produce invalid vocabulary; production untouched.")
        sys.exit(1)

    if dry:
        print("\n  (Use --apply to write validated changes)")
        return

    if token_count == 0:
        print("\n  No production changes to apply.")
        return

    backup_path = args.vocab_path.with_suffix(args.vocab_path.suffix + f".bak-{utc_timestamp().replace(':', '')}")
    shutil.copy2(args.vocab_path, backup_path)
    print(f"\n  Backup written: {backup_path.relative_to(ROOT)}")

    write_vocab(args.vocab_path, updated_vocab)
    after_text = read_text(args.vocab_path)
    after_hash = sha256_text(after_text)

    validator_ok, validator_output = run_vocab_validator(args.vocab_path)
    if not validator_ok:
        shutil.copy2(backup_path, args.vocab_path)
        print("FATAL: production validator failed after write; backup restored.")
        if validator_output:
            print(validator_output)
        sys.exit(1)

    change_num = next_change_id(args.review_log)
    now = utc_timestamp()
    audit_rows = []
    for row in pending_audit_rows:
        audit_rows.append(
            {
                "change_id": f"CHG-{change_num:04d}",
                "batch_id": "PROMOTE-01",
                "date": now[:10],
                "action": "PROMOTE",
                "created_at": now,
                "before_vocab_hash": before_hash,
                "after_vocab_hash": after_hash,
                **row,
            }
        )
        change_num += 1
    append_audit(args.review_log, audit_rows)
    print("  Production validator OK")
    print(f"  Appended {len(audit_rows)} change(s) to {args.review_log.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

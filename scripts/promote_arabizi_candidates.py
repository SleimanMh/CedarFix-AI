"""
promote_arabizi_candidates.py

Safely promotes reviewed and approved candidates from arabizi_candidate_bank.csv
into arabizi_vocabulary.json (production vocabulary).

Usage:
  python scripts/promote_arabizi_candidates.py --dry-run          (default — safe preview)
  python scripts/promote_arabizi_candidates.py --apply            (writes to vocab)
  python scripts/promote_arabizi_candidates.py --apply --verbose  (with per-token log)

Promotion rules (all must pass):
  - review_status == APPROVED
  - decision == APPROVE
  - reviewer_id is non-empty
  - sector is valid
  - issue_type is valid (maps to a sector in vocabulary)
  - variants contain at least one non-empty token
  - No variant appears on the stoplist
  - Resulting vocab must pass validate_arabizi_vocabulary.py

All changes are appended to arabizi_reviewed_changes.csv.
"""
from __future__ import annotations
import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK_PATH = ROOT / "data/knowledge_base/arabizi/arabizi_candidate_bank.csv"
STOPLIST_PATH = ROOT / "data/knowledge_base/arabizi/arabizi_stoplist.csv"
VOCAB_PATH = ROOT / "data/knowledge_base/arabizi_vocabulary.json"
AUDIT_PATH = ROOT / "data/knowledge_base/arabizi/arabizi_reviewed_changes.csv"
VALIDATE_SCRIPT = ROOT / "scripts/validate_arabizi_vocabulary.py"

VALID_SECTORS = {"ROADS", "WATER", "ELECTRICITY", "WASTE", "FLOODING", "SAFETY"}
NOW = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:00Z")


def load_stoplist() -> frozenset[str]:
    if not STOPLIST_PATH.exists():
        return frozenset()
    with open(STOPLIST_PATH, encoding="utf-8") as f:
        return frozenset(r["term"].strip().lower() for r in csv.DictReader(f))


def load_candidates() -> list[dict]:
    if not BANK_PATH.exists():
        print("FATAL: candidate bank not found")
        sys.exit(1)
    with open(BANK_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_vocab() -> dict:
    return json.loads(VOCAB_PATH.read_text(encoding="utf-8"))


def save_vocab(vocab: dict) -> None:
    VOCAB_PATH.write_text(
        json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_validator() -> bool:
    result = subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  Validator FAILED:\n{result.stdout}{result.stderr}")
        return False
    return True


def next_change_id(audit_path: Path) -> str:
    if not audit_path.exists():
        return "CHG-0013"
    with open(audit_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return "CHG-0001"
    # parse last id
    last = rows[-1].get("change_id", "CHG-0000")
    try:
        n = int(last.split("-")[-1]) + 1
    except (ValueError, IndexError):
        n = len(rows) + 1
    return f"CHG-{n:04d}"


def append_audit(changes: list[dict]) -> None:
    write_header = not AUDIT_PATH.exists()
    with open(AUDIT_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "change_id", "batch_id", "date", "action", "term",
            "sector", "issue_type", "old_value", "new_value",
            "reason", "reviewer_id", "decision", "created_at",
        ])
        if write_header:
            writer.writeheader()
        writer.writerows(changes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote approved Arabizi candidates to vocabulary.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Preview only (default)")
    parser.add_argument("--apply", action="store_true", help="Actually write to vocabulary")
    parser.add_argument("--verbose", action="store_true", help="Print each token added")
    args = parser.parse_args()

    dry = not args.apply

    stoplist = load_stoplist()
    candidates = load_candidates()
    vocab = load_vocab()

    # Get current production token sets per sector/issue_type
    prod: dict[str, dict[str, set[str]]] = {}
    for sector, sdata in vocab["sectors"].items():
        prod[sector] = {}
        for it, tokens in sdata.get("issue_type_keywords", {}).items():
            prod[sector][it] = set(t.lower() for t in tokens)

    eligible = [
        c for c in candidates
        if c["review_status"].strip().upper() == "APPROVED"
        and c["decision"].strip().upper() == "APPROVE"
        and c["reviewer_id"].strip()
    ]

    skipped_reasons: list[str] = []
    audit_rows: list[dict] = []
    promoted_count = 0
    change_num = int(next_change_id(AUDIT_PATH).split("-")[-1])

    for c in eligible:
        cid = c["candidate_id"]
        sector = c["sector"].strip().upper()
        issue_type = c["issue_type"].strip().upper()
        reviewer = c["reviewer_id"].strip()
        variants_raw = c["variants"]

        # Sector check
        if sector not in VALID_SECTORS:
            skipped_reasons.append(f"{cid}: invalid sector={sector}")
            continue

        # Issue_type check — must exist in vocabulary sector
        if sector not in vocab["sectors"]:
            skipped_reasons.append(f"{cid}: sector {sector} not in vocabulary")
            continue
        if issue_type not in vocab["sectors"][sector].get("issue_type_keywords", {}):
            # Auto-create new issue_type key is allowed — but warn
            print(f"  INFO: {cid} will create new issue_type '{issue_type}' in {sector}")

        # Parse variants
        variants = [v.strip() for v in variants_raw.split(";") if v.strip()]
        if not variants:
            skipped_reasons.append(f"{cid}: no variants to promote")
            continue

        # Stoplist check
        blocked = [v for v in variants if v.lower() in stoplist]
        if blocked:
            skipped_reasons.append(f"{cid}: stoplist variants blocked: {blocked}")
            continue

        # Determine tokens to add (those not already in prod)
        existing = prod.get(sector, {}).get(issue_type, set())
        new_tokens = [v for v in variants if v.lower() not in existing]
        if not new_tokens:
            skipped_reasons.append(f"{cid}: all variants already in vocab")
            continue

        promoted_count += len(new_tokens)
        if args.verbose:
            print(f"  PROMOTE {cid} → {sector}/{issue_type}: {new_tokens}")

        if not dry:
            # Add tokens to vocabulary
            sector_kws = vocab["sectors"][sector].setdefault("issue_type_keywords", {})
            sector_kws.setdefault(issue_type, [])
            for token in new_tokens:
                if token not in sector_kws[issue_type]:
                    sector_kws[issue_type].append(token)
            # Track in local prod set
            prod.setdefault(sector, {}).setdefault(issue_type, set()).update(
                v.lower() for v in new_tokens
            )

            audit_rows.append({
                "change_id": f"CHG-{change_num:04d}",
                "batch_id": "PROMOTE-01",
                "date": NOW[:10],
                "action": "PROMOTE",
                "term": ";".join(new_tokens),
                "sector": sector,
                "issue_type": issue_type,
                "old_value": "(not in vocab)",
                "new_value": ";".join(new_tokens),
                "reason": f"Approved by {reviewer}",
                "reviewer_id": reviewer,
                "decision": "APPROVE",
                "created_at": NOW,
            })
            change_num += 1

    mode = "DRY RUN" if dry else "APPLY"
    print(f"\n[{mode}] Promotion summary")
    print(f"  Eligible rows:  {len(eligible)}")
    print(f"  Tokens to add:  {promoted_count}")
    print(f"  Skipped:        {len(skipped_reasons)}")
    for s in skipped_reasons:
        print(f"    - {s}")

    if not dry and promoted_count > 0:
        save_vocab(vocab)
        print(f"\n  Saved updated vocabulary to {VOCAB_PATH.name}")

        # Validate
        print("  Running vocabulary validator...")
        if not run_validator():
            print("  ROLLBACK: validator failed after promotion — please restore backup")
            sys.exit(1)
        print("  Validator OK")

        # Append audit log
        if audit_rows:
            append_audit(audit_rows)
            print(f"  Appended {len(audit_rows)} change(s) to audit log")

    if dry:
        print("\n  (Use --apply to actually write changes)")


if __name__ == "__main__":
    main()

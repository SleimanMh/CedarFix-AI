"""
apply_v10_1_variant_patches.py
-------------------------------
Applies reviewed variant enrichments from v10_1_candidate_bank_variant_patch_plan.csv
to arabizi_candidate_bank.csv.

SAFETY RULES:
  - Never creates new rows in the candidate bank.
  - Never touches rows still in PENDING_NATIVE_REVIEW status.
  - Deduplicates variant tokens before appending.
  - Dry-run by default (no writes unless --apply is passed).
  - Never routes, never sets severity.

Usage:
  python scripts/apply_v10_1_variant_patches.py            # dry-run (default)
  python scripts/apply_v10_1_variant_patches.py --apply    # apply approved patches

A patch row is eligible when its review_status is APPROVED (or APPROVED_PARTIAL).
To approve a row, open the patch plan CSV and change the review_status field to APPROVED.
"""

import csv
import sys
import datetime
import io
from pathlib import Path

BANK_PATH = Path("data/knowledge_base/arabizi/arabizi_candidate_bank.csv")
PATCH_PLAN_PATH = Path("data/knowledge_base/arabizi/v10_1_candidate_bank_variant_patch_plan.csv")

APPROVED_STATUSES = {"APPROVED", "APPROVED_PARTIAL"}
PENDING = "PENDING_NATIVE_REVIEW"

DRY_RUN = "--apply" not in sys.argv


def load_bank():
    rows = list(csv.DictReader(BANK_PATH.open(encoding="utf-8-sig")))
    # Index by candidate_id
    index = {r["candidate_id"]: r for r in rows}
    return rows, index


def load_patches():
    return list(csv.DictReader(PATCH_PLAN_PATH.open(encoding="utf-8-sig")))


def existing_variant_tokens(bank_row):
    """Return the set of lowercase variant tokens already in this bank row."""
    return set(
        v.strip().lower()
        for v in bank_row["variants"].split(";")
        if v.strip()
    )


def parse_pipe_variants(pipe_str):
    """Split a pipe-separated variant string into a list of non-empty stripped tokens."""
    return [v.strip() for v in pipe_str.split("|") if v.strip()]


def compute_new_variants(patch_row, bank_row):
    """
    Return sorted list of net-new variant tokens from this patch that are
    not already present in the bank row's variants.

    Only uses safe_unique and reliable_alt pools (not context_only).
    """
    existing = existing_variant_tokens(bank_row)
    candidates = (
        parse_pipe_variants(patch_row["v10_safe_unique_variants_pipe"])
        + parse_pipe_variants(patch_row["v10_reliable_alt_review_variants_pipe"])
    )
    seen = set()
    net_new = []
    for tok in candidates:
        key = tok.lower()
        if key not in existing and key not in seen:
            net_new.append(tok)
            seen.add(key)
    return net_new


def main():
    bank_rows, bank_index = load_bank()
    patches = load_patches()

    eligible   = [p for p in patches if p["review_status"] in APPROVED_STATUSES]
    pending    = [p for p in patches if p["review_status"] == PENDING]
    other      = [p for p in patches if p["review_status"] not in APPROVED_STATUSES | {PENDING}]

    print(f"=== apply_v10_1_variant_patches {'DRY-RUN' if DRY_RUN else 'APPLY'} ===")
    print(f"Patch plan rows total : {len(patches)}")
    print(f"  Approved (eligible) : {len(eligible)}")
    print(f"  Pending (skipped)   : {len(pending)}")
    print(f"  Other status        : {len(other)}")
    print()

    if not eligible:
        print("No approved patches found. Nothing to apply.")
        print(f"To approve a patch, open {PATCH_PLAN_PATH} and set review_status to APPROVED.")
        return

    applied_count = 0
    skipped_count = 0
    today = datetime.date.today().isoformat()

    for patch in eligible:
        pid = patch["patch_id"]
        cid = patch["bank_candidate_id"]

        if cid not in bank_index:
            print(f"  [WARN] {pid}: bank_candidate_id {cid} not found in bank — skipped.")
            skipped_count += 1
            continue

        if patch["do_not_create_new_row"].upper() != "TRUE":
            print(f"  [WARN] {pid}: do_not_create_new_row != TRUE — skipped for safety.")
            skipped_count += 1
            continue

        bank_row = bank_index[cid]
        net_new = compute_new_variants(patch, bank_row)

        if not net_new:
            print(f"  [SKIP] {pid} → {cid}: no net-new variants after dedup.")
            skipped_count += 1
            continue

        current_variants = bank_row["variants"]
        new_variants_str = current_variants.rstrip(";") + ";" + ";".join(net_new)

        print(f"  {'[DRY] ' if DRY_RUN else '[APPLY] '}{pid} → {cid} ({bank_row['arabic_script']} / {bank_row['english']})")
        print(f"         adding: {'; '.join(net_new)}")
        print(f"         before: {current_variants}")
        print(f"         after : {new_variants_str}")

        if not DRY_RUN:
            bank_row["variants"] = new_variants_str
            bank_row["updated_at"] = today

        applied_count += 1

    print()
    if DRY_RUN:
        print(f"Dry-run complete. {applied_count} patches would be applied, {skipped_count} skipped.")
        print("Re-run with --apply to write changes.")
    else:
        if applied_count == 0:
            print("Nothing to write.")
            return

        # Write bank back preserving column order
        fieldnames = list(bank_rows[0].keys())
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(bank_rows)
        BANK_PATH.write_text(buf.getvalue(), encoding="utf-8")
        print(f"Applied {applied_count} patches ({skipped_count} skipped). Bank written to {BANK_PATH}")


if __name__ == "__main__":
    main()

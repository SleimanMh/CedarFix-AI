"""
absorb_v14_expansion_pack.py
V14 mega trusted expansion pack absorber.

Actions:
  1. Append 167 GWB rows (IDs GW0253-GW0419); normalize false_friend_risk medium→true
  2. Append 31 PC rows (skip 2 canonical dupes); renumber PC-V14-xxxx → PC-0079+
  3. Append 41 stoplist rows; add must_not_auto_promote=true

Safety guardrails:
  - NEVER edit HIGH_RISK_HINTS
  - NEVER modify any _merged_preview files
  - NEVER add collision-queue rows to GWB
  - all new GWB rows: must_not_auto_promote=true, blocked_uses contains routing
  - all new PC rows: must_not_auto_promote=true, reviewer_id=UNASSIGNED
  - all new stoplist rows: must_not_auto_promote=true

Run: python scripts/absorb_v14_expansion_pack.py
"""
import csv
import io
import json
import zipfile
import os
import sys
import datetime

ZIP_PATH = "arabizi_v14_mega_trusted_expansion_pack.zip"
PACK_PREFIX = "arabizi_v14_mega_trusted_expansion_pack/"

GWB_PATH = "data/knowledge_base/arabizi/arabizi_general_word_bank.csv"
PC_PATH  = "data/knowledge_base/arabizi/arabizi_protected_combos.csv"
SL_PATH  = "data/knowledge_base/arabizi/arabizi_stoplist.csv"
RL_PATH  = "data/knowledge_base/arabizi/arabizi_reliability_layer.json"

ABORT = False


def normalize_bool(val):
    """Normalize false_friend_risk: true/high/medium → 'true', false/low/'' → 'false'."""
    v = str(val).strip().lower()
    if v in ("true", "yes", "1", "high", "medium"):
        return "true"
    return "false"


def read_zip_csv(zf, filename):
    """Read a CSV from inside the zip; handle UTF-8 BOM."""
    raw = zf.read(PACK_PREFIX + filename).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw)))


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  Written: {path}  ({len(rows)} rows)")


# ── 1. GWB absorption ────────────────────────────────────────────────────────

def absorb_gwb(zf):
    print("\n=== GWB: absorbing V14 append-only rows ===")
    v14_rows = read_zip_csv(zf, "arabizi_general_word_bank_v14_mega_append_only.csv")
    cur_rows = read_csv(GWB_PATH)
    fieldnames = list(cur_rows[0].keys())

    cur_ids      = {r["word_id"] for r in cur_rows}
    cur_canonics = {r["romanized_canonical"].lower().strip() for r in cur_rows}

    skip_id    = 0
    skip_canon = 0
    skip_guard = 0
    normalized_ffr = 0
    appended   = 0
    new_rows   = []

    for r in v14_rows:
        wid    = r.get("word_id", "").strip()
        canon  = r.get("romanized_canonical", "").lower().strip()
        mnap   = r.get("must_not_auto_promote", "").strip().lower()
        blk    = r.get("blocked_uses", "").lower()

        # Safety checks
        if wid in cur_ids:
            print(f"  SKIP (id collision): {wid} | {r.get('english_gloss')}")
            skip_id += 1
            continue
        if canon in cur_canonics:
            print(f"  SKIP (canonical dupe): {canon} | {r.get('english_gloss')}")
            skip_canon += 1
            continue
        if mnap != "true":
            print(f"  ABORT (must_not_auto_promote != true): {wid}")
            skip_guard += 1
            continue
        if "routing" not in blk:
            print(f"  ABORT (routing missing from blocked_uses): {wid}")
            skip_guard += 1
            continue

        # Normalize false_friend_risk
        raw_ffr = r.get("false_friend_risk", "false").strip().lower()
        if raw_ffr not in ("true", "false"):
            r["false_friend_risk"] = normalize_bool(raw_ffr)
            normalized_ffr += 1

        # Ensure all fieldnames are present
        out = {f: r.get(f, "") for f in fieldnames}
        new_rows.append(out)
        cur_ids.add(wid)
        cur_canonics.add(canon)
        appended += 1

    all_rows = cur_rows + new_rows
    write_csv(GWB_PATH, all_rows, fieldnames)
    print(f"  GWB: {len(cur_rows)} existing + {appended} new = {len(all_rows)} total")
    print(f"  Skipped: {skip_id} id-dupes, {skip_canon} canonical-dupes, {skip_guard} guardrail-fails")
    print(f"  Normalized false_friend_risk: {normalized_ffr} rows (medium→true)")
    return appended


# ── 2. PC absorption ─────────────────────────────────────────────────────────

def absorb_pc(zf):
    print("\n=== PC: absorbing V14 suggestion rows ===")
    v14_rows = read_zip_csv(zf, "arabizi_protected_combos_v14_mega_suggestions.csv")
    cur_rows = read_csv(PC_PATH)
    fieldnames = list(cur_rows[0].keys())

    # Find highest current PC-NNNN number
    max_num = 0
    for r in cur_rows:
        cid = r.get("combo_id", "")
        if cid.startswith("PC-") and not cid.startswith("PC-V"):
            try:
                max_num = max(max_num, int(cid[3:]))
            except ValueError:
                pass
    next_num = max_num + 1

    cur_canonics = {r.get("romanized_canonical", "").lower().strip() for r in cur_rows}
    cur_ids      = {r.get("combo_id", "") for r in cur_rows}

    skip_canon = 0
    appended   = 0
    new_rows   = []

    for r in v14_rows:
        canon = r.get("romanized_canonical", "").lower().strip()
        mnap  = r.get("must_not_auto_promote", "").strip().lower()

        if canon in cur_canonics:
            print(f"  SKIP (canonical dupe): {canon} | {r.get('english_gloss')}")
            skip_canon += 1
            continue

        # Renumber ID to project scheme
        new_id = f"PC-{next_num:04d}"
        r["combo_id"] = new_id
        next_num += 1

        # Enforce guardrails
        r["must_not_auto_promote"] = "true"
        r["reviewer_id"]           = r.get("reviewer_id", "UNASSIGNED") or "UNASSIGNED"

        out = {f: r.get(f, "") for f in fieldnames}
        new_rows.append(out)
        cur_canonics.add(canon)
        appended += 1

    all_rows = cur_rows + new_rows
    write_csv(PC_PATH, all_rows, fieldnames)
    print(f"  PC: {len(cur_rows)} existing + {appended} new = {len(all_rows)} total")
    print(f"  Skipped: {skip_canon} canonical dupes")
    print(f"  New combo IDs: PC-{max_num+1:04d} through PC-{next_num-1:04d}")
    return appended


# ── 3. Stoplist absorption ───────────────────────────────────────────────────

def absorb_stoplist(zf):
    print("\n=== Stoplist: absorbing V14 support rows ===")
    v14_rows = read_zip_csv(zf, "arabizi_stoplist_support_v14_suggestions.csv")
    cur_rows = read_csv(SL_PATH)
    fieldnames = list(cur_rows[0].keys())   # 8 cols incl. must_not_auto_promote

    cur_terms = {r["term"].lower().strip() for r in cur_rows}
    cur_norms = {r["normalized_term"].lower().strip() for r in cur_rows}

    skip_term = 0
    appended  = 0
    new_rows  = []

    for r in v14_rows:
        term = r.get("term", "").lower().strip()
        norm = r.get("normalized_term", "").lower().strip()

        if term in cur_terms or norm in cur_norms:
            print(f"  SKIP (dupe): {term}")
            skip_term += 1
            continue

        # Add must_not_auto_promote (missing from V14 stoplist file)
        r["must_not_auto_promote"] = "true"

        out = {f: r.get(f, "") for f in fieldnames}
        new_rows.append(out)
        cur_terms.add(term)
        cur_norms.add(norm)
        appended += 1

    all_rows = cur_rows + new_rows
    write_csv(SL_PATH, all_rows, fieldnames)
    print(f"  Stoplist: {len(cur_rows)} existing + {appended} new = {len(all_rows)} total")
    print(f"  Skipped: {skip_term} dupes")
    return appended


# ── 4. Update reliability layer JSON ────────────────────────────────────────

def update_reliability_layer(gwb_count, pc_count, sl_count):
    print("\n=== Reliability Layer: updating metadata ===")
    with open(RL_PATH, encoding="utf-8") as f:
        rl = json.load(f)

    prev_version = rl.get("version", "")
    now_utc      = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    rl["version"]        = "v1.4-v14-mega-expansion"
    rl["updated_at_utc"] = now_utc

    # Update section_row_counts
    rl.setdefault("section_row_counts", {})
    rl["section_row_counts"]["general_word_bank_csv"]  = gwb_count
    rl["section_row_counts"]["protected_combos_csv"]   = pc_count
    rl["section_row_counts"]["stoplist"]               = sl_count

    # Update metadata.csv_file_registry (used by cross-file validator)
    rl.setdefault("metadata", {}).setdefault("csv_file_registry", {})
    reg = rl["metadata"]["csv_file_registry"]
    if "arabizi_general_word_bank.csv" in reg:
        reg["arabizi_general_word_bank.csv"]["row_count"] = gwb_count
    if "arabizi_protected_combos.csv" in reg:
        reg["arabizi_protected_combos.csv"]["row_count"] = pc_count

    # Add V14 metadata block
    rl["v14_mega_expansion"] = {
        "absorbed_at_utc"       : now_utc,
        "prior_version"         : prev_version,
        "gwb_rows_added"        : gwb_count - 252,   # minus V13.1 baseline
        "pc_rows_added"         : pc_count  - 78,
        "stoplist_rows_added"   : sl_count  - 36,
        "false_friends_file"    : "arabizi_false_friends_v14_review_only.csv (review only, not merged)",
        "morphology_file"       : "arabizi_morphology_notation_rules_v14_review_only.csv (review only, not merged)",
        "collision_queue_file"  : "arabizi_candidate_collision_review_queue_v14.csv (114 items, separate review needed)",
        "notes"                 : "Absorbed via absorb_v14_expansion_pack.py. Duplicate detection: 0 GWB dupes, 2 PC dupes skipped, 0 stoplist dupes.",
    }

    with open(RL_PATH, "w", encoding="utf-8") as f:
        json.dump(rl, f, indent=2, ensure_ascii=False)
    print(f"  RL version: {prev_version} → {rl['version']}")
    print(f"  Row counts updated: GWB={gwb_count}, PC={pc_count}, SL={sl_count}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(ZIP_PATH):
        print(f"ERROR: zip not found at {ZIP_PATH}")
        sys.exit(1)

    zf = zipfile.ZipFile(ZIP_PATH)

    # Run absorptions
    final_gwb = absorb_gwb(zf)
    final_pc  = absorb_pc(zf)
    final_sl  = absorb_stoplist(zf)

    # Count total rows written to each file for RL update
    gwb_total = len(read_csv(GWB_PATH))
    pc_total  = len(read_csv(PC_PATH))
    sl_total  = len(read_csv(SL_PATH))

    update_reliability_layer(gwb_total, pc_total, sl_total)

    print("\n=== SUMMARY ===")
    print(f"  GWB : {gwb_total} total rows  (+{final_gwb} from V14)")
    print(f"  PC  : {pc_total} total rows  (+{final_pc} from V14)")
    print(f"  SL  : {sl_total} total rows  (+{final_sl} from V14)")
    print("\nReview-only files (NOT merged — human review required):")
    print("  arabizi_false_friends_v14_review_only.csv")
    print("  arabizi_morphology_notation_rules_v14_review_only.csv")
    print("  arabizi_candidate_collision_review_queue_v14.csv  (114 items)")
    print("\nNext: run python scripts/validate_arabizi_support_layers.py")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()

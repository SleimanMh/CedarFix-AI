"""
convert_bfl_to_candidates.py
────────────────────────────
Converts build_full_candidate_bank_strengthened_v2.csv (BFL source) into
Batch 004 rows ready to append to arabizi_candidate_bank.csv.

What it does
  1. Reads BFL source (397 pre-analysed entries with per-variant risk metadata).
  2. Reads current candidate bank to deduplicate on arabic_script.
  3. Reads arabizi_reliability_layer.json for the false_friends list.
  4. Maps BFL schema → project candidate bank schema (21 columns).
  5. Deduplicates — skips any arabic_script already present in the bank.
  6. Assigns sequential ARZ-CAND-XXXX IDs starting from next available.
  7. Writes output to data/knowledge_base/arabizi/arabizi_candidate_bank_batch004_intake.csv

Run:
    python scripts/convert_bfl_to_candidates.py
"""

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
BFL_SOURCE = ROOT / 'data/knowledge_base/arabizi/bfl_source/build_full_candidate_bank_strengthened_v2.csv'
EXISTING_BANK = ROOT / 'data/knowledge_base/arabizi/arabizi_candidate_bank.csv'
RELIABILITY_LAYER = ROOT / 'data/knowledge_base/arabizi/arabizi_reliability_layer.json'
QUARANTINE_CSV = ROOT / 'data/knowledge_base/arabizi/bfl_quarantine_p0.csv'
OUTPUT = ROOT / 'data/knowledge_base/arabizi/arabizi_candidate_bank_batch004_intake.csv'

# ── frozen constants (do NOT edit) ────────────────────────────
HIGH_RISK_HINTS = {
    '5atar', '5atr', '5tr', '7ar2', '7are2', '7ariki',
    'ghaz', 'khatar', 'm5atr', 'masalla7', 'mshbouh',
    'nnar', 'sa32', 'saa2',
}

OUTPUT_COLS = [
    'candidate_id', 'arabic_script', 'english', 'sector', 'issue_type',
    'category', 'variants', 'tier_notes', 'usage_notes', 'source_type',
    'source_reference', 'dialect_region', 'confidence_level',
    'false_friend_risk', 'risk_level', 'review_status', 'reviewer_id',
    'decision', 'promotion_target', 'created_at', 'updated_at',
]

NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ── helpers ───────────────────────────────────────────────────

def _load_false_friends(reliability_path: Path) -> set:
    """Return set of arabizi false-friend trigger strings."""
    try:
        data = json.loads(reliability_path.read_text(encoding='utf-8'))
        ff = data.get('false_friends', {})
        if isinstance(ff, dict):
            # keys are the arabizi forms
            return set(ff.keys())
        if isinstance(ff, list):
            # list of dicts with 'arabizi' key
            result = set()
            for item in ff:
                if isinstance(item, dict):
                    result.add(item.get('arabizi', ''))
                else:
                    result.add(str(item))
            return result
    except Exception as e:
        print(f'  [WARN] Could not load reliability layer: {e}')
    return set()


def _variants_list(row: dict) -> list:
    """Return non-empty variants from variant_1..variant_6."""
    vs = []
    for i in range(1, 7):
        v = row.get(f'variant_{i}', '').strip()
        if v:
            vs.append(v)
    return vs


def _tiers_for_variants(row: dict, variants: list) -> str:
    """Return slash-separated tiers aligned to non-empty variants."""
    raw_tiers = [t.strip() for t in row.get('tiers', '').split('/')]
    # keep only tier positions that had a non-empty variant
    result = []
    for i in range(1, 7):
        v = row.get(f'variant_{i}', '').strip()
        if v:
            tier = raw_tiers[i - 1] if i - 1 < len(raw_tiers) else 'B'
            result.append(tier if tier else 'B')
    return '/'.join(result)


def _confidence(review_priority: str) -> str:
    p = review_priority.upper()
    if 'P2' in p or 'CORE' in p:
        return 'HIGH'
    if 'P1' in p or 'HIGH_RISK' in p:
        return 'MEDIUM'
    return 'LOW'     # P0 / quarantine


def _false_friend_risk(row: dict, ff_set: set, variants: list) -> str:
    flags = row.get('quality_flags', '').upper()
    if 'FALSE_FRIEND' in flags:
        return 'true'
    for v in variants:
        if v.lower() in ff_set:
            return 'true'
    return 'false'


def _risk_level(row: dict, variants: list) -> str:
    # CRITICAL — SAFETY sector
    if row.get('sector', '').upper() == 'SAFETY':
        return 'CRITICAL'
    # HIGH — any HIGH_RISK_HINTS token appears in any variant
    for v in variants:
        tokens = re.split(r'\s+', v.lower())
        for tok in tokens:
            if tok in HIGH_RISK_HINTS:
                return 'HIGH'
        if v.lower() in HIGH_RISK_HINTS:
            return 'HIGH'
    # HIGH — flagged by zip metadata
    if row.get('high_risk_second_review_required', '').upper() == 'TRUE':
        return 'HIGH'
    # MEDIUM — flooding
    if row.get('sector', '').upper() == 'FLOODING':
        return 'MEDIUM'
    return 'LOW'


def _promotion_target(row: dict) -> str:
    pt = row.get('promotion_target', '').strip()
    if not pt or pt in ('REJECT_OR_REWRITE', 'NEEDS_MORE_EVIDENCE'):
        return ''
    return pt


# ── main ──────────────────────────────────────────────────────

def main():
    print('=== BFL → Batch 004 converter ===')

    # 1. load existing bank — collect existing arabic_script for dedup
    existing_scripts: set = set()
    existing_max_id: int = 0
    with open(EXISTING_BANK, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            existing_scripts.add(row['arabic_script'].strip())
            try:
                n = int(row['candidate_id'].split('-')[-1])
                existing_max_id = max(existing_max_id, n)
            except ValueError:
                pass
    print(f'  Existing bank: {len(existing_scripts)} entries, last ID ARZ-CAND-{existing_max_id:04d}')

    # 2. load false friends set
    ff_set = _load_false_friends(RELIABILITY_LAYER)
    print(f'  False-friend trigger set: {len(ff_set)} entries')

    # 3. load quarantine variant IDs so we can note them in quality_flags
    quarantined_candidate_ids: set = set()
    with open(QUARANTINE_CSV, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            quarantined_candidate_ids.add(row['candidate_id'].strip())

    # 4. convert BFL rows
    next_id = existing_max_id + 1
    out_rows: list = []
    skipped_dupes: list = []
    skipped_empty: list = []

    with open(BFL_SOURCE, encoding='utf-8-sig') as f:
        bfl_rows = list(csv.DictReader(f))

    # strip BOM key if present
    if bfl_rows and '\ufeffcandidate_id' in bfl_rows[0]:
        for r in bfl_rows:
            r['candidate_id'] = r.pop('\ufeffcandidate_id')

    for bfl in bfl_rows:
        arabic = bfl.get('arabic_script', '').strip()
        if not arabic:
            skipped_empty.append(bfl.get('candidate_id', '?'))
            continue

        if arabic in existing_scripts:
            skipped_dupes.append(arabic)
            continue

        variants = _variants_list(bfl)
        if not variants:
            skipped_empty.append(bfl.get('candidate_id', '?'))
            continue

        tier_str = _tiers_for_variants(bfl, variants)
        conf = _confidence(bfl.get('review_priority', ''))
        ff = _false_friend_risk(bfl, ff_set, variants)
        risk = _risk_level(bfl, variants)

        # review_status: P0 stays PENDING_NATIVE_REVIEW with QUARANTINE note
        bfl_id = bfl.get('candidate_id', '').strip()
        is_quarantine = bfl_id in quarantined_candidate_ids
        review_status = 'PENDING_NATIVE_REVIEW'
        decision = 'UNREVIEWED'

        out_rows.append({
            'candidate_id': f'ARZ-CAND-{next_id:04d}',
            'arabic_script': arabic,
            'english': bfl.get('english', '').strip(),
            'sector': bfl.get('sector', 'OTHER').strip(),
            'issue_type': bfl.get('issue_type', 'ALL').strip(),
            'category': bfl.get('category', '').strip(),
            'variants': ';'.join(variants),
            'tier_notes': tier_str,
            'usage_notes': bfl.get('usage_note', '').strip(),
            'source_type': 'BUILD_FULL_LEXICON_SEED',
            'source_reference': 'build_full_lexicon_fixed_v2.py',
            'dialect_region': 'Beirut/Levant',
            'confidence_level': conf,
            'false_friend_risk': ff,
            'risk_level': risk,
            'review_status': review_status,
            'reviewer_id': 'UNASSIGNED',
            'decision': decision,
            'promotion_target': _promotion_target(bfl),
            'created_at': bfl.get('created_at_utc', NOW).strip(),
            'updated_at': NOW,
        })

        existing_scripts.add(arabic)   # prevent self-duplication if BFL has repeats
        next_id += 1

    # 5. write output
    with open(OUTPUT, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(out_rows)

    # 6. report
    print()
    print(f'  New rows written : {len(out_rows)}')
    print(f'  Skipped (dupe)   : {len(skipped_dupes)}')
    print(f'  Skipped (empty)  : {len(skipped_empty)}')
    print(f'  ID range         : ARZ-CAND-{existing_max_id+1:04d} → ARZ-CAND-{next_id-1:04d}')
    print()

    # breakdown by sector
    from collections import Counter
    sectors = Counter(r['sector'] for r in out_rows)
    print('  Sector breakdown:')
    for sec, cnt in sorted(sectors.items()):
        print(f'    {sec:<20} {cnt}')

    # risk breakdown
    risks = Counter(r['risk_level'] for r in out_rows)
    print()
    print('  Risk level breakdown:')
    for lvl, cnt in sorted(risks.items()):
        print(f'    {lvl:<12} {cnt}')

    # confidence breakdown
    conf_counts = Counter(r['confidence_level'] for r in out_rows)
    print()
    print('  Confidence breakdown:')
    for lvl, cnt in sorted(conf_counts.items()):
        print(f'    {lvl:<8} {cnt}')

    if skipped_dupes:
        print()
        print(f'  Duplicates skipped ({len(skipped_dupes)} arabic_script values already in bank):')
        for d in skipped_dupes[:10]:
            print(f'    {d}')
        if len(skipped_dupes) > 10:
            print(f'    ... and {len(skipped_dupes)-10} more')

    print()
    print(f'  Output: {OUTPUT.relative_to(ROOT)}')
    print('  Run validate_arabizi_candidate_bank.py to verify before appending.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

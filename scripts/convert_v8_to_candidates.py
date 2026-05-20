"""
convert_v8_to_candidates.py
───────────────────────────
Absorbs arabizi must-have word bank v8 operational grade into the
project's arabizi_candidate_bank.csv.

Rules:
  - Only rows with v8_merge_target == 'arabizi_candidate_bank_or_variant_lookup'
  - Skip D_REVIEW_OR_QUARANTINE trust class
  - Deduplicate on arabic_script (skip if already in bank)
  - Build variants: canonical_arabizi + safe_unique + context_only (pipe→semicolon, dedup, ordered)
  - Tier per variant: canonical=A(B_RELIABLE)/B(C_ONLY), safe_unique=A, context_only=B
  - Sector: infra_* prefix mapping
  - confidence_level: B_RELIABLE→HIGH, C_CONTEXT_ONLY→MEDIUM
  - risk_level: SAFETY sector→CRITICAL, HIGH_RISK_HINTS match→HIGH, else LOW

Run:
    python scripts/convert_v8_to_candidates.py
"""

import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V8_SOURCE = ROOT / 'lebanese_arabizi_must_have_word_bank_v8_operational_grade.csv'
EXISTING_BANK = ROOT / 'data/knowledge_base/arabizi/arabizi_candidate_bank.csv'
OUTPUT = ROOT / 'data/knowledge_base/arabizi/arabizi_candidate_bank_batch005_intake.csv'

HIGH_RISK_HINTS = {
    '5atar', '5atr', '5tr', '7ar2', '7are2', '7ariki',
    'ghaz', 'khatar', 'm5atr', 'masalla7', 'mshbouh',
    'nnar', 'sa32', 'saa2',
}

SECTOR_MAP = {
    'infra_roads':       'ROADS',
    'infra_safety':      'SAFETY',
    'infra_electricity': 'ELECTRICITY',
    'infra_waste':       'WASTE',
    'infra_water':       'WATER',
    'infra_flooding':    'FLOODING',
}

OUTPUT_COLS = [
    'candidate_id', 'arabic_script', 'english', 'sector', 'issue_type',
    'category', 'variants', 'tier_notes', 'usage_notes', 'source_type',
    'source_reference', 'dialect_region', 'confidence_level',
    'false_friend_risk', 'risk_level', 'review_status', 'reviewer_id',
    'decision', 'promotion_target', 'created_at', 'updated_at',
]

NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _split_pipe(val):
    """Split pipe-separated value, return clean non-empty list."""
    return [v.strip() for v in val.split('|') if v.strip()]


def _build_variants_and_tiers(row):
    """
    Build ordered (variant, tier) pairs.
    canonical_arabizi → tier A (B_RELIABLE) or B (C_ONLY)
    safe_unique variants → tier A
    context_only variants → tier B
    Deduplication preserves first occurrence.
    """
    trust = row['v8_trust_class']
    canonical_tier = 'A' if trust == 'B_RELIABLE_AFTER_REVIEW' else 'B'

    seen = {}  # variant → tier
    canonical = row['canonical_arabizi'].strip()
    if canonical:
        seen[canonical] = canonical_tier

    for v in _split_pipe(row['v8_safe_unique_variants_pipe']):
        if v and v not in seen:
            seen[v] = 'A'

    for v in _split_pipe(row['v8_context_only_variants_pipe']):
        if v and v not in seen:
            seen[v] = 'B'

    # also sweep all_operational for anything missed
    for v in _split_pipe(row['v8_all_operational_variants_pipe']):
        if v and v not in seen:
            seen[v] = 'B'

    if not seen:
        return '', ''

    variants = list(seen.keys())
    tiers = [seen[v] for v in variants]
    return ';'.join(variants), '/'.join(tiers)


def _risk_level(sector, variants_str):
    if sector == 'SAFETY':
        return 'CRITICAL'
    for v in variants_str.lower().split(';'):
        v = v.strip()
        if v in HIGH_RISK_HINTS:
            return 'HIGH'
        for tok in re.split(r'\s+', v):
            if tok in HIGH_RISK_HINTS:
                return 'HIGH'
    return 'LOW'


def main():
    print('=== V8 Word Bank → Batch 005 converter ===')

    # load existing bank
    with open(EXISTING_BANK, encoding='utf-8-sig') as f:
        existing_rows = list(csv.DictReader(f))
    existing_scripts = {r['arabic_script'].strip() for r in existing_rows}
    existing_max_id = max(
        int(r['candidate_id'].split('-')[-1]) for r in existing_rows
    )
    print(f'  Existing bank: {len(existing_scripts)} entries, last ID ARZ-CAND-{existing_max_id:04d}')

    # load v8 source
    with open(V8_SOURCE, encoding='utf-8-sig') as f:
        v8_rows = list(csv.DictReader(f))
    print(f'  V8 source: {len(v8_rows)} total rows')

    # filter to candidate bank targets only
    candidates = [r for r in v8_rows
                  if r['v8_merge_target'] == 'arabizi_candidate_bank_or_variant_lookup']
    print(f'  Targeted for candidate bank: {len(candidates)}')

    # exclude quarantine
    candidates = [r for r in candidates if r['v8_trust_class'] != 'D_REVIEW_OR_QUARANTINE']

    next_id = existing_max_id + 1
    out_rows = []
    skipped_dup = []
    skipped_empty = []

    for r in candidates:
        arabic = r['arabic_script'].strip()
        if not arabic:
            skipped_empty.append(r['term_id'])
            continue
        if arabic in existing_scripts:
            skipped_dup.append(arabic)
            continue

        variants_str, tier_str = _build_variants_and_tiers(r)
        if not variants_str:
            skipped_empty.append(r['term_id'])
            continue

        sector = SECTOR_MAP.get(r['category'], 'OTHER')
        trust = r['v8_trust_class']
        confidence = 'HIGH' if trust == 'B_RELIABLE_AFTER_REVIEW' else 'MEDIUM'
        risk = _risk_level(sector, variants_str)

        out_rows.append({
            'candidate_id':   'ARZ-CAND-{:04d}'.format(next_id),
            'arabic_script':  arabic,
            'english':        r['english_gloss'].strip(),
            'sector':         sector,
            'issue_type':     r['subcategory'].strip() or 'ALL',
            'category':       r['category'].strip(),
            'variants':       variants_str,
            'tier_notes':     tier_str,
            'usage_notes':    r['v8_policy_note'].strip(),
            'source_type':    'MUST_HAVE_WORD_BANK_V8',
            'source_reference': r['term_id'].strip(),
            'dialect_region': 'Beirut/Levant',
            'confidence_level': confidence,
            'false_friend_risk': 'false',
            'risk_level':     risk,
            'review_status':  'PENDING_NATIVE_REVIEW',
            'reviewer_id':    'UNASSIGNED',
            'decision':       'UNREVIEWED',
            'promotion_target': r['v8_merge_target'].strip(),
            'created_at':     r['created_at_utc'].strip() or NOW,
            'updated_at':     NOW,
        })

        existing_scripts.add(arabic)
        next_id += 1

    # write intake
    with open(OUTPUT, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(out_rows)

    # report
    from collections import Counter
    print()
    print('  New rows written : {}'.format(len(out_rows)))
    print('  Skipped (dupe)   : {}'.format(len(skipped_dup)))
    print('  Skipped (empty)  : {}'.format(len(skipped_empty)))
    if out_rows:
        print('  ID range         : ARZ-CAND-{:04d} -> ARZ-CAND-{:04d}'.format(
            existing_max_id + 1, next_id - 1))

    sectors = Counter(r['sector'] for r in out_rows)
    print('\n  Sector breakdown:')
    for s, n in sorted(sectors.items()):
        print('    {:20s} {}'.format(s, n))

    risks = Counter(r['risk_level'] for r in out_rows)
    print('\n  Risk level:')
    for lvl, n in sorted(risks.items()):
        print('    {:12s} {}'.format(lvl, n))

    conf = Counter(r['confidence_level'] for r in out_rows)
    print('\n  Confidence:')
    for lvl, n in sorted(conf.items()):
        print('    {:8s} {}'.format(lvl, n))

    print()
    print('  Output: {}'.format(OUTPUT.relative_to(ROOT)))
    return 0


if __name__ == '__main__':
    sys.exit(main())

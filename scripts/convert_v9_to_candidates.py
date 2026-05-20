"""Batch 006: Absorb net-new rows from v9 word bank into arabizi_candidate_bank.csv."""
import csv, datetime, re

HIGH_RISK_HINTS = {'5atar','5atr','5tr','7ar2','7are2','7ariki','ghaz','khatar',
                   'm5atr','masalla7','mshbouh','nnar','sa32','saa2'}
SECTOR_MAP = {
    'infra_roads': 'ROADS', 'infra_safety': 'SAFETY',
    'infra_electricity': 'ELECTRICITY', 'infra_waste': 'WASTE',
    'infra_water': 'WATER', 'infra_flooding': 'FLOODING',
}
BANK  = 'data/knowledge_base/arabizi/arabizi_candidate_bank.csv'
V9SRC = 'lebanese_arabizi_must_have_word_bank_v9_individual_terms_max.csv'

existing   = list(csv.DictReader(open(BANK,  encoding='utf-8-sig')))
fieldnames = list(existing[0].keys())
existing_arabic = {r['arabic_script'].strip() for r in existing}
# full variant token pool for canonical-level dedup
existing_variants = set()
for _r in existing:
    for _v in _r['variants'].split(';'):
        _tok = _v.strip().lower()
        if _tok:
            existing_variants.add(_tok)
last_id    = max(int(r['candidate_id'].split('-')[-1]) for r in existing)
print(f'Existing bank: {len(existing)} entries | Last ID: ARZ-CAND-{last_id:04d}')
print(f'Existing variant tokens: {len(existing_variants)}')

src  = list(csv.DictReader(open(V9SRC, encoding='utf-8-sig')))
targets = [r for r in src
           if r['v8_merge_target'] == 'arabizi_candidate_bank_or_variant_lookup'
           and r['v8_trust_class'] != 'D_REVIEW_OR_QUARANTINE'
           and r['arabic_script'].strip() not in existing_arabic
           and r['canonical_arabizi'].strip().lower() not in existing_variants]
print(f'Net-new targets (after variant dedup): {len(targets)}')

now     = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
counter = last_id + 1
new_rows = []

for r in targets:
    canonical = r['canonical_arabizi'].strip()
    safe      = [v.strip() for v in r['v9_safe_individual_variants_pipe'].split('|')    if v.strip()]
    context   = [v.strip() for v in r['v9_context_or_phrase_variants_pipe'].split('|') if v.strip()]

    seen, variant_list, tier_list = set(), [], []
    tier_a = r['v8_trust_class'] in ('A_SAFE_UNIQUE_AFTER_REVIEW', 'B_RELIABLE_AFTER_REVIEW')
    for v in ([canonical] if canonical else []) + safe:
        if v and v not in seen:
            variant_list.append(v); tier_list.append('A' if tier_a else 'B'); seen.add(v)
    for v in context:
        if v and v not in seen:
            variant_list.append(v); tier_list.append('B'); seen.add(v)

    sector = SECTOR_MAP.get(r['category'], 'OTHER')
    conf   = 'HIGH' if r['v8_trust_class'] == 'B_RELIABLE_AFTER_REVIEW' else 'MEDIUM'
    risk   = ('CRITICAL' if sector == 'SAFETY'
              else 'HIGH'  if any(v.lower() in HIGH_RISK_HINTS for v in variant_list)
              else 'LOW')

    # register new variants so later rows in same batch also dedup correctly
    for _v in variant_list:
        existing_variants.add(_v.lower())
    existing_arabic.add(r['arabic_script'].strip())

    new_rows.append({
        'candidate_id':    f'ARZ-CAND-{counter:04d}',
        'arabic_script':   r['arabic_script'].strip(),
        'english':         r['english_gloss'].strip(),
        'sector':          sector,
        'issue_type':      r['subcategory'].strip() or 'ALL',
        'category':        r['category'].strip(),
        'variants':        ';'.join(variant_list),
        'tier_notes':      '/'.join(tier_list),
        'usage_notes':     r.get('v9_notes', '').strip() or r.get('v8_policy_note', '').strip(),
        'source_type':     'MUST_HAVE_WORD_BANK_V9',
        'source_reference': r['term_id'].strip(),
        'dialect_region':  'Beirut/Levant',
        'confidence_level': conf,
        'false_friend_risk': 'false',
        'risk_level':      risk,
        'review_status':   'PENDING_NATIVE_REVIEW',
        'reviewer_id':     'UNASSIGNED',
        'decision':        'UNREVIEWED',
        'promotion_target': r['v9_merge_target'].strip() or r['v8_merge_target'].strip(),
        'created_at':      r.get('created_at_utc', '').strip() or now,
        'updated_at':      now,
    })
    counter += 1

from collections import Counter
for nr in new_rows:
    print(f"  {nr['candidate_id']} | {nr['sector']} | {nr['risk_level']} | {nr['english']}")

sec_c  = Counter(nr['sector']          for nr in new_rows)
risk_c = Counter(nr['risk_level']      for nr in new_rows)
conf_c = Counter(nr['confidence_level'] for nr in new_rows)

with open(BANK, 'a', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    for nr in new_rows:
        w.writerow(nr)

print()
print(f'Appended : {len(new_rows)} rows')
print(f'Bank total: {len(existing) + len(new_rows)}')
print(f'ID range : ARZ-CAND-{last_id+1:04d} -> ARZ-CAND-{counter-1:04d}')
print('Sectors  :', dict(sorted(sec_c.items())))
print('Risk     :', dict(sorted(risk_c.items())))
print('Conf     :', dict(sorted(conf_c.items())))

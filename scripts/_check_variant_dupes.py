"""Check variant-level deduplication across the entire candidate bank.

Scans every row's variants for collisions with other rows — useful after any
batch intake to surface cases where the same arabizi token appears under
multiple candidate IDs.
"""
import csv
from collections import defaultdict

BANK = 'data/knowledge_base/arabizi/arabizi_candidate_bank.csv'

rows = list(csv.DictReader(open(BANK, encoding='utf-8-sig')))

# Build  variant -> [candidate_id, ...]  map
variant_map = defaultdict(list)
for r in rows:
    for v in r['variants'].split(';'):
        v = v.strip().lower()
        if v:
            variant_map[v].append(r['candidate_id'])
    # include arabic_script too
    k = r['arabic_script'].strip()
    if k:
        variant_map[k].append(r['candidate_id'])

collisions = {v: ids for v, ids in variant_map.items() if len(ids) > 1}
print(f'Total unique variant tokens : {len(variant_map)}')
print(f'Colliding tokens            : {len(collisions)}')
print()

if collisions:
    # Group collisions by pair of candidate IDs
    pair_map = defaultdict(list)
    for v, ids in sorted(collisions.items()):
        key = tuple(sorted(set(ids)))
        pair_map[key].append(v)

    for pair, tokens in sorted(pair_map.items()):
        r1 = next(r for r in rows if r['candidate_id'] == pair[0])
        r2 = next(r for r in rows if r['candidate_id'] == pair[1])
        print(f"  {pair[0]} [{r1['english'][:25]}]  <->  {pair[1]} [{r2['english'][:25]}]")
        print(f"    shared tokens: {tokens}")
        print()
else:
    print('  No collisions — all variants are unique across the bank.')

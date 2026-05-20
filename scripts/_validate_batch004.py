"""Quick validation of batch004 intake CSV."""
import csv, re

HIGH_RISK_HINTS = {
    '5atar','5atr','5tr','7ar2','7are2','7ariki','ghaz','khatar',
    'm5atr','masalla7','mshbouh','nnar','sa32','saa2',
}
REQUIRED_COLS = [
    'candidate_id','arabic_script','english','sector','issue_type','category',
    'variants','tier_notes','usage_notes','source_type','source_reference',
    'dialect_region','confidence_level','false_friend_risk','risk_level',
    'review_status','reviewer_id','decision','promotion_target','created_at','updated_at',
]

with open('data/knowledge_base/arabizi/arabizi_candidate_bank_batch004_intake.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

errors = []

for col in REQUIRED_COLS:
    if col not in rows[0]:
        errors.append('MISSING COL: ' + col)

for r in rows:
    if re.search(r'\bmesh\b', r['variants']):
        errors.append('MESH ERROR: ' + r['candidate_id'] + ' ' + r['variants'])

for r in rows:
    if not r['variants'].strip():
        errors.append('EMPTY VARIANTS: ' + r['candidate_id'])

for r in rows:
    vs = [v.lower().strip() for v in r['variants'].split(';')]
    for v in vs:
        if v in HIGH_RISK_HINTS and r['risk_level'] == 'LOW':
            errors.append('RISK_MISS: ' + r['candidate_id'] + ' v=' + v + ' risk=' + r['risk_level'])

bad_rs = [r['candidate_id'] for r in rows if r['review_status'] != 'PENDING_NATIVE_REVIEW']
if bad_rs:
    errors.append('BAD review_status: ' + str(bad_rs[:5]))

bad_dec = [r['candidate_id'] for r in rows if r['decision'] != 'UNREVIEWED']
if bad_dec:
    errors.append('BAD decision: ' + str(bad_dec[:5]))

ids = [r['candidate_id'] for r in rows]
if len(ids) != len(set(ids)):
    errors.append('DUPLICATE IDs present')

bad_st = [r['candidate_id'] for r in rows if r['source_type'] != 'BUILD_FULL_LEXICON_SEED']
if bad_st:
    errors.append('BAD source_type: ' + str(bad_st[:5]))

print('Total rows  :', len(rows))
print('ID range    :', rows[0]['candidate_id'], '->', rows[-1]['candidate_id'])
print('Errors found:', len(errors))
if errors:
    for e in errors:
        print('  ERROR:', e)
else:
    print('  All checks PASSED')

print()
print('=== SPOT CHECK (rows 0, 100, 200) ===')
for i in [0, 100, 200]:
    r = rows[i]
    vshort = r['variants'][:80]
    print(r['candidate_id'], '|', r['arabic_script'], '|', r['english'], '|', r['sector'],
          '| risk=', r['risk_level'], '| conf=', r['confidence_level'], '| v=', vshort)

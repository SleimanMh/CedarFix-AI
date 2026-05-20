import csv
from collections import Counter

rows = list(csv.DictReader(open('lebanese_arabizi_must_have_word_bank_v8_operational_grade.csv', encoding='utf-8-sig')))

cand = [r for r in rows if r['v8_merge_target'] == 'arabizi_candidate_bank_or_variant_lookup']
print('Candidate bank targets:', len(cand))

cats = Counter(r['category'] for r in cand)
print('\nCategories in candidate targets:')
for c, n in sorted(cats.items(), key=lambda x: -x[1]):
    print('  {:4d}  {}'.format(n, c))

trust = Counter(r['v8_trust_class'] for r in cand)
print('\nTrust classes:')
for t, n in sorted(trust.items(), key=lambda x: -x[1]):
    print('  {:4d}  {}'.format(n, t))

existing = {r['arabic_script'].strip() for r in csv.DictReader(
    open('data/knowledge_base/arabizi/arabizi_candidate_bank.csv', encoding='utf-8-sig'))}
print('\nExisting bank size:', len(existing))

new_cand = [r for r in cand if r['arabic_script'].strip() not in existing]
dup_cand = [r for r in cand if r['arabic_script'].strip() in existing]
print('New after dedup:', len(new_cand))
print('Already in bank:', len(dup_cand))

new_trust = Counter(r['v8_trust_class'] for r in new_cand)
print('\nTrust class of net-new:')
for t, n in sorted(new_trust.items(), key=lambda x: -x[1]):
    print('  {:4d}  {}'.format(n, t))

d_class = [r for r in new_cand if r['v8_trust_class'] == 'D_REVIEW_OR_QUARANTINE']
print('D_REVIEW (will be excluded):', len(d_class))

non_d = [r for r in new_cand if r['v8_trust_class'] != 'D_REVIEW_OR_QUARANTINE']
print('Net importable (non-D):', len(non_d))
print('\n=== SAMPLE (first 6) ===')
for r in non_d[:6]:
    safe_v = r['v8_safe_unique_variants_pipe'][:50]
    print('  {} | {} | {} | {} | trust={} | safe_v={}'.format(
        r['term_id'], r['arabic_script'], r['english_gloss'],
        r['category'], r['v8_trust_class'], safe_v))

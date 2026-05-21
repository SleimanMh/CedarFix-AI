# Arabizi Controlled Lexicon

This directory is staging, review, and audit infrastructure for CedarFix's
Arabizi reliability layer.

Production vocabulary lives in:

- `data/knowledge_base/arabizi_vocabulary.json`

Active review assets in this directory are intentionally separated by risk:

```text
arabizi/
├── README.md
├── arabizi_candidate_bank.csv             # domain-sector candidate routing terms pending review
├── arabizi_candidate_bank_quarantine.csv  # non-domain/support rows removed from promotion queue
├── arabizi_general_word_bank.csv          # generic support words; routing/severity blocked
├── arabizi_protected_combos.csv           # phrase locks where token splitting changes meaning
├── arabizi_reliability_layer.json         # support, stoplist, provenance, reviewers, notation, OOV seeds
├── arabizi_reviewed_changes.csv           # append-only promotion/change audit log
├── arabizi_surface_forms_v15.csv          # generated review-only spelling variants / OOV surface forms
└── arabizi_stoplist.csv                   # terms blocked from promotion
```

Historical source files and the raw external pack are archived under `_archive/`.

## Reliability Layer Boundaries

`arabizi_reliability_layer.json` contains multiple review-only sections:

- `stoplist`: terms blocked from production promotion.
- `false_friends`: ambiguous tokens that must remain review-only.
- `general_word_bank`: common support words for normalization/OOV precision;
  routing, severity, and issue decisions are blocked.
- `variant_lookup`: fuzzy/OOV lookup rows with `use_for_routing_prediction_now=FALSE`.
- `internet_notation_rules`: notation support, not issue labels.
- `oov_seed_queue`: review seeds, not production corpus evidence.
- `reviewers`, `external_resources`, `source_policy`: governance and provenance.

Raw text still goes to semantic models. Unknown high-risk terms are logged,
reviewed, and routed to HITL when risk or uncertainty is high.

## Workflow

```text
Domain candidate terms / OOV observations
        ↓
arabizi_candidate_bank.csv  (domain sectors only, review_status=PENDING)
        ↓ native-speaker + engineer review
review_status=APPROVED / REJECTED / DEFERRED
        ↓ scripts/promote_arabizi_candidates.py --apply
arabizi_vocabulary.json + arabizi_reviewed_changes.csv
```

Generic words, protected phrases, place names, discourse terms, and other
support-only rows do not enter this promotion path. They remain in support
layers or `arabizi_candidate_bank_quarantine.csv` until a reviewer explicitly
reclassifies them.

`arabizi_surface_forms_v15.csv` is a high-volume generated layer for spelling
coverage. It supports normalization, OOV review, language detection features,
duplicate matching support, and stress tests. It is blocked from routing,
severity assignment, sector classification, issue-type decisions, and core
vocabulary promotion.

The promotion script reads the `stoplist` section of
`arabizi_reliability_layer.json`; a stopped term is never promoted.

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/validate_arabizi_candidate_bank.py` | Validate candidate-bank schema and promotion safety |
| `scripts/promote_arabizi_candidates.py` | Promote approved rows into production vocab |
| `scripts/validate_arabizi_reliability.py` | Measure production-vocab coverage on the corpus |
| `scripts/validate_arabizi_pack_absorption.py` | Validate consolidated reliability layer and eval suite |
| `scripts/cleanup_arabizi_candidate_bank_v13_1.py` | Reproduce the v13.1 domain-only candidate-bank cleanup |
| `scripts/build_arabizi_surface_forms_v15.py` | Generate the v15 high-volume surface-form layer |
| `scripts/validate_arabizi_surface_forms.py` | Validate that generated surface forms remain review-only and non-routing |

## Protected Constants

- `HIGH_RISK_HINTS` list in EEP / pipeline constants
- Benchmark SHA for `arabizi_benchmark_v0_regression.csv`
- `kasaret` remains deferred until review evidence justifies promotion

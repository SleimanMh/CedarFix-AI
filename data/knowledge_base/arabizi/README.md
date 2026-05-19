# Arabizi Controlled Lexicon

This directory is staging, review, and audit infrastructure for CedarFix's
Arabizi reliability layer.

Production vocabulary lives in:

- `data/knowledge_base/arabizi_vocabulary.json`

Active review assets in this directory are intentionally minimal:

```text
arabizi/
├── README.md
├── arabizi_candidate_bank.csv        # candidate routing terms pending review
├── arabizi_reliability_layer.json    # support, stoplist, provenance, reviewers, notation, OOV seeds
└── arabizi_reviewed_changes.csv      # append-only promotion/change audit log
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
Candidate terms / OOV observations
        ↓
arabizi_candidate_bank.csv  (review_status=PENDING)
        ↓ native-speaker + engineer review
review_status=APPROVED / REJECTED / DEFERRED
        ↓ scripts/promote_arabizi_candidates.py --apply
arabizi_vocabulary.json + arabizi_reviewed_changes.csv
```

The promotion script reads the `stoplist` section of
`arabizi_reliability_layer.json`; a stopped term is never promoted.

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/validate_arabizi_candidate_bank.py` | Validate candidate-bank schema and promotion safety |
| `scripts/promote_arabizi_candidates.py` | Promote approved rows into production vocab |
| `scripts/validate_arabizi_reliability.py` | Measure production-vocab coverage on the corpus |
| `scripts/validate_arabizi_pack_absorption.py` | Validate consolidated reliability layer and eval suite |

## Protected Constants

- `HIGH_RISK_HINTS` list in EEP / pipeline constants
- Benchmark SHA for `arabizi_benchmark_v0_regression.csv`
- `kasaret` remains deferred until review evidence justifies promotion

# Arabizi Controlled Lexicon — Directory Layout

This directory contains the **controlled workflow** for the CedarFix Arabizi lexicon.
Production vocabulary lives in `data/knowledge_base/arabizi_vocabulary.json`.
Everything here is staging / review / audit infrastructure.

```
arabizi/
├── README.md                     ← this file
├── arabizi_vocabulary_core.json  ← snapshot copy of production vocab (do NOT edit directly)
├── arabizi_candidate_bank.csv    ← new terms pending human review
├── arabizi_stoplist.csv          ← terms BLOCKED from production vocab forever
└── arabizi_reviewed_changes.csv  ← append-only audit log of every promotion decision
```

## Philosophy

CedarFix does NOT rely on a brittle dictionary.
The core vocabulary is **high-precision and reviewed**.
A larger candidate bank supports:
- normalization
- weak supervision
- OOV stress tests
- human-in-the-loop (HITL) review

Raw text still goes to semantic models.
Unknown high-risk terms are logged, reviewed, and routed to HITL when risk or
uncertainty is high.

## Workflow

```
Pasted rows / field notes
        ↓
arabizi_candidate_bank.csv  (review_status=PENDING)
        ↓  native-speaker + engineer review
review_status=APPROVED / REJECTED / DEFERRED
        ↓  scripts/promote_arabizi_candidates.py --apply
arabizi_vocabulary.json (production)   +  arabizi_reviewed_changes.csv (audit)
```

Stoplist entries are checked automatically by `promote_arabizi_candidates.py`
before any promotion. A term on the stoplist is NEVER promoted.

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/correct_arabizi_vocabulary.py` | One-off correction pass (v1.5.0 → v1.5.1) |
| `scripts/validate_arabizi_candidate_bank.py` | Validate bank CSV format and enum values |
| `scripts/promote_arabizi_candidates.py` | Promote APPROVED rows to production vocab |
| `scripts/validate_arabizi_reliability.py` | Measure vocab coverage on real corpus |

## Protected Constants

The following MUST NOT be changed by any script:
- `HIGH_RISK_HINTS` list in EEP / pipeline constants
- Benchmark SHA (frozen at v1.4.0 baseline)
- `kasaret` — deferred to Batch 003, do NOT promote yet

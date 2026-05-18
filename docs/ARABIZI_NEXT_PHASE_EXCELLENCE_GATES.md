# Arabizi Next-Phase Excellence Gates

Version 1.0 | Purpose: prevent the Arabizi work from becoming impressive only
in demos. These gates define what must be true before CedarFix claims
best-in-class Lebanese Arabizi reliability.

## Run

```bash
python scripts/audit_arabizi_excellence_gates.py
python scripts/evaluate_arabizi_pair_coverage.py
```

Artifacts:

```bash
data/eval/arabizi_excellence_gates_v1.json
data/eval/arabizi_pair_coverage_v1.json
```

## Final Arabizi Claim Gates

| Gate | Requirement | Why it matters |
| --- | --- | --- |
| ARZ-G01 | >=40 Arabizi/mixed rows before final Arabizi F1 claims | Batch 001 is regression evidence, not statistical proof |
| ARZ-G02 | >=90% Arabizi/mixed rows reviewed by native/dialect reviewer | Professor-proof linguistic validity |
| ARZ-G03 | >=10 cross-language duplicate pairs involving Arabizi/mixed | Proves multilingual incident fusion |
| ARZ-G04 | >=5 hard-negative pairs involving Arabizi/mixed | Prevents false same-area merges |
| ARZ-G05 | >=5 unrelated-negative pairs involving Arabizi/mixed | Prevents semantic-similarity overmerge |
| ARZ-G06 | Benchmark, Stress Lab, and Live Certificate artifacts exist | Reproducible demo and regression evidence |

## Batch 002 Minimum Target

Batch 002 should add at least:

- 26 new Arabizi/mixed reports, so total reaches >=40
- 10 new cross-language duplicate pairs involving Arabizi/mixed
- 5 hard-negative pairs involving Arabizi/mixed
- 5 unrelated pairs involving Arabizi/mixed
- districts outside central Beirut: Tripoli, Sidon, Zahleh, Bekaa, and at least one coastal/port setting
- at least 5 no-space/repeated-letter/digit-omission reports
- at least 5 French or English code-switch reports
- at least 5 public-safety or high-impact reports

## Native Review Rule

Use reviewer IDs prefixed with one of:

- `NATIVE-`
- `LEB-`
- `DIALECT-`

This lets the audit script mechanically distinguish native dialect review from
engineering review.

## Honest Claim Boundary

Before all gates pass:

> CedarFix has a strong Arabizi reliability prototype with regression and demo
> evidence.

After all gates pass:

> CedarFix has a best-in-class Lebanese Arabizi reliability layer for municipal
> incident triage, supported by reviewed corpus data, stress tests, live
> certificates, cross-language duplicate evidence, and native dialect review.

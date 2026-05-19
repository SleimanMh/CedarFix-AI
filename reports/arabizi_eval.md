# Arabizi Evaluation Report

Status: PENDING FULL EVAL DATA

This report lists each evaluation metric, the required inputs, how to generate it,
and the current blocker. No numeric results are claimed here except the measured
coverage baseline. The consolidated eval suite now contains a small number of
pack-derived smoke-test rows, including pair and notation seeds; these rows are
useful for regression checks but are below the threshold for reporting final
metrics. Schemas live in `data/eval/arabizi_eval_schemas.md`.

---

## Metrics Index

### M1: Vocabulary Coverage (word-level hit rate)

**Command to generate:**
```bash
python scripts/validate_arabizi_reliability.py --threshold 0.30 --save
```

**Required inputs:**
- `data/corpus/cedarfix_reports_v1.csv` — 80 real reports with `language` column
- `data/knowledge_base/arabizi_vocabulary.json` — production vocabulary v1.5.1

**Output file:** `reports/arabizi_reliability.txt`

**Current blocker:** None — corpus confirmed at expected path.

**Current result (v1.5.1 baseline):** Average hit rate = 12.5% on 40 arabizi/mixed rows.
36/40 rows below 30% threshold. Expected: precision-focused vocabulary intentionally
excludes non-incident tokens. Run `--save` to persist full per-row detail.

---

### M2: Sector Classification Accuracy

**Command to generate:** (integration runner not yet implemented)

**Required inputs:**
- `data/eval/arabizi_eval_suite.csv` — minimum 20 reviewed `CLEAN` rows
- `data/eval/arabizi_eval_suite.csv` — minimum 20 reviewed `NOISY` rows
- Pipeline runner that outputs `sector` predictions per `report_id`

**Current blocker:** Eval suite has 6 clean/noisy seed rows, below the reporting
threshold. No rows may be fabricated. Requires native Lebanese speaker review
session and additional rows.

**Current result:** NOT MEASURED

---

### M3: Issue Type Macro-F1

**Command to generate:** (integration runner not yet implemented)

**Required inputs:**
- `data/eval/arabizi_eval_suite.csv` — minimum 20 reviewed `CLEAN`/`NOISY` rows per issue_type present
- Pipeline runner outputs with `issue_type` predictions

**Current blocker:** Same as M2.

**Current result:** NOT MEASURED

---

### M4: Route Entity Accuracy

**Command to generate:** (integration runner not yet implemented)

**Required inputs:**
- `data/eval/arabizi_eval_suite.csv` — minimum 20 reviewed `CLEAN`/`NOISY` rows
- Pipeline runner outputs with `route_entity` predictions

**Importance:** CRITICAL. Wrong routing = repair request sent to wrong authority.

**Current blocker:** Same as M2.

**Current result:** NOT MEASURED

---

### M5: Severity Accuracy

**Command to generate:** (integration runner not yet implemented)

**Required inputs:**
- `data/eval/arabizi_eval_suite.csv` — minimum 20 reviewed `CLEAN`/`NOISY` rows
- Pipeline runner outputs with `severity` predictions

**Failure threshold:** Any HIGH or CRITICAL row misclassified as LOW is a critical failure.

**Current blocker:** Same as M2.

**Current result:** NOT MEASURED

---

### M6: OOV Detection Rate

**Command to generate:** (OOV detection module not yet implemented as standalone)

**Required inputs:**
- `data/eval/arabizi_eval_suite.csv` — minimum 10 reviewed `OOV` rows
- Pipeline runner outputs with OOV flags per report

**Current blocker:** Eval suite has 1 OOV seed row, below the reporting threshold.

**Current result:** NOT MEASURED

---

### M7: High-Risk OOV Recall

**Command to generate:** (integration runner not yet implemented)

**Required inputs:**
- `data/eval/arabizi_eval_suite.csv` — `OOV` rows where expected_severity=HIGH or CRITICAL
- Pipeline runner outputs confirming HITL escalation flag

**Importance:** CRITICAL. Missed high-risk OOV = potential safety incident not escalated.

**Current blocker:** Eval suite has 1 OOV seed row, below the reporting threshold.

**Current result:** NOT MEASURED

---

### M8: HITL Trigger Correctness

**Command to generate:** (requires production log access)

**Required inputs:**
- Production pipeline logs with HITL escalation decisions
- Reviewed ground truth for each escalated report

**Current blocker:** Requires production log access and reviewer time.

**Current result:** NOT MEASURED

---

### M9: Normalization Coverage

**Command to generate:**
```bash
# (normalization coverage script not yet implemented)
# To implement: scan corpus arabizi rows, attempt Arabic script mapping
# via vocabulary term_metadata, report fraction successfully mapped
```

**Required inputs:**
- `data/corpus/cedarfix_reports_v1.csv`
- `data/knowledge_base/arabizi_vocabulary.json` (term_metadata.arabic_script fields)

**Current blocker:** Script not yet implemented.

**Current result:** NOT MEASURED

---

## Ablation Plan (NOT YET RUN)

Four conditions for sector classification accuracy comparison:

| Condition ID | Description | Status |
|-------------|-------------|--------|
| A0: baseline | No vocabulary, semantic model only | NOT RUN |
| A1: raw_only | Raw Arabizi tokens + semantic model | NOT RUN |
| A2: norm_only | Normalized tokens only (Arabic script via vocab) | NOT RUN |
| A3: raw_plus_norm | Raw + normalized tokens | NOT RUN |
| A4: raw_plus_norm_oov | Raw + normalized + OOV feature flag | NOT RUN |

These conditions test the hypothesis that vocabulary normalization improves
sector classification. The ablation must be run on real eval data only.

---

## Eval Data Collection Plan

1. Collect or solicit real incident reports in Lebanese Arabizi (with consent).
2. Assign ground-truth labels (sector, issue_type, severity, route_entity).
3. Have a native Lebanese speaker verify:
   - Language classification (arabizi vs mixed)
   - Correctness of sector assignment
   - Correctness of severity assignment
   - That no OOV token was misidentified as a known token
4. Place reviewed rows in `data/eval/arabizi_eval_suite.csv` using the
   appropriate `row_type`:
   - Clean, no noise → `CLEAN`
   - OCR errors, typos, code-switching → `NOISY`
   - Contains meaningful unknown tokens → `OOV`
   - Cross-language pair checks → `PAIR`
   - Notation-only checks → `NOTATION`
5. Keep the current pack-derived rows as smoke-test seeds unless native review confirms them.
6. Minimum 20 reviewed rows per relevant row type before reporting any metric.
7. Never duplicate the same report text across eval rows unless the row is an explicit
   `PAIR` duplicate/relatedness test.

---

## How to Run All Validators

```bash
# Vocabulary integrity
python scripts/validate_arabizi_vocabulary.py

# Benchmark regression
python scripts/validate_arabizi_benchmark.py

# Candidate bank schema
python scripts/validate_arabizi_candidate_bank.py

# Reliability (exits non-zero if required input is missing)
python scripts/validate_arabizi_reliability.py

# Absorbed reliability-pack eval/governance assets
python scripts/validate_arabizi_pack_absorption.py
```

All five must pass before promoting any new candidates or releasing a vocabulary update.

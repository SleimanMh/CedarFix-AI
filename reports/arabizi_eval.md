# Arabizi Evaluation Report

Status: PENDING REAL DATA

This report lists each evaluation metric, the required inputs, how to generate it,
and the current blocker. No numeric results are claimed here except the measured
coverage baseline. The eval CSV files are intentionally header-only until reviewed
rows exist; their schemas live in `data/eval/arabizi_eval_schemas.md`.

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
- `data/eval/arabizi_clean_eval.csv` — minimum 20 reviewed rows
- `data/eval/arabizi_noisy_eval.csv` — minimum 20 reviewed rows
- Pipeline runner that outputs `sector` predictions per `report_id`

**Current blocker:** Eval files have 0 reviewed rows. No rows may be fabricated.
Requires native Lebanese speaker review session.

**Current result:** NOT MEASURED

---

### M3: Issue Type Macro-F1

**Command to generate:** (integration runner not yet implemented)

**Required inputs:**
- `data/eval/arabizi_clean_eval.csv` — minimum 20 reviewed rows per issue_type present
- Pipeline runner outputs with `issue_type` predictions

**Current blocker:** Same as M2.

**Current result:** NOT MEASURED

---

### M4: Route Entity Accuracy

**Command to generate:** (integration runner not yet implemented)

**Required inputs:**
- `data/eval/arabizi_clean_eval.csv` — minimum 20 reviewed rows
- Pipeline runner outputs with `route_entity` predictions

**Importance:** CRITICAL. Wrong routing = repair request sent to wrong authority.

**Current blocker:** Same as M2.

**Current result:** NOT MEASURED

---

### M5: Severity Accuracy

**Command to generate:** (integration runner not yet implemented)

**Required inputs:**
- `data/eval/arabizi_clean_eval.csv` — minimum 20 reviewed rows
- Pipeline runner outputs with `severity` predictions

**Failure threshold:** Any HIGH or CRITICAL row misclassified as LOW is a critical failure.

**Current blocker:** Same as M2.

**Current result:** NOT MEASURED

---

### M6: OOV Detection Rate

**Command to generate:** (OOV detection module not yet implemented as standalone)

**Required inputs:**
- `data/eval/arabizi_oov_eval.csv` — minimum 10 reviewed rows
- Pipeline runner outputs with OOV flags per report

**Current blocker:** Eval file has 0 reviewed rows.

**Current result:** NOT MEASURED

---

### M7: High-Risk OOV Recall

**Command to generate:** (integration runner not yet implemented)

**Required inputs:**
- `data/eval/arabizi_oov_eval.csv` — rows where expected_severity=HIGH or CRITICAL
- Pipeline runner outputs confirming HITL escalation flag

**Importance:** CRITICAL. Missed high-risk OOV = potential safety incident not escalated.

**Current blocker:** Eval file has 0 reviewed rows.

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
4. Place reviewed rows in the appropriate eval file:
   - Clean, no noise → `arabizi_clean_eval.csv`
   - OCR errors, typos, code-switching → `arabizi_noisy_eval.csv`
   - Contains meaningful unknown tokens → `arabizi_oov_eval.csv`
5. Minimum 20 rows per eval file before reporting any metric.
6. Never add the same report to multiple eval files (deduplication required).

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
```

All four must pass before promoting any new candidates or releasing a vocabulary update.

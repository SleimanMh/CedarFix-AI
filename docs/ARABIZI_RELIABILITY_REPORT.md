# Arabizi Reliability Report

**Status: PENDING REAL DATA**

This document defines the methodology for measuring CedarFix pipeline reliability
on Lebanese Arabizi input. No numeric results are claimed here until real corpus data
is collected and measured.

---

## 1. What Is Measured

### 1.1 Vocabulary Coverage (word-level hit rate)
The fraction of tokens in an Arabizi or mixed-language report that match a token in
`arabizi_vocabulary.json`. Measured by `scripts/validate_arabizi_reliability.py`.

**Scope**: Arabizi and mixed-language rows only.
**Not measured**: Rows classified as `en`, `ar`, or `fr` (different vocabularies).

**Why it matters**: Low hit rate means the pipeline must rely entirely on the semantic
(embedding) layer, which is slower and less explainable. Target: ≥ 50% hit rate on
arabizi rows at current vocabulary size.

### 1.2 Sector Classification Accuracy
Fraction of eval rows where pipeline output `sector` matches `expected_sector`.
Requires: `data/eval/arabizi_clean_eval.csv` to be populated with reviewed rows.

### 1.3 Issue Type Macro-F1
Macro-averaged F1 score across all `issue_type` classes on arabizi/mixed rows.
Macro averaging is required because class distribution is uneven.

### 1.4 Route Entity Accuracy
Fraction of eval rows where pipeline output `route_entity` matches `expected_route_entity`.
This is the most operationally critical metric: wrong routing = wrong repair authority.

### 1.5 Severity Accuracy
Fraction of eval rows where pipeline output `severity` matches `expected_severity`.
HIGH and CRITICAL misclassifications are treated as critical failures.

### 1.6 OOV Detection Rate
Fraction of rows in `arabizi_oov_eval.csv` where the pipeline correctly flags
at least one unknown meaningful token (not in production vocabulary).

### 1.7 High-Risk OOV Recall
Fraction of HIGH-risk OOV rows (expected_severity=HIGH or CRITICAL, oov_tokens non-empty)
that are correctly routed to HITL.

### 1.8 HITL Trigger Correctness
Of all rows that triggered HITL escalation: what fraction genuinely warranted HITL
(true positive rate)? This prevents HITL fatigue.

### 1.9 Normalization Coverage
Fraction of arabizi report tokens that can be normalized to a canonical form
(Arabic script or English) via the vocabulary's `arabic_script` and `english` metadata.

---

## 2. Current State (Honest Accounting)

| Metric | Data File Required | Status |
|--------|-------------------|--------|
| Vocabulary coverage | `cedarfix_reports_v1.csv` | MEASURED: 12.5% avg hit rate, 36/40 rows below 30% threshold (v1.5.1 baseline) |
| Sector accuracy | `arabizi_clean_eval.csv` | PENDING: no reviewed rows yet |
| Issue type F1 | `arabizi_clean_eval.csv` | PENDING: no reviewed rows yet |
| Route entity accuracy | `arabizi_clean_eval.csv` | PENDING: no reviewed rows yet |
| Severity accuracy | `arabizi_clean_eval.csv` | PENDING: no reviewed rows yet |
| OOV detection rate | `arabizi_oov_eval.csv` | PENDING: no reviewed rows yet |
| High-risk OOV recall | `arabizi_oov_eval.csv` | PENDING: no reviewed rows yet |
| HITL trigger correctness | Pipeline run logs | PENDING: requires production log access |
| Normalization coverage | `cedarfix_reports_v1.csv` | PENDING |

---

## 3. Known ARZ Gate Status

Gate definitions are in `data/eval/arabizi_excellence_gates_v1.json`.

| Gate | Description | Status |
|------|-------------|--------|
| ARZ-G01 | Vocab size ≥ 300 keywords | PASS (395 keywords in v1.5.1) |
| ARZ-G02 | Native speaker review sign-off | PENDING — needs human review |
| ARZ-G03 | Benchmark regression passes | PASS |
| ARZ-G04 | No stoplist terms in production | PASS |
| ARZ-G05 | Controlled promotion workflow | PASS (promote_arabizi_candidates.py) |
| ARZ-G06 | Reliability script runnable | PASS (gracefully handles missing corpus) |

5/6 gates passing. ARZ-G02 requires human review — cannot be automated.

---

## 4. Vocabulary State Summary

- **Version**: v1.5.1
- **Total keyword entries**: 395
- **Total term_metadata entries**: 24
- **Stoplist entries**: 7 (in `arabizi_stoplist.csv`)
- **Candidate bank**: 126 rows (122 PENDING, 4 DEFERRED)
- **Key corrections applied (v1.5.0 → v1.5.1)**:
  - Removed all `miye*` forms (Lebanese standard is `may`)
  - Removed `mat3a` forms (→ `2at3a`)
  - Removed `tire2` forms (→ `tari2`)
  - Removed `khafer` forms (non-word → `ri7a besh3a`)
  - Removed ambiguous `3ain` forms (→ `nab3`, `beer may`)

---

## 5. Ablation Plan (To Be Run When Eval Data Is Available)

Four conditions to measure sector accuracy:

| Condition | Description |
|-----------|-------------|
| raw_only | Raw Arabizi tokens, no normalization |
| normalized_only | Tokens normalized to Arabic script via vocabulary |
| raw_plus_norm | Both raw and normalized token signals |
| raw_plus_norm_oov | Above + OOV feature flag |

Expected ordering: raw_plus_norm_oov ≥ raw_plus_norm ≥ raw_only ≈ normalized_only.
**These are hypotheses, not results.** Actual ordering must be measured.

---

## 6. How to Generate Real Results

```bash
# Step 1: Confirm corpus is at correct path
ls data/corpus/cedarfix_reports_v1.csv

# Step 2: Run vocabulary coverage measurement
python scripts/validate_arabizi_reliability.py --save

# Step 3: Populate eval files with reviewed rows (requires native speaker)
#   data/eval/arabizi_clean_eval.csv
#   data/eval/arabizi_noisy_eval.csv
#   data/eval/arabizi_oov_eval.csv

# Step 4: Run classification pipeline on eval files and compare outputs
#   (integration with pipeline runner — implementation pending)
```

---

## 7. Important Guardrails

- Do NOT report any metric until the corresponding eval file has ≥ 20 reviewed rows.
- Do NOT use synthetic/fabricated rows for metrics — only real or native-speaker-approved examples.
- HIGH-risk OOV recall must be measured separately (not blended with overall OOV recall).
- The benchmark SHA (`arabizi_benchmark_v0_regression.sha256`) must continue to pass
  before and after any vocabulary change.
- `kasaret` is DEFERRED to Batch 003 — do not appear in any eval row until promoted.

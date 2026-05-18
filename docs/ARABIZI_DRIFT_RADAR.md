# CedarFix Adaptive Arabizi Layer

Version 1.0 | Purpose: turn unknown Lebanese Arabizi into measurable model-drift evidence

---

## 1. Why This Exists

A fixed Arabizi vocabulary is useful, but it is not enough. Real users will write misspellings, local phrases, panic shorthand, repeated letters, mixed English/French, and words the team did not predict.

The strongest CedarFix position is:

> CedarFix does not need the vocabulary to be complete. The system uses raw-text models for understanding, uses the vocabulary for high-precision normalization and explanations, and treats unknown meaningful Arabizi as monitored language drift.

---

## 2. Decision Loop

1. Citizen submits raw Arabizi/mixed report.
2. IEP-1 processes raw text and normalized text.
3. OOV detector extracts meaningful unknown tokens.
4. EEP lowers confidence if the unknown token appears in a high-impact or low-confidence case.
5. HITL reviewer labels the unknown token as vocabulary, stoplist, model-only, noise, or needs-more-examples.
6. Accepted terms become vocabulary/model retraining candidates.
7. MLflow/Grafana show OOV rate, accepted OOV rate, and high-risk OOV incidents over time.

---

## 3. Data Contract

Generated file:

`data/corpus/arabizi_oov_review_queue_v1.csv`

Required fields:

| Field | Meaning |
|-------|---------|
| `candidate_id` | Stable ID: `OOV-BNNN-NNN` |
| `batch` | Corpus batch where token was first detected |
| `normalized_token` | Noise-normalized token, e.g. `5tr444444` -> `5tr` |
| `raw_variants` | Pipe-separated raw spellings seen in reports |
| `frequency` | Total occurrences |
| `report_count` | Number of distinct reports containing the token |
| `report_ids` | Pipe-separated report IDs |
| `example_report_id` | First example report |
| `example_text` | Raw report text used for review |
| `proposed_sector` | Dominant sector if clear |
| `proposed_issue_type` | Dominant issue type if clear |
| `risk_hint` | `SAFETY_LEXICAL_HINT`, `HIGH_IMPACT_CONTEXT`, `HITL_CONTEXT`, or `LANGUAGE_DRIFT` |
| `suggested_action` | Initial automated suggestion |
| `reviewer_id` | Human reviewer ID |
| `review_status` | `PENDING_REVIEW`, `REVIEWED`, `NEEDS_CONTEXT`, `DISPUTED` |
| `decision` | Final human action |
| `notes` | Review rationale |

---

## 4. Reviewer Actions

| Decision | Meaning |
|----------|---------|
| `ADD_TO_VOCAB` | Promote to `arabizi_vocabulary.json` under a specific sector/issue_type |
| `KEEP_MODEL_ONLY` | Keep as model signal, but do not add to stable vocabulary |
| `ADD_TO_STOPLIST` | Suppress future alerts for connector/name/acronym/filler |
| `REJECT_NOISE` | Ignore as typo or irrelevant text |
| `NEEDS_MORE_EXAMPLES` | Wait for more corpus evidence |

---

## 5. Model Integration

The production pipeline must expose the `IEP1LanguageSignal` contract from
`src/shared/schemas.py`. Required operational fields:

- `language`
- `script_profile`
- `raw_text`
- `normalized_text`
- `normalization_applied`
- `normalization_confidence`
- `normalization_coverage`
- `arabizi_marker_count`
- `arabizi_marker_density`
- `code_mix_ratio`
- `oov_token_count`
- `oov_high_risk_count`
- `oov_tokens`
- `known_terms`
- `drift_score`
- `raw_text_embedding`
- `normalized_text_embedding`
- `explanation_features`

EEP uses them as confidence and fallback signals:

- If `oov_high_risk_count > 0`, force HITL.
- If `drift_score >= 2`, force HITL.
- If route confidence is below threshold and `oov_token_count > 0`, force HITL.
- If OOV rate for a batch spikes above baseline, mark the batch as drifted and require review before retraining.

The v1 regression probe in `src/shared/arabizi_features.py` is deliberately
heuristic. It exists to protect the contract before the trained IEP-1 model is
available; it is not the final classifier.

---

## 6. Demo Moment

Live input:

```text
fi jora kbire 3al tari2 w l wad3 m5atra ktir, seyyarat 3am tfel men 7adda
```

Expected visible outputs:

- Known terms: `jora`, `tari2`
- Unknown candidate: `m5atra`
- Predicted sector/issue: `ROADS / POTHOLE`
- Confidence impact: lower than clean vocabulary-covered report
- HITL reason: unknown high-risk Arabizi modifier
- Queue row: `m5atra` appears as a retraining/vocabulary candidate

This is stronger than a dictionary demo because it shows CedarFix surviving a term it did not know.

---

## 7. Evidence Required

To claim this in the final presentation, show:

- `python scripts/validate_arabizi_benchmark.py`
- `python scripts/analyze_arabizi_oov.py --self-test`
- `python scripts/analyze_arabizi_oov.py`
- `python scripts/validate_arabizi_oov_queue.py`
- `python scripts/tests/test_arabizi_adversarial.py`
- `python scripts/run_arabizi_stress_lab.py`
- `python scripts/certify_arabizi_input.py`
- `data/eval/arabizi_benchmark_v0_regression.sha256`
- `data/eval/arabizi_stress_lab_v1.json`
- `data/eval/arabizi_reliability_certificate_v1.json`
- `data/eval/arabizi_reliability_certificate_v1.html`
- OOV queue table before review
- One accepted/rejected example with reviewer rationale
- MLflow tag or run artifact containing vocabulary version and OOV queue hash
- Grafana panel: OOV candidates per batch and high-risk OOV count

`arabizi_benchmark_v0_regression.csv` is a frozen regression target, not a statistically meaningful final evaluation set. Use it to catch behavior changes; wait for Batch 002+ before reporting reliable Arabizi F1.

---

## 8. C-Phase Offline Evaluation

Script: `scripts/evaluate_arabizi_coverage.py`
Output: `data/eval/arabizi_coverage_batch001.json`

Run at the start of every batch review cycle:

```bash
python scripts/evaluate_arabizi_coverage.py
```

### Batch 001 Baseline (vocab v1.4.0, 14 arabizi/mixed rows)

| Metric | Value | Interpretation |
| --- | --- | --- |
| Mean known-term coverage | 97.7% | Strong post-v1.4.0 coverage after promoted OOV terms and proper-name/acronym suppression |
| Mean OOV tokens per row | 0.21 | Only meaningful non-promoted OOV remains visible instead of place names and service acronyms |
| Issue-type recall — probe | 100% (14/14) | All rows have ≥1 vocab seed matching the labeled issue_type |
| Issue-type recall — B1 raw | 100% (14/14) | Exact lowercase token lookup matches probe on clean Batch 001 data |
| Normalisation gain | 0.0pp | Expected: vocab built from these rows; noisier Batch 002 text will show positive gain |
| Drift score ≥ 2 rate | 28.6% (4/14) | Language-drift guard now triggers on actual ambiguity/risk instead of proper names |
| HITL labeled (ground truth) | 42.9% (6/14) | Actual HITL-required per corpus labeling |

### Drift distribution (Batch 001)

| Score | Count | % | Meaning |
| --- | --- | --- | --- |
| 0 — clean | 9 | 64.3% | Full vocab coverage, no OOV or language ambiguity |
| 1 — minor | 1 | 7.1% | 1 OOV token, coverage ≥ 75% |
| 2 — meaningful/HITL | 4 | 28.6% | Meaningful language-risk, safety hint, or ambiguity |
| 3 — severe | 0 | 0.0% | Severe drift condition not present in reviewed Batch 001 |

### HITL calibration note

The v1 heuristic probe triggers language-drift HITL (`drift_score >= 2`) for
28.6% of rows versus a 42.9% ground-truth HITL-labeled rate. This does **not**
mean the full system misses the remaining HITL rows: language drift is only one
guard. The EEP must also trigger HITL from sector, severity, public-safety
policy, and calibrated routing confidence. Once IEP-3 routing calibration is
built, the operative HITL threshold (`ROUTE_CONFIDENCE_THRESHOLD = 0.65`) will
combine with this language-risk signal.

### Per-sector summary (Batch 001)

| Sector | N | Cov | OOV | HITL% | Recall |
| --- | --- | --- | --- | --- | --- |
| ELECTRICITY | 3 | 100.0% | 0.0 | 100% | 100% |
| FLOODING | 2 | 100.0% | 0.0 | 0% | 100% |
| ROADS | 3 | 89.2% | 1.0 | 33% | 100% |
| SAFETY | 1 | 100.0% | 0.0 | 100% | 100% |
| WASTE | 2 | 100.0% | 0.0 | 0% | 100% |
| WATER | 3 | 100.0% | 0.0 | 33% | 100% |

### What to watch across batches

- **Normalisation gain** rising above 0pp in Batch 002 will confirm that
  `token_variants` / `hard_collapse_token` add value beyond exact lookup on
  noisier real-world text.
- **Mean coverage dropping** across batches indicates genuine vocabulary drift
  and triggers an OOV queue expansion.
- **Language-drift HITL** should not be forced to equal overall HITL. It should
  catch language-risk cases; sector/severity rules catch known public-safety
  cases.
- **Per-sector recall dropping** for any sector after a vocab promotion is a
  regression signal that requires OOV queue investigation for that sector.
- **Batch 001 recall is not generalization evidence** because v1.4.0 includes
  reviewed terms from Batch 001. Use it as a contract smoke test; use Batch
  002+ held-out rows for real Arabizi F1.

---

## 9. Arabizi Stress Lab

Script: `scripts/run_arabizi_stress_lab.py`
Output: `data/eval/arabizi_stress_lab_v1.json`

Run before demos and before promoting language-layer changes:

```bash
python scripts/run_arabizi_stress_lab.py
```

The Stress Lab is the adversarial "wow" surface for Arabizi. It generates messy
variants across pothole, transformer, and sewage scenarios, then records:

- strict sector and issue stability
- acceptable operational-decision stability for genuinely ambiguous cases
- OOV tokens and orthographic-noise counts
- code-mix ratio and marker density
- drift score and HITL trigger

Current gates:

| Gate | Threshold |
| --- | ---: |
| Stable sector rate | >= 90% |
| Acceptable decision rate | >= 90% |
| Strict issue rate observed | >= 75% |
| HITL-triggering variants | >= 3 |
| OOV/noise variants | >= 3 |

This is not a substitute for Batch 002+ held-out evaluation. It is a permanent
regression and demo artifact showing that CedarFix survives noisy Lebanese
Arabizi while exposing uncertainty instead of overclaiming certainty.

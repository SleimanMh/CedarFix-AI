# CedarFix Arabizi/Mixed Review Report — Batch 001

Version: 1.0  
Review date: 2026-05-18  
Review type: technical second-pass review, not a native-speaker human signoff  
Reviewer ID used in corpus: `CODEX-A2`  
Scope: 14 rows (`language=arabizi` or `language=mixed`) in `data/corpus/cedarfix_reports_v1.csv`

---

## 1. Reviewer Assignment And Scope

This review checked:

- semantic fidelity between `raw_text` and `normalized_text`
- sector, issue type, severity, route entity, HITL, and duplicate role consistency
- obvious Lebanese Arabizi spelling problems
- consistency with `arabizi_vocabulary.json`, `issue_severity_reference.yaml`, and the frozen B001 benchmark

Important limitation:

This is a technical/dialect-aware review by Codex. It should be treated as a strong pre-review, but a Lebanese speaker should still spot-check the rows before final submission if available.

---

## 2. Row-By-Row Findings

| report_id | language | action | correction | notes |
|---|---|---|---|---|
| `RPT-B001-003` | arabizi | Approved | None | `hofra` retained as known low-confidence `7ofra` variant; labels and duplicate role consistent. |
| `RPT-B001-006` | arabizi | Approved | None | Water-cut meaning, HIGH severity, and BMLWE route are consistent. |
| `RPT-B001-011` | arabizi | Approved | None | Exposed-wire CRITICAL safety semantics; HITL and EDL route correct. |
| `RPT-B001-015` | arabizi | Approved | None | Garbage non-collection; `tita3abba` preserved as meaningful bin-overflow verb. |
| `RPT-B001-019` | arabizi | Approved | None | Road-collapse/public-safety interpretation and CDR route are consistent. |
| `RPT-B001-024` | arabizi | Approved | None | Sewage overflow and public-health emergency labels are consistent. |
| `RPT-B001-028` | arabizi | Approved | Normalized `طريق غريق` to `الطريق غارق` | Same meaning, cleaner Arabic target for future normalization tests. |
| `RPT-B001-032` | arabizi | Approved | None | Structural-risk semantics; SAFETY/HITL/CD routing correct. |
| `RPT-B001-035` | arabizi | Approved | Light Arabic cleanup: `EDL مافي` to `EDL ما في`; added article to الكهرباء | Meaning preserved; POWER_OUTAGE/HITL policy correct. |
| `RPT-B001-040` | arabizi | Approved | Corrected `الأرض الخالي` to `الأرض الخالية` | Meaning preserved; illegal dumping and MOE route correct. |
| `RPT-B001-044` | arabizi | Approved | Corrected `balioa` to `balou3a` | Public Lebanese Arabic reference transliterates بالوعة as `Balou3a`; vocabulary and severity references updated. |
| `RPT-B001-049` | arabizi | Approved | None | High-severity pothole with vehicle-damage evidence; `kasaret` remains OOV watchlist. |
| `RPT-B001-051` | mixed | Approved | None | Raw-preserved mixed normalization accepted under current contract; `transformateur` tracked separately as `TRANSFORMER_FAULT` OOV token. |
| `RPT-B001-052` | mixed | Approved | None | Raw-preserved mixed normalization accepted under current contract; water-cut/BMLWE route consistent. |

---

## 3. Agreement Statistics

| Metric | Count |
|---|---:|
| Rows reviewed | 14 |
| Rows approved after technical review | 14 |
| Rows with label changes | 0 |
| Rows with normalization/text cleanup | 4 |
| Rows still `UNASSIGNED` | 0 |
| Rows still `PENDING_SECOND_REVIEW` | 0 |

Agreement by field:

| Field | Agreement |
|---|---:|
| `sector` | 14 / 14 |
| `issue_type` | 14 / 14 |
| `severity` | 14 / 14 |
| `route_entity` | 14 / 14 |
| `duplicate_role` | 14 / 14 |
| `hitl_required` | 14 / 14 |

---

## 4. Normalization Fidelity Observations

The review found no semantic drift that changed operational labels.

Notable normalization fixes:

- `RPT-B001-028`: `tari2 ghare2` is better represented as `الطريق غارق` than `طريق غريق`.
- `RPT-B001-035`: spacing/article cleanup improved Arabic readability without changing the power-outage meaning.
- `RPT-B001-040`: grammatical agreement corrected from `الأرض الخالي` to `الأرض الخالية`.
- `RPT-B001-044`: `balioa` was replaced with `balou3a`; active vocabulary and severity references were updated accordingly.

Mixed rows remain raw-preserved for now because the current schema sets `normalization_applied=false` for non-`arabizi` language values. This should be revisited when IEP-1 supports richer mixed-language normalization outputs.

---

## 5. Open Issues For Batch 002

1. Add a native Lebanese speaker spot-check before final submission if possible.
2. Include additional `balou3a` / `balo3a` blocked-drain examples so the normalizer does not overfit to one spelling.
3. Add mixed-language examples with French infrastructure terms: `transformateur`, `réseau`, `canalisation`, `panne`.
4. Keep `kasaret` on the OOV watchlist until a second independent occurrence confirms whether it belongs in vocabulary or model-only features.
5. Define a richer mixed-language normalization contract in IEP-1 so mixed rows can expose both raw and normalized Arabic views without violating the corpus validator.

---

## 6. Artifacts Updated

- `data/corpus/cedarfix_reports_v1.csv`
- `data/knowledge_base/arabizi_vocabulary.json`
- `data/knowledge_base/issue_severity_reference.yaml`
- `data/eval/arabizi_benchmark_v0_regression.csv`
- `data/eval/arabizi_benchmark_v0_regression.sha256`

Reference used for the blocked-drain transliteration check:

- Ithaca Bound Languages, "Drain / Drains in Lebanese Arabic" (`Balou3a`)

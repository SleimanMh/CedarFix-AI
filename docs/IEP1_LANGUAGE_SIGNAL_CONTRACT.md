# IEP-1 Language Signal Contract

Version: 1.0 | Applies to: CedarFix multilingual extraction service

---

## Purpose

IEP-1 must expose language reliability as structured data, not as a hidden model side effect. This contract lets the EEP route, abstain, explain, monitor, and retrain from the same evidence.

The contract is implemented in `src/shared/schemas.py` as `IEP1LanguageSignal`.

---

## Required Output Fields

| Field | Type | Why it exists |
|---|---|---|
| `language` | enum | Corpus and per-language evaluation split |
| `script_profile` | enum | Separates Arabic script, Latin Arabizi, mixed Latin, mixed script |
| `raw_text` | string | Audit and model input lineage |
| `normalized_text` | string | Arabic/mixed normalization output or raw-preserved text |
| `normalization_applied` | bool | Prevents silent `SAME` behavior |
| `normalization_confidence` | 0-1 float | Abstention and calibration feature |
| `normalization_coverage` | 0-1 float | Fraction of meaningful tokens covered by stable vocabulary/known terms |
| `arabizi_marker_count` | int | Direct evidence of Arabizi-specific characters |
| `arabizi_marker_density` | 0-1 float | Robustness signal for noisy Latin-script rows |
| `code_mix_ratio` | 0-1 float | French/English code-switching signal |
| `oov_token_count` | int | Language drift signal |
| `oov_high_risk_count` | int | Direct HITL trigger for safety-like unknowns |
| `oov_tokens` | list | Reviewer queue and active-learning lineage |
| `known_terms` | list | Explainability surface for the demo |
| `drift_score` | int 0-3 | Discrete EEP/HITL routing signal |
| `raw_text_embedding` | optional embedding ref | Raw input semantic channel |
| `normalized_text_embedding` | optional embedding ref | Normalized semantic channel |
| `explanation_features` | dict | Low-cardinality details for evidence cards |

Minimum v1 `explanation_features` keys:

| Key | Meaning |
|---|---|
| `vocab_version` | Vocabulary version used for analysis |
| `high_risk_term_count` | Known or unknown high-risk lexical hints |
| `semantic_ambiguity` | Whether wording is operationally ambiguous enough to justify review |
| `orthographic_noise_count` | Recognized-but-noisy tokens, such as repeated letters or embedded/fused known terms |
| `raw_token_count` | Raw Latin-token count |
| `meaningful_token_count` | Token count after stopword/entity suppression |

---

## Drift Score Semantics

| Score | Meaning | EEP behavior |
|---:|---|---|
| 0 | Clean or fully covered text | Use normal route confidence |
| 1 | Minor unknown language signal | Do not auto-fail; show in evidence |
| 2 | Meaningful drift, safety hint, ambiguity, or low coverage | Force HITL unless explicitly overridden in an experiment |
| 3 | Severe drift or multiple risky unknowns | Force HITL and log OOV review candidate |

`drift_score` is intentionally discrete in v1. It is a routing guardrail, not a calibrated probability.

---

## V1 Heuristic Probe

`src/shared/arabizi_features.py` provides a lightweight, non-model probe for regression tests. It is not the final IEP-1 classifier. Its job is to make sure known failure modes remain measurable before the trained model exists:

- repeated-character normalization
- digit-omission variants such as `hofra`
- no-space fused tokens
- French code-switching such as `transformateur`
- unknown high-risk modifiers such as `m5atra`
- sanitation ambiguity
- near-border non-merge distance checks for IEP-2

The final model must beat this probe in evaluation, but it must preserve the same output contract.

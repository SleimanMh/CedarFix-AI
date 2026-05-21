# Arabizi Data Expansion Strategy

## Decision

CedarFix should not inflate the production Arabizi vocabulary or candidate
promotion bank to thousands of rows just to look large. The reliable expansion
target is a separate, review-only surface-form layer:

```text
data/knowledge_base/arabizi/arabizi_surface_forms_v15.csv
```

This layer can safely grow to 5k-10k rows because it is blocked from routing,
severity assignment, sector classification, issue-type decisions, and core
vocabulary promotion.

## What To Expand

| Asset | Expansion Target | Reason |
|---|---:|---|
| `arabizi_surface_forms_v15.csv` | 5k-10k rows | Safe high-coverage normalization, OOV detection, duplicate matching support, stress tests |
| `arabizi_general_word_bank.csv` | 400-800 reviewed rows | Generic support words only; do not use for direct routing |
| `arabizi_protected_combos.csv` | 100-300 reviewed phrase locks | High value because phrases prevent false matches |
| `arabizi_eval_suite.csv` | 100-300 examples | Evaluation quality matters more than raw size |
| `arabizi_candidate_bank.csv` | Keep small and domain-only | Candidate rows can become production vocabulary, so they must stay conservative |
| `arabizi_vocabulary.json` | Promote slowly | Only approved, reviewer-signed, official-taxonomy terms enter production |

## External Research Notes

These resources are useful for future licensed ingestion or evaluation design,
but V15 does not import their raw rows:

| Resource | Use | Constraint |
|---|---|---|
| [CAMeL/CODA guidelines](https://camel-guidelines.readthedocs.io/en/latest/orthography/) | Orthographic governance and Arabic-script normalization principles | Use as guidance, not a word list |
| [`arbml/Arabizi_Transliteration`](https://huggingface.co/datasets/arbml/Arabizi_Transliteration) on Hugging Face | Candidate transliteration evaluation data | Check license and dialect fit before importing |
| [`palmaoui/AladdinBench`](https://huggingface.co/datasets/palmaoui/AladdinBench) on Hugging Face | Arabizi translation/evaluation examples with Lebanese coverage | Use only after license/provenance review |
| [Zenodo Romanised Arabic Chat Data](https://zenodo.org/record/4448380) | Real romanized Arabic chat-style language | Privacy/license review required before any import |
| [Arabic chat alphabet references](https://en.wikipedia.org/wiki/Arabic_chat_alphabet) | Notation sanity checks | Not a semantic vocabulary source |

## Professor-Safe Claim

CedarFix does not claim that thousands of generated surface forms are trusted
vocabulary. It claims a layered reliability design:

- trusted core vocabulary is small and reviewed;
- candidate bank is domain-only and promotion-gated;
- general word bank supports normalization but cannot route;
- protected combos prevent phrase-splitting errors;
- generated surface forms provide wide spelling coverage for OOV review,
  duplicate matching support, and stress testing.

## Why This Is Better Than A Giant Dictionary

A giant dictionary would create false confidence and make routing brittle.
Surface-form expansion gives the system broad recall while preserving
precision: generated variants can help recognize messy Arabizi, but they cannot
decide the complaint category by themselves.

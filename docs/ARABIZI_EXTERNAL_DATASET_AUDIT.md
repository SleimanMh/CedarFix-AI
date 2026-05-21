# Arabizi External Dataset Audit

Audit date: 2026-05-21

Purpose: identify external Arabizi / Lebanese / Levantine resources that can
improve CedarFix without weakening the reviewed-vocabulary governance model.

## Absorption Status

Project RBZ/SenZi, SenZi-Large, the Project RBZ thesis resources, and the Maria
Raïdy Kaggle Lebanese Arabizi dataset were downloaded or inspected from
quarantined `data/external_sources/` folders and mined into a review-only OOV
queue.

Generated artefacts:

- `data/knowledge_base/arabizi/external_source_ledger.csv`
- `data/knowledge_base/arabizi/lebanese_external_oov_candidates.csv`
- `docs/ARABIZI_EXTERNAL_ABSORPTION_REPORT.md`

No raw external text was copied into trusted vocabulary, and no external row was
promoted. The absorbed OOV rows remain blocked from routing, severity
assignment, and production promotion until native review. The current ledger
contains 14 source records, including sources intentionally not absorbed because
they are gated, license-unclear, tweet-ID-only, or Arabic-script rather than
Arabizi.

## Decision Summary

The best Lebanese-priority sources are:

1. **Project RBZ / SenZi / SenZi-Large / thesis resources**: deepest Lebanese
   Arabizi source family found. Contains Arabizi identification data, sentiment
   data, lexicons, expansion methodology, transliteration matrices, negation
   terms, and support lists.
2. **Maria Raïdy Kaggle Lebanese Arabizi tweets**: explicit Lebanese Arabizi
   Twitter dataset with CC0 metadata on Kaggle.
3. **AladdinBench**: real Arabizi messages from Lebanon, Egypt, and Algeria with
   MSA/English translations, but gated.
4. **Shami and ArSenTD-LEV**: useful Lebanese/Levantine Arabic-script resources,
   not Arabizi resources.

Professor-safe framing: CedarFix uses external sources through a provenance
ledger, license gate, reviewer queue, and non-routing support layers. External
data strengthens coverage and evaluation; it does not become trusted routing
vocabulary automatically.

## Priority Sources

| Priority | Source | Lebanese? | Size / Content | License / Access | CedarFix Use | Decision |
|---|---|---:|---|---|---|---|
| P0 | Project RBZ / SenZi / SenZi-Large / thesis resources | Yes | Identification data, 1.6K sentiment tweets, 4.4K Arabizi/not-Arabizi tweets, sentiment lexicons, large induced lexicons, translation matrices, negation/stopword support lists | Included disclaimers say non-commercial research use only and citation required | Best Lebanese Arabizi lexicon expansion and OOV source | Absorbed into review-only OOV queue; no production promotion |
| P0 | Kaggle: Datasets for Sentiment Analysis of Arabizi Tweets, Maria J. M. Raïdy | Yes | Lebanese Arabizi tweets, collected 2017-2020, geotagged in Lebanon; sentiment + highlight labels | Kaggle metadata shows CC0 Public Domain | Lebanese OOV mining, evaluation candidates, style reference | Absorbed into review-only OOV queue; sensitive raw text stays quarantined |
| P0 | AladdinBench, Hugging Face `palmaoui/AladdinBench` | Partial | Real Arabizi messages from Lebanon, Egypt, and Algeria; professional MSA/English translations | Gated Hugging Face dataset; must accept conditions | Excellent normalization/translation benchmark if access granted | Request access; do not import yet |
| P1 | Shami Dialect Corpus, GitHub `GU-CLASP/shami-corpus` | Yes | 117,805 Levantine Arabic-script sentences; Masader reports 16,304 Lebanese subset sentences | Apache-2.0 | Lebanese Arabic-script grounding and dialect-ID reference | Register as related source; not Arabizi |
| P1 | ArSenTD-LEV, Hugging Face `ramybaly/arsentd_lev` | Yes | 4,000 Arabic-script Levantine tweets equally from Jordan, Lebanon, Syria, Palestine | License marked "other"; card says to read/agree to OMA license | Lebanese/Levantine sentiment reference after license review | Register only; do not import until license checked |
| P1 | QADI, GitHub `qcri/QADI` | Yes country label | 540,590 tweet IDs across 18 countries; Lebanon subset exists | Tweet IDs only; hydration and Twitter/X compliance required | Lebanese dialect-ID stress test | Register only; do not depend on it |
| P1 | Levanti, Hugging Face `guymorlan/levanti` | Includes Lebanese/Levantine | 500K Levantine colloquial Arabic sentences with translations and transliteration fields | CC-BY-NC-4.0 | Non-commercial dialect grounding / transliteration comparison | Reference/eval only |
| P1 | Alexandria, Hugging Face `UBC-NLP/alexandria` | Yes LB subset | 107K English↔dialectal Arabic conversation turns | CC BY-NC-ND 4.0 | Reference only; no derivative training | Do not fine-tune on it |
| P1 | ArSyra Levantine, Hugging Face `ArSyra/arsyra-levantine` | Includes Lebanon | 50-row preview; 57,663 full records after purchase | Preview CC-BY-NC-SA; full set paid/licensed | Useful if licensed; not Arabizi-specific | Do not import full set without license |

## Broader Arabizi / Transliteration Sources

| Source | Region | Size / Content | License / Access | CedarFix Use | Decision |
|---|---|---|---|---|---|
| Hugging Face `arbml/Arabizi_Transliteration` | Mixed / unclear | 21,499 Arabizi↔Arabic token pairs; local manual drop exists | License field blank in `dataset_infos.json` | Good transliteration stress-test candidate | Blocked until license is clarified |
| Hugging Face `akhanafer/arabic-to-arabizi` | Levantine-ish examples | 433 Arabic↔Arabizi sentence pairs | README/license unclear | Small sanity set if license appears | Do not ingest yet |
| GitHub `HaifaCLG/Arabizi` | Mixed social media | Code-switching dataset, Reddit zip, tweet IDs, annotated word/sentence CSVs; local ZIP exists | No explicit license found in downloaded README | Useful methodology reference for code-switching | Do not import raw data yet |
| GitHub `iCompass-ai/TUNIZI` | Tunisian | 9,210 V1 and 100K V2 Tunisian Arabizi sentiment sentences | MIT | Tokenizer / stress-test source, not Lebanese training | Keep separate from Lebanese claims |
| GitHub `eligugliotta/tarc` | Tunisian | 4,797 sentences / 43,327 tokens with token class, CODA, POS, metadata | CC BY-NC-SA 4.0 | Methodology and non-Lebanese robustness | Reference/stress only |
| ELRA W0126 | Mixed | Arabizi detection/transliteration data | ELRA license required | Formal benchmark if licensed | Do not use without ELRA access |
| ELRA W0323 | Maghrebi | Annotated Arabizi/offense sequences and tweet IDs | ELRA license + tweet hydration constraints | Non-Lebanese stress if licensed | Do not use without ELRA access |

## Related Models

| Source | License / Access | Use | Decision |
|---|---|---|---|
| `assix-research/lebanese-llama-3.1-8b` | MIT model, not dataset | Lebanese/Arabizi teacher for synthetic examples | Never use as evaluation ground truth |
| `mradermacher/lebanese-llama-3.1-8b-GGUF` | MIT quantized model derivative | Local inference option | Model only, not corpus evidence |
| LebEval paper / benchmark lead | Dataset availability not verified | Track future Lebanese benchmark | Do not claim as available dataset |

## What Requires Access, License, Or Permission

| Source | Requirement |
|---|---|
| AladdinBench | Hugging Face gated access; accept conditions and share contact info |
| Project RBZ / SenZi / SenZi-Large / thesis | Non-commercial research use only; citation required |
| Raïdy Kaggle Lebanese Arabizi | CC0 metadata, but raw social text still needs sensitivity filtering before demo/public exposure |
| QADI | Twitter/X hydration and compliance |
| ArSenTD-LEV | License is "other"; read and agree to OMA license before import |
| ELRA W0126 / W0323 | ELRA registration/license; commercial fees may apply |
| ArSyra full Levantine | Paid academic or commercial license |
| Alexandria | CC BY-NC-ND: no derivatives |
| Levanti | CC-BY-NC: non-commercial only |
| TArC | CC-BY-NC-SA: non-commercial and share-alike |
| `arbml/Arabizi_Transliteration`, `akhanafer/arabic-to-arabizi`, `HaifaCLG/Arabizi`, `NArabizi` | License unclear; clarify before raw import |

## Recommended Next Actions

1. Request access to AladdinBench.
2. Clarify the license for `arbml/Arabizi_Transliteration`; if permissive, use
   it only for transliteration stress tests, not Lebanese claims.
3. Review the top 200 rows of `lebanese_external_oov_candidates.csv` with a
   native Lebanese reviewer and move only approved rows into GWB, stoplist, or
   domain candidate layers.
4. Keep the source ledger current:

```text
data/knowledge_base/arabizi/external_source_ledger.csv
```

5. Never write external source rows directly to:

```text
data/knowledge_base/arabizi_vocabulary.json
data/knowledge_base/arabizi/arabizi_candidate_bank.csv
```

## Professor-Safe Position

CedarFix did not scrape random Arabizi from the internet and call it trusted
data. The system uses external sources only through a provenance ledger, license
gate, reviewer queue, and non-routing support layers. Lebanese-specific sources
are prioritized, but no source is promoted into production without native review
and an official CedarFix issue-type target.

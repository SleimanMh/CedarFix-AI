# Arabizi External Dataset Audit

Audit date: 2026-05-21

Purpose: identify external Arabizi / Lebanese / Levantine resources that can
improve CedarFix without weakening the reviewed-vocabulary governance model.

No external raw dataset was imported during this audit.

## Decision Summary

The best next data sources are not more generic Hugging Face rows. The best
sources are:

1. Project RBZ / SenZi, because it is Lebanese Arabizi and contains lexicons,
   Arabizi identification data, sentiment data, a large Facebook corpus, and
   expansion methodology.
2. Maria Raïdy Lebanese Arabizi Kaggle dataset, because it is explicitly
   Lebanese Arabizi Twitter data.
3. AladdinBench, because it contains real Arabizi messages from Lebanon, Egypt,
   and Algeria with professional MSA and English translations, but it is gated.

All three require license/access review before ingestion.

## Priority Sources

| Priority | Source | Lebanese? | Size / Content | License / Access | CedarFix Use | Decision |
|---|---|---:|---|---|---|---|
| P0 | Project RBZ / SenZi | Yes | SenZi 2K sentiment words, 25K expanded words, 4.4K Arabizi/not-Arabizi tweets, 1.6K sentiment tweets, 1M Facebook Arabizi comments, 171K SenZi-Large expansion | Download links public, but no explicit machine-readable license found on page. Contact/permission recommended before raw import. | Best source for Lebanese Arabizi lexicon expansion methodology, spelling variants, language-ID examples, sentiment terms that can become non-routing support features. | Use as reference now. Import only after license/permission check. |
| P0 | Kaggle: Datasets for Sentiment Analysis of Arabizi Tweets, Maria J. M. Raïdy | Yes | Labeled Lebanese Arabizi tweets; collected 2017-2020; geotagging in Lebanon; columns include Text, sentiment, highlight | Kaggle page exposes a license section, but license text was not visible in browser audit. Must verify on Kaggle before import. Twitter/X reuse terms also matter if raw tweet text is included. | Strong candidate for Lebanese Arabizi evaluation, OOV mining, and synthetic infrastructure complaint style transfer. | Verify Kaggle license, then import a small audited subset if allowed. |
| P0 | AladdinBench, Hugging Face `palmaoui/AladdinBench` | Partial | Real Arabizi messages from Lebanon, Egypt, and Algeria; translated into MSA and English by a professional translator | Gated Hugging Face dataset; requires login and sharing contact info / accepting conditions. | Excellent benchmark for Arabizi normalization/translation robustness, especially Lebanese subset if exposed. | Request access. Use as evaluation/reference, not routing training. |
| P1 | QADI, GitHub `qcri/QADI` | Yes country label | 540,590 tweet IDs across 18 countries, including 38,386 LB train IDs and 194 LB test IDs | Tweet IDs only; hydration via Twitter/X tooling required; subject to Twitter/X terms and tweet availability. | Lebanese dialect-ID stress test; not Arabizi-specific. | Use only if hydration is feasible/legal. Do not depend on it. |
| P1 | Levanti, Hugging Face `guymorlan/levanti` | Includes Lebanese/Levantine | 500K Levantine colloquial Arabic sentences with English/Hebrew translations and transliteration fields | CC-BY-NC-4.0. Non-commercial only. | Useful for Lebanese/Levantine Arabic-script lexical grounding and transliteration comparison; not natural Arabizi. | Use only for non-commercial research/eval; cite. |
| P1 | Alexandria, Hugging Face `UBC-NLP/alexandria` | Yes LB subset | 107K English↔dialectal Arabic conversation turns across 13 countries with country/city/domain metadata | CC BY-NC-ND 4.0. Non-commercial, no derivatives. | Useful as reference/evaluation for Lebanese dialectal Arabic domains, not for fine-tuning or derivative training. | Use as benchmark/reference only. |
| P1 | ArSyra Levantine, Hugging Face `ArSyra/arsyra-levantine` | Includes Lebanon | 50-row free preview; 57,663 full records after purchase | Preview CC-BY-NC-SA-4.0; full dataset requires paid academic/commercial license. | Useful if purchased/licensed; not specifically Arabizi. | Do not import full dataset without paid license. |

## Broader Arabizi / Transliteration Sources

| Source | Region | Size / Content | License / Access | CedarFix Use | Decision |
|---|---|---|---|---|---|
| Hugging Face `arbml/Arabizi_Transliteration` | Mixed / unclear | 21,499 Arabizi↔Arabic token pairs | No dataset card/license visible during audit. | Good for notation/variant stress tests, but not Lebanese and not issue-domain specific. | Do not ingest until license is clarified. |
| Hugging Face `akhanafer/arabic-to-arabizi` | Levantine-ish examples | 433 Arabic↔Arabizi sentence pairs | README empty; no license visible. | Small useful sanity set for Arabic→Arabizi variants. | Do not ingest until license is clarified. |
| GitHub `HaifaCLG/Arabizi` | Mixed social media | Arabizi code-switching dataset, Reddit zip, tweet IDs, annotated word/sentence CSVs | No license visible during audit; tweet IDs/raw social data need caution. | Useful for language-ID/code-switching, not routing. | Use as methodology/reference; raw import requires license check. |
| GitHub `SamiaTouileb/NArabizi` | Algerian | NArabizi corpus with sentiment/topic annotations on top of treebank | No license visible on repo page during audit. | Useful for code-switching/parsing ideas; low Lebanese relevance. | Reference only unless license clarified. |
| GitHub `iCompass-ai/TUNIZI` | Tunisian | 9,210 V1 and 100K V2 Tunisian Arabizi sentiment sentences | MIT license. | Good for non-Lebanese stress tests and tokenizer robustness, not Lebanese training. | Safe to use with citation, but keep separate from Lebanese claims. |
| GitHub `eligugliotta/tarc` | Tunisian | 4,797 sentences / 43,327 tokens with token class, CODA, POS, metadata | CC BY-NC-SA 4.0. | Strong methodology source for token-level annotation and Arabizi classification. | Use for non-commercial methodology/stress tests, not Lebanese training. |
| ELRA W0126 | Mixed | Arabizi detection/transliteration train/test; 3,452 token transliterations and 127 tweet transliterations | ELRA license; registration/license required. | Useful formal transliteration benchmark. | Only use after ELRA license process. |
| ELRA W0323 | Morocco/Tunisia/Algeria | 17,103 annotated sequences; 495 Arabizi sequences / 21,216 tweets; tweet IDs + annotations | ELRA END USER / VAR licenses; commercial fees apply; tweets require API hydration. | Not Lebanese, but useful for hate/offense/code-switching stress tests. | Only use after ELRA license process. |

## Related Dialect Resources

| Source | License / Access | Use | Decision |
|---|---|---|---|
| `dataflare/arabic-dialect-corpus` | MIT | Large Arabic-script dialect corpus with Levantine category. | Use only for broad dialect pretraining/evaluation; not Arabizi. |
| `arbml/Arabic_Dialects_Dataset` | No license verified during audit | Arabic-script dialect text classification. | Low priority. |
| `assix-research/lebanese-llama-3.1-8b` | MIT model, not dataset | Lebanese Arabizi-capable model. | Can be used as a teacher for synthetic augmentation only; never as evaluation ground truth. |
| `alger-ia/dziribert` | Apache-2.0 model/code | Algerian Arabic + Latin-script model. | Useful methodological reference only. |

## What Requires Access, License, Or Permission

| Source | Requirement |
|---|---|
| AladdinBench | Hugging Face gated access; accept conditions and share contact info. |
| Project RBZ / SenZi | No explicit license found on project page; contact author or inspect downloaded ZIP license before import. |
| Raïdy Kaggle Lebanese Arabizi | Verify Kaggle license field and Twitter/X text reuse constraints before importing raw tweets. |
| QADI | Requires Twitter/X hydration; only tweet IDs are distributed. |
| ELRA W0126 / W0323 | ELRA registration/license. Commercial use may require fees. |
| ArSyra full Levantine | Paid academic or commercial license. |
| Alexandria | CC BY-NC-ND: no derivatives; avoid fine-tuning or transformed training outputs. |
| Levanti | CC-BY-NC: non-commercial only. |
| TArC | CC-BY-NC-SA: non-commercial and share-alike. |
| `arbml/Arabizi_Transliteration`, `akhanafer/arabic-to-arabizi`, `HaifaCLG/Arabizi`, `NArabizi` | License not visible/clear during audit; clarify before raw import. |

## Recommended Next Actions

1. Request/verify access to AladdinBench.
2. Open the Project RBZ ZIPs and check for an included license file before using
   any rows.
3. Check the Kaggle license for the Raïdy Lebanese Arabizi dataset from a logged
   in browser. If permissive, import a small audited subset into a separate
   `external_raw/` or `licensed_sources/` area, not directly into production
   vocab.
4. Create a source ledger CSV:

```text
data/knowledge_base/arabizi/external_source_ledger.csv
```

Required columns:

```text
source_id,source_name,url,region,license,access_requirement,allowed_uses,
blocked_uses,raw_import_allowed,notes,verified_by,verified_at
```

5. Only after license verification, create derived review queues:

```text
data/knowledge_base/arabizi/external_oov_candidates.csv
data/eval/arabizi_external_eval_candidates.csv
```

No external source should write directly to:

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

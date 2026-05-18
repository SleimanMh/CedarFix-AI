# External Arabizi NLP Resources

This document lists external references, datasets, tools, and research relevant to
Arabizi NLP for the CedarFix project. All resources below are research-grade references
only — they are NOT integrated into CedarFix. Integration requires review and explicit
approval.

---

## 1. What Is Arabizi?

Arabizi (also: Franco-Arabic, Arabish, Arabizi, Romanized Arabic) is the informal
romanization of Arabic used in digital communication — particularly in Lebanon, Egypt,
and the Levant. It is not a standardized orthography: the same word can be spelled
multiple ways by the same speaker.

CedarFix targets **Lebanese Arabizi** (Beirut dialect), which has specific features:
- Numbers as phoneme proxies: `3` = ع (ayin), `7` = ح (ha), `5` or `kh` = خ (kha), `2` = ء/أ (hamza), `4` = ش (sha) or ض
- French loanwords: `transformer`, `compteur`, `trottoir` → `troar`, `moteur`
- English loanwords: `pump`, `tank`, `generator`, `truck`
- Heavy ellipsis: `fi may` (there is water) = flood report

---

## 2. Academic Papers

| Title | Authors | Year | Notes |
|-------|---------|------|-------|
| ARLSCAN: Large-Scale Arabic Romanization | - | 2013+ | General Arabizi datasets, not Lebanese-specific |
| MADAR Arabic Dialect Corpus | Bouamor et al. | 2018 | 25 Arabic dialects incl. Beirut; no Arabizi transcriptions but very useful for lexical reference |
| ArabGlossBERT / AraBERT | Antoun et al. | 2020 | Arabic BERT; CedarFix does NOT use it yet — potential for semantic layer |
| Arabizi Identification in Twitter | Darwish | 2014 | Arabizi token detection in social media |
| Code-Switching in Lebanon | Kwaik et al. | 2018 | Ar/Fr/En code-switching patterns |

---

## 3. Useful Datasets

| Dataset | Language | Domain | Notes |
|---------|----------|--------|-------|
| MADAR Corpus | Arabic dialects | General | Beirut dialect sentences; no Arabizi |
| PADT (Prague Arabic Dependency Treebank) | MSA | News | Useful for morphological reference |
| Lebanese Twitter corpus (ad hoc) | Lebanese Arabizi | Social media | Not public; various scraped versions exist |
| DART (Dialectal Arabic Resources) | Multi-dialect | General | Check availability |

---

## 4. Normalisation Tools

| Tool | Notes |
|------|-------|
| Farasa | MSA segmentation; limited dialectal coverage |
| CAMeL Tools (NYU Abu Dhabi) | Arabic dialect NLP; includes some Levantine support |
| Qalb | Arabic spell correction; mostly MSA |
| Camel Morph | Morphological analysis; Beirut dialect coverage growing |

For CedarFix: do NOT plug external normalizers directly into pipeline without
offline testing on the local corpus. Unknown tools may introduce latency, licensing
issues, or misclassification.

---

## 5. Arabizi Encoding Conventions Used in CedarFix

| Number | Arabic letter | IPA | Example |
|--------|--------------|-----|---------|
| 2 | ء / أ | glottal stop | `2at3a` = قطعة |
| 3 | ع | pharyngeal fricative | `3atme` = عتمة |
| 4 | ش / ض | (varies) | `4anta` = rare; not in CedarFix vocab |
| 5 | خ | voiceless velar fricative | `5atar` = خطر |
| 6 | ط | emphatic t | rarely used in Lebanese Arabizi |
| 7 | ح | voiceless pharyngeal fricative | `7ufra` = حفرة |
| 8 | غ | voiced velar fricative | `8arib` (rare variant) |
| 9 | ص / ق | emphatic s or q | `9arsar` rare |

CedarFix uses: 2, 3, 5, 7 extensively. 4, 6, 8, 9 are marginal and not in production vocab.

---

## 6. Lebanese Dialect Reference

- **Frayha, Anis** — *A Dictionary of Modern Lebanese Proverbs* (general reference)
- **Naim Khattar** — *Dictionnaire libanais* (French-Lebanese)
- **AUB Linguistic Atlas of Lebanon** (ongoing) — if publicly available, good reference for regional variation
- Google Translate Lebanese Arabic: passable for common words; NOT reliable for Arabizi input; do not use for evaluation ground truth

---

## 7. Integration Checklist (before using any external tool/dataset)

- [ ] Confirm open license compatible with project use
- [ ] Offline evaluation on local corpus (no API calls in pipeline)
- [ ] Measure precision/recall delta vs current baseline on `arabizi_benchmark_v0_regression.csv`
- [ ] Native Lebanese speaker review of any new tokens added via external source
- [ ] SHA256 regression benchmark must still pass (`validate_arabizi_benchmark.py`)
- [ ] All new tokens go through candidate bank → human review → promotion workflow

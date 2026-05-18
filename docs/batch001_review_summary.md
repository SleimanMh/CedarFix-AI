# Batch 001 OOV Review Summary

**Reviewer:** LEAD-01  
**Review date:** 2026-05-18  
**Queue file:** `data/corpus/arabizi_oov_review_queue_v1.csv`  
**Corpus state after review:** 52 reports / 12 clusters / 90 pairs — validator 0 errors, 0 warnings

---

## Numbers

| Metric | Count |
| --- | --- |
| Candidates reviewed | 11 of 11 (full queue) |
| Confirmed ADD_TO_VOCAB (unchanged) | 5 |
| Promoted to ADD_TO_VOCAB (was NEEDS_MORE_EXAMPLES) | 5 |
| Kept at NEEDS_MORE_EXAMPLES (deferred) | 1 |
| Rejected / SKIP | 0 |
| **Final ADD_TO_VOCAB decisions** | **10** |

---

## Promotions (NEEDS_MORE_EXAMPLES → ADD_TO_VOCAB)

These five items were flagged by the auto-system as needing more examples but reviewer judged semantics unambiguous and sector signal strong enough to commit:

| Token | Arabic | Sector | Reason for promotion |
| --- | --- | --- | --- |
| `kuumeh` | كومة | WASTE | Sector-specific (pile of waste/rubble); not a general-purpose word |
| `nkesh` | إنكاش | WASTE | Lebanese colloquial for construction debris; distinct from `nfayat` (household garbage) |
| `ta7dir` | تحذير | ROADS | Correct 7=ح; "isharet ta7dir" (warning signs) is unambiguous |
| `tita3abba` | تتعبّى | WASTE | Contains mandatory 3=ع marker; bin overflow verb — clear semantic scope |
| `yroumo` | يرموا | WASTE | Standard plural conjugation; plurality signals organized (not accidental) dumping |

---

## Confirmed ADD_TO_VOCAB (system suggestion upheld)

| Token | Arabic | Sector | Notes |
| --- | --- | --- | --- |
| `7eet` | حيط | SAFETY | Structural damage vocabulary; always paired with `sa2f` (ceiling) |
| `ghare2` | غريق | FLOODING | Core flooding adjective for road surface; gh=غ standard |
| `mcharrak` | محرّك | ELECTRICITY | Live/running transformer — CRITICAL safety signal |
| `tetfa2ar` | تتفجّر | FLOODING | Dialectal overflow verb; 2=ء epenthetic glottal stop |
| `transformateur` | محوّل | ELECTRICITY | French loanword; required for mixed-language report detection |

---

## Deferred (kept at NEEDS_MORE_EXAMPLES)

| Token | Arabic | Reason |
| --- | --- | --- |
| `kasaret` | كسرت | General-purpose past-tense verb (broke/cracked); applicable across ROADS/SAFETY/WASTE; insufficient sector signal with frequency=1. Add to Batch 002 watchlist — promote on second occurrence. |

---

## Examples of corrections / notable findings

**1. `mcharrak` — transliteration deviation flagged**  
The auto-generated candidate used `ch` to represent ح, violating the vocab standard (`7` is mandatory for ح). The token was approved as a recognized variant, but the canonical form `m7arrak` must be the primary vocabulary entry. This is the only ch-for-ح inconsistency found in Batch 001.

**2. `nkesh` vs `nfayat` — semantic distinction preserved**  
Both appear in RPT-B001-040 (`3am yroumo nfayat w nkesh`). Promoting both allows the model to distinguish household garbage (`nfayat`) from construction debris (`nkesh`) — two different issue types routed differently (GARBAGE_NOT_COLLECTED vs ILLEGAL_DUMP).

**3. `transformateur` — first French-origin OOV**  
The OOV pipeline has not previously handled French loanwords. This entry establishes a precedent: French-origin tokens used natively in Lebanese speech should be admitted with metadata in a separate `term_metadata` section, while keeping `issue_type_keywords` as string lists. The token itself maps to ELECTRICITY/TRANSFORMER_FAULT even when the source report also mentions an exposed wire.

**4. `tetfa2ar` — epenthetic glottal stop pattern**  
The dialectal form `tetfa2ar` (تتفجّر with inserted ء) is a recurring Lebanese phonological pattern where a glottal stop is inserted before consonant clusters. Reviewers should expect similar forms in Batch 002 flooding reports (`yetle3`, `yef2aw`, etc.).

---

## Remaining limitations

1. **All 11 tokens have frequency = 1.** Vocabulary additions from this batch are provisional; coverage quality should be re-evaluated after Batch 002 provides independent confirmation.

2. **`kasaret` deferred.** The corpus currently lacks a second verb of the "physical damage" class in ROADS. Batch 002 should explicitly include 2–3 reports with tire or infrastructure damage to generate confirming instances.

3. **`mcharrak` canonical ambiguity resolved in v1.4.0.** The vocabulary now contains `m7arrak` as the canonical seed and `mcharrak` as a reviewed variant, with `term_metadata` documenting the ch-for-ح deviation.

4. **OOV pipeline does not tag French/English code-switching tokens separately.** `transformateur` entered the queue as a generic OOV. Batch 002 mixed-language reports will likely surface more French tokens (`réseau`, `canalisation`, `panne`). The pipeline should apply a `code_switch_origin: fr|en` flag to avoid conflating loanwords with transliteration errors.

5. **Sector coverage is uneven.** All LANGUAGE_DRIFT tokens (kasaret, kuumeh, nkesh, ta7dir, tita3abba, yroumo) come from just 3 reports (RPT-B001-015, RPT-B001-040, RPT-B001-049). ELECTRICITY, SAFETY, and FLOODING sectors are underrepresented in the OOV queue — Batch 002 should target denser per-report Arabizi in those sectors.

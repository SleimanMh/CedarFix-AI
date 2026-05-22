"""
apply_oov_v20f.py
=================
V20f: Full-corpus OOV dissection -- 51 new entries + 10 variant-form patches.
Bumps vocab 2.0.0 -> 2.1.0.

Sources:
  - Combined OOV scan (Lebanon CSV + arabizi-twitter-leb + Kaggle Arabizi +
    words_annotated.csv) top-300 OOV analysis
  - Manual review confirming Lebanese dialect authenticity

Additions breakdown:
  T3_GENERIC_SUPPORT  (function words / pronouns / particles / modals)  : 27 entries
  T2_SECTOR_SUPPORT   (nouns / verbs / temporal / sector-relevant)       : 17 entries
  T1_DIRECT_SIGNAL    (emotion / urgency / crisis markers)               :  7 entries
  VARIANT_PATCHES     (add missing forms to existing entries)            : 10 patches

Key high-frequency targets:
  helo/helou (198 occ) -- Lebanese 'beautiful' -- highest-freq OOV
  sar (59)             -- 'happened/became' -- core event-reporting verb
  ktr (28)             -- patch to ktir_quant (already in vocab)
  3melet (12)          -- patch to a3mel_verb (already in vocab)
  toli3/lt3 (20)       -- patch to tal3_verb (already in vocab)
  sa23a (23*)          -- 'hour' -- highest strict-digit OOV
  zaha2 (14*)          -- 'bored/fed up' -- digit-form emotion signal

Usage:
  python scripts/apply_oov_v20f.py [--dry-run]

All print() output is ASCII-only (Windows CP1252 constraint).
DO NOT re-run once vocab is at 2.1.0.
"""

import json
import re
import shutil
import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT            = Path(__file__).resolve().parent.parent
VOCAB_PATH      = ROOT / "data/knowledge_base/arabizi_vocabulary.json"
CURRENT_VERSION = "2.0.0"
NEW_VERSION     = "2.1.0"
REVIEWER_ID     = "SYSTEM-V20f"
REVIEW_DATE     = "2026-05-22"
ADDED_AT        = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

# ---------------------------------------------------------------------------
# 51 NEW ENTRIES
# ---------------------------------------------------------------------------
NEW_ENTRIES = {

    # -----------------------------------------------------------------------
    # T3_GENERIC_SUPPORT -- Function words: aspect markers, pronouns,
    # particles, modals, discourse markers.
    # -----------------------------------------------------------------------

    "la7_future": {
        "canonical_form": "la7",
        "arabic_equivalent": "\u0644\u062d",          # لح
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["la7", "lah", "la7a", "la72"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese future aspect marker 'will/gonna' (lah-ha = la7). "
            "la7 is the Arabizi digit form (7=ha ح); lah is the non-digit form. "
            "'la7 rou7' = 'I will go'. Core Lebanese grammar particle. "
            "Freq: la7=10*, lah=25 combined. Distinct from Egyptian ha- prefix."
        ),
        "added_at": ADDED_AT,
    },

    "houwe_pron": {
        "canonical_form": "houwe",
        "arabic_equivalent": "\u0647\u0648",          # هو
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["houwe", "huwe", "howe", "hou"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese third person masculine singular pronoun 'he' (huwwa). "
            "Lebanese full form 'houwe' vs MSA 'huwa'. "
            "Freq: houwe=18, huwe=13, howe=7 combined."
        ),
        "added_at": ADDED_AT,
    },

    "hiye_pron": {
        "canonical_form": "hiye",
        "arabic_equivalent": "\u0647\u064a",          # هي
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["hiye", "hiyeh", "hiyye"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese third person feminine singular pronoun 'she' (hiya). "
            "Lebanese full form 'hiye' vs MSA 'hiya'. "
            "Freq: hiye=10."
        ),
        "added_at": ADDED_AT,
    },

    "ento_pron": {
        "canonical_form": "ento",
        "arabic_equivalent": "\u0625\u0646\u062a\u0648",  # إنتو
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ento", "entou", "entun", "entow"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese second person plural pronoun 'you all/you guys' (intum). "
            "Lebanese form 'ento' vs MSA 'antum'. Freq: ento=16."
        ),
        "added_at": ADDED_AT,
    },

    "nehna_pron": {
        "canonical_form": "nehna",
        "arabic_equivalent": "\u0646\u062d\u0646\u0627",  # نحنا
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["nehna", "nahna", "ne7na", "ne7en"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese first person plural pronoun 'we' (nahnu). "
            "Lebanese 'nehna/nahna' vs MSA 'nahnu'. "
            "ne7na is Arabizi digit form (7=ha ح). "
            "Freq: nehna=8, nahna=7, ne7na=8* combined."
        ),
        "added_at": ADDED_AT,
    },

    "abel_prep": {
        "canonical_form": "abel",
        "arabic_equivalent": "\u0642\u0628\u0644",    # قبل
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["abel", "2abel", "2abl", "abl", "abil"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese preposition/adverb 'before' (qabla). "
            "Temporal and sequential marker. 'abel ma' = 'before that'. "
            "Lebanese form drops emphatic q: abel vs qabel. "
            "Freq: abel=31 -- 5th highest OOV."
        ),
        "added_at": ADDED_AT,
    },

    "heik_part": {
        "canonical_form": "heik",
        "arabic_equivalent": "\u0647\u064a\u0643",    # هيك
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["heik", "hek", "hayk", "heke"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese demonstrative adverb 'like this / so / thus' (haytha). "
            "Extremely common discourse particle: 'heik la2' = 'just like that', "
            "'heik w heik' = 'just so'. Freq: heik=22."
        ),
        "added_at": ADDED_AT,
    },

    "kello_quant": {
        "canonical_form": "kello",
        "arabic_equivalent": "\u0643\u0644\u0647",    # كله
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "kello", "kelo", "kella", "kela",
            "kelna", "kelon", "kellon",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese quantifier 'all of it / all / everyone' (kulluhu). "
            "kello=all of it (m clitic), kella=all of it (f), "
            "kelna=all of us, kelon=all of them. "
            "Very common totality marker. Freq: kello=19."
        ),
        "added_at": ADDED_AT,
    },

    "lezem_modal": {
        "canonical_form": "lezem",
        "arabic_equivalent": "\u0644\u0627\u0632\u0645",  # لازم
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["lezem", "lezm", "lazem", "lezim", "lezmo"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese obligation modal 'must / necessary / have to' (lazim). "
            "Urgency marker: 'lezem yeje' = 'he must come'. "
            "Lebanese shifts a->e in unstressed syllables. "
            "Freq: lezem=11, lezm=8 combined."
        ),
        "added_at": ADDED_AT,
    },

    "metel_prep": {
        "canonical_form": "metel",
        "arabic_equivalent": "\u0645\u062b\u0644",    # مثل
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["metel", "mtel", "mitl", "mitil", "mitel"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese comparative preposition 'like / similar to / such as' (mithla). "
            "Extremely common in comparisons and examples. "
            "'metel ma' = 'just as/like'. Freq: metel=25."
        ),
        "added_at": ADDED_AT,
    },

    "boukra_time": {
        "canonical_form": "boukra",
        "arabic_equivalent": "\u0628\u0643\u0631\u0627",  # بكرا
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "boukra", "bukra", "bokra",
            "bakir", "bakra", "bkra",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese temporal adverb 'tomorrow' (bukra). "
            "Multiple regional variants: boukra/bukra (Beirut), bakir/bokra (other). "
            "Freq: boukra=14, bukra=14, bokra=12, bakir=12 combined."
        ),
        "added_at": ADDED_AT,
    },

    "aslan_part": {
        "canonical_form": "aslan",
        "arabic_equivalent": "\u0623\u0635\u0644\u0627\u064b",  # أصلاً
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["aslan", "aslane", "asln"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese discourse particle 'actually / anyway / originally / still' (aslan). "
            "Common hedge and intensifier: 'aslan ma bya3rif' = 'he doesn't even know'. "
            "Freq: aslan=25."
        ),
        "added_at": ADDED_AT,
    },

    "bede_want": {
        "canonical_form": "bede",
        "arabic_equivalent": "\u0628\u062f\u064a",    # بدي
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "bede", "bedi", "beddi", "bedde",
            "baddo", "badda", "badak", "badik",
            "badon", "badkon", "badet",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese volitional verb 'want' (baddi). "
            "bede/bedi = I want, baddo = he wants, badak/badik = you want (m/f), "
            "badon = they want. Root b-d + clitic pronoun. "
            "Freq: bede=19, baddo=11, badak=10 combined."
        ),
        "added_at": ADDED_AT,
    },

    "fike_modal": {
        "canonical_form": "fike",
        "arabic_equivalent": "\u0641\u064a\u0643",    # فيك
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "fike", "fik", "fiki", "fiye",
            "fiya", "fina", "fiyon", "fikon",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese ability modal 'can' from fi (can/possible) + clitic pronoun. "
            "fike=you can (f), fik=you can (m), fina=we can, fiya/fiye=she can. "
            "'ma fike' = 'you cannot'. "
            "Freq: fike=17, fik=13, fina=13, fiya/fiye=10 combined."
        ),
        "added_at": ADDED_AT,
    },

    "lek_prep": {
        "canonical_form": "lek",
        "arabic_equivalent": "\u0644\u0643",          # لك
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["lek", "lak", "leki", "laki", "lkon"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese dative preposition 'for you / to you'. "
            "lek=for you (f), lak=for you (m). "
            "'3andi khabar lek' = 'I have news for you'. "
            "Freq: lek=17."
        ),
        "added_at": ADDED_AT,
    },

    "ele_prep": {
        "canonical_form": "ele",
        "arabic_equivalent": "\u0644\u0647",          # له
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ele", "elo", "ela", "elik", "elak"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese dative preposition 'for him / for her / for you'. "
            "ele/elo=for him, ela=for her, elik=for you (f), elak=for you (m). "
            "Lebanese clitic form of lahu/laha. "
            "Freq: ele=23, elo=17, ela=14 combined."
        ),
        "added_at": ADDED_AT,
    },

    "mnih_adj": {
        "canonical_form": "mnih",
        "arabic_equivalent": "\u0645\u0646\u064a\u062d",  # منيح
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["mnih", "mni7", "mniha", "mni7a", "mneeh"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese adjective 'good / well / nice / decent' (mniyah). "
            "mni7 is the Arabizi digit form (7=ha ح). "
            "Common positive assessment: 'mnih ktir' = 'very good'. "
            "Freq: mnih=12."
        ),
        "added_at": ADDED_AT,
    },

    "snin_noun": {
        "canonical_form": "snin",
        "arabic_equivalent": "\u0633\u0646\u064a\u0646",  # سنين
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["snin", "sneen", "sineen", "sinin"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese plural of 'year' (sanawat/snin). "
            "Common temporal reference: 'snin w snin' = 'years and years'. "
            "Freq: snin=11."
        ),
        "added_at": ADDED_AT,
    },

    "nes_noun": {
        "canonical_form": "nes",
        "arabic_equivalent": "\u0646\u0627\u0633",    # ناس
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["nes", "naas", "nass"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese noun 'people / folks' (nas). "
            "Very common community reference: 'kell el-nes' = 'all the people'. "
            "Freq: nes=26."
        ),
        "added_at": ADDED_AT,
    },

    "knt_past": {
        "canonical_form": "knt",
        "arabic_equivalent": "\u0643\u0646\u062a",    # كنت
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "knt", "kent", "kenet", "kenit",
            "kente", "kento", "keno",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese past tense forms of 'was/were' (kuntu). "
            "knt/kent=I was, kenet/kenit=I was (f. alt.), "
            "kente=you were (f.), kento=you were (pl.), keno=they were. "
            "Note: base form 'ken' already covered by ken_past entry. "
            "These are the abbreviated SMS/tweet forms. "
            "Freq: knt=12, keno=17, kenit=10 combined."
        ),
        "added_at": ADDED_AT,
    },

    "helou_adj": {
        "canonical_form": "helou",
        "arabic_equivalent": "\u062d\u0644\u0648",    # حلو
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "true",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "helou", "helo", "helwe", "helwi",
            "helwa", "helwin",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese adjective 'beautiful / nice / sweet / cute' (helw). "
            "helo/helou=m.sg, helwe=f.sg, helwin=pl. "
            "false_friend_risk=true: helo can be confused with English 'hello' -- "
            "disambiguation by context (standalone greeting vs descriptor). "
            "HIGHEST-FREQUENCY OOV: helo=198, helwe=20 combined."
        ),
        "added_at": ADDED_AT,
    },

    "ykoun_cop": {
        "canonical_form": "ykoun",
        "arabic_equivalent": "\u064a\u0643\u0648\u0646",  # يكون
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "ykoun", "ykun", "koun", "kono",
            "ykon", "ikoun", "tkoun", "nkoun",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese copula/existential verb 'to be / become / it is' (yakun). "
            "ykoun=he is, koun=be (imperative), kono=it was/became, "
            "tkoun=you are, nkoun=we are. "
            "Freq: ykoun=27, koun=15."
        ),
        "added_at": ADDED_AT,
    },

    "wallah_excl": {
        "canonical_form": "wallah",
        "arabic_equivalent": "\u0648\u0627\u0644\u0644\u0647",  # والله
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["wallah", "walla", "wallaw", "walla2"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic/Lebanese oath/exclamation 'by God / I swear / really' (wallahi). "
            "Used for emphasis, confirmation, and emotional intensity. "
            "'wallah ma 3ref' = 'I swear I don't know'. "
            "Freq: wallah=9."
        ),
        "added_at": ADDED_AT,
    },

    "wle_excl": {
        "canonical_form": "wle",
        "arabic_equivalent": "\u0648\u0644\u0627\u0647",  # ولاه
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["wle", "wlak", "wlo", "wlek", "wla"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese informal exclamation/vocative 'hey / dude / man' (ya walad). "
            "Masculine address particle used in colloquial speech. "
            "'wlak shu sa23a?' = 'man, what time is it?'. "
            "Freq: wle=11, wlak=10, wlo=10 combined."
        ),
        "added_at": ADDED_AT,
    },

    "inshallah_expr": {
        "canonical_form": "inshallah",
        "arabic_equivalent": "\u0625\u0646 \u0634\u0627\u0621 \u0627\u0644\u0644\u0647",  # إن شاء الله
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "inshallah", "inchallah", "nshalla",
            "nchallah", "nshallah", "nshla",
            "ensha2allah",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic/Lebanese expression 'God willing / hopefully / if God wills it'. "
            "Used for hope, deferment, polite refusal. Very common. "
            "Freq: nshalla=10, nchallah=8 combined."
        ),
        "added_at": ADDED_AT,
    },

    "mabsout_adj": {
        "canonical_form": "mabsout",
        "arabic_equivalent": "\u0645\u0628\u0633\u0648\u0637",  # مبسوط
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["mabsout", "mabsoute", "mbsout"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese adjective 'happy / content / satisfied / pleased' (mabsut). "
            "mabsout=m.sg, mabsoute=f.sg. "
            "Positive emotional state marker. Freq: mabsout=7."
        ),
        "added_at": ADDED_AT,
    },

    "tayeb_part": {
        "canonical_form": "tayeb",
        "arabic_equivalent": "\u0637\u064a\u0651\u0628",  # طيّب
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["tayeb", "tayyeb", "tayb", "6ayeb"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese discourse particle 'ok / alright / fine / well then' (tayyib). "
            "6ayeb is Arabizi digit form (6=ta emphatic ط). "
            "Very common conversation connector and acknowledgement. "
            "Freq: tayeb=10."
        ),
        "added_at": ADDED_AT,
    },

    "nos_noun": {
        "canonical_form": "nos",
        "arabic_equivalent": "\u0646\u0635",          # نص
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["nos", "noss", "nus", "nos2"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese noun 'half / middle / mid-' (nus). "
            "Common in quantities: 'nos kilo' = 'half a kilo', "
            "'nos se3a' = 'half an hour'. Freq: nos=17, noss=9 combined."
        ),
        "added_at": ADDED_AT,
    },

    # -----------------------------------------------------------------------
    # T2_SECTOR_SUPPORT -- Sector-relevant nouns, verbs, temporal markers.
    # -----------------------------------------------------------------------

    "sar_verb": {
        "canonical_form": "sar",
        "arabic_equivalent": "\u0635\u0627\u0631",    # صار
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "sar", "saret", "saro", "sarle",
            "sarlik", "sayer", "sayir",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese verb 'happened / became / turned into' (sara). "
            "Core event-reporting verb: 'shu sar?' = 'what happened?'. "
            "sar=it happened, saret=it happened (f/past), "
            "saro=they became, sayir=happening (active participle). "
            "HIGHEST-FREQUENCY non-digit OOV: sar=59."
        ),
        "added_at": ADDED_AT,
    },

    "sa23a_noun": {
        "canonical_form": "sa23a",
        "arabic_equivalent": "\u0633\u0627\u0639\u0629",  # ساعة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "sa23a", "sa3a", "sa3at", "sa3ten", "sa3o",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese noun 'hour / o'clock / time' (sa3a). "
            "Critical temporal reporting word: 'sa3a wle' = 'an hour ago', "
            "'sa3a kham' = 'five o'clock'. "
            "sa23a/sa3a are Arabizi digit forms (2=hamza, 3=ayin). "
            "HIGHEST strict-digit OOV: sa23a=23*."
        ),
        "added_at": ADDED_AT,
    },

    "hayet_noun": {
        "canonical_form": "hayet",
        "arabic_equivalent": "\u062d\u064a\u0627\u0629",  # حياة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "hayet", "hayete", "hayata",
            "hayatak", "hayeti", "hayetna",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese noun 'life / my life' (hayat). "
            "Used as endearment ('hayete' = 'my life / darling'), "
            "in pleas and crisis: 'khatar hayeto' = 'his life is at risk'. "
            "Freq: hayete=17, hayet=15 combined."
        ),
        "added_at": ADDED_AT,
    },

    "akel_noun": {
        "canonical_form": "akel",
        "arabic_equivalent": "\u0623\u0643\u0644",    # أكل
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["WATER", "WASTE"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["akel", "akl", "akla", "akalet", "akil"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese noun/verb 'food / eat / eating' (akl). "
            "Relevant to food safety, water contamination, waste context. "
            "Freq: akel=34, akl=11 combined."
        ),
        "added_at": ADDED_AT,
    },

    "wara_prep": {
        "canonical_form": "wara",
        "arabic_equivalent": "\u0648\u0631\u0627",    # ورا
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ROADS", "FLOODING"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["wara", "wara2", "warra"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese preposition 'behind / back / after' (wara2). "
            "Spatial indicator for road blockages, flood descriptions. "
            "'wara el-beit' = 'behind the house'. Freq: wara=12."
        ),
        "added_at": ADDED_AT,
    },

    "a7san_adj": {
        "canonical_form": "a7san",
        "arabic_equivalent": "\u0623\u062d\u0633\u0646",  # أحسن
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["a7san", "a7sen", "ahsan", "e7san"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese comparative adjective 'better / best / superior' (ahsan). "
            "a7san uses Arabizi digit 7=ha (ح). "
            "Used in service quality comparisons: 'a7san min abel' = 'better than before'. "
            "Freq: a7san=11*."
        ),
        "added_at": ADDED_AT,
    },

    "daroure_adj": {
        "canonical_form": "daroure",
        "arabic_equivalent": "\u0636\u0631\u0648\u0631\u064a",  # ضروري
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["daroure", "darouri", "daroura", "darure"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese adjective 'necessary / urgent / essential' (daruri). "
            "Urgency marker for crisis reporting: 'daroure teje' = 'it is urgent that you come'. "
            "severity_relevance=HIGH due to urgency signal. Freq: daroure=7."
        ),
        "added_at": ADDED_AT,
    },

    "emme_noun": {
        "canonical_form": "emme",
        "arabic_equivalent": "\u0625\u0645\u064a",    # إمي
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["emme", "emmi", "immi", "oummi", "ummi"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese noun 'my mother' (ummi). "
            "Common in emotional appeals and family context. "
            "Freq: emme=12."
        ),
        "added_at": ADDED_AT,
    },

    "chabeb_noun": {
        "canonical_form": "chabeb",
        "arabic_equivalent": "\u0634\u0628\u0627\u0628",  # شباب
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "chabeb", "shabeb", "chabab",
            "shabab", "shab",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese noun 'guys / youth / young people' (shabab). "
            "Informal address term and social group reference. "
            "Freq: chabeb=13, shabeb=9 combined."
        ),
        "added_at": ADDED_AT,
    },

    "albe_noun": {
        "canonical_form": "albe",
        "arabic_equivalent": "\u0642\u0644\u0628\u064a",  # قلبي
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["albe", "albi", "alb", "albo", "albak", "albha"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese noun 'heart / my heart' (qalbi). "
            "Common in emotional appeals and health context. "
            "'ya albe' = 'oh my heart'. 'alb' = heart (base). "
            "Freq: albe=33."
        ),
        "added_at": ADDED_AT,
    },

    "jou3_noun": {
        "canonical_form": "jou3",
        "arabic_equivalent": "\u062c\u0648\u0639",    # جوع
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["WATER", "WASTE"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["jou3", "joo3", "jaw3"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese noun 'hunger / starvation' (ju3). "
            "Arabizi digit 3=ayin (ع). "
            "Food security signal relevant to crisis reporting. "
            "severity_relevance=HIGH (food insecurity). Freq: jou3=9*."
        ),
        "added_at": ADDED_AT,
    },

    "mbere7_time": {
        "canonical_form": "mbere7",
        "arabic_equivalent": "\u0645\u0628\u0627\u0631\u062d",  # مبارح
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["mbere7", "mbare7", "embareh", "embare7"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese temporal adverb 'yesterday' (mbarrih). "
            "Arabizi digit 7=ha (ح). "
            "Event-reporting anchor: 'mbere7 sar' = 'yesterday it happened'. "
            "Freq: mbere7=9*."
        ),
        "added_at": ADDED_AT,
    },

    "fatra_noun": {
        "canonical_form": "fatra",
        "arabic_equivalent": "\u0641\u062a\u0631\u0629",  # فترة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["fatra", "fetre", "fetrit"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese noun 'period / duration / time span' (fatra). "
            "Temporal context: 'hal fatra' = 'this period / lately'. "
            "Freq: fatra=8."
        ),
        "added_at": ADDED_AT,
    },

    "kher_noun": {
        "canonical_form": "kheir",
        "arabic_equivalent": "\u062e\u064a\u0631",    # خير
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["kheir", "kher", "khayr", "kheer"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic/Lebanese noun 'good / blessing / welfare' (khayr). "
            "Common in assessments: 'ma fi kheir' = 'nothing good / things are bad'. "
            "Freq: kheir=7, kher=8 combined."
        ),
        "added_at": ADDED_AT,
    },

    "so2al_noun": {
        "canonical_form": "so2al",
        "arabic_equivalent": "\u0633\u0624\u0627\u0644",  # سؤال
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["so2al", "sou2al", "su2al", "so2alo"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese noun 'question / inquiry' (su2al). "
            "Arabizi digit 2=hamza (ء). "
            "Common in service requests and complaints. "
            "Freq: so2al=10*."
        ),
        "added_at": ADDED_AT,
    },

    # -----------------------------------------------------------------------
    # T1_DIRECT_SIGNAL -- Emotion, urgency, negative sentiment markers.
    # -----------------------------------------------------------------------

    "zaha2_adj": {
        "canonical_form": "zaha2",
        "arabic_equivalent": "\u0632\u0647\u0642",    # زهق
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["zaha2", "zahe2", "zehe2"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese adjective/state 'bored / fed up / exhausted by' (zahi2). "
            "Arabizi digit 2=hamza/qaf (ق). "
            "Strong negative-affect signal: 'zaha2t' = 'I am fed up'. "
            "Freq: zaha2=14*."
        ),
        "added_at": ADDED_AT,
    },

    "khara_expr": {
        "canonical_form": "khara",
        "arabic_equivalent": "\u062e\u0631\u0627",    # خرا
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["khara", "khara2", "khare"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese profanity 'shit / excrement' (khara). "
            "Strong negative sentiment signal used to express disgust or anger. "
            "must_not_auto_promote=true due to profanity; "
            "include for negative-sentiment detection. Freq: khara=11."
        ),
        "added_at": ADDED_AT,
    },

    "beche3_adj": {
        "canonical_form": "beche3",
        "arabic_equivalent": "\u0628\u0634\u0639",    # بشع
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["beche3", "bche3", "bche3a"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese adjective 'ugly / terrible / disgusting / horrible' (bashi3). "
            "Arabizi digit 3=ayin (ع). "
            "Strong negative assessment: 'hal shi beche3' = 'this thing is terrible'. "
            "Freq: beche3=9*."
        ),
        "added_at": ADDED_AT,
    },

    "bmout_expr": {
        "canonical_form": "bmout",
        "arabic_equivalent": "\u0628\u0645\u0648\u062a",  # بموت
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "true",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["bmout", "bmoute"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese hyperbolic intensity expression 'I die of (love/laughter/fear)' (bimut). "
            "false_friend_risk=true: USUALLY figurative, NOT literal death. "
            "'bmout 3lik' = 'I love you intensely' (lit. 'I die for you'). "
            "must_not_auto_promote=true: requires context for literal vs figurative. "
            "Freq: bmout=15."
        ),
        "added_at": ADDED_AT,
    },

    "habal_adj": {
        "canonical_form": "habal",
        "arabic_equivalent": "\u0647\u0628\u0644",    # هبل
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["habal", "hable", "hablanet", "7abal"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese adjective/noun 'crazy / stupid / idiot' (habal). "
            "7abal is Arabizi digit form (7=ha ح). "
            "Frustration/anger signal, occasionally used affectionately. "
            "Freq: habal=7."
        ),
        "added_at": ADDED_AT,
    },

    "nar_signal": {
        "canonical_form": "nar",
        "arabic_equivalent": "\u0646\u0627\u0631",    # نار
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["SAFETY", "FLOODING"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "true",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["nar", "naar"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Arabic/Lebanese noun 'fire' (nar). "
            "false_friend_risk=true: used LITERALLY ('fi nar' = 'there is fire') "
            "AND FIGURATIVELY ('hayde nar' = 'she is amazing'). "
            "As T1_DIRECT_SIGNAL for SAFETY when literal fire context. "
            "Context disambiguation required. Freq: nar=7."
        ),
        "added_at": ADDED_AT,
    },

    "ra23_expr": {
        "canonical_form": "ra23",
        "arabic_equivalent": "\u0631\u0639\u0634",    # رعش
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ra23", "ra3ch", "ra3ich"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese verb/state 'trembling / shaking' (ra3ash). "
            "Arabizi digits 2=hamza/3=ayin (ع). "
            "Can signal fear, shock, or physical reaction to an event. "
            "'ana ra23' = 'I am trembling'. Freq: ra23=8*."
        ),
        "added_at": ADDED_AT,
    },

}  # end NEW_ENTRIES


# ---------------------------------------------------------------------------
# 10 VARIANT PATCHES -- Add missing forms to existing entries
# ---------------------------------------------------------------------------
VARIANT_PATCHES = {

    # 3m: add 'aam' (non-digit form of the continuous aspect marker 3am/3em)
    "3m": {
        "add_variants": ["aam"],
    },

    # ktir_quant: add abbreviated/variant forms (ktr is 3rd highest OOV non-digit)
    "ktir_quant": {
        "add_variants": ["ktr", "kter", "ktiiir"],
    },

    # tal3_verb: add toli3/tole3/lt3 (past-tense/verbal-noun forms, freq 20+12+8)
    "tal3_verb": {
        "add_variants": ["toli3", "tole3", "lt3"],
    },

    # a3mel_verb: add past-tense conjugations (3melet = 'did/made', freq 12*)
    "a3mel_verb": {
        "add_variants": ["3melet", "3amelet", "3amelo", "3amlet"],
    },

    # ba3da_temporal: add ba3doun (they still/after them, freq 7*)
    "ba3da_temporal": {
        "add_variants": ["ba3doun", "ba3dun"],
    },

    # wad3_noun: add wade3 (non-compressed form, freq 10*)
    "wad3_noun": {
        "add_variants": ["wade3"],
    },

    # halla2_now: add hal2a (variant of halla2 'now', freq 8*)
    "halla2_now": {
        "add_variants": ["hal2a", "hala2a"],
    },

    # chou_question: add chu/sho/cho (high-freq Lebanese forms not yet covered)
    "chou_question": {
        "add_variants": ["chu", "sho", "cho"],
    },

    # allah_excl: add yalle/yalli (Lebanese variants of yalla, freq 9+7)
    "allah_excl": {
        "add_variants": ["yalle", "yalli"],
    },

    # 3la: add 3layk/3layki/3layna/3layon (directional clitics, freq 9+7+7)
    "3la": {
        "add_variants": ["3layk", "3layki", "3layna", "3layon", "3lakon"],
    },

}  # end VARIANT_PATCHES


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def normalise(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    s = re.sub(r"[0146]+$", "", s)
    s = re.sub(r"(.)\1{3,}", r"\1\1\1", s)
    return s


def build_known(vocab: dict) -> set:
    known = set()
    for entry in vocab["term_metadata"].values():
        for vf in entry.get("variant_forms", []):
            n = normalise(vf)
            if n:
                known.add(n)
    return known


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main(dry_run: bool) -> None:
    print("[V20f] Loading vocab from: " + str(VOCAB_PATH))
    vocab = json.load(open(VOCAB_PATH, encoding="utf-8"))

    current = vocab.get("version", "?")
    if current != CURRENT_VERSION:
        print("[ERROR] Expected version " + CURRENT_VERSION
              + ", got " + current + ". Aborting.")
        return

    meta = vocab["term_metadata"]

    # -- Check for key collisions ---
    collisions = [k for k in NEW_ENTRIES if k in meta]
    if collisions:
        print("[WARN] Already-existing keys: " + str(collisions))

    # -- Check for missing patch targets ---
    missing_patches = [k for k in VARIANT_PATCHES if k not in meta]
    if missing_patches:
        print("[WARN] Patch targets missing from meta: " + str(missing_patches))

    # -- Report plan ---
    t1 = sum(1 for e in NEW_ENTRIES.values() if e["semantic_type"] == "T1_DIRECT_SIGNAL")
    t2 = sum(1 for e in NEW_ENTRIES.values() if e["semantic_type"] == "T2_SECTOR_SUPPORT")
    t3 = sum(1 for e in NEW_ENTRIES.values() if e["semantic_type"] == "T3_GENERIC_SUPPORT")
    print("[V20f] New entries      : " + str(len(NEW_ENTRIES))
          + "  (T1=" + str(t1) + " T2=" + str(t2) + " T3=" + str(t3) + ")")
    print("[V20f] Variant patches  : " + str(len(VARIANT_PATCHES)))
    print("[V20f] Version          : " + CURRENT_VERSION + " -> " + NEW_VERSION)

    if dry_run:
        print()
        print("[DRY-RUN] New entry keys:")
        for k in NEW_ENTRIES:
            vf = NEW_ENTRIES[k]["variant_forms"]
            print("  " + k.ljust(28) + "  variants=" + str(vf[:4]))
        print()
        print("[DRY-RUN] Variant patches:")
        for entry_key, patch in VARIANT_PATCHES.items():
            if entry_key in meta:
                existing = meta[entry_key].get("variant_forms", [])
                new_vf = [v for v in patch["add_variants"] if v not in existing]
                print("  " + entry_key + ": +" + str(new_vf))
            else:
                print("  [MISSING] " + entry_key + " not found in meta")
        print()
        # Simulate
        sim_vocab = json.loads(json.dumps(vocab))
        sim_meta  = sim_vocab["term_metadata"]
        known_before = build_known(vocab)
        for k, entry in NEW_ENTRIES.items():
            if k not in sim_meta:
                sim_meta[k] = entry
        for entry_key, patch in VARIANT_PATCHES.items():
            if entry_key in sim_meta:
                existing = set(sim_meta[entry_key].get("variant_forms", []))
                for v in patch["add_variants"]:
                    existing.add(v)
                sim_meta[entry_key]["variant_forms"] = sorted(existing)
        known_after = build_known(sim_vocab)
        added = known_after - known_before
        print("[DRY-RUN] known_tokens before : " + str(len(known_before)))
        print("[DRY-RUN] known_tokens after  : " + str(len(known_after)))
        print("[DRY-RUN] New normalised forms: " + str(len(added)))
        print("[DRY-RUN] Sample new forms    : " + str(sorted(added)[:30]))
        return

    # -- Backup ---
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = VOCAB_PATH.with_suffix(".bak-before-v20f-" + ts + ".json")
    shutil.copy2(VOCAB_PATH, backup)
    print("[V20f] Backup saved: " + backup.name)

    known_before = build_known(vocab)

    # -- Apply new entries ---
    added_count = 0
    for k, entry in NEW_ENTRIES.items():
        if k in meta:
            print("[SKIP] " + k + " already exists")
        else:
            meta[k] = entry
            added_count += 1

    # -- Apply variant patches ---
    patch_count = 0
    for entry_key, patch in VARIANT_PATCHES.items():
        if entry_key not in meta:
            print("[WARN] Patch target '" + entry_key + "' not found -- skipping")
            continue
        existing = set(meta[entry_key].get("variant_forms", []))
        before_len = len(existing)
        for v in patch["add_variants"]:
            existing.add(v)
        meta[entry_key]["variant_forms"] = sorted(existing)
        added_vf = len(existing) - before_len
        patch_count += added_vf
        print("[PATCH] " + entry_key + ": +" + str(added_vf) + " variant form(s)")

    # -- Bump version + changelog ---
    vocab["version"] = NEW_VERSION
    changelog_entry = (
        NEW_VERSION + " (2026-05-22): V20f full-corpus OOV dissection -- "
        + str(added_count) + " new term_metadata entries + "
        + str(len(VARIANT_PATCHES)) + " entry patches. "
        "Covers: Lebanese pronouns (houwe/hiye/ento/nehna), "
        "aspect markers (la7 future), discourse particles (heik/aslan/wle/wallah), "
        "event verb (sar=59 occ), temporal (boukra/mbere7/sa23a), "
        "adjectives (helou=198 occ, mnih, a7san, zaha2), "
        "modals (lezem/fike/bede), function words (abel/metel/kello/nes/snin). "
        "Patches: 3m+aam, ktir_quant+ktr, tal3_verb+toli3/tole3/lt3, "
        "a3mel_verb+3melet, chou_question+chu/sho, allah_excl+yalle/yalli, "
        "3la+3layk/3layki/3layna, wad3_noun+wade3, halla2_now+hal2a, "
        "ba3da_temporal+ba3doun. "
        "Source: combined OOV scan top-300 (Lebanon CSV + arabizi-twitter-leb + "
        "Kaggle Arabizi + words_annotated.csv)."
    )
    vocab.setdefault("changelog", []).append(changelog_entry)

    known_after = build_known(vocab)
    new_forms = known_after - known_before

    # -- Save ---
    with open(VOCAB_PATH, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=2)

    print()
    print("[V20f] Done. Vocab bumped " + CURRENT_VERSION + " -> " + NEW_VERSION)
    print("[V20f] term_metadata entries : " + str(len(meta)))
    print("[V20f] New entries applied   : " + str(added_count))
    print("[V20f] Variant patch forms   : " + str(patch_count))
    print("[V20f] known_tokens before   : " + str(len(known_before)))
    print("[V20f] known_tokens after    : " + str(len(known_after)))
    print("[V20f] New normalised forms  : " + str(len(new_forms)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing")
    args = parser.parse_args()
    main(dry_run=args.dry_run)

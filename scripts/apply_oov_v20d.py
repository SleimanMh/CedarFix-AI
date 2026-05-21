"""
apply_oov_v20d.py
=================
V20d: Full-corpus OOV closure — 34 new entries + 2 variant-form patches.
Bumps vocab 1.8.0 -> 1.9.0.

Sources:
  - scripts/_scan_corpus_oov_full.py   (64K-tweet full corpus scan)
  - scripts/_check_gaps.py             (gap verification vs vocab 1.8.0)

Polysemous entries (separate entries per distinct meaning):
  fi_prep / fi_exist         -- "in" (preposition) vs "there is" (existential)
  ma_neg / ma_excl           -- negation "not" vs exclamative intensifier "how!"
  ra3is_political / ra3is_general  -- president vs boss/chief (domain difference)
  ba3da_temporal / ba3da_possessive -- "still/yet" vs "after her"
  ma3na_noun                 -- "meaning" (separate from ma3_preposition which covers "with us")

Usage:
  python scripts/apply_oov_v20d.py [--dry-run]

All print() output is ASCII-only (Windows CP1252 constraint).
DO NOT re-run once vocab is at 1.9.0.
"""

import json
import re
import shutil
import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT         = Path(__file__).resolve().parent.parent
VOCAB_PATH   = ROOT / "data/knowledge_base/arabizi_vocabulary.json"
CURRENT_VERSION = "1.8.0"
NEW_VERSION     = "1.9.0"
REVIEWER_ID     = "SYSTEM-V20d"
REVIEW_DATE     = "2026-05-22"
ADDED_AT        = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

# ---------------------------------------------------------------------------
# 34 NEW ENTRIES
# ---------------------------------------------------------------------------
NEW_ENTRIES = {

    # -----------------------------------------------------------------------
    # TIER 1 — Critical functional words (freq >= 50)
    # -----------------------------------------------------------------------

    "ma_neg": {
        "canonical_form": "ma",
        "arabic_equivalent": "\u0645\u0627",          # ما
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "true",       # "ma" = French "my" / English "mom"
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ma", "maa", "mah"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi negation particle 'not' (ma bidi = I don't want). "
            "POLYSEMY NOTE: see ma_excl for exclamative use 'how...!'. "
            "false_friend: English 'ma' = mother, French 'ma' = my (fem)."
        ),
        "added_at": ADDED_AT,
    },

    "ma_excl": {
        "canonical_form": "ma",
        "arabic_equivalent": "\u0645\u0627",          # ما
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "true",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ma"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese Arabizi exclamative intensifier 'how...!' "
            "(ma 7elo = how beautiful!). "
            "POLYSEMY: same surface form 'ma' as ma_neg (negation particle). "
            "Context distinguishes: exclamative follows 'ma' + adjective/predicate."
        ),
        "added_at": ADDED_AT,
    },

    "el_article": {
        "canonical_form": "el",
        "arabic_equivalent": "\u0627\u0644",          # ال
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["el", "al", "l", "il"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic definite article 'the'. "
            "Lebanese Arabizi: 'el' most common, 'al' also used, "
            "'l' as clitic prefix (l-beit = the house)."
        ),
        "added_at": ADDED_AT,
    },

    "ya_vocative": {
        "canonical_form": "ya",
        "arabic_equivalent": "\u064a\u0627",          # يا
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ya", "yaa"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic vocative particle 'hey/oh', used to address someone "
            "(ya habibi = hey my friend, ya allah = oh God). "
            "Extremely common in Lebanese Arabizi."
        ),
        "added_at": ADDED_AT,
    },

    "bi_prep": {
        "canonical_form": "bi",
        "arabic_equivalent": "\u0628",               # ب
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["bi", "b"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic preposition 'in/at/with/by' as prefix or standalone. "
            "Lebanese Arabizi: 'bi' standalone, 'b' as prefix clitic (b-Beirut). "
            "Note: bel/bil entries cover the 'bi+al' contraction."
        ),
        "added_at": ADDED_AT,
    },

    "fi_prep": {
        "canonical_form": "fi",
        "arabic_equivalent": "\u0641\u064a",          # في
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["fi", "fii"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic preposition 'in' (locative). "
            "POLYSEMY: see fi_exist for existential use 'there is/are'. "
            "Context: fi_prep precedes a noun phrase indicating location "
            "(fi l-beit = in the house)."
        ),
        "added_at": ADDED_AT,
    },

    "fi_exist": {
        "canonical_form": "fi",
        "arabic_equivalent": "\u0641\u064a",          # في
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["fi", "fee", "fih"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic existential particle 'there is/there are' (fi mshkle = there is a problem). "
            "POLYSEMY: same surface form 'fi' as fi_prep (preposition 'in'). "
            "Negated as: ma fi (there isn't). Very common in Arabizi complaint tweets."
        ),
        "added_at": ADDED_AT,
    },

    "men_prep": {
        "canonical_form": "men",
        "arabic_equivalent": "\u0645\u0646",          # من
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "true",        # English "men" = plural of man
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["men", "min", "mn"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic preposition/conjunction: 'from' (men Beirut = from Beirut), "
            "'who/whoever' as relative pronoun (men shou = whoever/who). "
            "false_friend: English 'men' = plural of man. "
            "'mn' is the short/clitic form."
        ),
        "added_at": ADDED_AT,
    },

    "bel_prep": {
        "canonical_form": "bel",
        "arabic_equivalent": "\u0628\u0627\u0644",    # بال
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["bel", "bil", "bl", "bal", "bell"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic preposition+article contraction 'in the / with the / by the'. "
            "Lebanese Arabizi: 'bel' most common (bel-sayara = in the car), "
            "'bil' also frequent, 'bl' as short clitic prefix."
        ),
        "added_at": ADDED_AT,
    },

    # -----------------------------------------------------------------------
    # TIER 2 — High frequency (freq 20-49)
    # -----------------------------------------------------------------------

    "eh_affirm": {
        "canonical_form": "eh",
        "arabic_equivalent": "\u0625\u064a",          # إي
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["eh", "ehe", "eeh", "aah"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi affirmative particle 'yes, yeah'. "
            "Also used as hedging/acknowledgement ('eh mni7' = yeah ok/fine). "
            "Distinct from 'ee' (another yes variant)."
        ),
        "added_at": ADDED_AT,
    },

    "allah_excl": {
        "canonical_form": "allah",
        "arabic_equivalent": "\u0627\u0644\u0644\u0647", # الله
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["allah", "allahu", "alla", "yallah"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic theonym 'God'; also used as multi-function exclamation: "
            "praise (allah! shou 7elo = wow how beautiful!), "
            "dismay (ya allah = oh God), "
            "farewell/encouragement (allah ma3ak = God be with you). "
            "'yallah' = let's go / come on."
        ),
        "added_at": ADDED_AT,
    },

    "ktir_quant": {
        "canonical_form": "ktir",
        "arabic_equivalent": "\u0643\u062a\u064a\u0631", # كتير
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ktir", "ktiir", "kteer", "keter", "kteer", "kteerr"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi intensifier/quantifier: 'a lot, very, many, much'. "
            "Can modify adjectives (ktir mni7 = very good) or verbs (7abbo ktir = loved it a lot). "
            "Extremely common in Lebanese social media."
        ),
        "added_at": ADDED_AT,
    },

    "kel_det": {
        "canonical_form": "kel",
        "arabic_equivalent": "\u0643\u0644",          # كل
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["kel", "kell", "kol", "kul", "kill"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic universal quantifier/determiner: 'all, every, each'. "
            "Lebanese Arabizi: 'kel' / 'kell' most common "
            "(kel youm = every day, kel shi = everything). "
            "Distinct from imperative 'kol' (eat!) which has same base but different vowel."
        ),
        "added_at": ADDED_AT,
    },

    "a7la_superl": {
        "canonical_form": "a7la",
        "arabic_equivalent": "\u0623\u062d\u0644\u0649", # أحلى
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["a7la", "a7le", "ahla", "a7laa", "a7lla"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi superlative/comparative: 'most beautiful, best, sweetest'. "
            "From root 7-l-w (sweet/beautiful). 7=ha. "
            "Used as general superlative in social media (a7la nas = the best people)."
        ),
        "added_at": ADDED_AT,
    },

    # -----------------------------------------------------------------------
    # TIER 3 — Medium frequency (freq 5-19)
    # -----------------------------------------------------------------------

    "saba7_morning": {
        "canonical_form": "saba7",
        "arabic_equivalent": "\u0635\u0628\u0627\u062d", # صباح
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["saba7", "sabah", "saba7o", "saba77"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: morning. 9=sa digit NOT used here (saba7 not sa9ba7). "
            "Used in greetings: saba7 el kheir = good morning, "
            "saba7 el nour = morning of light (response)."
        ),
        "added_at": ADDED_AT,
    },

    "halla2_now": {
        "canonical_form": "halla2",
        "arabic_equivalent": "\u0647\u0644\u0642",    # هلق
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["halla2", "halla", "hala2", "hallak", "hala2a"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi temporal adverb 'now, right now, at this moment'. "
            "Distinctly Lebanese (vs. MSA 'al-an'). 2=hamza digit. "
            "Common in urgent complaint tweets (halla2 ma fi kahraba = there's no electricity right now)."
        ),
        "added_at": ADDED_AT,
    },

    "ta3_imperative": {
        "canonical_form": "ta3",
        "arabic_equivalent": "\u062a\u0639\u0627",    # تعا
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ta3", "ta3a", "ta3e", "ta3i", "ta3o", "t3a"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi imperative 'come!'. 3=3ayn digit. "
            "Gender/number inflected: ta3 (m.sg), ta3e/ta3i (f.sg), ta3o (pl). "
            "Informal; standard Arabic uses 'ta3al'."
        ),
        "added_at": ADDED_AT,
    },

    "ya3ne_discourse": {
        "canonical_form": "ya3ne",
        "arabic_equivalent": "\u064a\u0639\u0646\u064a", # يعني
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ya3ne", "ya3ni", "ya3neh", "yani", "yanni", "ya3ny"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: literal 'it means/meaning'; "
            "also extremely common discourse filler/hedge 'like, you know, sort of, I mean'. "
            "3=3ayn digit. Both uses occur in same surface form; context determines function. "
            "One of the most characteristic Arabizi discourse markers."
        ),
        "added_at": ADDED_AT,
    },

    "ra7_future": {
        "canonical_form": "ra7",
        "arabic_equivalent": "\u0631\u062d",          # رح
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ra7", "rah", "rha", "ra7a"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi future particle 'will, going to'. "
            "Precedes verb: ra7 yiji = he will come. "
            "7=ha digit. Distinctly Lebanese (vs. MSA sa-/sawfa). "
            "Common in complaint predictions (ra7 tibat = it will get cut off)."
        ),
        "added_at": ADDED_AT,
    },

    "fari2_noun": {
        "canonical_form": "fari2",
        "arabic_equivalent": "\u0641\u0631\u064a\u0642", # فريق
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "ROADS"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["fari2", "fari2a", "farik", "frik", "fari2"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: team, group. 2=hamza digit. "
            "Relevant for emergency response teams, repair crews (fari2 el kahraba = electricity team/crew). "
            "Also used for sports teams in general tweets."
        ),
        "added_at": ADDED_AT,
    },

    "b7ebbik_verb": {
        "canonical_form": "b7ebbik",
        "arabic_equivalent": "\u0628\u062d\u0628\u0643", # بحبك
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "b7ebbik", "bhebbik",   # I love you (f)
            "b7ebbak", "bhebbak",   # I love you (m)
            "b7ebbo",  "bhebbo",    # I love him
            "b7ebba",  "bhebba",    # I love her
            "b7ebbkun",             # I love you (pl)
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'I love you' — conjugated form of 7ebb (to love). "
            "7=ha digit. b- prefix = present tense marker. "
            "Inflected for object: -ik (f), -ak (m), -o (him), -a (her). "
            "Social media context; not safety-relevant."
        ),
        "added_at": ADDED_AT,
    },

    "7ayete_endear": {
        "canonical_form": "7ayete",
        "arabic_equivalent": "\u062d\u064a\u0627\u062a\u064a", # حياتي
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["7ayete", "7ayati", "7ayety", "7ayat", "7ayati"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'my life'; used as term of endearment "
            "(ya 7ayete = oh my darling/my life). "
            "7=ha digit. Social media/conversational context."
        ),
        "added_at": ADDED_AT,
    },

    "hal2ad_intens": {
        "canonical_form": "hal2ad",
        "arabic_equivalent": "\u0647\u0627\u0644\u0642\u062f", # هالقد
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["hal2ad", "hal2add", "hal2edd", "hal2add"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi degree intensifier: 'this much, so much, to this extent'. "
            "2=hamza digit. "
            "Often expresses frustration/surprise (hal2ad ktir = this much / so much)."
        ),
        "added_at": ADDED_AT,
    },

    "3anjad_affirm": {
        "canonical_form": "3anjad",
        "arabic_equivalent": "\u0639\u0646\u062c\u062f", # عنجد
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["3anjad", "3anjed", "3injad", "3enjad", "3anjad"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi discourse intensifier: 'seriously, really, for real'. "
            "3=3ayn digit. Used to emphasise sincerity or disbelief "
            "(3anjad? = seriously? / 3anjad ktir = really a lot). "
            "Distinctly Lebanese; not used in other Arabic dialects."
        ),
        "added_at": ADDED_AT,
    },

    "ra3is_political": {
        "canonical_form": "ra3is",
        "arabic_equivalent": "\u0631\u0626\u064a\u0633", # رئيس
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "ROADS", "ELECTRICITY"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ra3is", "ra2is", "rais", "rayes"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: president (political leader). 3=3ayn digit. "
            "POLYSEMY: see ra3is_general for boss/chief (non-political). "
            "Context: ra3is el jomhoriye = president of the republic. "
            "Political domain; relevant for government accountability tweets."
        ),
        "added_at": ADDED_AT,
    },

    "ra3is_general": {
        "canonical_form": "ra3is",
        "arabic_equivalent": "\u0631\u0626\u064a\u0633", # رئيس
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ra3is", "ra2is", "rais", "rayes"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: boss, head, chief, manager (general leadership). "
            "3=3ayn digit. "
            "POLYSEMY: same surface 'ra3is' as ra3is_political (president). "
            "Context distinguishes: general leadership use (ra3is el shirkeh = company head). "
            "Also ra3is baladiye = mayor (municipality head) -- between both senses."
        ),
        "added_at": ADDED_AT,
    },

    "wa2t_noun": {
        "canonical_form": "wa2t",
        "arabic_equivalent": "\u0648\u0642\u062a",    # وقت
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["wa2t", "wa2et", "wa2it", "waqt", "wa2te"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: time, moment. 2=hamza digit (2=qaf in some encodings). "
            "Common in Arabizi (wa2t el az3a = rush hour time, "
            "wa2t el kahraba = electricity time/schedule)."
        ),
        "added_at": ADDED_AT,
    },

    "ou3a_warn": {
        "canonical_form": "ou3a",
        "arabic_equivalent": "\u0623\u0648\u0639\u0649", # أوعى
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "ROADS"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ou3a", "ou3e", "ow3a", "ow3e", "ow3"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi warning imperative: 'don't!, be careful!, watch out!'. "
            "3=3ayn digit. Distinctly Lebanese; "
            "used to warn others of hazards (ou3a tmur hon = don't pass here). "
            "Relevant for road safety and hazard warning tweets."
        ),
        "added_at": ADDED_AT,
    },

    "3a2bel_wish": {
        "canonical_form": "3a2bel",
        "arabic_equivalent": "\u0639\u0642\u0628\u0627\u0644", # عقبال
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["3a2bel", "3a2balek", "3a2belik", "3a2belna", "3a2belkon"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi well-wishing expression: 'may you be next / wishing you the same'. "
            "3=3ayn, 2=hamza digit. "
            "Inflected for addressee: 3a2balek (m), 3a2belik (f), 3a2belna (us), 3a2belkon (you.pl). "
            "Social media: used after someone shares good news."
        ),
        "added_at": ADDED_AT,
    },

    "tari2_noun": {
        "canonical_form": "tari2",
        "arabic_equivalent": "\u0637\u0631\u064a\u0642", # طريق
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ROADS", "SAFETY"],
        "severity_relevance": ["LOW", "MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["tari2", "tari2a", "tarik", "trik", "tri2"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: road, path (literal); also way/method (figurative). "
            "2=hamza digit (2=qaf variant). "
            "MILD POLYSEMY: physical road vs abstract way/method -- context usually clear. "
            "Highly relevant for roads/infrastructure domain."
        ),
        "added_at": ADDED_AT,
    },

    "mawdou3_noun": {
        "canonical_form": "mawdou3",
        "arabic_equivalent": "\u0645\u0648\u0636\u0648\u0639", # موضوع
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["mawdou3", "mawdou3e", "mawdoo3", "mawdo3", "mawdoo3"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: topic, subject (discourse); also issue, matter, situation. "
            "3=3ayn digit. "
            "POLYSEMY: abstract topic vs concrete situation/matter "
            "(el mawdou3 = the topic/issue/matter). Context usually clear."
        ),
        "added_at": ADDED_AT,
    },

    "ba3da_temporal": {
        "canonical_form": "ba3da",
        "arabic_equivalent": "\u0628\u0639\u062f\u0627", # بعدا
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ba3da", "ba3do", "ba3den", "ba3dein"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi temporal adverb: 'still, yet, not yet'. "
            "3=3ayn digit. "
            "POLYSEMY: 'ba3da' also means 'after her' (prepositional+pronoun); see ba3da_possessive. "
            "Temporal use: ba3da mawjoud = still present, ma ji ba3da = hasn't come yet. "
            "Related to ba3ed entry (after); ba3da is the suffixed/adverbial form."
        ),
        "added_at": ADDED_AT,
    },

    "ba3da_possessive": {
        "canonical_form": "ba3da",
        "arabic_equivalent": "\u0628\u0639\u062f\u0647\u0627", # بعدها
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ba3da", "ba3do", "ba3dak", "ba3dik"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese Arabizi prepositional phrase: 'after her/it' (ba3d + pronoun suffix -a). "
            "3=3ayn digit. "
            "POLYSEMY: same surface 'ba3da' as ba3da_temporal ('still/yet'). "
            "Context distinguishes: after+pronoun vs temporal aspect. "
            "ba3do = after him, ba3dak = after you (m), ba3dik = after you (f)."
        ),
        "added_at": ADDED_AT,
    },

    "ma3na_noun": {
        "canonical_form": "ma3na",
        "arabic_equivalent": "\u0645\u0639\u0646\u0649", # معنى
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ma3na", "ma3neta", "ma3neto", "ma3neh"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese Arabizi noun: 'meaning, significance, sense'. "
            "3=3ayn digit. "
            "POLYSEMY: 'ma3na' (معنى) = meaning vs 'ma3na' (معنا) = with us "
            "(ma3 + pronoun -na). The latter is covered under ma3_preposition. "
            "Root: 3-n-y. Shu ma3na hayk = what does this mean?"
        ),
        "added_at": ADDED_AT,
    },
}

# ---------------------------------------------------------------------------
# VARIANT PATCHES — add forms to EXISTING entries
# ---------------------------------------------------------------------------
VARIANT_PATCHES = {
    "ma3_preposition": {
        "add_variants": ["ma3ak", "ma3ik", "ma3na", "ma3kum", "ma3on", "ma3a", "ma3o"],
    },
    "ba3ed": {
        "add_variants": ["b3d", "ba3d", "b3da"],
    },
}


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
    print(f"[V20d] Loading vocab from {VOCAB_PATH}")
    vocab = json.load(open(VOCAB_PATH, encoding="utf-8"))

    current = vocab.get("version", "?")
    if current != CURRENT_VERSION:
        print(f"[ERROR] Expected version {CURRENT_VERSION}, got {current}. Aborting.")
        return

    meta = vocab["term_metadata"]

    # -- Check for collisions ---
    collisions = [k for k in NEW_ENTRIES if k in meta]
    if collisions:
        print(f"[WARN] Already-existing keys: {collisions}")

    # -- Report plan ---
    print(f"[V20d] New entries      : {len(NEW_ENTRIES)}")
    print(f"[V20d] Variant patches  : {len(VARIANT_PATCHES)}")
    print(f"[V20d] Polysemous pairs : ma_neg/ma_excl, fi_prep/fi_exist, "
          "ra3is_political/ra3is_general, ba3da_temporal/ba3da_possessive, "
          "ma3na_noun vs ma3_preposition")

    if dry_run:
        print()
        print("[DRY-RUN] New entry keys:")
        for k in NEW_ENTRIES:
            vf = NEW_ENTRIES[k]["variant_forms"]
            print(f"  {k:30s}  variants={vf[:3]}")
        print()
        print("[DRY-RUN] Variant patches:")
        for entry_key, patch in VARIANT_PATCHES.items():
            if entry_key in meta:
                existing = meta[entry_key].get("variant_forms", [])
                new_vf = [v for v in patch["add_variants"]
                          if v not in existing]
                print(f"  {entry_key}: +{new_vf}")
            else:
                print(f"  [MISSING] {entry_key} not found in meta")
        print()
        known_before = build_known(vocab)
        # Simulate
        for k, entry in NEW_ENTRIES.items():
            if k not in meta:
                meta[k] = entry
        for entry_key, patch in VARIANT_PATCHES.items():
            if entry_key in meta:
                existing = set(meta[entry_key].get("variant_forms", []))
                for v in patch["add_variants"]:
                    existing.add(v)
                meta[entry_key]["variant_forms"] = sorted(existing)
        known_after = build_known(vocab)
        added = known_after - known_before
        print(f"[DRY-RUN] known_tokens before : {len(known_before)}")
        print(f"[DRY-RUN] known_tokens after  : {len(known_after)}")
        print(f"[DRY-RUN] New normalised forms: {len(added)}")
        print("[DRY-RUN] Sample new forms:", sorted(added)[:20])
        return

    # -- Backup ---
    backup = VOCAB_PATH.with_suffix(
        f".bak-before-v20d-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    shutil.copy2(VOCAB_PATH, backup)
    print(f"[V20d] Backup saved: {backup.name}")

    known_before = build_known(vocab)

    # -- Apply new entries ---
    added_count = 0
    for k, entry in NEW_ENTRIES.items():
        if k in meta:
            print(f"[SKIP] {k} already exists")
        else:
            meta[k] = entry
            added_count += 1

    # -- Apply variant patches ---
    patch_count = 0
    for entry_key, patch in VARIANT_PATCHES.items():
        if entry_key not in meta:
            print(f"[WARN] Patch target '{entry_key}' not found — skipping")
            continue
        existing = set(meta[entry_key].get("variant_forms", []))
        before_len = len(existing)
        for v in patch["add_variants"]:
            existing.add(v)
        meta[entry_key]["variant_forms"] = sorted(existing)
        added_vf = len(existing) - before_len
        patch_count += added_vf
        print(f"[PATCH] {entry_key}: +{added_vf} variant forms")

    # -- Bump version + changelog ---
    vocab["version"] = NEW_VERSION
    changelog_entry = (
        f"{NEW_VERSION} (2026-05-22): V20d full-corpus OOV closure -- "
        f"{added_count} new term_metadata entries ({len(NEW_ENTRIES)} planned) + "
        f"{len(VARIANT_PATCHES)} entry patches. "
        "Includes 5 polysemous pairs: ma_neg/ma_excl, fi_prep/fi_exist, "
        "ra3is_political/ra3is_general, ba3da_temporal/ba3da_possessive, ma3na_noun. "
        "Source: 64K-tweet Lebanon corpus scan."
    )
    vocab.setdefault("changelog", []).append(changelog_entry)

    known_after = build_known(vocab)
    new_forms = known_after - known_before

    # -- Save ---
    with open(VOCAB_PATH, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=2)

    print()
    print(f"[V20d] Done. Vocab bumped {CURRENT_VERSION} -> {NEW_VERSION}")
    print(f"[V20d] term_metadata entries : {len(meta)}")
    print(f"[V20d] New entries applied   : {added_count}")
    print(f"[V20d] Variant patch forms   : {patch_count}")
    print(f"[V20d] known_tokens before   : {len(known_before)}")
    print(f"[V20d] known_tokens after    : {len(known_after)}")
    print(f"[V20d] New normalised forms  : {len(new_forms)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing")
    args = parser.parse_args()
    main(dry_run=args.dry_run)

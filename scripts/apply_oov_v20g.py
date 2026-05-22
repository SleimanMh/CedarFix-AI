"""
apply_oov_v20g.py
=================
V20g vocab patch: 37 new entries + 14 variant patches (2.1.0 -> 2.2.0)

Full corpus OOV analysis across 6 datasets (arabizi-twitter-leb, Lebanon CSV,
Kaggle 2/3-class, words_annotated, Arabizi Transliteration train.csv) revealed:
- 3an/3and/3ade cluster: super-common prepositions/adjectives not yet in vocab
- Location/greeting/question words: hon/hay/amtin/mar7aba/salam
- Verb/expression gaps: yaret/3atini/bebke/tfaddal
- Noun gaps: 3ammo/alf/msa/sett/oum/dene/menne
- Sector support: sha3b/ta3ban/mariz/dawa/ekhet/3asha
- T1 signals: 3atshan/3atesh (water crisis)
- Patches: digit-form helou (7elo), pronoun enty/enti, rou7 variants,
  kel variants, kif declensions, la2an variants, wain, habibi digit-forms,
  emme forms, sar future, eza variants, meshe forms

Source: combined scan of all 6 available Arabizi corpora (91,817 total rows).

Usage:
  python scripts/apply_oov_v20g.py --dry-run   # preview only
  python scripts/apply_oov_v20g.py              # apply to vocab

DO NOT re-run after successful apply (vocab will be at 2.2.0).
"""

import json
import re
import os
import sys
import copy
import shutil
from datetime import datetime, timezone

VOCAB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "knowledge_base", "arabizi_vocabulary.json"
)

CURRENT_VERSION = "2.1.0"
NEW_VERSION     = "2.2.0"
REVIEWER_ID     = "SYSTEM-V20g"
REVIEW_DATE     = "2026-05-22"

# ─────────────────────────────────────────────────────────────────────────────
# NORMALISATION (must match normalise_token in inference pipeline)
# ─────────────────────────────────────────────────────────────────────────────
def norm(t: str) -> str:
    t = t.lower()
    t = re.sub(r"[^a-z0-9]", "", t)
    t = re.sub(r"[0146]+$", "", t)
    t = re.sub(r"(.)\1{3,}", r"\1\1\1", t)
    return t


# ─────────────────────────────────────────────────────────────────────────────
# 37 NEW ENTRIES
# ─────────────────────────────────────────────────────────────────────────────
# Schema: term_key -> {arabic_equivalent, semantic_type, sector_relevance,
#   severity_relevance, false_friend_risk, must_not_auto_promote, loanword_from,
#   variant_forms, notes}
# false_friend_risk / must_not_auto_promote are ALWAYS string "true"/"false"

NEW_ENTRIES = {

    # ── T3_GENERIC_SUPPORT ──────────────────────────────────────────────────

    "3an_prep": {
        "arabic_equivalent": "\u0639\u0646",         # عن
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "3an", "3anno", "3anha", "3anna", "3anak", "3anik",
            "3annak", "3annik", "3annon", "3ankon"
        ],
        "notes": "Preposition 'about/from/regarding'. Freq 49+ in digit-OOV scan. "
                 "One of the most common Arabic prepositions; critical for coverage."
    },

    "3and_poss": {
        "arabic_equivalent": "\u0639\u0646\u062f",   # عند
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "3and", "3ande", "3andi", "3andak", "3andik",
            "3ando", "3anda", "3andna", "3andon", "3andkon", "3andkon"
        ],
        "notes": "Possession/location: 3andi=I have, 3andak=you have. Freq 20+ in scan."
    },

    "3ade_adj": {
        "arabic_equivalent": "\u0639\u0627\u062f\u064a",  # عادي
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "3ade", "3adi", "3adeh", "3adiye", "3ade2", "3adeh2"
        ],
        "notes": "Adjective 'normal/usual/casual'. Freq 21+ in scan."
    },

    "hon_loc": {
        "arabic_equivalent": "\u0647\u0648\u0646",   # هون
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "hon", "houn", "hene", "hona", "honik", "henek",
            "hona2", "houn2", "hene2"
        ],
        "notes": "Lebanese locative adverb 'here'. Very common in Lebanese dialect. "
                 "Freq 3+ in pure Arabizi dataset."
    },

    "hay_excl": {
        "arabic_equivalent": "\u0647\u0627\u064a",   # هاي
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "hay", "hei", "heyy", "hayy", "heyyy"
        ],
        "notes": "Informal greeting 'hey/hi'. Also feminine 'yes' or 'this (f)'. "
                 "Must not confuse with Arabic hiye (she). T3 greeting marker."
    },

    "yaret_expr": {
        "arabic_equivalent": "\u064a\u0627\u0631\u064a\u062a",  # يارت
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "medium",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "yaret", "yyaret", "y2ret", "yaret2", "yareit"
        ],
        "notes": "Wish particle 'I wish / if only'. Very common in expressions of "
                 "desire, complaint, hope. T3 support for sentiment context."
    },

    "3ammo_noun": {
        "arabic_equivalent": "\u0639\u0645\u0648",   # عمو
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "3ammo", "3amo", "3amu", "3amou", "3amm", "3mm"
        ],
        "notes": "Address form 'uncle / mister'. Very common in Lebanese conversation."
    },

    "alf_noun": {
        "arabic_equivalent": "\u0623\u0644\u0641",   # ألف
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "alf", "alaf", "elef", "2alf", "talef", "alf2"
        ],
        "notes": "Number word 'thousand'. Common in expressions: alf mabrouk, "
                 "alf shukr, alf salameh."
    },

    "msa_time": {
        "arabic_equivalent": "\u0645\u0633\u0627\u0621",  # مساء
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "msa", "masa", "masa2", "msa2", "el2masa", "elmasa"
        ],
        "notes": "Temporal word 'evening / good evening'. Common in greetings: "
                 "masa el kheir = good evening."
    },

    "sa7_part": {
        "arabic_equivalent": "\u0635\u062d",         # صح
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "sa7", "sah", "sa77", "sa7e", "sa77e", "sa7ten"
        ],
        "notes": "Affirmative/agreement particle 'right / correct / true'. "
                 "Very common in colloquial affirmation."
    },

    "mohem_adj": {
        "arabic_equivalent": "\u0645\u0647\u0645",   # مهم
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "mohem", "mhimm", "mhimme", "muhem", "mhem",
            "mhim", "mohimm", "muhim"
        ],
        "notes": "Adjective 'important / significant'. Common in commentary tweets."
    },

    "mazbout_adj": {
        "arabic_equivalent": "\u0645\u0636\u0628\u0648\u0637",  # مضبوط
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "mazbout", "mazboot", "mzbt", "mazbouta", "mazboote",
            "madbout", "madbout2"
        ],
        "notes": "Adjective 'correct / calibrated / right / proper'. "
                 "Also used as confirmation. Common in Lebanese."
    },

    "mawjoud_adj": {
        "arabic_equivalent": "\u0645\u0648\u062c\u0648\u062f",  # موجود
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "mawjoud", "mawjoude", "mwjoud", "moujoude",
            "moujoud", "mawjoudin", "mawjoudat"
        ],
        "notes": "Adjective 'present / available / existing'. Key for describing "
                 "service availability (electricity, water, etc.)."
    },

    "dene_noun": {
        "arabic_equivalent": "\u062f\u0646\u064a\u0627",  # دنيا
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "dene", "denia", "denye", "denyete", "denye2", "denyeti"
        ],
        "notes": "Noun 'world / life / universe'. Used as endearment: 'dene' in "
                 "Lebanese colloquial = 'my world / my life'."
    },

    "bebke_verb": {
        "arabic_equivalent": "\u0628\u064a\u0628\u0643\u064a",  # ببكي
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "medium",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "bebke", "bybke", "betbke", "beke", "bke",
            "bikke", "nbke", "bybki"
        ],
        "notes": "Verb 'I cry / I weep'. Emotion verb common in distress/grief tweets."
    },

    "amtin_adv": {
        "arabic_equivalent": "\u0622\u0645\u062a\u064a\u0646",  # آمتين
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "amtin", "emtin", "aimte", "imte", "mtin",
            "2amten", "emten", "amten"
        ],
        "notes": "Question adverb 'when?' (Lebanese). OOV freq 4+ in pure Arabizi."
    },

    "3omri_expr": {
        "arabic_equivalent": "\u0639\u0645\u0631\u064a",  # عمري
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "3omri", "3omre", "3mri", "3umri", "3ommri",
            "3omrak", "3omrik", "3omro", "3omra", "3omrkon"
        ],
        "notes": "Possessive noun 'my life / my age'. Used as term of endearment "
                 "or exclamation. Also: 3omrak=your age, 3omrna=our life."
    },

    "3atini_verb": {
        "arabic_equivalent": "\u0639\u0637\u064a\u0646\u064a",  # عطيني
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "3tini", "3atini", "3atinik", "3tinak", "3atine",
            "3atna", "3atineh", "3atikon"
        ],
        "notes": "Imperative verb 'give me'. Lebanese colloquial request."
    },

    "sett_noun": {
        "arabic_equivalent": "\u0633\u062a",  # ست
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "sett", "sett2", "sitto", "siti", "settna",
            "el sett", "elsett"
        ],
        "notes": "Noun 'woman / Mrs / grandmother / lady'. Common address in Lebanese."
    },

    "ad_conj": {
        "arabic_equivalent": "\u0642\u062f",  # قد
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "ad", "2ad", "add", "addo", "adda", "adde", "2adde"
        ],
        "notes": "Degree particle 'as much as / just as / how much'. "
                 "Common in comparisons and exclamations."
    },

    "oum_noun": {
        "arabic_equivalent": "\u0623\u0645",  # أم
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "oum", "oom", "oumi", "omi", "oume", "oumna"
        ],
        "notes": "Noun 'mother'. Variant of emme/immi using Western oum/oom spelling. "
                 "Distinct normalised form from emme_noun entry."
    },

    "menne_prep": {
        "arabic_equivalent": "\u0645\u0646\u064a",  # مني
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "menne", "menni", "minne", "minni", "menne2",
            "mennak", "mennik", "menno", "menna", "mennon"
        ],
        "notes": "Prepositional phrase 'from me / of me'. Declined: mennak=from you, "
                 "menno=from him."
    },

    "yeha_excl": {
        "arabic_equivalent": "\u064a\u062d\u064a\u0627",  # يحيا
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "yeha", "yi7ya", "yi7ye", "yehya", "ye7ya"
        ],
        "notes": "Exclamation 'long live / hurray / viva'. Common in celebratory or "
                 "political tweets."
    },

    "tfaddal_part": {
        "arabic_equivalent": "\u062a\u0641\u0636\u0644",  # تفضل
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "tfaddal", "tfadal", "tfaddaleh", "tafaddal",
            "tfaddali", "tfaddalo", "tfaddalou"
        ],
        "notes": "Politeness particle 'please / go ahead / help yourself / here you go'. "
                 "Very common in Lebanese hospitality context."
    },

    "mar7aba_greet": {
        "arabic_equivalent": "\u0645\u0631\u062d\u0628\u0627",  # مرحبا
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "mar7aba", "mar7abe", "marhaba", "mar7abtek",
            "marhabe", "mar7aba2", "marhaba2"
        ],
        "notes": "Standard greeting 'hello / hi'. One of the most common Lebanese "
                 "greetings alongside ahlan."
    },

    "salam_greet": {
        "arabic_equivalent": "\u0633\u0644\u0627\u0645",  # سلام
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "salam", "sallem", "salamo", "salam2", "salami",
            "salmit", "salomit", "sallamit", "salaamu"
        ],
        "notes": "Greeting/farewell 'peace / hi / bye'. Used to open/close messages. "
                 "Also sallem = 'say hi / convey greetings'."
    },

    "noom_noun": {
        "arabic_equivalent": "\u0646\u0648\u0645",  # نوم
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "noom", "nom", "noum", "nome", "noumi", "noumak", "tnaam", "tnami"
        ],
        "notes": "Noun/verb 'sleep'. Common in daily life tweets. Also: tnaam=sleep(imp)."
    },

    # ── T2_SECTOR_SUPPORT ────────────────────────────────────────────────────

    "sha3b_noun": {
        "arabic_equivalent": "\u0634\u0639\u0628",   # شعب
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["GOVERNMENT", "SOCIAL"],
        "severity_relevance": "medium",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "sha3b", "sha3eb", "sha3bi", "sha3bna", "sha3biye",
            "sha3biyyeh", "sha3bkon"
        ],
        "notes": "Noun 'people / nation / folk'. Key political/social term. "
                 "sha3bi=of the people; sha3bna=our people."
    },

    "rab_noun": {
        "arabic_equivalent": "\u0631\u0628",  # رب
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SOCIAL", "GENERAL"],
        "severity_relevance": "medium",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "rab", "rabb", "rab2", "rabbi", "rabbo", "rabba",
            "rabbna", "rab2i", "ya rab", "yarab"
        ],
        "notes": "Noun 'Lord / God / Creator'. Freq 7 in pure Arabizi. "
                 "Common in supplication: ya rab (oh Lord), rabbi (my Lord)."
    },

    "ta3ban_adj": {
        "arabic_equivalent": "\u062a\u0639\u0628\u0627\u0646",  # تعبان
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["HEALTH", "GENERAL"],
        "severity_relevance": "high",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "ta3ban", "ta3bane", "ta3baneh", "t3ban", "ta3ben",
            "t3ben", "ta3bana", "ta3banin"
        ],
        "notes": "Adjective 'tired / exhausted / broken / sick'. Dual-use: "
                 "describes people (fatigue, illness) AND infrastructure (broken, faulty). "
                 "High-severity when infrastructure context is detected."
    },

    "mariz_adj": {
        "arabic_equivalent": "\u0645\u0631\u064a\u0636",  # مريض
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["HEALTH"],
        "severity_relevance": "high",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "mariz", "marize", "marida", "marada", "mrid",
            "mride", "marido", "maraad"
        ],
        "notes": "Adjective 'sick / ill / diseased'. Health sector signal. "
                 "Also used metaphorically: 'the system is sick'."
    },

    "dawa_noun": {
        "arabic_equivalent": "\u062f\u0648\u0627\u0621",  # دواء
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["HEALTH", "PHARMACY"],
        "severity_relevance": "high",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "dawa", "dowa", "daweh", "dawa2", "dawawi",
            "adwiye", "edwiyeh", "dwiyeh"
        ],
        "notes": "Noun 'medicine / drug / remedy'. Health crisis signal. "
                 "adwiye/edwiyeh=medicines (plural)."
    },

    "ekhet_noun": {
        "arabic_equivalent": "\u0623\u062e\u062a",  # أخت
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SOCIAL", "GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "ekhet", "okhet", "2okhet", "2ekhet", "khet",
            "khte", "ekhte", "okhte"
        ],
        "notes": "Noun 'sister'. Common family term in Lebanese social context. "
                 "OOV freq 5 in pure Arabizi. T2 for social sector support."
    },

    "mno_prep": {
        "arabic_equivalent": "\u0645\u0646\u0647",  # منه
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "mno", "mnou", "mnha", "mnon", "mnkon", "mna",
            "mennon", "mennha", "menno"
        ],
        "notes": "Prepositional pronoun 'from him / from her / from them'. "
                 "Contracted form of men + pronoun suffix. Common in Lebanese."
    },

    "3asha_noun": {
        "arabic_equivalent": "\u0639\u0634\u0627\u0621",  # عشاء
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["FOOD", "GENERAL"],
        "severity_relevance": "low",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "3asha", "3asha2", "3ache", "3ashe", "3ache2",
            "el3asha", "hal3asha"
        ],
        "notes": "Noun 'dinner / supper'. Food sector support. Common in daily tweets."
    },

    # ── T1_DIRECT_SIGNAL ─────────────────────────────────────────────────────

    "3atshan_adj": {
        "arabic_equivalent": "\u0639\u0637\u0634\u0627\u0646",  # عطشان
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["WATER", "HEALTH"],
        "severity_relevance": "critical",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "3atshan", "3atshane", "3atshana", "3tshn",
            "3tshan", "3atshana"
        ],
        "notes": "Adjective 'thirsty'. Direct T1 water-crisis signal. "
                 "When combined with water-sector context, indicates acute shortage."
    },

    "3atesh_noun": {
        "arabic_equivalent": "\u0639\u0637\u0634",  # عطش
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["WATER", "HEALTH"],
        "severity_relevance": "critical",
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "3atesh", "3tesh", "3atas", "3atash", "3tsh"
        ],
        "notes": "Noun 'thirst'. Direct water-crisis T1 signal. "
                 "Pair with 3atshan_adj for dehydration/water-shortage detection."
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 14 VARIANT PATCHES (add new forms to existing term_metadata entries)
# ─────────────────────────────────────────────────────────────────────────────
# Each key must already exist in term_metadata; new_forms will be appended.

VARIANT_PATCHES = {
    # digit-form حلو variants
    "helou_adj":        ["7elo", "7elou", "7elweh", "7elwa"],

    # enty/enti — you (f) — patch to inta_pronoun
    "inta_pronoun":     ["enty", "enti", "enty2", "enti2"],

    # go (f) — trouhe/trou7 forms
    "rou7_verb":        ["trouhe", "trou7", "trouh", "troo7", "troo7e"],

    # kel abbreviated
    "kel_det":          ["kl", "kil", "kl2"],

    # emme: emy form
    "emme_noun":        ["emy", "emmy", "emmeh"],

    # habibi digit forms
    "habibi":           ["7bibi", "7bibe", "7bibti", "7bibto", "7abibteh"],

    # la2an extended forms
    "la2an_conj":       ["la2enno", "la2ino", "la2in", "la2inno", "la2inne"],

    # eza/iza extended
    "eza_conditional":  ["iza2", "idha", "idha2", "2iza", "2iza2"],

    # wain = where (wen_adv already has wayn/wein; missing wain)
    "wen_adv":          ["wain", "wayne", "w2in"],

    # kif declensions: kifak/kifik/kfak
    "kif_question":     ["kiff", "kifak", "kifik", "kfak", "kifkon", "kifen", "kifna"],

    # youm = day variant
    "yom":              ["youm", "youme", "alyoum", "alyom"],

    # 3esh variant
    "3aish":            ["3esh", "3eshe", "3aysha"],

    # meshe: mechi/mache forms
    "meshe":            ["mechi", "mache", "meshi"],

    # sar: sarkon + feminine forms
    "sar_verb":         ["sarkon", "sayra", "saret2", "saro2"],
}


# ─────────────────────────────────────────────────────────────────────────────
# APPLY LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def build_known(voc):
    known = set()
    for e in voc["term_metadata"].values():
        for v in e.get("variant_forms", []):
            n = norm(v)
            if n:
                known.add(n)
    return known


def apply_patches(voc, dry_run):
    added_forms = 0
    missing_keys = []
    for term_key, new_forms in VARIANT_PATCHES.items():
        entry = voc["term_metadata"].get(term_key)
        if entry is None:
            missing_keys.append(term_key)
            continue
        existing = set(norm(v) for v in entry.get("variant_forms", []))
        to_add = [f for f in new_forms if norm(f) not in existing]
        if not dry_run and to_add:
            entry["variant_forms"].extend(to_add)
        added_forms += len(to_add)
        if to_add:
            print("  PATCH %-22s +%d forms: %s" % (term_key, len(to_add), to_add))
        else:
            print("  PATCH %-22s  (all forms already present)" % term_key)
    if missing_keys:
        print("  WARNING: patch target keys not found: %s" % missing_keys)
    return added_forms


def apply_new_entries(voc, dry_run):
    tm = voc["term_metadata"]
    added_count = 0
    skipped = []
    by_type = {"T1_DIRECT_SIGNAL": 0, "T2_SECTOR_SUPPORT": 0, "T3_GENERIC_SUPPORT": 0}
    for term_key, entry_data in NEW_ENTRIES.items():
        if term_key in tm:
            skipped.append(term_key)
            continue
        added_count += 1
        stype = entry_data["semantic_type"]
        by_type[stype] = by_type.get(stype, 0) + 1
        if not dry_run:
            full_entry = dict(entry_data)
            full_entry["reviewer_id"]  = REVIEWER_ID
            full_entry["review_date"]  = REVIEW_DATE
            full_entry["confidence"]   = 0.9
            full_entry["added_at"]     = REVIEW_DATE
            tm[term_key] = full_entry
        print("  NEW  %-22s  %s  vf=%d" % (
            term_key,
            entry_data["semantic_type"],
            len(entry_data["variant_forms"])
        ))
    if skipped:
        print("  SKIPPED (already exist): %s" % skipped)
    print("  Breakdown: T1=%d  T2=%d  T3=%d" % (
        by_type["T1_DIRECT_SIGNAL"],
        by_type["T2_SECTOR_SUPPORT"],
        by_type["T3_GENERIC_SUPPORT"]
    ))
    return added_count


def main():
    dry_run = "--dry-run" in sys.argv

    print("V20g apply script  dry_run=%s" % dry_run)
    print("VOCAB: %s" % VOCAB_PATH)

    with open(VOCAB_PATH, "r", encoding="utf-8") as f:
        voc = json.load(f)

    actual_version = voc.get("version", "")
    if actual_version != CURRENT_VERSION:
        print("ERROR: expected version %s but found %s" % (CURRENT_VERSION, actual_version))
        print("This script is designed for vocab %s only." % CURRENT_VERSION)
        sys.exit(1)

    known_before = build_known(voc)
    entries_before = len(voc["term_metadata"])
    print("Entries before: %d   known_tokens before: %d" % (entries_before, len(known_before)))

    if dry_run:
        voc_work = copy.deepcopy(voc)
    else:
        # backup
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bak = VOCAB_PATH.replace(".json", ".bak-before-v20g-%s.json" % ts)
        shutil.copy2(VOCAB_PATH, bak)
        print("Backup saved: %s" % os.path.basename(bak))
        voc_work = voc

    print()
    print("=== NEW ENTRIES (%d) ===" % len(NEW_ENTRIES))
    added = apply_new_entries(voc_work, dry_run)

    print()
    print("=== VARIANT PATCHES (%d targets) ===" % len(VARIANT_PATCHES))
    patch_forms = apply_patches(voc_work, dry_run)

    known_after = build_known(voc_work)
    entries_after = len(voc_work["term_metadata"])
    new_tokens = len(known_after) - len(known_before)

    print()
    print("=== SUMMARY ===")
    print("  New entries applied  : %d" % added)
    print("  Variant form patches : %d new forms across %d targets" % (patch_forms, len(VARIANT_PATCHES)))
    print("  term_metadata        : %d -> %d  (+%d)" % (entries_before, entries_after, entries_after - entries_before))
    print("  known_tokens         : %d -> %d  (+%d)" % (len(known_before), len(known_after), new_tokens))

    if dry_run:
        print()
        print("DRY-RUN complete. No changes written.")
    else:
        voc_work["version"] = NEW_VERSION
        if "changelog" not in voc_work:
            voc_work["changelog"] = []
        voc_work["changelog"].append({
            "version": NEW_VERSION,
            "date": REVIEW_DATE,
            "author": REVIEWER_ID,
            "summary": (
                "V20g: %d new entries + %d variant patches -> %d entries, "
                "%d known_tokens" % (added, patch_forms, entries_after, len(known_after))
            )
        })
        with open(VOCAB_PATH, "w", encoding="utf-8") as f:
            json.dump(voc_work, f, ensure_ascii=False, indent=2)
        print()
        print("SUCCESS: vocab written as version %s" % NEW_VERSION)
        print("  term_metadata entries : %d" % entries_after)
        print("  known_tokens          : %d" % len(known_after))


if __name__ == "__main__":
    main()

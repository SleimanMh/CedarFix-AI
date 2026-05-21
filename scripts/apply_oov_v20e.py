"""
apply_oov_v20e.py
=================
V20e: Corpus-gap closure -- 35 new entries + 7 variant-form patches.
Bumps vocab 1.9.0 -> 2.0.0.

Sources:
  - strict Arabizi digit-token OOV scan (2,747 digit-token instances, 17.0% covered)
  - broad filtered OOV scan (14,233 instances, 19.8% covered)
  - Manual review of top-frequency genuine Lebanese Arabizi gaps

Additions breakdown:
  T3_GENERIC_SUPPORT  (function words / pronouns / conjunctions) : 16 entries
  T2_SECTOR_SUPPORT   (common nouns / verbs / discourse markers)  : 13 entries
  T1_DIRECT_SIGNAL    (frustration signals / sectarian / crisis)  :  6 entries
  VARIANT_PATCHES     (add missing forms to existing entries)      :  7 patches

Milestone: version 2.0.0 -- significant vocabulary expansion
  247 entries (V20d) -> ~282 entries (V20e).

Usage:
  python scripts/apply_oov_v20e.py [--dry-run]

All print() output is ASCII-only (Windows CP1252 constraint).
DO NOT re-run once vocab is at 2.0.0.
"""

import json
import re
import shutil
import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT            = Path(__file__).resolve().parent.parent
VOCAB_PATH      = ROOT / "data/knowledge_base/arabizi_vocabulary.json"
CURRENT_VERSION = "1.9.0"
NEW_VERSION     = "2.0.0"
REVIEWER_ID     = "SYSTEM-V20e"
REVIEW_DATE     = "2026-05-22"
ADDED_AT        = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

# ---------------------------------------------------------------------------
# 35 NEW ENTRIES
# ---------------------------------------------------------------------------
NEW_ENTRIES = {

    # -----------------------------------------------------------------------
    # T3_GENERIC_SUPPORT -- Function words (conjunctions, prepositions,
    # pronouns, discourse markers).  These are high-frequency words needed
    # for corpus coverage.  None are direct crisis signals.
    # -----------------------------------------------------------------------

    "aw_conj": {
        "canonical_form": "aw",
        "arabic_equivalent": "\u0623\u0648",          # أو
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["aw", "2aw", "aw2"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic/Lebanese disjunction 'or'. "
            "Extremely common connector (aw kaza = or something). "
            "No false-friend risk; the sequence 'aw' does not resemble any "
            "common English word in tweet context."
        ),
        "added_at": ADDED_AT,
    },

    "lal_prep": {
        "canonical_form": "lal",
        "arabic_equivalent": "\u0644\u0644",          # لل
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["lal"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Contraction of la (to/for) + al (the definite article) = lal (to the). "
            "E.g. lal-beit = to the house. Very common in Lebanese Arabizi. "
            "Written as one token 'lal' without hyphen."
        ),
        "added_at": ADDED_AT,
    },

    "li_prep": {
        "canonical_form": "li",
        "arabic_equivalent": "\u0644\u0650",          # لِ
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "true",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["li", "le"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Arabic preposition 'to/for (me/you)'. Short clitic form. "
            "false_friend: 'li' = Italian/Spanish 'the/to them'; 'le' = French 'the (m.)'. "
            "must_not_auto_promote=true due to extreme shortness and high ambiguity. "
            "Use only as normalisation anchor; do not promote as Arabic signal alone."
        ),
        "added_at": ADDED_AT,
    },

    "inta_pronoun": {
        "canonical_form": "inta",
        "arabic_equivalent": "\u0625\u0646\u062a",    # إنت
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "inta", "enta", "int", "ent",
            "inte", "ente",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi second-person masculine singular pronoun 'you (m.)'. "
            "inta/enta = you (m.), inte/ente = you (f.). "
            "All six forms consolidated into one entry for coverage simplicity -- "
            "the masculine/feminine distinction is morphological, not lexical. "
            "POLYSEMY: none; all forms unambiguously Arabizi pronouns in tweet context."
        ),
        "added_at": ADDED_AT,
    },

    "wahad_num": {
        "canonical_form": "wahad",
        "arabic_equivalent": "\u0648\u0627\u062d\u062f",  # واحد
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "wahad", "wa7ad", "wahed", "wa7ed",
            "wa7id", "wahid",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi numeral/pronoun 'one / someone / a person'. "
            "7=ha (ح). wa7ad/wahad are the most common Lebanese Arabizi forms. "
            "Also used as indefinite pronoun: 'someone' (wa7ad 2al li = someone told me)."
        ),
        "added_at": ADDED_AT,
    },

    "ken_past": {
        "canonical_form": "ken",
        "arabic_equivalent": "\u0643\u0627\u0646",    # كان
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "ken", "kan", "kanet", "kenet",
            "kano", "kenu", "kanen",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi past-tense copula/auxiliary 'was/were/used to be'. "
            "ken/kan = he/it was; kanet/kenet = she/it was; kano/kenu/kanen = they were. "
            "Extremely common in narration and complaint tweets. "
            "No digit encoding needed -- no emphatic/pharyngeal consonants in this root."
        ),
        "added_at": ADDED_AT,
    },

    "marra_noun": {
        "canonical_form": "marra",
        "arabic_equivalent": "\u0645\u0631\u0629",    # مرة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "marra", "mara", "marr", "marre",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi noun 'once / a time / one time'. "
            "E.g. marra wa7ad = just once; hayk marra = at that time. "
            "Also used as intensifier: marra mnee7 = really good. "
            "No digit encoding needed."
        ),
        "added_at": ADDED_AT,
    },

    "wen_adv": {
        "canonical_form": "wen",
        "arabic_equivalent": "\u0648\u064a\u0646",    # وين
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "wen", "win", "wayn", "wein",
            "wayin", "wein",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi interrogative adverb 'where'. "
            "wen/win are the most common Lebanese forms of Arabic 'ayna'. "
            "Used in questions and relative clauses: wen knet? = where were you?"
        ),
        "added_at": ADDED_AT,
    },

    "akid_affirm": {
        "canonical_form": "akid",
        "arabic_equivalent": "\u0623\u0643\u064a\u062f",  # أكيد
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "akid", "akeed", "2akid", "2akeed",
            "akide", "akide",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi affirmation adverb 'of course / certainly / definitely'. "
            "Extremely common discourse marker in tweets. "
            "Loanword from Classical Arabic 'muakkad' (confirmed). "
            "No complex digit encoding -- no pharyngeal/emphatic consonants."
        ),
        "added_at": ADDED_AT,
    },

    "law_cond": {
        "canonical_form": "law",
        "arabic_equivalent": "\u0644\u0648",          # لو
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["law", "low"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic/Lebanese conditional conjunction 'if / even if / I wish'. "
            "law beddak = if you want; law ma = even if not. "
            "No false-friend risk in Lebanese Arabizi tweet context."
        ),
        "added_at": ADDED_AT,
    },

    "gher_particle": {
        "canonical_form": "gher",
        "arabic_equivalent": "\u063a\u064a\u0631",    # غير
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "gher", "ghair", "gheir", "ghayr",
            "8er", "8air", "8ayr",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic/Lebanese particle 'other / non- / except / different'. "
            "8=gh (8er = gher = ghair = non-). "
            "Common in negation/contrast: gher 3adi = not normal; ma fi gher = nothing else."
        ),
        "added_at": ADDED_AT,
    },

    "enu_conj": {
        "canonical_form": "enu",
        "arabic_equivalent": "\u0625\u0646\u0648",    # إنو
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "enu", "ino", "enno", "inno",
            "enno", "anno",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi complementizer/conjunction 'that / because / so that'. "
            "enu/ino/enno = that (subordinating, after verbs of saying/thinking). "
            "E.g. 2al enu = he said that; sme3t enno = I heard that. "
            "Distinct from la2an (causal 'because') -- this is a neutral subordinator."
        ),
        "added_at": ADDED_AT,
    },

    "nem_affirm": {
        "canonical_form": "nem",
        "arabic_equivalent": "\u0646\u0639\u0645",    # نعم
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["nem", "naem", "naam", "na3am"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Arabic/Lebanese affirmation 'yes' (formal/written register). "
            "nem is the common Lebanese Arabizi transcription of Arabic na3am. "
            "3=ayn in na3am; nem is the monophthongised Lebanese form. "
            "Contrast: aa/ah/aih are informal yes forms."
        ),
        "added_at": ADDED_AT,
    },

    "la2an_conj": {
        "canonical_form": "la2an",
        "arabic_equivalent": "\u0644\u0623\u0646",    # لأن
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "la2an", "la2ano", "la2anne", "la2ane",
            "la2anno", "lian", "li2anno", "la2ann",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi causal conjunction 'because'. "
            "2=hamza (lam-hamza-nun = li+an). "
            "la2an = because; la2ano = because (+ clitic -o 'it/him'). "
            "Very common in explanatory/complaint tweets. "
            "Distinct from enu_conj (neutral 'that') -- la2an is specifically causal."
        ),
        "added_at": ADDED_AT,
    },

    "hayda_dem": {
        "canonical_form": "hayda",
        "arabic_equivalent": "\u0647\u064a\u062f\u0627",  # هيدا
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "hayda", "heyda", "heida", "haida",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi masculine singular demonstrative pronoun/adjective 'this (m.)'. "
            "Feminine form is hayde/heydi (see hayde entry). "
            "hayda is the more formal/written form; hada/hada (see hada_demonstrative) "
            "is the shorter colloquial form. Both are Arabizi signals."
        ),
        "added_at": ADDED_AT,
    },

    "yo2borne_expr": {
        "canonical_form": "yo2borne",
        "arabic_equivalent": "\u064a\u0642\u0628\u0631\u0646\u064a",  # يقبرني
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "yo2borne", "yo2bourne", "yibroni",
            "yibborne", "y2borne",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese Arabizi endearment/affective expression 'may you bury me' "
            "(lit. he-buries-me = I love you so much I'd die for you). "
            "2=qaf (yo2borne = yiqborne). Exclusively Lebanese sentimental register. "
            "Not a crisis signal -- generic affective expression."
        ),
        "added_at": ADDED_AT,
    },

    # -----------------------------------------------------------------------
    # T2_SECTOR_SUPPORT -- Common verbs, nouns, discourse markers
    # -----------------------------------------------------------------------

    "rou7_verb": {
        "canonical_form": "rou7",
        "arabic_equivalent": "\u0631\u0648\u062d",    # روح
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "rou7", "roo7", "ru7", "rouh",
            "ruh", "brou7", "bru7", "roo7e",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi verb 'to go / go away / soul'. "
            "7=ha (ح). rou7! = go away! (imperative). "
            "Also used as noun: el-rou7 = the soul. "
            "brou7/bru7 = I go (b- present tense prefix in Lebanese). "
            "Relevant in evacuation/movement context: rou7 min hon = leave from here."
        ),
        "added_at": ADDED_AT,
    },

    "erja3_verb": {
        "canonical_form": "erja3",
        "arabic_equivalent": "\u0627\u0631\u062c\u0639",  # ارجع
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "erja3", "irja3", "arja3", "rja3",
            "berja3", "birja3", "bterja3",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi verb 'come back / return'. "
            "3=ayn (ع). erja3! = come back! (imperative). "
            "berja3/birja3 = he comes back (b- prefix, present). "
            "bterja3 = you come back (bt- prefix, second person). "
            "Relevant in displacement/evacuation context."
        ),
        "added_at": ADDED_AT,
    },

    "sara7a_adv": {
        "canonical_form": "sara7a",
        "arabic_equivalent": "\u0635\u0631\u0627\u062d\u0629",  # صراحة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "sara7a", "sara7e", "sara7ten",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi discourse marker 'honestly / frankly / to be honest'. "
            "7=ha (ح). sara7a is an intensifier/hedger placed at the start of a candid statement. "
            "Very common in opinion and complaint tweets. "
            "sara7ten = honestly (alternate form)."
        ),
        "added_at": ADDED_AT,
    },

    "la7za_noun": {
        "canonical_form": "la7za",
        "arabic_equivalent": "\u0644\u062d\u0638\u0629",  # لحظة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "la7za", "la7ze", "la7az",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi noun 'a moment / wait a moment'. "
            "7=ha (ح). la7za! = wait a second! (interjection). "
            "Also used as hedge: la7za w she7it = wait and see."
        ),
        "added_at": ADDED_AT,
    },

    "wad3_noun": {
        "canonical_form": "wad3",
        "arabic_equivalent": "\u0648\u0636\u0639",    # وضع
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "wad3", "wad3o", "wad3ak", "wad3na",
            "wad3e", "wad3ha", "wad3on",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi noun 'situation / condition / state of affairs'. "
            "3=ayn (ع) at end of root w-d-3 (wad3). "
            "wad3o = his/its situation; wad3na = our situation; wad3ak = your situation. "
            "Highly relevant in crisis monitoring: el-wad3 sara = the situation got worse."
        ),
        "added_at": ADDED_AT,
    },

    "ra2em_noun": {
        "canonical_form": "ra2em",
        "arabic_equivalent": "\u0631\u0642\u0645",    # رقم
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "ra2em", "ra2am", "ra2m", "raqam",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi noun 'number / figure'. "
            "2=qaf (ق). ra2em = number (ra2am/raqam are alt spellings). "
            "Used in context: ra2em el-telefon = phone number; ra2em kbir = big number. "
            "Relevant in reporting/statistics context."
        ),
        "added_at": ADDED_AT,
    },

    "rawa2_verb": {
        "canonical_form": "rawa2",
        "arabic_equivalent": "\u0631\u0648\u0651\u0642",  # روّق
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "rawa2", "rawwi2", "rawi2", "rwa2",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi slang verb 'to chill / relax / calm down'. "
            "2=qaf (ق). rawa2 = chill out! (imperative). "
            "Often used in social media to tell someone to calm down in a heated discussion. "
            "Relevant as a de-escalation signal in crisis-related threads."
        ),
        "added_at": ADDED_AT,
    },

    "a3mel_verb": {
        "canonical_form": "a3mel",
        "arabic_equivalent": "\u0627\u0639\u0645\u0644",  # اعمل
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "a3mel", "a3mil", "e3mel", "i3mel",
            "na3mel", "ba3mel", "bta3mel",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi verb 'to do / make / act'. "
            "3=ayn (ع). a3mel = do! / make! (imperative). "
            "na3mel = we do; ba3mel = I do; bta3mel = you do. "
            "Very common in imperative calls-to-action in crisis tweets."
        ),
        "added_at": ADDED_AT,
    },

    "b2oul_verb": {
        "canonical_form": "b2oul",
        "arabic_equivalent": "\u0628\u0642\u0648\u0644",  # بقول
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "b2oul", "b2ol", "bi2oul", "bi2ol",
            "bt2oul", "bye2oul",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi verb 'I say / I think / I am saying'. "
            "2=qaf (ق). b2oul = I say (b- present-tense prefix). "
            "bt2oul = you say; bye2oul = he says. "
            "Common discourse marker: b2oul shi = I'd say something."
        ),
        "added_at": ADDED_AT,
    },

    "be3te2ed_verb": {
        "canonical_form": "be3te2ed",
        "arabic_equivalent": "\u0628\u0639\u062a\u0642\u062f",  # بعتقد
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "be3te2ed", "ba3te2id", "ba3ta2id",
            "be3ta2ad", "bte3te2id",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi verb 'I believe / I think / I am of the opinion'. "
            "3=ayn (ع), 2=qaf (ق). be3te2ed = I believe (b- prefix + Form VIII). "
            "Very common as epistemic hedge in opinion tweets."
        ),
        "added_at": ADDED_AT,
    },

    "l3alam_noun": {
        "canonical_form": "l3alam",
        "arabic_equivalent": "\u0627\u0644\u0639\u0627\u0644\u0645",  # العالم
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "l3alam", "el3alam", "al3alam", "3alam",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Arabic Arabizi noun 'the world / the people'. "
            "3=ayn (ع). l3alam = the world (l- = definite article clitic). "
            "el3alam/al3alam = explicit definite form. "
            "Also means 'people (in general)': el3alam mish 3arfin = people don't know."
        ),
        "added_at": ADDED_AT,
    },

    "tal3_verb": {
        "canonical_form": "tal3",
        "arabic_equivalent": "\u0637\u0644\u0639",    # طلع
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "tal3a", "tal3e", "tal3et", "tal3o",
            "tala3", "tela3", "tal3",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi verb 'to go up / come out / appear / turn out'. "
            "3=ayn (ع). tal3 = it went up/came out. "
            "tal3a = she went up / it turned out (f.); tal3et = she went out (past). "
            "Relevant in crisis context: tal3 7ari2 = a fire broke out; tal3 el-ma = water came out."
        ),
        "added_at": ADDED_AT,
    },

    "3omr_noun": {
        "canonical_form": "3omr",
        "arabic_equivalent": "\u0639\u0645\u0631",    # عمر
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "3omr", "3omrak", "3omrik", "3omro",
            "3omrha", "3omrna", "3omr",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Arabic Arabizi noun 'age / lifetime / life (used in endearments)'. "
            "3=ayn (ع). 3omrak = your (m.) life; 3omrik = your (f.) life; "
            "3omro = his life; 3omrha = her life; 3omrna = our lives. "
            "Very common in affective/endearment expressions: 3omrik = my darling (lit. your life). "
            "Also used in negation: ma 3omri = never in my life."
        ),
        "added_at": ADDED_AT,
    },

    "le2e_verb": {
        "canonical_form": "le2e",
        "arabic_equivalent": "\u0644\u0642\u064a",    # لقي
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "le2e", "la2a", "la2o", "le2it",
            "le2yu", "la2et", "la2etna",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi verb 'to find / encounter / come across'. "
            "2=qaf (ق). le2e = he found; la2a = she found (alt form). "
            "la2et = she found (past); le2it = I found. "
            "Common in investigative/discovery context."
        ),
        "added_at": ADDED_AT,
    },

    "we3e_noun": {
        "canonical_form": "we3e",
        "arabic_equivalent": "\u0648\u0639\u064a",    # وعي
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "we3e", "wa3ye", "wa3i", "we3i",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese/Levantine Arabizi noun 'awareness / consciousness / civic sense'. "
            "3=ayn (ع). we3e = awareness. "
            "Common in civic/social media: fi we3e = there is awareness. "
            "Also possible: interjection of disgust (see ha3_expr) -- context distinguishes."
        ),
        "added_at": ADDED_AT,
    },

    "da2_verb": {
        "canonical_form": "da2",
        "arabic_equivalent": "\u062f\u0642",          # دق
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "da2", "da22", "do22", "bda2",
            "eda2",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi verb 'to knock / ring (door or phone) / beat'. "
            "2=qaf (ق). da2 = he knocked/rang; da2! = knock! ring! (imperative). "
            "bda2 = I knock/ring (b- prefix). "
            "Relevant in emergency-alert context: da2 el-jarras = ring the bell; "
            "da2 3ala telefon al-is3af = call the ambulance."
        ),
        "added_at": ADDED_AT,
    },

    "ne2_verb": {
        "canonical_form": "ne2",
        "arabic_equivalent": "\u0646\u0642",          # نق
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "ne2", "na2", "ne22", "bne2",
            "mne2", "byene2",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese Arabizi verb 'to nag / complain / grumble'. "
            "2=qaf (ق). ne2/na2 = nag/complain; bne2 = we nag; mne2 = we nag (alt). "
            "Common in social commentary: bas yene2 = he just nags. "
            "Note: na2 can also derive from ناق 'to ring/chime' -- context distinguishes."
        ),
        "added_at": ADDED_AT,
    },

    # -----------------------------------------------------------------------
    # T1_DIRECT_SIGNAL -- Frustration expressions, crisis/sectarian signals
    # -----------------------------------------------------------------------

    "yel3an_expr": {
        "canonical_form": "yel3an",
        "arabic_equivalent": "\u064a\u0644\u0639\u0646",  # يلعن
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["SAFETY"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "yel3an", "yil3an", "yel3ane",
            "yel3anak", "yel3ano", "yel3an",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Levantine Arabizi curse/imprecation 'damn (X) / curse (X)'. "
            "3=ayn (ع). yel3an = may he/it be cursed; yel3anak = damn you. "
            "Strong frustration signal -- commonly found in crisis/anger tweets. "
            "yel3an abu... = damn [someone's father] = very strong curse. "
            "HIGH severity when paired with service/infrastructure complaints."
        ),
        "added_at": ADDED_AT,
    },

    "l3ama_expr": {
        "canonical_form": "l3ama",
        "arabic_equivalent": "\u0627\u0644\u0639\u0645\u0649",  # العمى
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["SAFETY"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "l3ama", "el3ama", "3ama",
            "l3ameh", "3ameh",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi expletive/exclamation 'blindness! / damn it!'. "
            "3=ayn (ع). l3ama (lit. 'the blindness') = damn! / what the heck! "
            "Mild-to-medium Lebanese profanity used as an exclamation of frustration. "
            "Severity: MEDIUM when used as standalone expletive; HIGH if in context "
            "of infrastructure failure or emergency."
        ),
        "added_at": ADDED_AT,
    },

    "ha3_expr": {
        "canonical_form": "ha3",
        "arabic_equivalent": "\u0647\u0639",          # هع
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "ha3", "haa3", "ha3a",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese Arabizi interjection of disgust/nausea 'ugh / yuck / bleh'. "
            "3=ayn (ع). ha3 = sound of disgust or nausea (هع). "
            "Distinct from haa (simple exclamation) by the 3/ayn. "
            "Signal of strong negative reaction -- potentially relevant in "
            "environmental/sanitation complaints."
        ),
        "added_at": ADDED_AT,
    },

    "bo3_expr": {
        "canonical_form": "bo3",
        "arabic_equivalent": "\u0628\u0648\u0639",    # بوع
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "bo3", "boo3", "baw3",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese Arabizi interjection/noun 'nausea / yuck / feel sick'. "
            "3=ayn (ع). bo3/baw3 = نausea sound (بوع). "
            "Used as interjection of disgust or to express literal nausea. "
            "Relevant in health/sanitation-complaint context."
        ),
        "added_at": ADDED_AT,
    },

    "shi3a_sect": {
        "canonical_form": "shi3a",
        "arabic_equivalent": "\u0634\u064a\u0639\u0629",  # شيعة
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["SAFETY"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "shi3a", "shi3e", "shi3ia", "shia",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese/Arabic Arabizi noun 'Shia (Muslim sect/community)'. "
            "3=ayn (ع). shi3a = Shia; shia = alternate spelling without digit. "
            "High-sensitivity socio-political term in Lebanese context. "
            "Relevant for sectarian-conflict detection. "
            "must_not_auto_promote=false but use with care in automated scoring."
        ),
        "added_at": ADDED_AT,
    },

    "ta2es_adj": {
        "canonical_form": "ta2es",
        "arabic_equivalent": "\u062a\u0627\u0626\u0633",  # تائس
        "semantic_type": "T1_DIRECT_SIGNAL",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "ta2es", "ta2is", "ta2is",
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese/Levantine Arabizi adjective 'despairing / hopeless / pessimistic'. "
            "2=hamza (ء) as in ta2is (ta-hamza-is). "
            "ta2es/ta2is = despairing, feeling hopeless (from root y-a-s = despair). "
            "Direct distress signal relevant to mental-state and crisis-severity detection. "
            "Note: could also derive from طقس (ta2s = weather/storm) in weather context -- "
            "review with context."
        ),
        "added_at": ADDED_AT,
    },

}  # end NEW_ENTRIES


# ---------------------------------------------------------------------------
# 7 VARIANT PATCHES (add missing forms to existing entries)
# ---------------------------------------------------------------------------
VARIANT_PATCHES = {

    # bas_connector: add 'bass' (double-s intensified form) and 'bs' (abbreviated)
    "bas_connector": {
        "add_variants": ["bass", "bs"],
    },

    # chou_question: add 'shou' (most common Lebanese Arabizi) and 'shoo' (elongated)
    "chou_question": {
        "add_variants": ["shou", "shoo"],
    },

    # allah_excl: add 'yalla' (common short form) and 'yella' (alt spelling)
    "allah_excl": {
        "add_variants": ["yalla", "yella"],
    },

    # hada_demonstrative: add hayda/heyda (fuller Lebanese 'this m.')
    "hada_demonstrative": {
        "add_variants": ["hayda", "heyda"],
    },

    # halla2_now: add 'hl2' (ultra-compressed SMS-style form)
    "halla2_now": {
        "add_variants": ["hl2"],
    },

    # ma3_preposition: add 'ma3kon' (Lebanese f.pl. 'with you all')
    "ma3_preposition": {
        "add_variants": ["ma3kon"],
    },

    # ba3da_temporal: add 'ba3don' (they still / still them)
    "ba3da_temporal": {
        "add_variants": ["ba3don"],
    },

    # wa2t_noun: add missing inflected forms (wa2ta, wa2tik, wa2tak, wa2tha, wa2at)
    "wa2t_noun": {
        "add_variants": ["wa2ta", "wa2tik", "wa2tak", "wa2tha", "wa2at"],
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
    print("[V20e] Loading vocab from:", str(VOCAB_PATH))
    vocab = json.load(open(VOCAB_PATH, encoding="utf-8"))

    current = vocab.get("version", "?")
    if current != CURRENT_VERSION:
        print("[ERROR] Expected version " + CURRENT_VERSION + ", got " + current + ". Aborting.")
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
    print("[V20e] New entries      : " + str(len(NEW_ENTRIES))
          + "  (T1=" + str(t1) + " T2=" + str(t2) + " T3=" + str(t3) + ")")
    print("[V20e] Variant patches  : " + str(len(VARIANT_PATCHES)))
    print("[V20e] Version          : " + CURRENT_VERSION + " -> " + NEW_VERSION)

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
        print("[DRY-RUN] Sample new forms    : " + str(sorted(added)[:25]))
        return

    # -- Backup ---
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = VOCAB_PATH.with_suffix(".bak-before-v20e-" + ts + ".json")
    shutil.copy2(VOCAB_PATH, backup)
    print("[V20e] Backup saved: " + backup.name)

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
        NEW_VERSION + " (2026-05-22): V20e corpus-gap closure -- "
        + str(added_count) + " new term_metadata entries ("
        + str(len(NEW_ENTRIES)) + " planned) + "
        + str(len(VARIANT_PATCHES)) + " entry patches. "
        "Milestone: 2.0.0 -- covers major Lebanese function words, connectors, "
        "pronouns, verbs, and frustration signals. "
        "Patches: bas_connector+bass/bs, chou_question+shou/shoo, "
        "allah_excl+yalla/yella, hada_demonstrative+hayda/heyda, "
        "halla2_now+hl2, ma3_preposition+ma3kon, ba3da_temporal+ba3don. "
        "Source: Lebanon-corpus strict-Arabizi OOV scan (2,747 digit-token instances)."
    )
    vocab.setdefault("changelog", []).append(changelog_entry)

    known_after = build_known(vocab)
    new_forms = known_after - known_before

    # -- Save ---
    with open(VOCAB_PATH, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=2)

    print()
    print("[V20e] Done. Vocab bumped " + CURRENT_VERSION + " -> " + NEW_VERSION)
    print("[V20e] term_metadata entries : " + str(len(meta)))
    print("[V20e] New entries applied   : " + str(added_count))
    print("[V20e] Variant patch forms   : " + str(patch_count))
    print("[V20e] known_tokens before   : " + str(len(known_before)))
    print("[V20e] known_tokens after    : " + str(len(known_after)))
    print("[V20e] New normalised forms  : " + str(len(new_forms)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing")
    args = parser.parse_args()
    main(dry_run=args.dry_run)

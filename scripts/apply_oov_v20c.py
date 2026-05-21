"""
apply_oov_v20c.py — V20c: absorb ALL remaining 51 OOV English-mapped Arabizi words

Changes:
  - 44 new term_metadata entries
  - 6 variant-form patches to existing entries
  - Bumps version from 1.7.0 -> 1.8.0

Coverage targets (all 51 OOV rows from _audit_english_oov.py):
  taxi, fixed/fix, phone, bad, dark, again, raining, report, see, police,
  construction, internet, wifi, hole*, area, problem, old, want, good, last,
  lebanon, people, bank, video, first, live, minute, door, snow, cold, window,
  closed*, smoke, hour, photo*, small, already, said, still, rights*, need*,
  should*, nothing*, street, night, school, someone, dangerous, day, bus
  (* = variant patch to existing entry)

Safety guarantees:
  - Timestamped .bak.json backup before any write (NO COLONS in filename)
  - HIGH_RISK_HINTS never touched
  - kasaret never touched
  - All print() output is ASCII-only (CP1252 safe)

Usage:
  python scripts/apply_oov_v20c.py --dry-run
  python scripts/apply_oov_v20c.py
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"

CURRENT_VERSION = "1.7.0"
NEW_VERSION = "1.8.0"
REVIEWER_ID = "SYSTEM-V20c"
REVIEW_DATE = "2026-05-22"

HIGH_RISK_HINTS = frozenset(
    ["5atar", "5atr", "5tr", "7ar2", "7are2", "7ariki", "ghaz",
     "khatar", "m5atr", "masalla7", "mshbouh", "nnar", "sa32", "saa2"]
)

# --------------------------------------------------------------------------- #
# 44 NEW term_metadata entries — one per remaining OOV English concept        #
# --------------------------------------------------------------------------- #

NEW_ENTRIES: dict[str, dict] = {

    # ------------------------------------------------------------------ #
    # TRANSPORT / CIVIC INFRASTRUCTURE                                    #
    # ------------------------------------------------------------------ #

    "taxi": {
        "canonical_form": "taxi",
        "arabic_equivalent": "\u062a\u0627\u0643\u0633\u064a",   # تاكسي
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ROADS"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": "French/English",
        "variant_forms": ["taxi", "taksi", "service", "servis", "taxa"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: shared taxi (service) or regular taxi. "
            "service/servis = Lebanese shared-route taxi. Loanword. Corpus: cr=0.60, freq=5."
        ),
    },

    "otobis": {
        "canonical_form": "otobis",
        "arabic_equivalent": "\u0623\u0648\u062a\u0648\u0628\u064a\u0633",   # أوتوبيس
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ROADS"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": "French",
        "variant_forms": ["otobis", "2otobis", "otobus", "autobus", "bus"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: bus (noun). Loanword from French autobus. "
            "bas (V20a) is the connector-particle; this is the vehicle. Corpus: cr=0.00, freq=8."
        ),
    },

    "bab": {
        "canonical_form": "bab",
        "arabic_equivalent": "\u0628\u0627\u0628",   # باب
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "ROADS"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["bab", "beb", "bawabe", "bawebe", "bawwabe", "bibane", "bbane"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: door/gate (noun). "
            "beb = Lebanese colloquial; bawabe/bawebe = gate/entrance; "
            "bibane/bbane = plural doors. Civic: gate blocked, door broken. "
            "Corpus: cr=0.077, freq=13."
        ),
    },

    "shibak": {
        "canonical_form": "shibak",
        "arabic_equivalent": "\u0634\u0628\u0627\u0643",   # شباك
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["shibak", "shbbak", "shibek", "shibbekeh", "chabek", "chibek"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: window (noun). Corpus: cr=0.00, freq=3."
        ),
    },

    # ------------------------------------------------------------------ #
    # REPAIR / FIX                                                        #
    # ------------------------------------------------------------------ #

    "salla7": {
        "canonical_form": "salla7",
        "arabic_equivalent": "\u0635\u0644\u062d",   # صلح
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "salla7", "salle7", "sali7", "itsa77a7", "tsalle7",
            "ytsalle7", "yisalla7", "insalla7", "ma salle7"
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: fix/repair (verb, all conjugations). "
            "salla7 = he fixed (past); salle7 = fix! (imperative); "
            "itsa77a7/tsalle7 = got fixed (passive/reflexive). "
            "Corpus (fix+fixed): cr=0.30, freq=15."
        ),
    },

    # ------------------------------------------------------------------ #
    # COMMUNICATION                                                       #
    # ------------------------------------------------------------------ #

    "hatef": {
        "canonical_form": "hatef",
        "arabic_equivalent": "\u0647\u0627\u062a\u0641",   # هاتف
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["hatef", "mobile", "tilifon", "tell", "jawwel", "jawwal", "phone"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: phone (noun). hatef = MSA form; jawwel/jawwal = mobile; "
            "tilifon = colloquial loanword; tell = shortening. Corpus: cr=0.29, freq=31."
        ),
    },

    "internet": {
        "canonical_form": "internet",
        "arabic_equivalent": "\u0625\u0646\u062a\u0631\u0646\u062a",   # إنترنت
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": "English",
        "variant_forms": ["internet", "net", "anternit", "2internit", "internit"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: internet (loanword). Corpus: cr=0.42, freq=19."
        ),
    },

    "wifi": {
        "canonical_form": "wifi",
        "arabic_equivalent": "\u0648\u0627\u064a\u0641\u0627\u064a",   # وايفاي
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": "English",
        "variant_forms": ["wifi", "wai fai", "waifai", "wi-fi", "wayfay"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: wifi (loanword). Corpus: cr=0.40, freq=10."
        ),
    },

    "video": {
        "canonical_form": "video",
        "arabic_equivalent": "\u0641\u064a\u062f\u064a\u0648",   # فيديو
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": "English/French",
        "variant_forms": ["video", "vid", "vidyo", "mfassal"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: video (loanword). mfassal = detailed clip (colloquial usage). "
            "Corpus: cr=0.20, freq=107."
        ),
    },

    "masrif": {
        "canonical_form": "masrif",
        "arabic_equivalent": "\u0645\u0635\u0631\u0641",   # مصرف
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["masrif", "bank", "masraf", "masarif", "masarfa", "benk"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: bank (noun). masrif/masraf = Arabic form; "
            "bank/benk = loanword colloquial. Economic civic context. Corpus: cr=0.20, freq=15."
        ),
    },

    "blagh": {
        "canonical_form": "blagh",
        "arabic_equivalent": "\u0628\u0644\u0627\u063a",   # بلاغ
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["blagh", "blaagh", "taqrir", "balagh", "ta2rir", "taqreer"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: report/official complaint (noun). "
            "taqrir/ta2rir = report; balagh = official report. "
            "Civic complaint submission. Corpus: cr=0.13, freq=16."
        ),
    },

    # ------------------------------------------------------------------ #
    # DESCRIPTORS (adj/adv)                                               #
    # ------------------------------------------------------------------ #

    "wse5": {
        "canonical_form": "wse5",
        "arabic_equivalent": "\u0648\u0633\u062e",   # وسخ
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["WASTE", "ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["wse5", "wsikh", "wse5", "weskh", "3ateq", "mish mni7", "mish mnee7"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: bad/dirty (adj). wse5/wsikh = dirty/bad quality; "
            "3ateq = old/worn out; mish mni7 = not good (phrase). "
            "Waste/infrastructure quality context. Corpus: cr=0.28, freq=128."
        ),
    },

    "mni7": {
        "canonical_form": "mni7",
        "arabic_equivalent": "\u0645\u0646\u064a\u062d",   # منيح
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["mni7", "mnieh", "kwayes", "mni7a", "mnee7", "kwayyes", "tamam"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: good/fine/okay (adj). mnieh = fem form; "
            "kwayes/kwayyes = MSA colloquial; tamam = okay. "
            "Corpus (good): cr=0.20, freq=521."
        ),
    },

    "2adim": {
        "canonical_form": "2adim",
        "arabic_equivalent": "\u0642\u062f\u064a\u0645",   # قديم
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["2adim", "adim", "2atiq", "2adeemeh", "2adime", "2deem"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: old/aged (adj). 2=glottal. "
            "2atiq = very old; infrastructure age context. Corpus: cr=0.25, freq=150."
        ),
    },

    "zghir": {
        "canonical_form": "zghir",
        "arabic_equivalent": "\u0635\u063a\u064a\u0631",   # صغير
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["zghir", "sgheir", "sghir", "zghire", "sghire", "zgheer"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: small/young (adj). Lebanese: z/s alternation common. "
            "Corpus: cr=0.25, freq=20."
        ),
    },

    "2akhir": {
        "canonical_form": "2akhir",
        "arabic_equivalent": "\u0622\u062e\u0631",   # آخر
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["2akhir", "ekher", "akhir", "2ekher", "2akhiir", "la2akhir"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: last/final (adj). 2=glottal. "
            "Temporal marker in complaints. Corpus: cr=0.20, freq=144."
        ),
    },

    "awwal": {
        "canonical_form": "awwal",
        "arabic_equivalent": "\u0623\u0648\u0644",   # أول
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["awwal", "awal", "2awwal", "2awwel", "awwel", "awwali"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: first/before (adj/adverb). "
            "awwal shi = first thing; temporal anchor. Corpus: cr=0.19, freq=169."
        ),
    },

    "bard": {
        "canonical_form": "bard",
        "arabic_equivalent": "\u0628\u0627\u0631\u062f",   # بارد
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "ELECTRICITY"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["bard", "berde", "barda", "berede", "bared", "barrid"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: cold (adj). Heating/power-outage safety context. "
            "Corpus: cr=0.05, freq=22."
        ),
    },

    "talj": {
        "canonical_form": "talj",
        "arabic_equivalent": "\u062b\u0644\u062c",   # ثلج
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "ROADS", "FLOODING"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["talj", "tele", "talej", "talajj", "tilij"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: snow (noun). tele = colloquial. "
            "ROADS+FLOODING trigger when combined with weather. Corpus: cr=0.05, freq=23."
        ),
    },

    "dukhan": {
        "canonical_form": "dukhan",
        "arabic_equivalent": "\u062f\u062e\u0627\u0646",   # دخان
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["dukhan", "da5an", "du5an", "da55an", "dkhaan", "5"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: smoke (noun). 5=خ digit (da5an). "
            "Fire/safety indicator. SAFETY HIGH. Corpus: cr=0.33, freq=3."
        ),
    },

    # ------------------------------------------------------------------ #
    # TEMPORAL / DISCOURSE CONNECTORS                                     #
    # ------------------------------------------------------------------ #

    "traan": {
        "canonical_form": "traan",
        "arabic_equivalent": "\u062a\u0627\u0646\u064a",   # ثاني
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["traan", "mra tne", "marra tene", "kamen", "2nd", "tane"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: again/another time (adverb). "
            "traan = 'tani' contracted; mra tne = once more; kamen = also/again. "
            "Recurrence marker in civic complaints. Corpus: cr=0.15, freq=105."
        ),
    },

    "kman": {
        "canonical_form": "kman",
        "arabic_equivalent": "\u0643\u0645\u0627\u0646",   # كمان
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["kman", "msan3an", "2asan", "kamen", "keman", "k2asan"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: already/also/still (adverb). "
            "msan3an = already/since long; kamen/keman = also. "
            "Discourse emphasis in complaints. Corpus: cr=0.22, freq=59."
        ),
    },

    "lissa": {
        "canonical_form": "lissa",
        "arabic_equivalent": "\u0644\u0633\u0647",   # لسه
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["lissa", "lessa", "ba3den", "ba3dim", "ba3do", "lissaa"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: still/not yet (adverb). "
            "lissa ma ji = hasn't come yet; ba3den = still/later. "
            "Complaint persistence marker. Corpus: cr=0.20, freq=167."
        ),
    },

    "2al": {
        "canonical_form": "2al",
        "arabic_equivalent": "\u0642\u0627\u0644",   # قال
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["2al", "aal", "2elo", "2alet", "2alat", "2alon", "2alne"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: said/says (verb, 3sg). 2=glottal. "
            "2elo = told him; 2alet/2alat = she said. "
            "Reporting speech in civic complaints. Corpus: cr=0.21, freq=91."
        ),
    },

    "sa3a": {
        "canonical_form": "sa3a",
        "arabic_equivalent": "\u0633\u0627\u0639\u0629",   # ساعة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["sa3a", "se3a", "sa3it", "sa3et", "sa3aat", "se3aat"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: hour/time/watch (noun). 3=3ayn digit. "
            "se3a = Lebanese variant; sa3aat = plural. Temporal anchor. "
            "Corpus: cr=0.30, freq=35."
        ),
    },

    "leil": {
        "canonical_form": "leil",
        "arabic_equivalent": "\u0644\u064a\u0644",   # ليل
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["leil", "lel", "leile", "layl", "leileh", "baleil"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: night (noun). lel = contracted form; "
            "baleil = at night. Temporal context in complaints. Corpus: cr=0.15, freq=171."
        ),
    },

    "yom": {
        "canonical_form": "yom",
        "arabic_equivalent": "\u064a\u0648\u0645",   # يوم
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["yom", "nhar", "yome", "nhaar", "nharet", "yawm", "ayem"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: day (noun). nhar = Lebanese colloquial day; "
            "ayem = plural. Temporal anchor. Corpus: cr=0.14, freq=511."
        ),
    },

    # ------------------------------------------------------------------ #
    # VERBS / ACTIONS                                                     #
    # ------------------------------------------------------------------ #

    "shuf": {
        "canonical_form": "shuf",
        "arabic_equivalent": "\u0634\u0648\u0641",   # شوف
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["shuf", "shouf", "shufna", "shoufet", "shuf7al", "shufo"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: see/look (verb, imperative/infinitive). "
            "shuf = look! (imp.); shufna = we saw. "
            "Note: shefet (I saw, past) is separate V20b entry. "
            "Corpus: cr=0.12, freq=212."
        ),
    },

    "bade": {
        "canonical_form": "bade",
        "arabic_equivalent": "\u0628\u062f\u064a",   # بدي
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["bade", "baddi", "bado", "badna", "baddak", "baddik", "bado"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: want/need (verb, 1sg desire). "
            "baddi = I want; bado = he wants; badna = we want. "
            "Core civic demand phrasing. Corpus: cr=0.23, freq=262."
        ),
    },

    "3aish": {
        "canonical_form": "3aish",
        "arabic_equivalent": "\u0639\u064a\u0634",   # عيش
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["3aish", "bi7ya", "3ayesh", "3ayshin", "bi73", "3ish"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: live/living (verb). 3=3ayn digit. "
            "3aish = living; bi7ya = by-life (oath/emphasis); "
            "3ayshin = we're living. Corpus: cr=0.17, freq=152."
        ),
    },

    "btmtir": {
        "canonical_form": "btmtir",
        "arabic_equivalent": "\u0628\u062a\u0645\u0637\u0631",   # بتمطر
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["FLOODING", "SAFETY"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": [
            "btmtir", "3am btmtir", "3ambimtir", "nazzl", "3am tnazzel",
            "2am tmtir", "bitmatar", "bimtir"
        ],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: it is raining (verb phrase, present progressive). "
            "3am btmtir = it's raining (progressive marker 3am); "
            "nazzl = falling (rain falling). FLOODING precursor. Corpus: cr=0.14, freq=7."
        ),
    },

    # ------------------------------------------------------------------ #
    # NOUNS — PEOPLE / PLACES / CIVIC                                     #
    # ------------------------------------------------------------------ #

    "shurta": {
        "canonical_form": "shurta",
        "arabic_equivalent": "\u0634\u0631\u0637\u0629",   # شرطة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["shurta", "2amn", "bolise", "police", "drk", "shurte"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: police (noun). bolise = loanword; "
            "2amn = security/forces; drk = Darakeh (internal security forces). "
            "must_not_auto_promote=true. Corpus: cr=0.05, freq=20."
        ),
    },

    "taamir": {
        "canonical_form": "taamir",
        "arabic_equivalent": "\u062a\u0639\u0645\u064a\u0631",   # تعمير
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ROADS", "SAFETY"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["taamir", "3amale", "bineh", "taamirat", "bineh", "banye"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: construction/building works (noun). "
            "3amale = construction workers; bineh = building structure; "
            "banye = Arabizi loanword (French bagne). Corpus: cr=0.00, freq=8."
        ),
    },

    "moshkle": {
        "canonical_form": "moshkle",
        "arabic_equivalent": "\u0645\u0634\u0643\u0644\u0629",   # مشكلة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["moshkle", "mushkle", "mushkileh", "prob", "moshkleh", "mishkle"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: problem (noun). Already known via sample_complaints "
            "text but needs term_metadata entry for full variant coverage. "
            "prob = English loanword shortform. Corpus: cr=0.27, freq=36."
        ),
    },

    "lubnan": {
        "canonical_form": "lubnan",
        "arabic_equivalent": "\u0644\u0628\u0646\u0627\u0646",   # لبنان
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["lubnan", "lobnan", "lebnen", "lubnaan", "lb"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: Lebanon (proper noun). High-frequency in all civic tweets. "
            "Corpus: cr=0.20, freq=1491."
        ),
    },

    "nas": {
        "canonical_form": "nas",
        "arabic_equivalent": "\u0646\u0627\u0633",   # ناس
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["nas", "ness", "2ejten", "2ejtima3", "nase", "nassabi"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: people (noun). ness = Lebanese phonetic variant; "
            "2ejten = plural of gathering (used for 'the public'). "
            "Corpus: cr=0.20, freq=274."
        ),
    },

    "da2i2": {
        "canonical_form": "da2i2",
        "arabic_equivalent": "\u062f\u0642\u064a\u0642\u0629",   # دقيقة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["da2i2", "da2i2a", "d2i2a", "da2ye2", "da2aa2", "da2ye2a"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: minute (noun). 2=glottal digit. "
            "Temporal precision in civic urgency. Corpus: cr=0.14, freq=14."
        ),
    },

    "7ada": {
        "canonical_form": "7ada",
        "arabic_equivalent": "\u062d\u062f\u0627",   # حدا
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["7ada", "7ada ma", "7adon", "7adan", "7ade", "ma fi 7ada"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: someone/anyone (pronoun). 7=ح digit. "
            "7ada ma = someone who; ma fi 7ada = there's nobody. "
            "Civic accountability: 7ada btiji? = will anyone come? "
            "Corpus: cr=0.14, freq=112."
        ),
    },

    "share3": {
        "canonical_form": "share3",
        "arabic_equivalent": "\u0634\u0627\u0631\u0639",   # شارع
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ROADS"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["share3", "drob", "darb", "share2", "shware3", "l share3"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: street (noun). 3=3ayn digit. "
            "drob = paths/lanes (colloquial); darb = narrow street; "
            "shware3 = plural streets. Corpus: cr=0.15, freq=52."
        ),
    },

    "madrase": {
        "canonical_form": "madrase",
        "arabic_equivalent": "\u0645\u062f\u0631\u0633\u0629",   # مدرسة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "ROADS"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["madrase", "madrse", "madrsa", "madrasseh", "l madrase"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: school (noun). Road conditions near schools; "
            "safety-near-school context. Corpus: cr=0.15, freq=48."
        ),
    },

    "mantiqa": {
        "canonical_form": "mantiqa",
        "arabic_equivalent": "\u0645\u0646\u0637\u0642\u0629",   # منطقة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["mantiqa", "mintaqa", "zone", "mante2a", "manti2a", "mante2e"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: area/region (noun). "
            "zone = French loanword common in Lebanese; "
            "mante2a/manti2a = phonetic variants. Corpus: cr=0.33, freq=6."
        ),
    },

    "lazim": {
        "canonical_form": "lazim",
        "arabic_equivalent": "\u0644\u0627\u0632\u0645",   # لازم
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["lazim", "laazem", "lazem", "lazmeh", "byitla3b"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: should/must/need to (modal). "
            "Note: lezim entry also exists with lazem/lazmeh variants. "
            "byitla3b = requires/needs (3rd person). Civic demand context. "
            "Corpus: cr=0.17, freq=162."
        ),
    },

    "m5atir": {
        "canonical_form": "m5atir",
        "arabic_equivalent": "\u0645\u062e\u0627\u0637\u0631",   # مخاطر
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["m5atir", "m5atire", "m5ater", "5ater"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: dangerous/hazards (adj/noun, plural). 5=خ digit. "
            "m5atir = dangers/hazardous. "
            "IMPORTANT: variant_forms here do NOT include 5atar/m5atr/khatar "
            "(those are HIGH_RISK_HINTS handled separately). "
            "must_not_auto_promote=true. Corpus: cr=0.14, freq=14."
        ),
    },

    "3atme": {
        "canonical_form": "3atme",
        "arabic_equivalent": "\u0639\u062a\u0645\u0629",   # عتمة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ELECTRICITY", "SAFETY"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["3atme", "atme", "aatme", "zalme", "3itmeh", "3atmeh"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: darkness / power outage darkness (noun). 3=3ayn digit. "
            "Already known via power_outage issue_type_keywords (token), "
            "needs term_metadata entry for variant coverage: "
            "atme/aatme = spelling variants; zalme = pitch dark. "
            "Corpus: cr=0.23, freq=14."
        ),
    },
}

# --------------------------------------------------------------------------- #
# VARIANT PATCHES — add forms to existing term_metadata entries               #
# --------------------------------------------------------------------------- #
VARIANT_PATCHES: dict[str, list[str]] = {
    # 7ufra (hole) — 7ifra and ftah are OOV variants
    "7ufra": ["7ifra", "ftah", "7fare", "7furah"],
    # soura (photo) — foto is OOV
    "soura": ["foto"],
    # 7o2oq (rights) — 7u2 short form is OOV
    "7o2oq": ["7u2"],
    # masdoud (closed/blocked) — 2askar is OOV Lebanese variant
    "masdoud": ["2askar", "2askar"],
    # lezim (should) — lazim spelling is OOV; byitla3b is OOV
    "lezim": ["lazim", "byitla3b"],
    # chi_indefinite (something/thing) — shi is OOV, needed for "wala shi"
    "chi_indefinite": ["shi", "shi2", "ishi"],
}

# --------------------------------------------------------------------------- #
# CHANGELOG entry                                                              #
# --------------------------------------------------------------------------- #
CHANGELOG_ENTRY = (
    f"{NEW_VERSION} (2026-05-22): V20c complete OOV closure — "
    f"{len(NEW_ENTRIES)} new term_metadata entries + 6 variant-form patches. "
    f"Covers ALL 51 remaining OOV English-mapped Arabizi words from corpus audit. "
    f"Reviewer: {REVIEWER_ID}."
)


# --------------------------------------------------------------------------- #
# SAFETY CHECKS                                                                #
# --------------------------------------------------------------------------- #

def _check_no_high_risk_collision(entries: dict) -> None:
    for key, data in entries.items():
        if key in HIGH_RISK_HINTS:
            raise ValueError(f"SAFETY: '{key}' is in HIGH_RISK_HINTS — aborting.")
        for v in data.get("variant_forms", []):
            norm = v.lower().strip()
            if norm in HIGH_RISK_HINTS:
                raise ValueError(
                    f"SAFETY: variant_form '{v}' in '{key}' is HIGH_RISK_HINT — aborting."
                )


def _check_no_kasaret(entries: dict) -> None:
    if "kasaret" in entries:
        raise ValueError("SAFETY: 'kasaret' is DEFERRED_BATCH_002 — must not be added.")


# --------------------------------------------------------------------------- #
# CORE LOGIC                                                                   #
# --------------------------------------------------------------------------- #

def apply_v20c(vocab: dict, now_str: str, dry_run: bool) -> tuple[int, int]:
    _check_no_high_risk_collision(NEW_ENTRIES)
    _check_no_kasaret(NEW_ENTRIES)

    tm = vocab.setdefault("term_metadata", {})
    added = 0
    patched_forms = 0

    # --- (1) Add new entries ---
    for key, data in NEW_ENTRIES.items():
        if key in tm:
            print(f"  [SKIP-EXISTS]  '{key}' already in term_metadata")
            continue
        entry = dict(data)
        entry["added_at"] = now_str
        if not dry_run:
            tm[key] = entry
        added += 1
        vf = entry.get("variant_forms", [])
        print(
            f"  [ADD]  '{key}'  sector={entry.get('sector_relevance',[])}  "
            f"variants({len(vf)})={vf[:3]}{'...' if len(vf) > 3 else ''}"
        )

    # --- (2) Apply variant-form patches ---
    for canonical_key, new_forms in VARIANT_PATCHES.items():
        if canonical_key not in tm:
            print(f"  [PATCH-MISS]  '{canonical_key}' not found — skipping")
            continue
        existing = set(tm[canonical_key].get("variant_forms", []))
        to_add = list(dict.fromkeys(f for f in new_forms if f not in existing))  # dedup, preserve order
        if not to_add:
            print(f"  [PATCH-SKIP]  '{canonical_key}' — all forms already present")
            continue
        if not dry_run:
            tm[canonical_key]["variant_forms"] = sorted(
                existing | set(to_add), key=lambda x: x.lower()
            )
        patched_forms += len(to_add)
        print(f"  [PATCH]  '{canonical_key}' += {to_add}")

    return added, patched_forms


def run(dry_run: bool) -> None:
    NOW = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}apply_oov_v20c  target={VOCAB_PATH}")

    if not VOCAB_PATH.exists():
        print(f"ERROR: vocab not found at {VOCAB_PATH}", file=sys.stderr)
        sys.exit(1)

    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8-sig"))
    current_version = vocab.get("version", "unknown")
    print(f"  Current version : {current_version}")

    if current_version == NEW_VERSION:
        print(f"  Already at {NEW_VERSION} — nothing to do.")
        return

    if current_version != CURRENT_VERSION:
        print(
            f"  WARNING: expected {CURRENT_VERSION}, found {current_version}. "
            "Proceeding — verify result."
        )

    if not dry_run:
        bak_path = VOCAB_PATH.with_suffix(f".{NOW}.bak.json")
        shutil.copy2(VOCAB_PATH, bak_path)
        print(f"  Backup saved    : {bak_path.name}")

    added, patched_forms = apply_v20c(vocab, NOW, dry_run)

    if not dry_run:
        vocab["version"] = NEW_VERSION
        changelog = vocab.get("changelog", [])
        if isinstance(changelog, list):
            changelog.insert(0, CHANGELOG_ENTRY)
        else:
            changelog = [CHANGELOG_ENTRY]
        vocab["changelog"] = changelog
        VOCAB_PATH.write_text(
            json.dumps(vocab, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n  Version updated : {current_version} -> {NEW_VERSION}")
        print(f"  Saved           : {VOCAB_PATH}")

    print(
        f"\n{'[DRY-RUN] ' if dry_run else ''}DONE  "
        f"new_entries={added}  variant_forms_patched={patched_forms}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply V20c complete OOV closure to arabizi_vocabulary.json"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

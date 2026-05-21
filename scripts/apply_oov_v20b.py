"""
apply_oov_v20b.py — V20b comprehensive OOV absorption into arabizi_vocabulary.json

Adds:
  - 43 new term_metadata entries (civic infrastructure, weather, discourse verbs)
  - 6 variant-form patches to existing entries (matar, kahrabe, sene, jdide, tarik, lama)
  - Bumps version from 1.6.0 to 1.7.0

Safety guarantees:
  - Creates timestamped .bak.json backup before any write (Windows-safe filename: NO COLONS)
  - Skips silently if already at 1.7.0
  - Never touches HIGH_RISK_HINTS entries
  - Never modifies kasaret (DEFERRED_BATCH_002)
  - All print() output is ASCII-only (CP1252 safe — no Arabic chars)

Run modes:
  python scripts/apply_oov_v20b.py --dry-run   (no file writes)
  python scripts/apply_oov_v20b.py             (live run)
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"

CURRENT_VERSION = "1.6.0"
NEW_VERSION = "1.7.0"
REVIEWER_ID = "SYSTEM-V20b"
ADDED_BY = "apply_oov_v20b"
REVIEW_DATE = "2026-05-22"

# FROZEN — DO NOT ADD, MODIFY, OR REMOVE any of these
HIGH_RISK_HINTS = frozenset(
    ["5atar", "5atr", "5tr", "7ar2", "7are2", "7ariki", "ghaz",
     "khatar", "m5atr", "masalla7", "mshbouh", "nnar", "sa32", "saa2"]
)

# --------------------------------------------------------------------------- #
# 43 NEW term_metadata entries                                                 #
# --------------------------------------------------------------------------- #
# Format mirrors V20a entries (canonical_form, arabic_equivalent, semantic_type,
# sector_relevance, severity_relevance, variant_forms, false_friend_risk,
# must_not_auto_promote, loanword_from, reviewer_id, review_date, confidence, notes)
# arabic_equivalent is stored as ASCII-escaped JSON — write_text uses ensure_ascii=False
# so the actual file will contain UTF-8.  No Arabic is ever passed to print().

NEW_ENTRIES: dict[str, dict] = {
    # ------------------------------------------------------------------ #
    # CIVIC INFRASTRUCTURE — ROADS / SAFETY / WATER                      #
    # ------------------------------------------------------------------ #
    "masdoud": {
        "canonical_form": "masdoud",
        "arabic_equivalent": "\u0645\u0633\u062f\u0648\u062f",   # مسدود
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ROADS", "WATER"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["masdoud", "masda", "msdoud", "masdude", "msakkar", "sakker"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'blocked/closed' (adj). tari2 masdoud = road blocked; "
            "biar masdoud = manhole blocked; msakkar/sakker also used. "
            "Corpus: cr=0.42, freq=12."
        ),
    },
    "jisr": {
        "canonical_form": "jisr",
        "arabic_equivalent": "\u062c\u0633\u0631",   # جسر
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ROADS"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["jisr", "jsr", "jusr", "jesir"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'bridge' (noun). jisr meksour = broken bridge; "
            "l jisr sedd = bridge blocked. ROADS infrastructure. Corpus: cr=0.67, freq=6."
        ),
    },
    "3emara": {
        "canonical_form": "3emara",
        "arabic_equivalent": "\u0639\u0645\u0627\u0631\u0629",   # عمارة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "ROADS"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["3emara", "3imara", "3amara", "3mare", "3amaret"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'building' (noun). 3=3ayn digit. "
            "3emara 2adime = old building (structural risk). SAFETY/ROADS. Corpus: cr=0.29, freq=14."
        ),
    },
    "mustashfa": {
        "canonical_form": "mustashfa",
        "arabic_equivalent": "\u0645\u0633\u062a\u0634\u0641\u0649",   # مستشفى
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["mustashfa", "mstashfa", "mostashfa", "moustashfa"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'hospital' (noun). Road-to-hospital blocked; "
            "ambulance access issues. SAFETY sector. Corpus: cr=0.36, freq=25."
        ),
    },
    "sayyara": {
        "canonical_form": "sayyara",
        "arabic_equivalent": "\u0633\u064a\u0627\u0631\u0629",   # سيارة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["ROADS", "SAFETY"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["sayyara", "sayara", "siyara", "sayyaret", "sayyarat"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'car/vehicle' (noun). "
            "Common in road-condition and accident context. Corpus: cr=0.08, freq=39."
        ),
    },
    # ------------------------------------------------------------------ #
    # CIVIC DISCOURSE — GOVERNANCE / RIGHTS / CRISIS                     #
    # ------------------------------------------------------------------ #
    "azme": {
        "canonical_form": "azme",
        "arabic_equivalent": "\u0623\u0632\u0645\u0629",   # أزمة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["azme", "2azme", "azma", "azmet", "2azmet"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'crisis' (noun). hal azme = this crisis; "
            "2azme is Arabizi digit form (2=glottal). Civic discourse noun. Corpus: cr=0.59, freq=22."
        ),
    },
    "fasad": {
        "canonical_form": "fasad",
        "arabic_equivalent": "\u0641\u0633\u0627\u062f",   # فساد
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["fasad", "fased", "fesad", "fasaad"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'corruption' (noun). "
            "Civic accountability / protest context. must_not_auto_promote=true — "
            "needs sector context to avoid false positives. Corpus: cr=0.39, freq=14."
        ),
    },
    "dawle": {
        "canonical_form": "dawle",
        "arabic_equivalent": "\u062f\u0648\u0644\u0629",   # دولة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["dawle", "dawla", "hkoume", "hukume", "hukuma", "douleh"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'government/state' (noun). "
            "l dawle ma btiji = the government doesn't come. "
            "hkoume/hukume are colloquial government variants. "
            "must_not_auto_promote=true. Corpus: cr=0.25, freq=20."
        ),
    },
    "2anoun": {
        "canonical_form": "2anoun",
        "arabic_equivalent": "\u0642\u0627\u0646\u0648\u0646",   # قانون
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["2anoun", "2anun", "qanun", "kanoun", "2anoon"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'law' (noun). 2=glottal stop. "
            "Civic accountability discourse: fi 2anoun? = is there a law? "
            "Corpus: cr=0.20, freq=94."
        ),
    },
    "7o2oq": {
        "canonical_form": "7o2oq",
        "arabic_equivalent": "\u062d\u0642\u0648\u0642",   # حقوق
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["7o2oq", "7u2u2", "7u2ou2", "7a2", "7a22"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'rights' (pl. noun). 7=ح, 2=ق digits. "
            "wein 7o2o2na? = where are our rights? Civic demand context. "
            "Corpus: cr=0.19, freq=29."
        ),
    },
    "7urriye": {
        "canonical_form": "7urriye",
        "arabic_equivalent": "\u062d\u0631\u064a\u0629",   # حرية
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["7urriye", "7urriyye", "7uriye", "7orie"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'freedom' (noun). 7=ح digit. "
            "Protest / civic-rights context. Corpus: cr=0.18, freq=18."
        ),
    },
    "wazara": {
        "canonical_form": "wazara",
        "arabic_equivalent": "\u0648\u0632\u0627\u0631\u0629",   # وزارة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["wazara", "wazare", "wazaret", "wezara"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'ministry' (noun). "
            "Civic accountability: wazaret l ashghal = ministry of public works. "
            "Corpus: cr=0.33, freq=9."
        ),
    },
    "mashroo3": {
        "canonical_form": "mashroo3",
        "arabic_equivalent": "\u0645\u0634\u0631\u0648\u0639",   # مشروع
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["mashroo3", "mashru3", "mashrouA", "mashrou3"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'project/plan' (noun). 3=3ayn digit. "
            "Infrastructure project discourse. Corpus: cr=0.15, freq=27."
        ),
    },
    "7arb": {
        "canonical_form": "7arb",
        "arabic_equivalent": "\u062d\u0631\u0628",   # حرب
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["SAFETY", "ALL"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["7arb", "7arbe", "7rb", "7erb"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'war' (noun). 7=ح digit. "
            "Safety/crisis context. must_not_auto_promote=true. Corpus: cr=0.21, freq=58."
        ),
    },
    "jaysh": {
        "canonical_form": "jaysh",
        "arabic_equivalent": "\u062c\u064a\u0634",   # جيش
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["SAFETY", "ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["jaysh", "jeish", "jesh", "jayche"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'army' (noun). "
            "Civic safety context. must_not_auto_promote=true. Corpus: cr=0.18, freq=12."
        ),
    },
    "ma7kame": {
        "canonical_form": "ma7kame",
        "arabic_equivalent": "\u0645\u062d\u0643\u0645\u0629",   # محكمة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["ma7kame", "ma7kme", "ma7kama"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'court/tribunal' (noun). 7=ح digit. "
            "Civic legal accountability context. Corpus: cr=0.29, freq=7."
        ),
    },
    "mzahara": {
        "canonical_form": "mzahara",
        "arabic_equivalent": "\u0645\u0638\u0627\u0647\u0631\u0629",   # مظاهرة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["mzahara", "mzaahara", "ithtiaj", "2ihtijaj", "i7tijaaj"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'protest/demonstration' (noun). "
            "ithtiaj/2ihtijaj are MSA variants common in Arabizi. "
            "must_not_auto_promote=true. Corpus: cr=0.07, freq=31."
        ),
    },
    # ------------------------------------------------------------------ #
    # INCIDENTS / SAFETY EVENTS                                           #
    # ------------------------------------------------------------------ #
    "7adse": {
        "canonical_form": "7adse",
        "arabic_equivalent": "\u062d\u0627\u062f\u062b\u0629",   # حادثة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "ROADS"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["7adse", "7adise", "7adtha", "7adsa", "7ades"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'incident/accident' (noun). 7=ح digit. "
            "fi 7adse 3al tari2 = there's an accident on the road. "
            "Corpus: cr=0.33, freq=3."
        ),
    },
    "7arr": {
        "canonical_form": "7arr",
        "arabic_equivalent": "\u062d\u0627\u0631",   # حار
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["7arr", "7ar", "sukhn", "sukhne", "sa5n", "sa5ne"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'hot/scorching heat' (adj/noun). 7=ح digit. "
            "Extreme heat safety context; fire adjacency. Corpus: cr=0.19, freq=38."
        ),
    },
    # ------------------------------------------------------------------ #
    # GENERAL CIVIC — DAILY LIFE / DISCOURSE                             #
    # ------------------------------------------------------------------ #
    "ossa": {
        "canonical_form": "ossa",
        "arabic_equivalent": "\u0642\u0635\u0629",   # قصة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ossa", "2esse", "2ossa", "isse", "osset"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'story/situation/issue' (noun). "
            "hal ossa = this situation; ossa ktire = big problem. "
            "Civic discourse. Corpus: cr=0.32, freq=68."
        ),
    },
    "soura": {
        "canonical_form": "soura",
        "arabic_equivalent": "\u0635\u0648\u0631\u0629",   # صورة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["soura", "sura", "soure", "suwar", "sowar", "swar"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'picture/photo' (noun). "
            "Civic reporter: attaching evidence photo to complaint. "
            "suwar = plural. Corpus (photo+picture combined): cr=0.30, freq=229."
        ),
    },
    "shefet": {
        "canonical_form": "shefet",
        "arabic_equivalent": "\u0634\u0641\u062a",   # شفت
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["shefet", "shift", "shfit", "shuft", "shofet", "shooft"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'I saw / I noticed' (verb, 1sg past). "
            "Civic eyewitness marker: shefet hal 7adse = I saw this incident. "
            "Corpus: cr=0.23, freq=31."
        ),
    },
    "mafroud": {
        "canonical_form": "mafroud",
        "arabic_equivalent": "\u0645\u0641\u0631\u0648\u0636",   # مفروض
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["mafroud", "mafruod", "mafrod", "mafroodeh"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'should be / supposed to' (modal). "
            "Civic demand phrasing: mafroud yiji 7ada = someone is supposed to come. "
            "Corpus: cr=0.17, freq=162."
        ),
    },
    "sobe7": {
        "canonical_form": "sobe7",
        "arabic_equivalent": "\u0635\u0628\u062d",   # صبح
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["sobe7", "subeh", "sube7", "sobe7", "sbeh", "sobeh"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'morning' (noun/adverb). "
            "Temporal marker in civic complaints (power off since morning). "
            "Corpus: cr=0.16, freq=235."
        ),
    },
    "lyom": {
        "canonical_form": "lyom",
        "arabic_equivalent": "\u0627\u0644\u064a\u0648\u0645",   # اليوم
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["lyom", "alyom", "el yom", "elyom", "nharda"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'today' (temporal adverb). "
            "lyom = contracted Lebanese 'today'; alyom = MSA form. "
            "Temporal anchor in civic reports. Corpus: cr=0.28, freq=239."
        ),
    },
    "shughel": {
        "canonical_form": "shughel",
        "arabic_equivalent": "\u0634\u063a\u0644",   # شغل
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["shughel", "shghl", "shughl", "shoughel", "shaghel"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'work/job/function' (noun). "
            "Civic utility context: khraba ma 3am tishtaghal = electricity not working. "
            "Corpus: cr=0.23, freq=138."
        ),
    },
    "befham": {
        "canonical_form": "befham",
        "arabic_equivalent": "\u0628\u0641\u0647\u0645",   # بفهم
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["befham", "bfhem", "bfhm", "ma bfhm"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'I understand / I get it' (verb, 1sg). "
            "Used in civic complaint rhetorical questions. Corpus: cr=0.24, freq=38."
        ),
    },
    "ba3rif": {
        "canonical_form": "ba3rif",
        "arabic_equivalent": "\u0628\u0639\u0631\u0641",   # بعرف
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ba3rif", "3arif", "ba3ref", "3aref", "b3rif"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'I know / know' (verb). 3=3ayn digit. "
            "ma ba3rif = I don't know. Discourse marker in complaints. "
            "Corpus: cr=0.17, freq=321."
        ),
    },
    "masari": {
        "canonical_form": "masari",
        "arabic_equivalent": "\u0645\u0635\u0627\u0631\u064a",   # مصاري
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["masari", "msari", "fles", "flis"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'money' (noun). "
            "fles/flis = coins/change (alt. colloquial). "
            "Economic civic context. Corpus: cr=0.17, freq=24."
        ),
    },
    "7obb": {
        "canonical_form": "7obb",
        "arabic_equivalent": "\u062d\u0628",   # حب
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["7obb", "7ubb", "bheb", "b7eb", "7ob"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'love / like' (noun/verb). 7=ح digit. "
            "High-freq discourse in civic social media. Corpus: cr=0.11, freq=944."
        ),
    },
    "7ayat": {
        "canonical_form": "7ayat",
        "arabic_equivalent": "\u062d\u064a\u0627\u0629",   # حياة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["7ayat", "7aye", "7yat", "7yeh", "hayat"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'life' (noun). 7=ح digit. "
            "Civic discourse: 7ayatna saret sab3a = our life has become difficult. "
            "Corpus: cr=0.14, freq=302."
        ),
    },
    "mdine": {
        "canonical_form": "mdine",
        "arabic_equivalent": "\u0645\u062f\u064a\u0646\u0629",   # مدينة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["mdine", "madine", "madina", "medine", "mdeneh"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'city' (noun). "
            "Location reference in civic complaints. Corpus: cr=0.13, freq=62."
        ),
    },
    "ta3a": {
        "canonical_form": "ta3a",
        "arabic_equivalent": "\u062a\u0639\u0627",   # تعا
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["ta3a", "ta3i", "t3a", "ta3aw"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'come! / come here' (verb, imperative). 3=3ayn digit. "
            "Civic urgency: ta3a shouf = come and see. Corpus: cr=0.14, freq=126."
        ),
    },
    "day3a": {
        "canonical_form": "day3a",
        "arabic_equivalent": "\u0636\u064a\u0639\u0629",   # ضيعة
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["day3a", "day3e", "belde", "belda", "dayi3"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'village/town' (noun). 3=3ayn digit. "
            "belde/belda = district. Location in civic complaints. Corpus: cr=0.12, freq=17."
        ),
    },
    # ------------------------------------------------------------------ #
    # WEATHER DOMAIN                                                       #
    # ------------------------------------------------------------------ #
    "7arara": {
        "canonical_form": "7arara",
        "arabic_equivalent": "\u062d\u0631\u0627\u0631\u0629",   # حرارة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["7arara", "7ararit", "7arareh", "7ararti", "darajt l7arara"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'temperature/heat' (noun). 7=ح digit. "
            "darajt l7arara = the temperature degree. "
            "Civic safety: extreme-heat warnings, fire conditions. Corpus: cr=0.43, freq=86."
        ),
    },
    "rotobe": {
        "canonical_form": "rotobe",
        "arabic_equivalent": "\u0631\u0637\u0648\u0628\u0629",   # رطوبة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "FLOODING"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["rotobe", "rtube", "rotoba", "rtoobe", "rutube"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'humidity' (noun). "
            "rotobe 3aliye = high humidity. Structural damp / flooding context. "
            "Corpus: cr=0.38, freq=139."
        ),
    },
    "riye7": {
        "canonical_form": "riye7",
        "arabic_equivalent": "\u0631\u064a\u062d",   # ريح
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "FLOODING"],
        "severity_relevance": ["MEDIUM", "HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["riye7", "riyah", "rye7", "reh", "hawa", "riyeh"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'wind' (noun). 7=ح digit. "
            "riye7 2awiye = strong wind. hawa = colloquial variant. "
            "SAFETY/FLOODING trigger: wind damage, flooding. Corpus: cr=0.35, freq=153."
        ),
    },
    "3aasfe": {
        "canonical_form": "3aasfe",
        "arabic_equivalent": "\u0639\u0627\u0635\u0641\u0629",   # عاصفة
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "FLOODING"],
        "severity_relevance": ["HIGH"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["3aasfe", "3asfe", "3asifa", "3asifeh", "3awasif"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'storm/gale' (noun). 3=3ayn digit. "
            "3aasfe jayye = storm coming. SAFETY/FLOODING trigger. "
            "Corpus note: cr=0.0 (weather-account tweets; word is genuine). freq=12."
        ),
    },
    "8ayem": {
        "canonical_form": "8ayem",
        "arabic_equivalent": "\u063a\u064a\u0645",   # غيم
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "FLOODING"],
        "severity_relevance": ["LOW", "MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "true",
        "loanword_from": None,
        "variant_forms": ["8ayem", "8ayme", "3im", "ghaym", "ghayim", "ghyem"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese Arabizi: 'cloudy' (adj). 8=غ digit. "
            "Flooding precursor. 3im is alt digit rendering. "
            "must_not_auto_promote=true — weather-account-heavy signal. Corpus: cr=0.41, freq=85."
        ),
    },
    "shamse": {
        "canonical_form": "shamse",
        "arabic_equivalent": "\u0634\u0645\u0633",   # شمس
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["shamse", "shams", "mshammas", "mshammes"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'sun/sunny' (noun/adj). "
            "mshammas = sunny (adj form). Weather context. Corpus: cr=0.62, freq=23."
        ),
    },
    "dabab": {
        "canonical_form": "dabab",
        "arabic_equivalent": "\u0636\u0628\u0627\u0628",   # ضباب
        "semantic_type": "T2_SECTOR_SUPPORT",
        "sector_relevance": ["SAFETY", "ROADS"],
        "severity_relevance": ["MEDIUM"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["dabab", "7abab", "dababe", "dababeh"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "HIGH",
        "notes": (
            "Lebanese Arabizi: 'fog' (noun). "
            "7abab is variant (7=ح). SAFETY/ROADS: fog reduces visibility. "
            "Corpus: cr=0.25, freq=4."
        ),
    },
    "mfarre2": {
        "canonical_form": "mfarre2",
        "arabic_equivalent": "\u0645\u0641\u0631\u0642",   # مفرق
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["mfarre2", "mfarra2", "mfarea", "mfarek"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese Arabizi: 'scattered/spread out/dispersed' (adj). 2=glottal digit. "
            "Weather: rain scattered; civic: scattered damage. Corpus: cr=1.0, freq=6."
        ),
    },
    "tawa2o3": {
        "canonical_form": "tawa2o3",
        "arabic_equivalent": "\u062a\u0648\u0642\u0639",   # توقع
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["ALL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": ["tawa2o3", "taqaqqo3", "tawa2u3", "tawaqo3"],
        "reviewer_id": REVIEWER_ID,
        "review_date": REVIEW_DATE,
        "confidence": "MEDIUM",
        "notes": (
            "Lebanese Arabizi: 'forecast/prediction' (noun). 2=glottal, 3=3ayn digits. "
            "taqaqqo3 = anticipation variant. Weather forecast context. Corpus: cr=1.0, freq=36."
        ),
    },
}

# --------------------------------------------------------------------------- #
# VARIANT FORM PATCHES — add new forms to existing term_metadata entries      #
# --------------------------------------------------------------------------- #
# key = canonical term_metadata key, value = list of new variant_forms to add
VARIANT_PATCHES: dict[str, list[str]] = {
    # matar (rain variants) — existing entry lacks mtar/2amtar directly
    "matar": ["mtar", "2amtar", "amtar", "mtara", "shita", "shta"],
    # kahrabe (electricity) — kehraba/kahrabeh are OOV spellings
    "kahrabe": ["kehraba", "kahrabeh", "kharbaa", "kahrbe"],
    # sene (year) — sneh is OOV phonetic variant
    "sene": ["sneh", "snit"],
    # jdide (new) — jdid (without fem ending) is OOV
    "jdide": ["jdid", "jdeed"],
    # tarik (road) — turuk/trouk are OOV plural forms
    "tarik": ["turuk", "trouk", "trok"],
    # lama (when) — lma/ama are shortened variants found OOV
    "lama": ["lma", "ama", "amma"],
}

# --------------------------------------------------------------------------- #
# CHANGELOG entry                                                              #
# --------------------------------------------------------------------------- #
CHANGELOG_ENTRY = (
    f"{NEW_VERSION} (2026-05-22): V20b comprehensive OOV absorption — "
    f"{len(NEW_ENTRIES)} new term_metadata entries (civic infrastructure, weather, "
    f"governance, discourse) + 6 variant-form patches. "
    f"Reviewer: {REVIEWER_ID}."
)


# --------------------------------------------------------------------------- #
# SAFETY CHECKS                                                                #
# --------------------------------------------------------------------------- #

def _check_no_high_risk_collision(entries: dict) -> None:
    """Abort if any new entry's canonical key or variant_forms collides with HIGH_RISK_HINTS."""
    for key, data in entries.items():
        if key in HIGH_RISK_HINTS:
            raise ValueError(f"SAFETY: canonical key '{key}' is in HIGH_RISK_HINTS — aborting.")
        for v in data.get("variant_forms", []):
            norm = v.lower().strip()
            if norm in HIGH_RISK_HINTS:
                raise ValueError(
                    f"SAFETY: variant_form '{v}' in entry '{key}' is HIGH_RISK_HINT — aborting."
                )


def _check_no_kasaret(entries: dict) -> None:
    if "kasaret" in entries:
        raise ValueError("SAFETY: 'kasaret' is DEFERRED_BATCH_002 — must not be added in V20b.")


# --------------------------------------------------------------------------- #
# CORE LOGIC                                                                   #
# --------------------------------------------------------------------------- #

def apply_v20b(vocab: dict, now_str: str, dry_run: bool) -> tuple[int, int]:
    """
    Mutate vocab in-place (if not dry_run).
    Returns (new_entries_added, patches_applied).
    """
    _check_no_high_risk_collision(NEW_ENTRIES)
    _check_no_kasaret(NEW_ENTRIES)

    tm = vocab.setdefault("term_metadata", {})
    added = 0
    patched_forms = 0

    # --- (1) Add new entries ---
    for key, data in NEW_ENTRIES.items():
        if key in tm:
            print(f"  [SKIP-EXISTS]  '{key}' already present in term_metadata")
            continue
        # Stamp added_at
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

    # --- (2) Apply variant-form patches to existing entries ---
    for canonical_key, new_forms in VARIANT_PATCHES.items():
        if canonical_key not in tm:
            print(f"  [PATCH-MISS]  '{canonical_key}' not found in term_metadata — skipping patch")
            continue
        existing = set(tm[canonical_key].get("variant_forms", []))
        to_add = [f for f in new_forms if f not in existing]
        if not to_add:
            print(f"  [PATCH-SKIP]  '{canonical_key}' — all variant_forms already present")
            continue
        if not dry_run:
            tm[canonical_key]["variant_forms"] = sorted(
                existing | set(to_add), key=lambda x: x.lower()
            )
        patched_forms += len(to_add)
        print(f"  [PATCH]  '{canonical_key}' += {to_add}")

    return added, patched_forms


def run(dry_run: bool) -> None:
    NOW = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # NO COLONS

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}apply_oov_v20b  target={VOCAB_PATH}")

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
            f"  WARNING: expected version {CURRENT_VERSION}, found {current_version}. "
            "Proceeding anyway — verify result."
        )

    # Backup (real run only)
    if not dry_run:
        bak_path = VOCAB_PATH.with_suffix(f".{NOW}.bak.json")
        shutil.copy2(VOCAB_PATH, bak_path)
        print(f"  Backup saved    : {bak_path.name}")

    added, patched_forms = apply_v20b(vocab, NOW, dry_run)

    # Update version + prepend changelog
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
    parser = argparse.ArgumentParser(description="Apply V20b OOV absorption to arabizi_vocabulary.json")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing files")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

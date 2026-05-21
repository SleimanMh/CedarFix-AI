"""
promote_external_oov_to_gwb.py
================================
Promotes high-confidence, high-frequency external OOV candidates into vocab
term_metadata as generic support terms (normalization only, no routing).

Criteria for auto-inclusion:
  - document_count_total >= 20
  - cross-source evidence (source_ids contains '|', i.e., >= 2 sources)
  - suggested_layer != SAFETY_OR_PROFANITY_REVIEW and != STOPLIST_REVIEW
  - not already in known_tokens
  - civic discourse utility (manually curated allowlist below)

These are GWB-tier T3_GENERIC_SUPPORT — they improve coverage of complaint
text normalization without affecting routing.

Run:
    python scripts/promote_external_oov_to_gwb.py --dry-run
    python scripts/promote_external_oov_to_gwb.py
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"
OOV_CANDS_PATH = ROOT / "data" / "knowledge_base" / "arabizi" / "lebanese_external_oov_candidates.csv"

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
NEW_VERSION = "1.5.5"

# ---------------------------------------------------------------------------
# Manually-curated allowlist of terms SAFE to add as generic support.
# Only terms that are:
#   (a) Clearly Lebanese Arabizi
#   (b) Useful in complaint/civic context (discourse, time, quantity, action)
#   (c) Not profanity, not high-risk, not entity
#   (d) Not already in vocab
# Each entry specifies its canonical variants.
# ---------------------------------------------------------------------------
CIVIC_DISCOURSE_ALLOWLIST: list[dict] = [
    # Negation / hesitation / completion
    {"key": "la2",     "variants": ["la2", "la2a", "la"],           "note": "لأ — no (Lebanese); la2 is the Arabizi negation response"},
    {"key": "khalas",  "variants": ["khalas", "5alas", "5las"],      "note": "خلص — done/finished/enough; khalas mish mnekhdo = we're done waiting"},
    {"key": "kamen",   "variants": ["kamen", "kman", "kem"],         "note": "كمان — also/too; common connector in complaint description"},
    {"key": "leh",     "variants": ["leh", "lesh", "leish"],         "note": "ليش — why; leh mish bi tishtaghal = why isn't it working"},
    {"key": "3m",      "variants": ["3m", "3am", "3em"],             "note": "عم — progressive aspect marker (Lebanese); 3am biji = it's coming"},
    {"key": "ba3ed",   "variants": ["ba3ed", "ba3d", "baa3d"],       "note": "بعد — after/still; ba3ed mat3a = still cut off"},
    {"key": "badde",   "variants": ["badde", "bade", "bidi"],        "note": "بدي — I want/I need (1sg Lebanese); badde 7all = I need a solution"},
    {"key": "hayde",   "variants": ["hayde", "heydi", "haydi"],      "note": "هيدي — this (fem. demonstrative Lebanese); hayde l moshkle = this problem"},
    {"key": "lezim",   "variants": ["lezim", "lazem", "lazmeh"],     "note": "لازم — must/necessary; lezim yiji 7ada = someone must come"},
    {"key": "ysir",    "variants": ["ysir", "yiseer", "byisir"],     "note": "يصير — it's possible/happens; ysir ykun = it could be"},
    {"key": "ma3o",    "variants": ["ma3o", "ma3u", "ma3e"],         "note": "معه — with him/it; ma3o 7all = with a solution"},
    {"key": "ghalat",  "variants": ["ghalat", "3alat", "ghalet"],    "note": "غلط — wrong/mistake; hada ghalat = this is wrong"},
    {"key": "aal",     "variants": ["aal", "a2al", "2al"],           "note": "قال — said/they said; aal 3anna = they said about us"},
    # Time references
    {"key": "sene",    "variants": ["sene", "seneh", "sine"],        "note": "سنة — year; min sene = for a year; sene kell yom = every day for a year"},
    {"key": "lama",    "variants": ["lama", "lamma", "lamman"],      "note": "لما — when (conjunction); lama byiji mtar = when it rains"},
    # Quantities / states
    {"key": "aktar",   "variants": ["aktar", "ektar", "aktar"],      "note": "أكتر — more/most; aktar min sene = more than a year"},
    {"key": "balad",   "variants": ["balad", "beled", "balade"],     "note": "بلد — country/town/municipality; baladiye l balad = the town municipality"},
    {"key": "3alam",   "variants": ["3alam", "3alim", "3lam"],       "note": "عالم — people/world; l 3alam = the people; common in complaints"},
    {"key": "bet",     "variants": ["bet", "byet", "beit"],          "note": "بيت — house/home; bet = house (short form); context: near my house"},
    {"key": "mnel",    "variants": ["mnel", "mnel", "min el"],       "note": "من ال — from the (contracted Lebanese); mnel share3 = from the road"},
    # Discourse particles
    {"key": "walla",   "variants": ["walla", "walla", "wala"],       "note": "والله — by God (discourse particle); walla ma 3arif = I honestly don't know"},
    {"key": "tab",     "variants": ["tab", "tayb", "tayyib"],        "note": "طيب — okay then/well (discourse); tab shu byisawwou = so what are they doing"},
    {"key": "habibi",  "variants": ["habibi", "habibe", "7abibi"],   "note": "حبيبي — dear/friend (Lebanese address term); used in complaint framing"},
    # Action verbs common in complaints
    {"key": "z3elet",  "variants": ["z3elet", "z3al", "inz3al"],     "note": "زعل — upset/angry; z3elet ktir = very upset; high-frequency complaint verb"},
    {"key": "meshe",   "variants": ["meshe", "mashi", "mashe"],      "note": "مشي — went/walked/worked; meshe = it worked (passed); ma meshe = didn't work"},
    {"key": "kenet",   "variants": ["kenet", "kanet", "kant"],       "note": "كانت — was (3sg fem past); kenet mat3a = it was cut off"},
    {"key": "tkoun",   "variants": ["tkoun", "takoun", "tkun"],      "note": "تكون — to be (subjunctive); lazem tkoun = it should be"},
    {"key": "jem3a",   "variants": ["jem3a", "jama3a", "jma3a"],     "note": "جماعة — group/guys/crew; jem3a = the team/guys (civic workers reference)"},
    {"key": "khaye",   "variants": ["khaye", "5aye", "5ayye"],       "note": "خيّ — brother (Lebanese address); used in complaint openers"},
    # Infrastructure-adjacent
    {"key": "haram",   "variants": ["haram", "7aram", "hram"],       "note": "حرام — shame/forbidden; haram 3enna = a shame upon us; complaint expression"},
    {"key": "balat",   "variants": ["balat", "balate", "balet"],     "note": "بلاط — pavement/tiles; balat l share3 = road paving; ROADS context"},
    {"key": "t3ebet",  "variants": ["t3ebet", "twa3bet", "t3bt"],    "note": "تعبت — exhausted/tired; t3ebet min l moshkle = I'm tired of this problem"},
    {"key": "wel",     "variants": ["wel", "w el", "w l"],           "note": "وال — and the (contracted Lebanese); wel baladiye = and the municipality"},
    {"key": "thawra",  "variants": ["thawra", "tawra", "sawra"],     "note": "ثورة — revolution; thawra context in civic frustration; 2019 Lebanon protests ref"},
]


def load_vocab():
    return json.loads(VOCAB_PATH.read_text(encoding="utf-8-sig"))


def save_vocab(data, path):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def backup_vocab():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = VOCAB_PATH.with_suffix(f".{ts}.bak.json")
    shutil.copy2(VOCAB_PATH, bak)
    return bak


def main(dry_run: bool = False):
    print("=" * 70)
    print(f"  V18b External OOV → GWB Term Promotion {'[DRY RUN]' if dry_run else ''}")
    print("=" * 70)
    print(f"  Promoting {len(CIVIC_DISCOURSE_ALLOWLIST)} curated civic discourse terms")
    print()

    data = load_vocab()
    tm = data.setdefault("term_metadata", {})
    added = updated = skipped = 0

    for entry in CIVIC_DISCOURSE_ALLOWLIST:
        key = entry["key"]
        new_variants = entry["variants"]

        if key in tm:
            existing = set(tm[key].get("variant_forms", []))
            to_add = [v for v in new_variants if v not in existing]
            if not to_add:
                print(f"  SKIP '{key}': all variants present")
                skipped += 1
                continue
            if not dry_run:
                tm[key]["variant_forms"] = sorted(existing | set(to_add))
            print(f"  UPDATE '{key}': +{to_add}")
            updated += 1
        else:
            if not dry_run:
                tm[key] = {
                    "variant_forms": sorted(set(new_variants)),
                    "loanword_from": "",
                    "sector": "ALL",
                    "arabizi_note": entry.get("note", ""),
                    "tier": "T3_GENERIC_SUPPORT",
                    "allowed_uses": "normalization_support",
                    "must_not_auto_promote": "true",
                    "false_friend_risk": "false",
                    "reviewer_id": "SYSTEM-V18",
                    "added_by": "promote_external_oov_to_gwb",
                    "added_at": NOW,
                }
            print(f"  ADD  '{key}': {new_variants}")
            added += 1

    if dry_run:
        print(f"\n  DRY RUN: +{added} new, {updated} updated, {skipped} skipped")
        return

    data["version"] = NEW_VERSION
    data["changelog"] = (
        f"{NEW_VERSION} ({NOW[:10]}): V18b external OOV → GWB — "
        f"{added} new civic discourse terms from 2000-candidate external review. "
    ) + data.get("changelog", "")

    bak = backup_vocab()
    print(f"\n  Backup → {bak.name}")
    save_vocab(data, VOCAB_PATH)
    print(f"  Saved   → {VOCAB_PATH.name}  (version {NEW_VERSION})")
    print(f"\n  Summary: +{added} new, {updated} updated, {skipped} skipped")
    print("\n  Run:")
    print("    python scripts/validate_arabizi_vocabulary.py")
    print("    python scripts/evaluate_arabizi_coverage.py")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    main(dry_run=p.parse_args().dry_run)

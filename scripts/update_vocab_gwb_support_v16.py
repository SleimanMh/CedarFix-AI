"""
update_vocab_gwb_support_v16.py
================================
Syncs V16 GWB generic-support entries into arabizi_vocabulary.json
term_metadata.  These additions are NON-ROUTING: they extend known_tokens
for OOV coverage without touching sector routing or issue_type_keywords.

This is the correct path for GWB T3_GENERIC_SUPPORT terms:
  blocked_uses: routing|severity_assignment|sector_classification|issue_type_decision
  allowed_uses: normalization_support|stopword_filtering|oov_precision

Run:
    python scripts/update_vocab_gwb_support_v16.py

Or dry-run:
    python scripts/update_vocab_gwb_support_v16.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"
VALIDATE_SCRIPT = ROOT / "scripts" / "validate_arabizi_vocabulary.py"

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
NEW_VERSION = "1.5.2"

# ---------------------------------------------------------------------------
# GWB V16 support-term updates for term_metadata
# Each entry: (term_key, variant_forms, loanword_from, sector, arabizi_note)
#
# RULES:
#   - term appears in term_metadata keyed by romanized_canonical
#   - variant_forms → ALL end up in known_tokens (no routing)
#   - loanword_from → term key itself ends up in loanword_tokens
#   - sector → informational only (not used by load_vocabulary_index routing)
# ---------------------------------------------------------------------------

# Terms to UPDATE (already exist in term_metadata — add missing variants)
UPDATES = {
    "mayye": {
        "variant_forms_add": ["miye", "miyeh", "miyye", "miyyeh"],
        "note": "miye is the Lebanese dialectal form for ميّه (water); "
                "false_friend: miye=100 (مية) in formal Arabic; "
                "miye mat3a = water is cut (WATER/WATER_CUT status phrase); "
                "must not route on miye alone",
    },
    "ta7dir": {
        "variant_forms_add": ["ta7zir", "ta7deer"],
        "note": "warning/caution (تحذير); isharet ta7dir = warning signs; "
                "ROADS/FLOODING support term",
    },
    "nkesh": {
        "variant_forms_add": ["ankesh", "inkesh", "nkaash", "2inkesh"],
        "note": "إنكاش — inert construction/demolition debris; "
                "WASTE/ILLEGAL_DUMP routing candidate in CB",
    },
}

# Terms to ADD (new term_metadata entries)
NEW_ENTRIES = [
    # Status words
    {
        "key": "mat3a",
        "variant_forms": ["mat3a", "mta3a", "mat3et", "mta3et", "mat3"],
        "loanword_from": "",
        "sector": "WATER,ELECTRICITY",
        "arabizi_note": "مقطوعة — feminine adj. for cut-off/absent; "
                        "kahraba mat3a=power cut, miye mat3a=water cut; "
                        "protected phrase combos in PC; do not route mat3a alone",
    },
    # Verbs — general/reporting
    {
        "key": "byiji",
        "variant_forms": ["byiji", "byije", "biji", "bije", "yiji"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "بيجي — 3sg masc present 'comes/will come'; "
                        "ma 7ada byiji = nobody comes; complaint discourse verb",
    },
    {
        "key": "t2a3",
        "variant_forms": ["t2a3", "tou2a3", "twa2a3", "bi t2a3"],
        "loanword_from": "",
        "sector": "ROADS",
        "arabizi_note": "تقع — falls/drops; bi terji3 t2a3 = keeps falling in (pothole); "
                        "2=ء emphatic qaf; ROADS pothole damage signal",
    },
    {
        "key": "terji3",
        "variant_forms": ["terji3", "tirja3", "terja3", "trja3", "yirja3"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "ترجع — returns/goes back; bi terji3 t2a3 = comes back and falls in; "
                        "recurring issue discourse marker",
    },
    {
        "key": "titrakam",
        "variant_forms": ["titrakam", "yitrakam", "titrakm", "3am titrakam"],
        "loanword_from": "",
        "sector": "WASTE,FLOODING",
        "arabizi_note": "تتراكم — accumulates/piles up; zbele 3am titrakam = "
                        "garbage accumulating; used for WASTE and FLOODING buildup",
    },
    {
        "key": "tirfa3",
        "variant_forms": ["tirfa3", "byirfa3", "bitrfa3", "3am tirfa3"],
        "loanword_from": "",
        "sector": "FLOODING,WATER",
        "arabizi_note": "ترفع — rises/goes up; miye 3am tirfa3 = water is rising; "
                        "FLOODING support when paired with water vocab",
    },
    {
        "key": "yishtikou",
        "variant_forms": ["yishtikou", "bishtiku", "byishtikou", "yshtiku"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "يشتكوا — 3pl present 'they complain'; l nas killon yishtikou = "
                        "all the people are complaining; complaint discourse marker",
    },
    # Time expressions
    {
        "key": "imbere7",
        "variant_forms": ["imbere7", "imbari7", "embere7"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "إمبارح — yesterday (Lebanese); uniquely Lebanese/Levantine "
                        "colloquial (cf. formal Arabic ams); 7=ح",
    },
    {
        "key": "ghayet",
        "variant_forms": ["ghayet", "ghayit", "ghayeh"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "غاية — extreme/for so long; ghayet min l zaman = for way too long; "
                        "Lebanese degree/duration idiom in complaint discourse",
    },
    {
        "key": "zaman",
        "variant_forms": ["zaman", "zamman", "zameen"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "زمان — a long time; men zaman = for a long time/since forever; "
                        "common unresolved-issue discourse marker",
    },
    # Nouns — civic / general
    {
        "key": "masoul",
        "variant_forms": ["masoul", "mas2oul", "mass2oul"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "مسؤول — official/responsible person; l masoul ma bada yiji = "
                        "the official won't come; civic complaint actor",
    },
    {
        "key": "jawab",
        "variant_forms": ["jawab", "jaweb", "joab", "jwaab"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "جواب — answer/official response; ma fi jawab = no response; "
                        "civic complaint discourse noun",
    },
    {
        "key": "killon",
        "variant_forms": ["killon", "killoun", "kllon"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "كلّون — all of them (Lebanese plural); l nas killon = all the people; "
                        "Lebanese quantifier",
    },
    # Location words
    {
        "key": "7aret",
        "variant_forms": ["7aret", "7ara", "7aara"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "حارة — alley/sub-neighbourhood; sub-district location term; "
                        "7=ح correct Arabizi encoding",
    },
    {
        "key": "tarik",
        "variant_forms": ["tarik", "tire2"],
        "loanword_from": "",
        "sector": "ROADS",
        "arabizi_note": "طريق — road (variant); tire2 uses 2=ء for emphatic qaf; "
                        "tari2 is in CB for routing; tarik here is recognition support only",
    },
    {
        "key": "khandaq",
        "variant_forms": ["khandaq", "5andaq", "khandek", "khandak"],
        "loanword_from": "",
        "sector": "ROADS,SAFETY",
        "arabizi_note": "خندق — ditch/trench; also part of neighbourhood name "
                        "'el khandaq el ghamik' (PC-0118); "
                        "5=خ alternative Arabizi encoding",
    },
    {
        "key": "mokhzen",
        "variant_forms": ["mokhzen", "makhzan", "makhzen"],
        "loanword_from": "",
        "sector": "SAFETY",
        "arabizi_note": "مخزن — warehouse/storage building; SAFETY context when "
                        "fire or hazardous; 5=خ in 5andaq etc.",
    },
    {
        "key": "jdide",
        "variant_forms": ["jdide", "jdidi", "jdeed", "jdeedeh"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "جديدة — new (fem. adj.); hay el jdide is also a Beirut district name; "
                        "variant of jdid",
    },
    {
        "key": "ghamik",
        "variant_forms": ["ghamik", "ghamek", "ghamok"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "غامق — deep/dark adj.; appears in 'el khandaq el ghamik' "
                        "(Beirut neighbourhood) — see PC-0118 for full location combo",
    },
    # Code-switch terms
    {
        "key": "jours",
        "variant_forms": ["jours", "jour"],
        "loanword_from": "fr",
        "sector": "ALL",
        "arabizi_note": "French 'day(s)'; standard Lebanese French code-switch; "
                        "depuis 3 jours = for 3 days",
    },
    {
        "key": "route",
        "variant_forms": ["route"],
        "loanword_from": "fr",
        "sector": "ROADS",
        "arabizi_note": "French 'road'; route completement abimee = road completely "
                        "damaged; French code-switch for ROADS reports",
    },
    {
        "key": "schedule",
        "variant_forms": ["schedule", "chidoul"],
        "loanword_from": "en",
        "sector": "ELECTRICITY",
        "arabizi_note": "English 'schedule'; schedule l kahraba = power cut schedule; "
                        "common English code-switch for EDL electricity schedules",
    },
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


def main(dry_run=False):
    print("=" * 70)
    print(f"  V16 Vocab GWB Support Sync  {'[DRY RUN]' if dry_run else ''}")
    print("=" * 70)

    data = load_vocab()
    tm = data.setdefault("term_metadata", {})
    added, updated, skipped = 0, 0, 0

    # -- Apply updates to existing term_metadata entries --------------------
    for term_key, upd in UPDATES.items():
        if term_key not in tm:
            print(f"  WARN: cannot update '{term_key}' — not in term_metadata")
            continue
        entry = tm[term_key]
        existing_variants = entry.get("variant_forms", [])
        new_forms = [v for v in upd["variant_forms_add"] if v not in existing_variants]
        if not new_forms:
            print(f"  SKIP update '{term_key}' — all variants already present")
            skipped += 1
            continue
        if not dry_run:
            entry["variant_forms"] = sorted(set(existing_variants) | set(new_forms))
            # update note if provided
            if entry.get("arabizi_note") and upd.get("note"):
                entry["arabizi_note"] = upd["note"]
        print(f"  UPDATE '{term_key}': +{new_forms}")
        updated += 1

    # -- Add new term_metadata entries -------------------------------------
    for entry_def in NEW_ENTRIES:
        key = entry_def["key"]
        if key in tm:
            # Already exists — check for missing variants
            existing_vf = tm[key].get("variant_forms", [])
            new_vf = [v for v in entry_def["variant_forms"] if v not in existing_vf]
            if new_vf:
                if not dry_run:
                    tm[key]["variant_forms"] = sorted(set(existing_vf) | set(new_vf))
                print(f"  UPDATE '{key}' (existing): +variants {new_vf}")
                updated += 1
            else:
                print(f"  SKIP '{key}' — already in term_metadata with all variants")
                skipped += 1
            continue

        if not dry_run:
            tm[key] = {
                "variant_forms": entry_def["variant_forms"],
                "loanword_from": entry_def.get("loanword_from", ""),
                "sector":        entry_def.get("sector", "ALL"),
                "arabizi_note":  entry_def.get("arabizi_note", ""),
                "added_by":      "update_vocab_gwb_support_v16",
                "added_at":      NOW,
            }
        print(f"  ADD  '{key}': variants={entry_def['variant_forms'][:3]}...")
        added += 1

    # -- Bump version -------------------------------------------------------
    if not dry_run:
        old_version = data.get("version", "?")
        data["version"] = NEW_VERSION
        changelog = data.get("changelog", "")
        data["changelog"] = (
            f"{NEW_VERSION} ({NOW[:10]}): V16 GWB support sync — "
            f"{added} new, {updated} updated term_metadata entries. "
            f"Key additions: miye (water variant, freq=9 in B001), "
            f"mat3a (cut-off status), {len(NEW_ENTRIES)} generic support terms. "
            f"Previous: {old_version}. "
            + changelog
        )

    if dry_run:
        print(f"\n  DRY RUN summary: +{added} add, {updated} update, {skipped} skip")
        print("  (no files written)")
        return

    # -- Write backup + save ------------------------------------------------
    bak = backup_vocab()
    print(f"\n  Backup → {bak.name}")
    save_vocab(data, VOCAB_PATH)
    print(f"  Saved   → {VOCAB_PATH.name}  (version {NEW_VERSION})")
    print(f"\n  Summary: +{added} new entries, {updated} updated, {skipped} skipped")
    print("\n  Run validator:")
    print("    python scripts/validate_arabizi_vocabulary.py")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = p.parse_args()
    main(dry_run=args.dry_run)

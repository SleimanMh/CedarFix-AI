"""
update_vocab_gwb_support_v17_oov_patch.py
==========================================
Targeted patch for OOV tokens still unresolved after V16.

Source: arabizi_coverage_batch001.json per_row_details, rows with oov >= 2

Remaining OOV tokens addressed:
  ROADS:      tire, 3jelatna, armeniye, abimee, completement, sursok
  ELECTRICITY: 3la, app, makdissi, arc, jeanne, masliye
  WASTE:       khafer, bada, bala, fil, haje, nahr
  SKIPPED:     kasaret (NEVER_PROMOTE guardrail), 20h (timestamp token), sin (artifact)

Run:
    python scripts/update_vocab_gwb_support_v17_oov_patch.py --dry-run
    python scripts/update_vocab_gwb_support_v17_oov_patch.py
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

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
NEW_VERSION = "1.5.3"

# ---------------------------------------------------------------------------
# Terms to UPDATE (extend existing term_metadata variant_forms)
# ---------------------------------------------------------------------------
UPDATES = {
    "tarik": {
        "variant_forms_add": ["tire"],
        "note": "tire is a shortened Lebanese form of tire2/tari2 (طريق); "
                "e.g. 'l tire mt2a3et' = the road is blocked",
    },
}

# ---------------------------------------------------------------------------
# Terms to ADD
# ---------------------------------------------------------------------------
NEW_ENTRIES = [
    # --- ROADS ---
    {
        "key": "3jelet",
        "variant_forms": ["3jelet", "3jelatna", "3jalo", "3jalt", "3jeltak"],
        "loanword_from": "",
        "sector": "ROADS",
        "arabizi_note": "عجلة/عجلتنا — wheel(s); 3jelatna = our wheels; "
                        "common in ROADS reports about damage to vehicles from potholes",
    },
    {
        "key": "sursok",
        "variant_forms": ["sursok", "sursuk", "sarsok"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "سرسق — Sursok: Beirut neighbourhood/street name; "
                        "appears in PC-0112 (share3 sursok); "
                        "standalone token also needs to be known",
    },
    {
        "key": "armeniye",
        "variant_forms": ["armeniye", "armeniyi", "armeni"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "الأرمن/الأرمنية — Armenian quarter reference; "
                        "Beirut street name in PC-0113 (share3 armeniye); "
                        "standalone token also needs to be known",
    },
    {
        "key": "abimee",
        "variant_forms": ["abimee", "abime", "abimee", "abimeh"],
        "loanword_from": "fr",
        "sector": "ROADS",
        "arabizi_note": "French 'abîmée' — damaged/destroyed (fem.); "
                        "route completement abimee = road completely destroyed; "
                        "French code-switch in ROADS reports",
    },
    {
        "key": "completement",
        "variant_forms": ["completement", "totalement", "entierement"],
        "loanword_from": "fr",
        "sector": "ROADS",
        "arabizi_note": "French 'complètement' — completely; "
                        "route completement abimee = road completely destroyed; "
                        "French intensifier code-switch",
    },
    # --- ELECTRICITY ---
    {
        "key": "3la",
        "variant_forms": ["3la", "3ala", "3al"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "على — on/at/to (Lebanese colloquial prep); "
                        "3la (no internal vowel) is a common condensed form; "
                        "3ala and 3al are more common but 3la is unregistered",
    },
    {
        "key": "app",
        "variant_forms": ["app", "application", "appli"],
        "loanword_from": "en",
        "sector": "ALL",
        "arabizi_note": "English 'app' — mobile application; "
                        "common in Lebanese civic tech complaints; "
                        "app EDL = EDL app, app l baladiye = municipality app",
    },
    {
        "key": "makdissi",
        "variant_forms": ["makdissi", "maqdessy", "makdessy"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "مقدسي — Makdissi: Beirut street name in Hamra; "
                        "appears in PC-0114 (share3 makdissi); "
                        "standalone token also needs to be known",
    },
    {
        "key": "arc",
        "variant_forms": ["arc", "arc electrique", "arc_electrique"],
        "loanword_from": "fr",
        "sector": "ELECTRICITY",
        "arabizi_note": "French 'arc électrique' — electric arc/flashover; "
                        "arc 3al transformer = arc on transformer; "
                        "ELECTRICITY safety signal",
    },
    {
        "key": "jeanne",
        "variant_forms": ["jeanne", "jeanne d arc"],
        "loanword_from": "fr",
        "sector": "ALL",
        "arabizi_note": "Jeanne — part of 'share3 jeanne d arc' (Rue Jeanne d'Arc); "
                        "Beirut street name in Hamra area (PC-0115); "
                        "French loanword for the street proper name",
    },
    {
        "key": "masliye",
        "variant_forms": ["masliye", "masliyi", "maslieh"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "المصيلحية — Maslieh: Beirut/Hamra area street name; "
                        "appears in ELECTRICITY reports referencing the neighbourhood",
    },
    # --- WASTE ---
    {
        "key": "khafer",
        "variant_forms": ["khafer", "khfer", "5afer"],
        "loanword_from": "",
        "sector": "WASTE",
        "arabizi_note": "خفر — putrid/foul smell emanating from waste; "
                        "WASTE/OVERFLOWING_BIN signal; 5=خ alternative Arabizi encoding; "
                        "khafer ktir = very foul smell",
    },
    {
        "key": "bada",
        "variant_forms": ["bada", "bada2", "bedo", "b2ida"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "بدا — wants/is going to (3sg masc Lebanese future/desire); "
                        "ma bada 7ada yiji = nobody comes; "
                        "common complaint discourse modal verb",
    },
    {
        "key": "bala",
        "variant_forms": ["bala", "bila", "bidoun"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "بلا — without (Lebanese preposition); "
                        "bala may = without water; bala kahraba = without electricity; "
                        "high-frequency generic Lebanese prep",
    },
    {
        "key": "fil",
        "variant_forms": ["fil", "fil2", "fill"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "في ال — in the (contracted prep + definite article); "
                        "fil share3 = in the road; fil 7aret = in the alley; "
                        "tokenized as single unit in Arabizi",
    },
    {
        "key": "haje",
        "variant_forms": ["haje", "haja", "hajeh"],
        "loanword_from": "",
        "sector": "ALL",
        "arabizi_note": "حاجة — thing/something (Lebanese); "
                        "ma fi haje = there's nothing; common discourse noun; "
                        "high frequency in complaint reports",
    },
    {
        "key": "nahr",
        "variant_forms": ["nahr", "naher", "el nahr"],
        "loanword_from": "",
        "sector": "WASTE,FLOODING",
        "arabizi_note": "نهر — river; el nahr = the river; "
                        "appears in WASTE reports about illegal dump near rivers; "
                        "also FLOODING context",
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
    print(f"  V17 OOV Quick Patch {'[DRY RUN]' if dry_run else ''}")
    print("=" * 70)
    print(f"  Source: B001 per_row OOV tokens (rows with oov >= 2)")
    print()

    data = load_vocab()
    tm = data.setdefault("term_metadata", {})
    added, updated, skipped = 0, 0, 0

    for term_key, upd in UPDATES.items():
        if term_key not in tm:
            print(f"  WARN: cannot update '{term_key}' — not in term_metadata")
            continue
        entry = tm[term_key]
        existing = entry.get("variant_forms", [])
        new_forms = [v for v in upd["variant_forms_add"] if v not in existing]
        if not new_forms:
            print(f"  SKIP update '{term_key}' — all variants already present")
            skipped += 1
            continue
        if not dry_run:
            entry["variant_forms"] = sorted(set(existing) | set(new_forms))
        print(f"  UPDATE '{term_key}': +{new_forms}")
        updated += 1

    for e in NEW_ENTRIES:
        key = e["key"]
        if key in tm:
            existing_vf = tm[key].get("variant_forms", [])
            new_vf = [v for v in e["variant_forms"] if v not in existing_vf]
            if new_vf:
                if not dry_run:
                    tm[key]["variant_forms"] = sorted(set(existing_vf) | set(new_vf))
                print(f"  UPDATE '{key}' (existing): +{new_vf}")
                updated += 1
            else:
                print(f"  SKIP '{key}' — already complete")
                skipped += 1
            continue

        if not dry_run:
            tm[key] = {
                "variant_forms": e["variant_forms"],
                "loanword_from": e.get("loanword_from", ""),
                "sector":        e.get("sector", "ALL"),
                "arabizi_note":  e.get("arabizi_note", ""),
                "added_by":      "update_vocab_gwb_support_v17_oov_patch",
                "added_at":      NOW,
            }
        print(f"  ADD  '{key}': variants={e['variant_forms'][:3]}...")
        added += 1

    if not dry_run:
        old_version = data.get("version", "?")
        data["version"] = NEW_VERSION
        cl = data.get("changelog", "")
        data["changelog"] = (
            f"{NEW_VERSION} ({NOW[:10]}): V17 OOV quick patch — "
            f"{added} new, {updated} updated term_metadata entries. "
            f"Addresses remaining B001 OOV tokens: tire, 3jelatna, sursok/armeniye "
            f"(location standalone forms), abimee/completement (FR), khafer, bada, "
            f"bala, fil, haje, nahr, 3la, app, arc, jeanne, makdissi, masliye. "
            f"Previous: {old_version}. " + cl
        )

    if dry_run:
        print(f"\n  DRY RUN: +{added} add, {updated} update, {skipped} skip")
        return

    bak = backup_vocab()
    print(f"\n  Backup → {bak.name}")
    save_vocab(data, VOCAB_PATH)
    print(f"  Saved   → {VOCAB_PATH.name}  (version {NEW_VERSION})")
    print(f"\n  Summary: +{added} new, {updated} updated, {skipped} skipped")
    print("\n  Run validators:")
    print("    python scripts/validate_arabizi_vocabulary.py")
    print("    python scripts/evaluate_arabizi_coverage.py")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(dry_run=args.dry_run)

"""
absorb_thesis_negations.py
===========================
V19a — Absorb Lebanese negation/functional forms from Taha Tobaili's thesis
negations.txt into arabizi_vocabulary.json as T3_GENERIC_SUPPORT entries.

Source:
    data/external_sources/manual_drop/thesis_extracted/thesis/Misc/
    Lexicon-Based-Classification-Features/negations.txt

Groups ~200 negation forms into 10 canonical term_metadata entries.
Each group is added only if its canonical key is not already present.

Run:
    python scripts/absorb_thesis_negations.py --dry-run
    python scripts/absorb_thesis_negations.py
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"
NEGATIONS_TXT = (
    ROOT
    / "data/external_sources/manual_drop/thesis_extracted/thesis/Misc"
    / "Lexicon-Based-Classification-Features/negations.txt"
)

NOW = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
NEW_VERSION = "1.5.7"

# ---------------------------------------------------------------------------
# Negation group definitions (canonical key → group config)
# Each entry will become one term_metadata entry.  The 'prefixes' field is
# used to assign lines from negations.txt to the group.
# Order matters: first matching prefix wins.
# ---------------------------------------------------------------------------
NEGATION_GROUPS: list[dict] = [
    {
        "key": "mish_neg",
        "prefixes": ["mish", "mesh", "mech", "mich", "moch", "mosh", "mush", "mouc", "mous", "mshy", "msha", "lmsh", "mshh"],
        "also_exact": ["lmsh", "msh", "mshh"],
        "note": "Lebanese negation 'not/isn't' — mish/mesh/mich variants. mish/msh already in STOPWORDS; adding extended family for coverage.",
        "sector": "ALL",
    },
    {
        "key": "mabada_neg",
        "prefixes": ["mabad", "mabde", "mabdo", "mabdn", "mabda", "mabdd", "mabdi", "mabdk", "mabdh",
                     "mbad", "mbde", "mbdo", "mbdn", "mabed", "mabid"],
        "also_exact": [],
        "note": "Lebanese 'won't/never/hasn't ever been' — mabada family (50+ conjugated forms).",
        "sector": "ALL",
    },
    {
        "key": "mafi_neg",
        "prefixes": ["mafi", "mafe", "mafs", "mafk", "mafy", "mafch", "mfch", "mfe", "mfec", "mfes", "mfi", "mfic", "mfis"],
        "also_exact": [],
        "note": "Lebanese 'there is none/nothing' — mafi/mafish/mafesh/mafech variants.",
        "sector": "ALL",
    },
    {
        "key": "mana_neg",
        "prefixes": ["mana", "mann", "manko", "manku", "manno", "manne", "manno", "mannu", "mano", "manu",
                     "manh", "mank", "mani", "mane", "manek"],
        "also_exact": [],
        "note": "Lebanese 'forbidden/prohibited/not allowed' — mana/mann conjugations.",
        "sector": "ALL",
    },
    {
        "key": "ma3ash_neg",
        "prefixes": ["ma3", "m3"],
        "also_exact": [],
        "note": "Lebanese 'no longer/not anymore' — ma3ash/ma3ch/ma3m variants (3=ع).",
        "sector": "ALL",
    },
    {
        "key": "ma7a_neg",
        "prefixes": ["ma7", "mara7", "mar7", "mar77", "mal7", "mala7", "mr7", "mra7", "mrah", "marh", "marra", "ml7", "mla7", "m7"],
        "also_exact": ["malah", "marah"],
        "note": "Lebanese 'won't happen/impossible/won't come' — ma7a/mara7/mal7 (7=ح).",
        "sector": "ALL",
    },
    {
        "key": "mab2a_neg",
        "prefixes": ["mab2", "mba2", "mb2", "maba2", "maba22"],
        "also_exact": [],
        "note": "Lebanese 'won't become/not going to be anymore' — mab2a (2=ء/ق).",
        "sector": "ALL",
    },
    {
        "key": "batala_neg",
        "prefixes": ["batal", "batel", "batil", "batl", "btalet", "btalt", "btlna", "battil", "betalet"],
        "also_exact": [],
        "note": "Lebanese 'became invalid/stopped/was cancelled' — battal/batala conjugations.",
        "sector": "ALL",
    },
    {
        "key": "bala_neg",
        "prefixes": [],
        "also_exact": ["bala", "bla", "wbala", "wballa", "wbla"],
        "note": "Lebanese 'without' — bala/bla. 'bla' already in STOPWORDS; adding extended forms.",
        "sector": "ALL",
    },
    {
        "key": "wala_neg",
        "prefixes": ["wala", "wla", "wmaba", "wmafi", "wmana", "wmane", "wmanna", "wmanno", "wmano",
                     "wmanon", "wmara", "wmarah", "wmch", "wmec", "wmes", "wmic", "wmis", "wmsh"],
        "also_exact": ["wma"],
        "note": "Lebanese 'neither/nor/not even' + compound w-negations (wala/wla/wmish/wmesh).",
        "sector": "ALL",
    },
]


def normalise(token: str) -> str:
    token = token.lower().strip()
    token = re.sub(r"[^a-z0-9]", "", token)
    token = re.sub(r"[0146]+$", "", token)
    token = re.sub(r"([a-z0-9])\1{3,}", r"\1\1", token)
    return token


def assign_group(form: str) -> str | None:
    fl = form.lower().strip()
    for grp in NEGATION_GROUPS:
        if fl in grp["also_exact"]:
            return grp["key"]
        for prefix in grp["prefixes"]:
            if fl.startswith(prefix):
                return grp["key"]
    return None


def load_vocab(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_vocab(vocab: dict, path: Path) -> None:
    path.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Absorb thesis negation forms into vocab")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without modifying vocab")
    args = parser.parse_args()

    if not NEGATIONS_TXT.exists():
        raise FileNotFoundError(f"negations.txt not found at {NEGATIONS_TXT}")

    # Read and classify negation forms
    raw_forms = [line.strip() for line in NEGATIONS_TXT.read_text(encoding="utf-8").splitlines() if line.strip()]
    grouped: dict[str, list[str]] = defaultdict(list)
    unmatched: list[str] = []
    for form in raw_forms:
        grp = assign_group(form)
        if grp:
            grouped[grp].append(form)
        else:
            unmatched.append(form)

    vocab = load_vocab(VOCAB_PATH)
    current_version = vocab.get("version", "unknown")

    if current_version == NEW_VERSION:
        print(f"[SKIP] Vocab already at {NEW_VERSION} — negation absorption already applied.")
        return

    term_meta = vocab.setdefault("term_metadata", {})

    # Build existing known normalised forms from term_metadata variant_forms
    existing_normalised: set[str] = set()
    for _key, meta in term_meta.items():
        for vf in meta.get("variant_forms", []):
            existing_normalised.add(normalise(vf))

    actions: list[tuple[str, str, list[str]]] = []  # (action, key, forms)

    for grp_def in NEGATION_GROUPS:
        key = grp_def["key"]
        forms = grouped.get(key, [])
        if not forms:
            print(f"  [WARN] No forms matched for group '{key}' from negations.txt")
            continue

        # Deduplicate and check coverage
        unique_forms = sorted(set(forms))
        new_forms = [f for f in unique_forms if normalise(f) not in existing_normalised]

        if key in term_meta:
            # Already exists — extend variant_forms with new ones
            existing_vf = set(term_meta[key].get("variant_forms", []))
            truly_new = [f for f in unique_forms if f not in existing_vf]
            if truly_new:
                actions.append(("UPDATE", key, truly_new))
            else:
                print(f"  [SKIP] {key}: already fully covered ({len(unique_forms)} forms)")
        else:
            actions.append(("ADD", key, unique_forms))

    print(f"\nVocab version: {current_version} → {NEW_VERSION}")
    print(f"Source: {NEGATIONS_TXT.name} ({len(raw_forms)} forms, {len(unmatched)} unmatched)")
    print(f"\nActions ({len(actions)}):")
    for action, key, forms in actions:
        print(f"  {action:6s}  {key}  ({len(forms)} forms)")
        if len(forms) <= 12:
            print(f"           {forms}")
        else:
            print(f"           {forms[:8]} ... +{len(forms)-8} more")

    if unmatched:
        print(f"\nUnmatched forms ({len(unmatched)}): {unmatched}")

    if args.dry_run:
        print("\n[DRY-RUN] No changes written.")
        return

    # --- Apply ---
    backup_path = VOCAB_PATH.with_suffix(f".{NOW}.bak.json")
    shutil.copy2(VOCAB_PATH, backup_path)
    print(f"\nBackup: {backup_path.name}")

    for action, key, forms in actions:
        if action == "ADD":
            grp_def = next(g for g in NEGATION_GROUPS if g["key"] == key)
            term_meta[key] = {
                "sector": grp_def["sector"],
                "tier": "T3_GENERIC_SUPPORT",
                "allowed_uses": "normalization_support",
                "false_friend_risk": "false",
                "must_not_auto_promote": "true",
                "review_status": "APPROVED",
                "reviewer_id": "SYSTEM-V19",
                "note": grp_def["note"],
                "source": "thesis_tobaili_negations",
                "added": NOW,
                "variant_forms": forms,
            }
        elif action == "UPDATE":
            existing_vf = term_meta[key].get("variant_forms", [])
            term_meta[key]["variant_forms"] = sorted(set(existing_vf) | set(forms))
            term_meta[key]["updated"] = NOW

    # Changelog
    added_count = sum(1 for a, _, _ in actions if a == "ADD")
    updated_count = sum(1 for a, _, _ in actions if a == "UPDATE")
    total_forms = sum(len(f) for _, _, f in actions)
    entry = (
        f"{NEW_VERSION} ({NOW[:10]}): V19a thesis negation absorption — "
        f"{added_count} new groups, {updated_count} updated, ~{total_forms} forms total"
    )
    changelog = vocab.get("changelog", "")
    vocab["changelog"] = f"{entry}. {changelog}" if changelog else entry
    vocab["version"] = NEW_VERSION

    save_vocab(vocab, VOCAB_PATH)
    print(f"\n[OK] Saved vocab {NEW_VERSION} — {added_count} new groups, {updated_count} updated.")


if __name__ == "__main__":
    main()

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"
GUIDELINES_PATH = ROOT / "docs" / "ANNOTATION_GUIDELINES.md"

FORBIDDEN_ACTIVE_SEEDS = {
    "mansour men may",
    "2abu 2araq",
    "balioa",
    "balioa mafiyye",
    "hal 3am yenkaser",
    "hafra",
    "hufra",
    "may mesh raye7a",
}

MIN_SEEDS_PER_ISSUE_TYPE = 3


def load_expected_issue_types() -> dict[str, set[str]]:
    text = GUIDELINES_PATH.read_text(encoding="utf-8")
    match = re.search(r"```\n(ROADS:.*?)\n```", text, re.S)
    if not match:
        raise ValueError("Could not find issue taxonomy block in ANNOTATION_GUIDELINES.md")

    expected: dict[str, set[str]] = {}
    for line in match.group(1).splitlines():
        sector, values = line.split(":", 1)
        expected[sector] = {value.strip().lower() for value in values.split(",")}
    return expected


def iter_active_seed_strings(vocab: dict):
    for sector_name, sector in vocab["sectors"].items():
        for issue_type, seeds in sector.get("issue_type_keywords", {}).items():
            for seed in seeds:
                yield sector_name, issue_type, seed
        for seed in sector.get("sample_complaints", []):
            yield sector_name, "sample_complaints", seed
        for seed in sector.get("catch_all_phrases", []):
            yield sector_name, "catch_all_phrases", seed


def add_error(errors: list[str], code: str, message: str) -> None:
    errors.append(f"{code}: {message}")


def validate(vocab_path: Path = VOCAB_PATH) -> int:
    vocab = json.loads(vocab_path.read_text(encoding="utf-8-sig"))
    expected = load_expected_issue_types()
    errors: list[str] = []
    warnings: list[str] = []

    if not vocab.get("version"):
        add_error(errors, "VERSION", "Vocabulary must include a version")
    if "lexicon_policy" not in vocab:
        add_error(errors, "LEXICON_POLICY", "Vocabulary must include lexicon_policy")
    elif "adaptive_oov_policy" not in vocab["lexicon_policy"]:
        add_error(errors, "ADAPTIVE_OOV_POLICY", "lexicon_policy must define adaptive_oov_policy")
    if "source_notes" not in vocab:
        add_error(errors, "SOURCE_NOTES", "Vocabulary must include source_notes")

    for sector_name, expected_keys in expected.items():
        sector = vocab["sectors"].get(sector_name)
        if not sector:
            add_error(errors, "SECTOR", f"Missing sector {sector_name}")
            continue

        actual_keys = set(sector.get("issue_type_keywords", {}))
        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys
        if missing:
            add_error(errors, "ISSUE_KEYS", f"{sector_name} missing issue keys: {sorted(missing)}")
        if extra:
            add_error(errors, "ISSUE_KEYS", f"{sector_name} has non-taxonomy issue keys: {sorted(extra)}")

        for issue_type, seeds in sector.get("issue_type_keywords", {}).items():
            if len(seeds) < MIN_SEEDS_PER_ISSUE_TYPE:
                add_error(
                    errors,
                    "SEED_COUNT",
                    f"{sector_name}.{issue_type} has {len(seeds)} seeds; minimum is {MIN_SEEDS_PER_ISSUE_TYPE}",
                )
            if len(seeds) != len(set(seeds)):
                add_error(errors, "DUPLICATE_SEED", f"{sector_name}.{issue_type} contains duplicate seeds")

    for sector_name, issue_type, seed in iter_active_seed_strings(vocab):
        lowered = seed.lower()
        for forbidden in FORBIDDEN_ACTIVE_SEEDS:
            if forbidden in lowered:
                add_error(
                    errors,
                    "FORBIDDEN_SEED",
                    f"{sector_name}.{issue_type} contains forbidden phrase: {forbidden!r}",
                )

    return finish(errors, warnings)


def finish(errors: list[str], warnings: list[str]) -> int:
    for warning in warnings:
        print(f"WARNING {warning}")
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        print(f"FAILED: {len(errors)} errors, {len(warnings)} warnings")
        return 1
    print(f"OK: Arabizi vocabulary validation passed with {len(warnings)} warnings")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Arabizi production vocabulary.")
    parser.add_argument(
        "--vocab-path",
        type=Path,
        default=VOCAB_PATH,
        help=f"Vocabulary JSON to validate (default: {VOCAB_PATH.relative_to(ROOT)})",
    )
    args = parser.parse_args()
    sys.exit(validate(args.vocab_path))


if __name__ == "__main__":
    main()

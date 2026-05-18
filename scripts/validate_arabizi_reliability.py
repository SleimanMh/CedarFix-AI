"""
validate_arabizi_reliability.py

Measures vocabulary hit-rate coverage on the real corpus (cedarfix_reports_v1.csv).

Coverage metric:
  For each row where language in ('arabizi', 'mixed'), tokenize the text field
  and count what fraction of tokens appear in the production vocabulary.
  Report per-row hit-rate, overall average, and rows below threshold.

Usage:
  python scripts/validate_arabizi_reliability.py
  python scripts/validate_arabizi_reliability.py --threshold 0.3 --low-only

Outputs to stdout (and optionally to reports/arabizi_reliability.txt).
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "data/knowledge_base/arabizi_vocabulary.json"
CORPUS_PATH = ROOT / "data/corpus/cedarfix_reports_v1.csv"
REPORT_PATH = ROOT / "reports/arabizi_reliability.txt"

DEFAULT_THRESHOLD = 0.30  # rows below this are flagged


def build_token_set(vocab: dict) -> frozenset[str]:
    """Collect every keyword from the production vocabulary (lowercased)."""
    tokens: set[str] = set()
    for sec in vocab["sectors"].values():
        for tok_list in sec.get("issue_type_keywords", {}).values():
            for tok in tok_list:
                tokens.add(tok.lower().strip())
    # Also include high-risk hints
    for hint in vocab.get("high_risk_hints", []):
        tokens.add(hint.lower().strip())
    return frozenset(tokens)


def tokenize(text: str) -> list[str]:
    """
    Very simple tokenizer: lowercase, split on whitespace and punctuation.
    Keeps Arabic-script codepoints, Latin letters, digits and apostrophe
    (needed for tokens like '2at3a', 'l may', '7ufra').
    """
    text = text.lower()
    parts = re.split(r"[^\w\u0600-\u06FF']+", text)
    return [p for p in parts if p]


def measure_coverage(
    vocab_tokens: frozenset[str],
    text: str,
    multi_word: bool = True,
) -> float:
    """
    Returns the fraction of tokens in `text` that have a match in vocab_tokens.
    Also tries 2-token and 3-token windows (multi-word phrases) when multi_word=True.
    """
    words = tokenize(text)
    if not words:
        return 0.0

    matched: set[int] = set()
    n = len(words)

    if multi_word:
        for size in (3, 2):
            for i in range(n - size + 1):
                phrase = " ".join(words[i: i + size])
                if phrase in vocab_tokens:
                    for j in range(size):
                        matched.add(i + j)

    for i, w in enumerate(words):
        if w in vocab_tokens:
            matched.add(i)

    return len(matched) / n


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure Arabizi vocabulary coverage on corpus.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Flag rows below this hit rate (default {DEFAULT_THRESHOLD})")
    parser.add_argument("--low-only", action="store_true",
                        help="Print only rows below threshold")
    parser.add_argument("--save", action="store_true",
                        help=f"Save report to {REPORT_PATH.relative_to(ROOT)}")
    args = parser.parse_args()

    # Load vocabulary
    if not VOCAB_PATH.exists():
        print(f"FATAL: vocabulary not found at {VOCAB_PATH}")
        sys.exit(1)
    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    vocab_tokens = build_token_set(vocab)
    print(f"Vocabulary tokens loaded: {len(vocab_tokens)}")

    # Load corpus
    if not CORPUS_PATH.exists():
        print(f"FATAL: corpus not found at {CORPUS_PATH}")
        print("  Expected: data/corpus/cedarfix_reports_v1.csv")
        print("  To generate coverage, provide the real corpus file.")
        sys.exit(1)

    import csv
    results: list[tuple[str, str, float]] = []
    arabizi_rows = 0

    with open(CORPUS_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        text_field = None
        lang_field = None
        for col in (reader.fieldnames or []):
            if col.lower() in ("text", "raw_text", "report_text", "content", "message"):
                text_field = col
            if col.lower() in ("language", "lang"):
                lang_field = col

        if not text_field:
            print("FATAL: could not detect text column in corpus. "
                  "Expected column named 'text', 'report_text', 'content', or 'message'.")
            sys.exit(1)
        if not lang_field:
            print("WARNING: could not detect language column. "
                  "Processing all rows (not just arabizi/mixed).")

        for row in reader:
            lang = row.get(lang_field, "arabizi").lower().strip() if lang_field else "arabizi"
            if lang not in ("arabizi", "mixed"):
                continue
            arabizi_rows += 1
            text = row.get(text_field, "").strip()
            if not text:
                results.append((row.get("report_id", str(arabizi_rows)), lang, 0.0))
                continue
            hit = measure_coverage(vocab_tokens, text)
            results.append((row.get("report_id", str(arabizi_rows)), lang, hit))

    if not results:
        print(f"No arabizi/mixed rows found in corpus ({CORPUS_PATH.name}).")
        sys.exit(1)

    scores = [s for _, _, s in results]
    avg = sum(scores) / len(scores)
    below = [(rid, lang, s) for rid, lang, s in results if s < args.threshold]

    lines: list[str] = []
    lines.append(f"Arabizi Vocabulary Reliability Report")
    lines.append(f"Vocabulary version: {vocab.get('version', vocab.get('metadata', {}).get('version', 'unknown'))}")
    lines.append(f"Vocabulary tokens:  {len(vocab_tokens)}")
    lines.append(f"Corpus: {CORPUS_PATH.name}")
    lines.append(f"Arabizi/mixed rows: {arabizi_rows}")
    lines.append(f"Average hit rate:   {avg:.1%}")
    lines.append(f"Below {args.threshold:.0%} threshold: {len(below)} / {len(results)}")
    lines.append("")

    if not args.low_only:
        lines.append("All rows (report_id | language | hit_rate):")
        for rid, lang, s in results:
            flag = " <- LOW" if s < args.threshold else ""
            lines.append(f"  {rid:>10}  {lang:<8}  {s:>6.1%}{flag}")
        lines.append("")

    if below:
        lines.append(f"Rows below {args.threshold:.0%}:")
        for rid, lang, s in below:
            lines.append(f"  {rid:>10}  {lang:<8}  {s:>6.1%}")

    output = "\n".join(lines)
    print(output)

    if args.save:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(output, encoding="utf-8")
        print(f"\nSaved to {REPORT_PATH}")


if __name__ == "__main__":
    main()

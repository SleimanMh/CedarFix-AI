"""
Language Detector — IEP-1
==========================
Detects the language of incoming complaint text.
Supports Arabic, French, English, and Arabizi (Arabic in Latin script).

Detection order:
  1. Arabizi heuristic  (zero-cost, runs first)
  2. Arabic Unicode check
  3. langdetect for French / English
  4. Fallback → English
"""

import re
from langdetect import detect, LangDetectException

# ---------------------------------------------------------------------------
# Arabizi signals
# ---------------------------------------------------------------------------

# Numbers used as Arabic letter substitutes in Lebanese Arabizi
_ARABIZI_ADJACENT = re.compile(r"[a-zA-Z][37259268]|[37259268][a-zA-Z]")

# High-confidence Lebanese Arabizi tokens
_ARABIZI_TOKENS = {
    "3al", "ma3", "3an", "3am", "w3al", "3ndo", "3ando",
    "2al", "2eli", "2elon", "2oul",
    "7aki", "7elo", "7elu", "7afra", "7afre",
    "ktir", "kter", "shi", "hek", "shu", "wlo", "yalla",
    "tari2", "shari3", "kahraba", "kahrabe",
    "daww", "maye", "may ", "3awame", "3awameh",
    "mafi", "fi ", "mn ", "min ", "3a ", "b ",
}

# Arabic Unicode range
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def detect_arabizi(text: str) -> bool:
    """
    Returns True if the text is Arabizi (Arabic written in Latin + number substitutes).
    Safe to call before any library — pure regex, zero latency.
    """
    # Text with Arabic Unicode is proper Arabic, not Arabizi
    if _ARABIC_RE.search(text):
        return False

    lower = text.lower()

    # Strong signal: known Lebanese Arabizi token present
    for token in _ARABIZI_TOKENS:
        if token in lower:
            return True

    # Medium signal: number immediately adjacent to a Latin letter (e.g. "3al", "fi7", "m3a")
    adjacent_matches = _ARABIZI_ADJACENT.findall(lower)
    if len(adjacent_matches) >= 2:
        return True

    return False


def detect_language(text: str) -> str:
    """
    Returns a language code string:
      "arabizi" | "ar" | "fr" | "en" | "unknown"
    """
    # 1. Arabizi check (must run before Arabic Unicode check)
    if detect_arabizi(text):
        return "arabizi"

    # 2. Has Arabic Unicode → Arabic
    if _ARABIC_RE.search(text):
        return "ar"

    # 3. Use langdetect for French / English
    try:
        code = detect(text)
        if code in ("ar", "fr", "en"):
            return code
    except LangDetectException:
        pass

    # 4. Default to English
    return "en"

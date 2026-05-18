from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from src.shared.arabizi_lexical_policy import HIGH_RISK_HINTS, IGNORED_OOV_TOKENS, STOPWORDS
from src.shared.schemas import IEP1LanguageSignal, Language, OOVRiskHint, OOVToken, ScriptProfile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"

TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
LATIN_RE = re.compile(r"[a-z]", re.I)
ARABIZI_MARKER_RE = re.compile(r"[235789]")
HIGH_RISK_RE = re.compile(r"(5tr|5atr|5atar|khatar|m5atr|sa32|saa2|ghaz|7ar2|7are2)", re.I)


@dataclass(frozen=True)
class VocabularyIndex:
    version: str
    known_tokens: frozenset[str]
    loanword_tokens: frozenset[str]
    token_issue_map: dict[str, set[tuple[str, str]]]


def normalise_token(token: str) -> str:
    token = token.lower().strip()
    token = re.sub(r"[^a-z0-9]", "", token)
    token = re.sub(r"[0146]+$", "", token)
    token = re.sub(r"([a-z0-9])\1{3,}", r"\1\1", token)
    return token


def hard_collapse_token(token: str) -> str:
    return re.sub(r"([a-z0-9])\1+", r"\1", token)


def token_variants(token: str) -> list[str]:
    variants = [normalise_token(token)]
    hard = hard_collapse_token(variants[0])
    if hard not in variants:
        variants.append(hard)
    return [variant for variant in variants if variant]


def tokenize(text: str) -> list[str]:
    return [normalise_token(match.group(0)) for match in TOKEN_RE.finditer(text) if normalise_token(match.group(0))]


def iter_strings(value) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)


def load_vocabulary_index(vocab_path: Path = DEFAULT_VOCAB_PATH) -> VocabularyIndex:
    vocab = json.loads(vocab_path.read_text(encoding="utf-8-sig"))
    known: set[str] = set(STOPWORDS)
    token_issue_map: dict[str, set[tuple[str, str]]] = {}

    for text in iter_strings(vocab.get("arabizi_notes", {})):
        known.update(tokenize(text))

    for sector_name, sector in vocab.get("sectors", {}).items():
        for issue_type, seeds in sector.get("issue_type_keywords", {}).items():
            for seed in iter_strings(seeds):
                for token in tokenize(seed):
                    known.add(token)
                    token_issue_map.setdefault(token, set()).add((sector_name, issue_type.upper()))
        for section in ("sample_complaints", "catch_all_phrases", "issue_type_aliases"):
            for text in iter_strings(sector.get(section, {})):
                known.update(tokenize(text))

    loanwords: set[str] = set()
    for term, metadata in vocab.get("term_metadata", {}).items():
        if metadata.get("loanword_from"):
            loanwords.add(normalise_token(term))
        for variant in metadata.get("variant_forms", []):
            known.add(normalise_token(variant))

    return VocabularyIndex(
        version=vocab.get("version", "unknown"),
        known_tokens=frozenset(token for token in known if token),
        loanword_tokens=frozenset(loanwords),
        token_issue_map=token_issue_map,
    )


def infer_language(raw_text: str, language_hint: str | None = None) -> Language:
    if language_hint:
        try:
            return Language(language_hint)
        except ValueError:
            pass
    has_arabic = bool(ARABIC_RE.search(raw_text))
    has_latin = bool(LATIN_RE.search(raw_text))
    has_marker = bool(ARABIZI_MARKER_RE.search(raw_text))
    if has_arabic and has_latin:
        return Language.MIXED
    if has_arabic:
        return Language.ARABIC
    if has_marker:
        return Language.ARABIZI
    return Language.UNKNOWN


def infer_script_profile(raw_text: str, language: Language, loanword_hits: int) -> ScriptProfile:
    has_arabic = bool(ARABIC_RE.search(raw_text))
    has_latin = bool(LATIN_RE.search(raw_text))
    has_marker = bool(ARABIZI_MARKER_RE.search(raw_text))
    if has_arabic and has_latin:
        return ScriptProfile.MIXED_SCRIPT
    if has_arabic:
        return ScriptProfile.ARABIC_SCRIPT
    if language == Language.MIXED or (loanword_hits and has_marker):
        return ScriptProfile.MIXED_LATIN
    if has_marker:
        return ScriptProfile.LATIN_ARABIZI
    if has_latin:
        return ScriptProfile.LATIN_OTHER
    return ScriptProfile.UNKNOWN


def risk_hint_for_token(token: str) -> OOVRiskHint:
    if HIGH_RISK_RE.search(token) or token in HIGH_RISK_HINTS:
        return OOVRiskHint.SAFETY_LEXICAL_HINT
    return OOVRiskHint.LANGUAGE_DRIFT


def is_meaningful_oov(token: str) -> bool:
    return bool(token) and len(token) >= 3 and token not in IGNORED_OOV_TOKENS and not token.isdigit()


def analyze_language_signal(
    raw_text: str,
    *,
    normalized_text: str | None = None,
    language_hint: str | None = None,
    report_id: str | None = None,
    vocab_path: Path = DEFAULT_VOCAB_PATH,
) -> IEP1LanguageSignal:
    vocab = load_vocabulary_index(vocab_path)
    raw_tokens = tokenize(raw_text)
    known_terms: set[str] = set()
    oov_by_token: dict[str, OOVToken] = {}
    loanword_hits = 0
    marker_count = sum(1 for token in raw_tokens for char in token if ARABIZI_MARKER_RE.match(char))
    high_risk_term_count = 0
    covered_token_count = 0
    orthographic_noise_count = 0

    for raw_token in raw_tokens:
        variants = token_variants(raw_token)
        matched = next((variant for variant in variants if variant in vocab.known_tokens), "")
        if matched:
            if matched != variants[0]:
                orthographic_noise_count += 1
            if matched not in STOPWORDS:
                covered_token_count += 1
            known_terms.add(matched)
            if matched in vocab.loanword_tokens:
                loanword_hits += 1
            if HIGH_RISK_RE.search(matched) or matched in HIGH_RISK_HINTS:
                high_risk_term_count += 1
            continue

        embedded = [
            token
            for token in vocab.known_tokens
            if len(token) >= 5 and len(raw_token) >= 9 and token in raw_token
        ]
        if embedded:
            known_terms.update(embedded)
            matched = embedded[0]
            orthographic_noise_count += 1
            if matched in vocab.loanword_tokens:
                loanword_hits += 1

        token = variants[0]
        if not is_meaningful_oov(token):
            continue
        risk_hint = risk_hint_for_token(token)
        if risk_hint != OOVRiskHint.LANGUAGE_DRIFT:
            high_risk_term_count += 1
        oov_by_token[token] = OOVToken(
            token=token,
            raw_variants=[raw_token],
            risk_hint=risk_hint,
            suggested_action="NEEDS_MORE_EXAMPLES",
            matched_context="Generated by v1 heuristic language-signal probe.",
        )

    meaningful_count = max(1, len([token for token in raw_tokens if token not in IGNORED_OOV_TOKENS]))
    coverage = min(1.0, covered_token_count / meaningful_count)
    code_mix_ratio = min(1.0, loanword_hits / max(1, len(raw_tokens)))
    marker_density = min(1.0, marker_count / max(1, len(raw_tokens)))
    language = infer_language(raw_text, language_hint)
    script_profile = infer_script_profile(raw_text, language, loanword_hits)
    oov_tokens = sorted(oov_by_token.values(), key=lambda item: item.token)
    oov_high_risk_count = sum(1 for item in oov_tokens if item.risk_hint != OOVRiskHint.LANGUAGE_DRIFT)

    semantic_ambiguity = False
    token_set = set(raw_tokens) | known_terms
    if {"may", "sarif"} <= token_set or {"ws5a", "sarif"} <= token_set:
        semantic_ambiguity = True

    drift_score = 0
    if oov_tokens:
        drift_score = 1
    if orthographic_noise_count:
        drift_score = max(drift_score, 1)
    if len(oov_tokens) >= 2 or coverage < 0.75:
        drift_score = max(drift_score, 2)
    if oov_high_risk_count or high_risk_term_count or semantic_ambiguity:
        drift_score = max(drift_score, 2)
    if len(oov_tokens) >= 5 or (coverage < 0.4 and (oov_high_risk_count or semantic_ambiguity)):
        drift_score = 3

    return IEP1LanguageSignal(
        report_id=report_id,
        language=language,
        script_profile=script_profile,
        raw_text=raw_text,
        normalized_text=normalized_text or raw_text,
        normalization_applied=language in {Language.ARABIZI, Language.MIXED},
        normalization_confidence=round(coverage, 4),
        normalization_coverage=round(coverage, 4),
        arabizi_marker_count=marker_count,
        arabizi_marker_density=round(marker_density, 4),
        code_mix_ratio=round(code_mix_ratio, 4),
        oov_token_count=len(oov_tokens),
        oov_high_risk_count=oov_high_risk_count,
        oov_tokens=oov_tokens,
        known_terms=sorted(known_terms),
        drift_score=drift_score,
        explanation_features={
            "vocab_version": vocab.version,
            "high_risk_term_count": high_risk_term_count,
            "semantic_ambiguity": semantic_ambiguity,
            "orthographic_noise_count": orthographic_noise_count,
            "raw_token_count": len(raw_tokens),
            "meaningful_token_count": meaningful_count,
        },
    )


def flat_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    mean_lat = math.radians((lat1 + lat2) / 2)
    dlat = (lat1 - lat2) * 111_000
    dlon = (lon1 - lon2) * 111_000 * math.cos(mean_lat)
    return math.sqrt(dlat * dlat + dlon * dlon)

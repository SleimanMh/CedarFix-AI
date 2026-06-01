"""IEP-1 language signal extraction, issue classification, and embedding.

Three steps per complaint:
  1. Language signal  — via src.shared.arabizi_features.analyze_language_signal
                        (returns IEP1LanguageSignal with drift_score, OOV, etc.)
  2. Issue type       — hybrid rules + learned multilingual classifier
  3. Text embedding   — sentence-transformers paraphrase-multilingual-mpnet-base-v2
                        (falls back gracefully if the model is unavailable)

The keyword V1 classifier is retained as the non-AI baseline (B1). IEP-1 now
also asks a lightweight learned char-gram model trained from the repository's
JSONL supervision for a top-3 semantic issue hypothesis, then records the
hybrid arbitration trace for ablation and HITL review.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

from src.shared.arabizi_features import VocabularyIndex, analyze_language_signal, load_vocabulary_index
from src.shared.arabizi_lexical_policy import IGNORED_OOV_TOKENS
from src.shared.schemas import (
    IEP1LanguageSignal,
    IssueCandidate,
    IssueEvidenceTerm,
    ROUTE_CONFIDENCE_THRESHOLD,
)
from src.iep1.semantic_classifier import SemanticPrediction, classify_text

logger = logging.getLogger("iep1.extractor")

# ── Issue-type keyword table (B1 baseline) ────────────────────────────────────
_SECTOR_KEYWORDS: dict[str, list[str]] = {
    "ROADS": [
        "pothole", "road", "street", "asphalt", "pavement", "sidewalk", "curb",
        "حفرة", "طريق", "شارع", "رصيف", "asfalt",
        "trou", "route", "chaussée",
        "7ofra", "shar3", "tari2", "rmeil",
    ],
    "WATER": [
        "water", "pipe", "leak", "sewage", "drain", "overflow", "flood",
        "ماء", "ماي", "مياه", "أنبوب", "تسرب", "صرف",
        "eau", "fuite", "tuyau",
        "may", "miye", "3atl", "sarif",
    ],
    "ELECTRICITY": [
        "electricity", "power", "blackout", "wire", "cable", "transformer",
        "كهرباء", "كابل", "سلك", "محول",
        "électricité", "câble", "panne",
        "kahraba", "kahrabeh", "salk", "kabel", "silk", "transformateur", "m7arrak", "mcharrak",
    ],
    "WASTE": [
        "garbage", "trash", "waste", "litter", "bin", "rubbish", "recycling",
        "نفايات", "زبالة", "قمامة",
        "déchets", "ordures", "poubelle",
        "zibele", "nfeyyet", "zbele",
    ],
    "FLOODING": [
        "flooding", "flood", "inundation", "accumulation", "standing water",
        "فيضان", "تجمع مياه", "غمر",
        "inondation", "débordement",
        "fayadene", "sayel", "balo3a", "balou3a", "msdoude", "ghatat", "tit3abba",
    ],
    "SAFETY": [
        "danger", "fire", "explosion", "collapse", "accident", "crime", "threat",
        "خطر", "حريق", "انهيار", "جريمة",
        "danger", "incendie", "effondrement",
        "5atr", "khatar", "7arik", "7ariki", "7ar2", "7are2", "nnar", "masalla7",
    ],
}

_ISSUE_TIEBREAK_PRIORITY: dict[tuple[str, str], int] = {
    ("ELECTRICITY", "TRANSFORMER_FAULT"): 30,
    ("ELECTRICITY", "WIRING_HAZARD"): 20,
    ("WATER", "SEWAGE_OVERFLOW"): 30,
    ("WATER", "PUBLIC_PIPE_LEAK"): 25,
    ("ROADS", "POTHOLE"): 30,
}


def _issue_priority(key: tuple[str, str]) -> int:
    return _ISSUE_TIEBREAK_PRIORITY.get((key[0].upper(), key[1].upper()), 0)


def classify_sector_with_evidence(text: str) -> tuple[str, float, dict[str, list[str]]]:
    """Keyword V1 sector classifier plus matched keyword evidence.

    Returns (sector, confidence, keyword_hits_by_sector). Confidence is the
    fractional keyword hit share; returns OTHER at 0.4 when no keywords match.
    """
    lower = text.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lower))
    keyword_hits: dict[str, list[str]] = {sector: [] for sector in _SECTOR_KEYWORDS}
    for sector, keywords in _SECTOR_KEYWORDS.items():
        for kw in keywords:
            if re.fullmatch(r"[a-z0-9]+", kw):
                matched = kw in tokens
            else:
                matched = kw in lower
            if matched:
                keyword_hits[sector].append(kw)

    scores: dict[str, int] = {sector: len(hits) for sector, hits in keyword_hits.items()}
    best = max(scores, key=lambda k: scores[k])
    compact_hits = {
        sector: sorted(set(hits))
        for sector, hits in keyword_hits.items()
        if hits
    }
    if scores[best] == 0:
        return "OTHER", 0.4, compact_hits

    total = sum(scores.values())
    return best, round(scores[best] / total, 3), compact_hits


def classify_sector(text: str) -> tuple[str, float]:
    """Keyword V1 sector classifier (non-AI baseline B1)."""
    sector, confidence, _keyword_hits = classify_sector_with_evidence(text)
    return sector, confidence


def _language_risk_reasons(
    signal: IEP1LanguageSignal,
    issue_type: str,
    issue_confidence: float,
) -> list[str]:
    reasons: list[str] = []
    if signal.drift_score >= 2:
        reasons.append(f"drift_score_{signal.drift_score}")
    if signal.oov_high_risk_count:
        reasons.append("high_risk_oov")
    elif signal.oov_token_count:
        reasons.append("meaningful_oov")
    if signal.normalization_coverage < 0.75:
        reasons.append("low_normalization_coverage")
    if signal.explanation_features.get("semantic_ambiguity"):
        reasons.append("semantic_ambiguity")
    if issue_type == "UNCLASSIFIED":
        reasons.append("issue_type_unclassified")
    elif issue_confidence < ROUTE_CONFIDENCE_THRESHOLD:
        reasons.append("low_issue_confidence")
    return sorted(set(reasons))


def _review_recommendation(
    signal: IEP1LanguageSignal,
    issue_type: str,
    issue_confidence: float,
    risk_reasons: list[str] | None = None,
) -> str:
    if signal.force_hitl():
        return "HITL_LANGUAGE_REVIEW"
    if any("model_rules_" in reason for reason in (risk_reasons or [])):
        return "REVIEW_BEFORE_AUTOROUTE"
    if issue_type == "UNCLASSIFIED" or issue_confidence < ROUTE_CONFIDENCE_THRESHOLD:
        return "REVIEW_BEFORE_AUTOROUTE"
    return "AUTO_ROUTE_ELIGIBLE"


def _model_candidates(prediction: SemanticPrediction) -> list[IssueCandidate]:
    candidates: list[IssueCandidate] = []
    for hypothesis in prediction.top3:
        candidates.append(
            IssueCandidate(
                sector=hypothesis.sector,
                issue_type=hypothesis.issue_type,
                evidence_count=0,
                matched_terms=[],
                sector_keyword_hits=[],
                confidence=hypothesis.confidence,
                selected=False,
                reason="learned_chargram_semantic_model",
            )
        )
    return candidates


def _apply_hybrid_arbitration(
    *,
    rules_sector: str,
    rules_issue_type: str,
    rules_confidence: float,
    issue_candidates: list[IssueCandidate],
    model_prediction: SemanticPrediction,
) -> tuple[str, str, float, list[IssueCandidate], str, list[str]]:
    """Fuse rules and learned classifier output without allowing unsafe jumps."""
    selected = model_prediction.selected
    risk_reasons: list[str] = []
    hybrid_reason = "rules_only_model_unavailable"
    sector = rules_sector
    issue_type = rules_issue_type
    confidence = rules_confidence

    if selected is None or not model_prediction.available:
        return sector, issue_type, confidence, issue_candidates, hybrid_reason, risk_reasons

    model_sector = selected.sector
    model_issue = selected.issue_type
    model_conf = selected.confidence
    rules_gap = rules_sector in {"OTHER", "UNKNOWN", ""} or rules_issue_type == "UNCLASSIFIED"

    if rules_gap and model_conf >= 0.35:
        sector = model_sector
        issue_type = model_issue
        confidence = max(confidence, model_conf)
        hybrid_reason = "model_fills_rules_gap"
    elif model_sector == rules_sector and model_issue == rules_issue_type:
        confidence = min(0.98, round(((rules_confidence + model_conf) / 2) + 0.08, 3))
        hybrid_reason = "rules_model_exact_agreement"
    elif model_sector == rules_sector:
        risk_reasons.append("model_rules_issue_disagreement")
        if model_conf >= 0.50:
            issue_type = model_issue
            confidence = max(confidence, round(model_conf * 0.95, 3))
            hybrid_reason = "model_refines_issue_with_same_sector"
        else:
            hybrid_reason = "rules_keep_issue_after_model_disagreement"
    else:
        risk_reasons.append("model_rules_sector_disagreement")
        if model_conf >= 0.50 or (model_conf >= 0.35 and rules_confidence < 0.80):
            sector = model_sector
            issue_type = model_issue
            confidence = model_conf
            hybrid_reason = "model_leads_with_rules_disagreement_review"
        else:
            hybrid_reason = "rules_keep_sector_after_model_conflict"

    matched_selected = False
    for candidate in issue_candidates:
        candidate.selected = (
            candidate.sector == sector
            and candidate.issue_type == issue_type
            and candidate.reason != "learned_chargram_semantic_model"
        )
        matched_selected = matched_selected or candidate.selected
    if not matched_selected:
        issue_candidates.append(
            IssueCandidate(
                sector=sector,
                issue_type=issue_type,
                evidence_count=0,
                matched_terms=[],
                sector_keyword_hits=[],
                confidence=confidence,
                selected=True,
                reason=f"hybrid:{hybrid_reason}",
            )
        )

    return sector, issue_type, round(confidence, 3), issue_candidates, hybrid_reason, risk_reasons


def build_issue_intelligence(
    signal: IEP1LanguageSignal,
    vocab: VocabularyIndex | None = None,
    *,
    use_model: bool = True,
) -> dict:
    """Build a reviewer-facing issue classification evidence bundle."""
    vocab = vocab or load_vocabulary_index()
    sector_hint, sector_confidence, sector_keyword_hits = classify_sector_with_evidence(signal.raw_text)

    hits: dict[tuple[str, str], int] = {}
    candidate_terms: dict[tuple[str, str], set[str]] = {}
    evidence_terms: list[IssueEvidenceTerm] = []
    ambiguous_term_count = 0

    for term in signal.known_terms:
        term_hits = {
            (sector, issue_type)
            for sector, issue_type in vocab.token_issue_map.get(term, set())
            if issue_type not in {"ALL", "UNCLASSIFIED"}
        }
        if sector_hint != "OTHER" and any(sector == sector_hint for sector, _issue_type in term_hits):
            term_hits = {
                (sector, issue_type)
                for sector, issue_type in term_hits
                if sector == sector_hint
            }
        if term in IGNORED_OOV_TOKENS:
            continue
        if len(term_hits) != 1:
            if len(term_hits) > 1:
                ambiguous_term_count += 1
            continue
        sector, issue_type = next(iter(term_hits))
        key = (sector, issue_type)
        hits[key] = hits.get(key, 0) + 1
        candidate_terms.setdefault(key, set()).add(term)
        evidence_terms.append(
            IssueEvidenceTerm(
                term=term,
                sector=sector,
                issue_type=issue_type,
            )
        )

    if hits and sector_hint != "OTHER" and any(key[0] == sector_hint for key in hits):
        hits = {key: count for key, count in hits.items() if key[0] == sector_hint}
        candidate_terms = {key: terms for key, terms in candidate_terms.items() if key in hits}
        evidence_terms = [
            item for item in evidence_terms
            if (item.sector, item.issue_type) in hits
        ]

    issue_candidates: list[IssueCandidate] = []
    if hits:
        best_key, best_count = max(
            hits.items(),
            key=lambda item: (item[1], _issue_priority(item[0]), item[0]),
        )
        sector, issue_type = best_key
        issue_confidence = min(0.95, max(sector_confidence, 0.55) + 0.10 * best_count)
        issue_confidence = round(issue_confidence, 3)
        for key, count in sorted(
            hits.items(),
            key=lambda item: (-item[1], -_issue_priority(item[0]), item[0]),
        ):
            candidate_sector, candidate_issue = key
            candidate_confidence = min(
                0.95,
                max(sector_confidence if candidate_sector == sector_hint else 0.45, 0.55)
                + 0.10 * count,
            )
            issue_candidates.append(
                IssueCandidate(
                    sector=candidate_sector,
                    issue_type=candidate_issue,
                    evidence_count=count,
                    matched_terms=sorted(candidate_terms.get(key, set())),
                    sector_keyword_hits=sector_keyword_hits.get(candidate_sector, []),
                    confidence=round(candidate_confidence, 3),
                    selected=key == best_key,
                    reason=(
                        "vocab_terms_match_sector_hint"
                        if candidate_sector == sector_hint
                        else "vocab_terms_match"
                    ),
                )
            )
    else:
        sector = sector_hint
        issue_type = "UNCLASSIFIED"
        issue_confidence = max(0.35, round(sector_confidence * 0.6, 3))
        if sector_hint != "OTHER":
            issue_candidates.append(
                IssueCandidate(
                    sector=sector_hint,
                    issue_type="UNCLASSIFIED",
                    evidence_count=len(sector_keyword_hits.get(sector_hint, [])),
                    matched_terms=[],
                    sector_keyword_hits=sector_keyword_hits.get(sector_hint, []),
                    confidence=issue_confidence,
                    selected=True,
                    reason="sector_keywords_only",
                )
            )

    rules_sector = sector
    rules_issue_type = issue_type
    rules_confidence = issue_confidence
    model_prediction = (
        classify_text(signal.raw_text)
        if use_model
        else SemanticPrediction(
            model_name="rules_only_ablation",
            available=False,
            training_examples=0,
            label_count=0,
            top3=(),
            reason="disabled_for_rules_only_ablation",
        )
    )
    model_issue_candidates = _model_candidates(model_prediction)
    (
        sector,
        issue_type,
        issue_confidence,
        issue_candidates,
        hybrid_reason,
        model_risk_reasons,
    ) = _apply_hybrid_arbitration(
        rules_sector=rules_sector,
        rules_issue_type=rules_issue_type,
        rules_confidence=rules_confidence,
        issue_candidates=issue_candidates,
        model_prediction=model_prediction,
    )
    risk_reasons = _language_risk_reasons(signal, issue_type, issue_confidence)
    risk_reasons.extend(model_risk_reasons)
    explanation_features = dict(signal.explanation_features)
    explanation_features.update(
        {
            "sector_keyword_hit_count": sum(len(hits) for hits in sector_keyword_hits.values()),
            "selected_issue_evidence_count": max(hits.values()) if hits else 0,
            "issue_candidate_count": len(issue_candidates),
            "model_issue_candidate_count": len(model_issue_candidates),
            "ambiguous_issue_term_count": ambiguous_term_count,
            "selected_sector_hint": sector_hint,
            "selected_issue_type": issue_type,
            "model_available": model_prediction.available,
            "model_training_examples": model_prediction.training_examples,
        }
    )
    classification_trace = {
        "rules": {
            "sector": rules_sector,
            "issue_type": rules_issue_type,
            "confidence": rules_confidence,
            "candidate_count": len(issue_candidates),
        },
        "model": model_prediction.model_dump(),
        "hybrid": {
            "sector": sector,
            "issue_type": issue_type,
            "confidence": issue_confidence,
            "reason": hybrid_reason,
            "risk_reasons": sorted(set(model_risk_reasons)),
        },
    }

    return {
        "routing_sector": sector,
        "issue_type": issue_type,
        "issue_type_confidence": issue_confidence,
        "issue_evidence_terms": evidence_terms,
        "issue_candidates": issue_candidates,
        "model_issue_candidates": model_issue_candidates,
        "language_risk_reasons": risk_reasons,
        "review_recommendation": _review_recommendation(
            signal,
            issue_type,
            issue_confidence,
            risk_reasons,
        ),
        "explanation_features": explanation_features,
        "classification_trace": classification_trace,
    }


def classify_issue_type_from_signal(
    signal: IEP1LanguageSignal,
    vocab: VocabularyIndex | None = None,
    *,
    use_model: bool = True,
) -> tuple[str, str, float]:
    """Return (sector, issue_type, confidence) from reviewed vocabulary hits.

    This avoids the earlier anti-pattern of writing broad sectors such as ROADS
    into the `issue_type` DB column. If no specific issue is visible, the sector
    baseline still runs, but issue_type remains UNCLASSIFIED.
    """

    intelligence = build_issue_intelligence(signal, vocab, use_model=use_model)
    return (
        intelligence["routing_sector"],
        intelligence["issue_type"],
        intelligence["issue_type_confidence"],
    )


# ── Sentence-transformers embedding ───────────────────────────────────────────
_EMBED_MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"


@lru_cache(maxsize=1)
def _load_embedder():
    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        logger.info("Loading embedding model %s …", _EMBED_MODEL_NAME)
        return SentenceTransformer(_EMBED_MODEL_NAME)
    except Exception as exc:  # noqa: BLE001
        logger.warning("sentence-transformers unavailable: %s — embedding disabled", exc)
        return None


def embed_text(text: str) -> list[float] | None:
    """Return a normalised float vector or None if the model is not loaded."""
    model = _load_embedder()
    if model is None:
        return None
    try:
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed_text failed: %s", exc)
        return None


# ── Top-level extraction function ────────────────────────────────────────────
def extract(
    complaint_id: str,
    text: str,
    language_hint: str | None = None,
    *,
    include_embedding: bool = True,
    use_model: bool = True,
) -> dict:
    """Run all IEP-1 sub-tasks and return a flat dict suitable for DB writes."""
    # Step 1 — language signal (Arabizi-aware, drift-aware)
    signal: IEP1LanguageSignal = analyze_language_signal(
        raw_text=text,
        language_hint=language_hint or None,
        report_id=complaint_id,
    )

    # Step 2 — issue type (V1 vocabulary-backed baseline) with evidence trace
    issue_intelligence = build_issue_intelligence(signal, use_model=use_model)
    sector = issue_intelligence["routing_sector"]
    issue_type = issue_intelligence["issue_type"]
    issue_conf = issue_intelligence["issue_type_confidence"]
    signal = signal.model_copy(
        update={
            "issue_evidence_terms": issue_intelligence["issue_evidence_terms"],
            "issue_candidates": issue_intelligence["issue_candidates"],
            "model_issue_candidates": issue_intelligence["model_issue_candidates"],
            "language_risk_reasons": issue_intelligence["language_risk_reasons"],
            "review_recommendation": issue_intelligence["review_recommendation"],
            "explanation_features": issue_intelligence["explanation_features"],
            "classification_trace": issue_intelligence["classification_trace"],
        }
    )

    # Step 3 — embedding. Unit tests and demo stress probes can disable this
    # so contract checks do not depend on a local model download.
    embedding = embed_text(signal.normalized_text) if include_embedding else None
    embedding_ref = f"iep1:{complaint_id}" if embedding else None

    return {
        "language": signal.language.value,
        "language_confidence": signal.normalization_confidence,
        "drift_score": signal.drift_score,
        "issue_type": issue_type,
        "issue_type_confidence": issue_conf,
        "routing_sector": sector,
        "normalized_text": signal.normalized_text,
        "text_embedding_ref": embedding_ref,
        "iep1_signal_json": signal.model_dump(mode="json"),
        # Pass the vector inline for IEP-2 in V1 (avoids a second DB query)
        "_embedding_vector": embedding,
    }

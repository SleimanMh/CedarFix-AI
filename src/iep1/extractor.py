"""IEP-1 language signal extraction, issue classification, and embedding.

Three steps per complaint:
  1. Language signal  — via src.shared.arabizi_features.analyze_language_signal
                        (returns IEP1LanguageSignal with drift_score, OOV, etc.)
  2. Issue type       — keyword V1 classifier across five sectors + SAFETY
  3. Text embedding   — sentence-transformers paraphrase-multilingual-mpnet-base-v2
                        (falls back gracefully if the model is unavailable)

The keyword V1 classifier is intentionally simple: it is the non-AI baseline (B1)
against which the trained multilingual classifier must be compared in T5.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from src.shared.arabizi_features import analyze_language_signal
from src.shared.schemas import IEP1LanguageSignal

logger = logging.getLogger("iep1.extractor")

# ── Issue-type keyword table (B1 baseline) ────────────────────────────────────
# Keys match the Sector enum values in src/shared/schemas.py
_ISSUE_KEYWORDS: dict[str, list[str]] = {
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
        "kahraba", "kahrabeh", "salk", "kabel",
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
        "fayadene", "sayel",
    ],
    "SAFETY": [
        "danger", "fire", "explosion", "collapse", "accident", "crime", "threat",
        "خطر", "حريق", "انهيار", "جريمة",
        "danger", "incendie", "effondrement",
        "5atr", "khatar", "7arik", "7ariki", "nnar", "masalla7",
    ],
}


def classify_issue_type(text: str) -> tuple[str, float]:
    """Keyword V1 sector classifier (non-AI baseline B1).

    Returns (sector: str, confidence: float ∈ [0, 1]).
    Confidence is the fractional keyword hit share; returns OTHER at 0.4
    when no keywords match.
    """
    lower = text.lower()
    scores: dict[str, int] = {k: 0 for k in _ISSUE_KEYWORDS}
    for sector, keywords in _ISSUE_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[sector] += 1

    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "OTHER", 0.4

    total = sum(scores.values())
    return best, round(scores[best] / total, 3)


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
) -> dict:
    """Run all IEP-1 sub-tasks and return a flat dict suitable for DB writes."""
    # Step 1 — language signal (Arabizi-aware, drift-aware)
    signal: IEP1LanguageSignal = analyze_language_signal(
        raw_text=text,
        language_hint=language_hint or None,
        report_id=complaint_id,
    )

    # Step 2 — issue type (V1 keyword baseline)
    issue_type, issue_conf = classify_issue_type(text)

    # Upgrade issue type to SAFETY if the signal has high-risk OOV tokens
    if signal.oov_high_risk_count > 0 and issue_type not in {"SAFETY"}:
        # High-risk Arabizi safety tokens dominate over infra keyword hits
        issue_type = "SAFETY"
        issue_conf = max(issue_conf, 0.6)

    # Step 3 — embedding
    embedding = embed_text(signal.normalized_text)
    embedding_ref = f"iep1:{complaint_id}" if embedding else None

    return {
        "language": signal.language.value,
        "language_confidence": signal.normalization_confidence,
        "drift_score": signal.drift_score,
        "issue_type": issue_type,
        "issue_type_confidence": issue_conf,
        "normalized_text": signal.normalized_text,
        "text_embedding_ref": embedding_ref,
        "iep1_signal_json": signal.model_dump(mode="json"),
        # Pass the vector inline for IEP-2 in V1 (avoids a second DB query)
        "_embedding_vector": embedding,
    }

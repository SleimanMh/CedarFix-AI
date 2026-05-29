"""
Candidate Retriever — IEP-3

Performs THREE independent searches and merges the results using
Reciprocal Rank Fusion (RRF) into a de-duplicated candidate pool.

Sources:
  text_search     — cosine search on text_embeddings collection
  image_search    — cosine search on image_embeddings collection (if image present)
  geo_time_search — payload filter on text_embeddings (type + location + time window)

Merging rule (RRF):
  Each source produces an ordered list. Each complaint gets a score of
  1 / (k + rank) from each list it appears in. Final ordering is by the
  sum of RRF scores across all lists. k=60 is the standard RRF constant.

  This avoids mixing embedding spaces: text and image similarities are
  combined at the rank level, not at the vector level.
  raw_text_similarity and raw_image_similarity are preserved from their
  respective searches for downstream use by the scorer in IEP-4.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from cedarfix_shared.schemas import (
    CanonicalComplaint,
    RawCandidate,
    TextUnderstandingResult,
    ImageUnderstandingResult,
)
from .qdrant_client import QdrantStore

# How far back to look for geo-time matches (days)
GEO_TIME_WINDOW_DAYS = int(7)
GEO_SEARCH_RADIUS_KM = float(1.0)
TOP_K = int(10)

# RRF constant — standard value, dampens the effect of very high ranks
RRF_K = 60


class CandidateRetriever:
    """
    Runs independent retrieval from each source and merges into a single pool.
    """

    def __init__(self, qdrant: QdrantStore):
        self._qdrant = qdrant

    async def retrieve(
        self,
        canonical: CanonicalComplaint,
        text_embedding: List[float],
        image_embedding: List[float],
        image_present: bool,
    ) -> List[RawCandidate]:
        """
        Returns a merged, de-duplicated list of RawCandidate objects ordered
        by Reciprocal Rank Fusion score across all active search sources.
        Each candidate has a `sources` list indicating how it was found.
        """
        # Collect ordered result lists per source
        result_lists: List[List[RawCandidate]] = []

        # ── Source 1: Text search ────────────────────────────────────────────
        if text_embedding:
            hits = [
                h for h in await self._qdrant.search_text(text_embedding, top_k=TOP_K)
                if h.complaint_id != canonical.complaint_id
            ]
            result_lists.append(hits)

        # ── Source 2: Image search ───────────────────────────────────────────
        if image_present and image_embedding:
            hits = [
                h for h in await self._qdrant.search_image(image_embedding, top_k=TOP_K)
                if h.complaint_id != canonical.complaint_id
            ]
            result_lists.append(hits)

        # ── Source 3: Geo-time search ────────────────────────────────────────
        since_iso = (
            datetime.now(tz=timezone.utc) - timedelta(days=GEO_TIME_WINDOW_DAYS)
        ).isoformat()

        geo_hits = [
            h for h in await self._qdrant.search_geo_time(
                issue_type=canonical.issue_type.value,
                latitude=canonical.location.latitude,
                longitude=canonical.location.longitude,
                district=canonical.location.district,
                since_iso=since_iso,
                radius_km=GEO_SEARCH_RADIUS_KM,
                top_k=20,
            )
            if h.complaint_id != canonical.complaint_id
        ]
        result_lists.append(geo_hits)

        return _rrf_merge(result_lists)


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def _rrf_merge(result_lists: List[List[RawCandidate]]) -> List[RawCandidate]:
    """
    Merge multiple ranked candidate lists using Reciprocal Rank Fusion.

    For each candidate in each list, add 1 / (RRF_K + rank) to its total
    RRF score. Candidates found by multiple sources accumulate higher scores.
    Similarity scores from their respective searches are preserved on the
    merged candidate for downstream use by the IEP-4 scorer.
    """
    rrf_scores: Dict[str, float] = {}
    pool: Dict[str, RawCandidate] = {}

    for result_list in result_lists:
        for rank, candidate in enumerate(result_list):
            cid = candidate.complaint_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
            if cid not in pool:
                pool[cid] = candidate
            else:
                # Merge sources and take max of each similarity score
                existing = pool[cid]
                for src in candidate.sources:
                    if src not in existing.sources:
                        existing.sources.append(src)
                existing.raw_text_similarity = max(
                    existing.raw_text_similarity, candidate.raw_text_similarity
                )
                existing.raw_image_similarity = max(
                    existing.raw_image_similarity, candidate.raw_image_similarity
                )

    # Return sorted by RRF score descending
    return sorted(pool.values(), key=lambda c: rrf_scores[c.complaint_id], reverse=True)

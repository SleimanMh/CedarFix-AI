"""
Candidate Retriever — IEP-3

Performs up to FOUR independent vector searches plus a geo-time filter,
then merges the vector-search results with Reciprocal Rank Fusion (RRF).

Search sources:
  text_search          — cosine on text_embeddings  (MPNet 768D)
  clip_text_search     — cosine on clip_embeddings  (CLIP 512D, text query, always)
  clip_image_search    — cosine on clip_embeddings  (CLIP 512D, image query, if image present)
  geo_time_search      — payload filter on text_embeddings (type + location + time window)
                         Not included in RRF; merged afterwards by complaint_id.

Cross-modal detection:
  When a CLIP text query matches a clip_image entry in clip_embeddings (or vice-versa),
  that hit is flagged cross-modal.  The IEP-4 scorer applies a penalty factor and, when
  both cross-modal signals are strong (>0.70), adds a convergence bonus.

Merging rule (RRF):
  Each vector source produces a ranked list. Each complaint earns 1/(k+rank) per list.
  k=60 is the standard RRF constant. Scores accumulate across sources so complaints
  found by multiple searches rank higher. raw_* similarity fields from each search are
  preserved via max-merge for the downstream IEP-4 scorer.
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
        clip_text_embedding: List[float],
        image_present: bool,
    ) -> List[RawCandidate]:
        """
        Returns a merged, de-duplicated list of RawCandidate objects ordered
        by Reciprocal Rank Fusion score across all active vector search sources.
        Each candidate has a `sources` list indicating how it was found.
        """
        # Ordered result lists for RRF (vector searches only)
        result_lists: List[List[RawCandidate]] = []

        # ── Source 1: MPNet text search ──────────────────────────────────────
        if text_embedding:
            hits = [
                h for h in await self._qdrant.search_text(text_embedding, top_k=TOP_K)
                if h.complaint_id != canonical.complaint_id
            ]
            result_lists.append(hits)

        # ── Source 2: CLIP text search (always — enables cross-modal detection)
        if clip_text_embedding:
            hits = [
                h for h in await self._qdrant.search_clip(
                    clip_text_embedding, query_type="clip_text", top_k=TOP_K
                )
                if h.complaint_id != canonical.complaint_id
            ]
            result_lists.append(hits)

        # ── Source 3: CLIP image search (only when image is present) ─────────
        if image_present and image_embedding:
            hits = [
                h for h in await self._qdrant.search_clip(
                    image_embedding, query_type="clip_image", top_k=TOP_K
                )
                if h.complaint_id != canonical.complaint_id
            ]
            result_lists.append(hits)

        # ── Geo-time search (structured filter — outside RRF) ─────────────────
        since_iso = (
            datetime.now(tz=timezone.utc) - timedelta(days=GEO_TIME_WINDOW_DAYS)
        ).isoformat()

        geo_hits = [
            h for h in await self._qdrant.search_geo_time(
                issue_type=canonical.issue_type,
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
    All similarity fields are preserved via max-merge across matching entries.
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
                existing = pool[cid]
                # Merge sources
                for src in candidate.sources:
                    if src not in existing.sources:
                        existing.sources.append(src)
                # Max-merge all similarity scores
                existing.raw_text_similarity = max(
                    existing.raw_text_similarity, candidate.raw_text_similarity
                )
                existing.raw_image_similarity = max(
                    existing.raw_image_similarity, candidate.raw_image_similarity
                )
                existing.raw_mpnet_text_sim = max(
                    existing.raw_mpnet_text_sim, candidate.raw_mpnet_text_sim
                )
                existing.raw_clip_text_sim = max(
                    existing.raw_clip_text_sim, candidate.raw_clip_text_sim
                )
                existing.raw_clip_image_sim = max(
                    existing.raw_clip_image_sim, candidate.raw_clip_image_sim
                )
                # Propagate cross-modal flags (True wins)
                existing.clip_text_is_xmodal = (
                    existing.clip_text_is_xmodal or candidate.clip_text_is_xmodal
                )
                existing.clip_image_is_xmodal = (
                    existing.clip_image_is_xmodal or candidate.clip_image_is_xmodal
                )

    # Return sorted by RRF score descending
    return sorted(pool.values(), key=lambda c: rrf_scores[c.complaint_id], reverse=True)

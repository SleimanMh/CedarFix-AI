"""
Candidate Retriever — IEP-3

Performs THREE independent searches and merges the results into a
de-duplicated candidate pool, each tagged with its source(s).

Sources:
  text_search     — cosine search on text_embeddings collection
  image_search    — cosine search on image_embeddings collection (if image present)
  geo_time_search — payload filter on text_embeddings (type + location + time window)

Merging rule: if the same complaint appears from multiple sources, its
candidate_source list is extended and similarity scores are max-merged.
This means a complaint found by BOTH image and geo-time search is stronger
evidence than one found by only one source.
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
        Returns a merged, de-duplicated list of RawCandidate objects.
        Each candidate has a `sources` list indicating how it was found.
        """
        pool: Dict[str, RawCandidate] = {}

        # ── Source 1: Text search ────────────────────────────────────────────
        if text_embedding:
            hits = await self._qdrant.search_text(text_embedding, top_k=TOP_K)
            for h in hits:
                if h.complaint_id != canonical.complaint_id:
                    _merge_into(pool, h)

        # ── Source 2: Image search ───────────────────────────────────────────
        if image_present and image_embedding:
            hits = await self._qdrant.search_image(image_embedding, top_k=TOP_K)
            for h in hits:
                if h.complaint_id != canonical.complaint_id:
                    _merge_into(pool, h)

        # ── Source 3: Geo-time search ────────────────────────────────────────
        since_iso = (
            datetime.now(tz=timezone.utc) - timedelta(days=GEO_TIME_WINDOW_DAYS)
        ).isoformat()

        hits = await self._qdrant.search_geo_time(
            issue_type=canonical.issue_type.value,
            latitude=canonical.location.latitude,
            longitude=canonical.location.longitude,
            district=canonical.location.district,
            since_iso=since_iso,
            radius_km=GEO_SEARCH_RADIUS_KM,
            top_k=20,
        )
        for h in hits:
            if h.complaint_id != canonical.complaint_id:
                _merge_into(pool, h)

        return list(pool.values())


# ---------------------------------------------------------------------------
# Merge helper
# ---------------------------------------------------------------------------

def _merge_into(pool: Dict[str, RawCandidate], incoming: RawCandidate) -> None:
    """
    If `incoming` is already in the pool, merge its sources and take the
    max of each similarity score.  Otherwise add it directly.
    """
    cid = incoming.complaint_id
    if cid not in pool:
        pool[cid] = incoming
        return

    existing = pool[cid]
    # Merge source tags (preserve unique, maintain order)
    for src in incoming.sources:
        if src not in existing.sources:
            existing.sources.append(src)
    # Take max of similarity scores
    existing.raw_text_similarity = max(
        existing.raw_text_similarity, incoming.raw_text_similarity
    )
    existing.raw_image_similarity = max(
        existing.raw_image_similarity, incoming.raw_image_similarity
    )

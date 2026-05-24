"""
Qdrant client wrapper — supports three collections for independent retrieval.

Collections:
  text_embeddings  (768-dim)  — one point per complaint
  image_embeddings (512-dim)  — one point per complaint that has an image
  fused_embeddings (768-dim)  — weighted fusion (backwards-compat)
"""

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    GeoBoundingBox,
    GeoPoint,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)

from cedarfix_shared.schemas import RawCandidate, ComplaintType, SeverityLevel, CanonicalLocationJSON

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

TEXT_COLLECTION  = os.getenv("QDRANT_TEXT_COLLECTION",  "text_embeddings")
IMAGE_COLLECTION = os.getenv("QDRANT_IMAGE_COLLECTION", "image_embeddings")
FUSED_COLLECTION = os.getenv("QDRANT_COLLECTION",       "fused_embeddings")

TEXT_DIM  = int(os.getenv("TEXT_EMBEDDING_DIM",  "768"))
IMAGE_DIM = int(os.getenv("IMAGE_EMBEDDING_DIM", "512"))
FUSED_DIM = int(os.getenv("FUSED_EMBEDDING_DIM", "768"))


def _stable_id(complaint_id: str) -> str:
    """Deterministic UUID from complaint_id string."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, complaint_id))


class QdrantStore:
    def __init__(self):
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    async def init_collections(self):
        existing = {c.name for c in self.client.get_collections().collections}
        specs = [
            (TEXT_COLLECTION,  TEXT_DIM),
            (IMAGE_COLLECTION, IMAGE_DIM),
            (FUSED_COLLECTION, FUSED_DIM),
        ]
        for name, dim in specs:
            if name not in existing:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
                print(f"[IEP-3] Created Qdrant collection: {name} ({dim}-dim)")

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    async def store_text(self, complaint_id: str, vector: List[float], payload: Dict):
        self.client.upsert(
            collection_name=TEXT_COLLECTION,
            points=[PointStruct(
                id=_stable_id(complaint_id),
                vector=vector,
                payload={"complaint_id": complaint_id, **payload},
            )],
        )

    async def store_image(self, complaint_id: str, vector: List[float], payload: Dict):
        self.client.upsert(
            collection_name=IMAGE_COLLECTION,
            points=[PointStruct(
                id=_stable_id(complaint_id),
                vector=vector,
                payload={"complaint_id": complaint_id, **payload},
            )],
        )

    async def store_fused(self, complaint_id: str, vector: List[float], payload: Dict):
        self.client.upsert(
            collection_name=FUSED_COLLECTION,
            points=[PointStruct(
                id=_stable_id(complaint_id),
                vector=vector,
                payload={"complaint_id": complaint_id, **payload},
            )],
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _to_raw_candidate(self, r: Any, source: str) -> RawCandidate:
        p = r.payload or {}
        loc = CanonicalLocationJSON(
            normalized_location=p.get("normalized_location", ""),
            district=p.get("district"),
            latitude=p.get("latitude"),
            longitude=p.get("longitude"),
        )
        ts_str = p.get("timestamp")
        timestamp = None
        if ts_str:
            try:
                timestamp = datetime.fromisoformat(ts_str)
            except Exception:
                pass
        return RawCandidate(
            complaint_id=p.get("complaint_id", str(r.id)),
            cluster_id=p.get("cluster_id"),
            summary=p.get("summary", ""),
            issue_type=p.get("issue_type", ComplaintType.OTHER),
            subcategory=p.get("subcategory", ""),
            location=loc,
            timestamp=timestamp,
            severity=p.get("severity", SeverityLevel.LOW),
            sources=[source],
            raw_text_similarity=round(r.score, 4) if source == "text_search" else 0.0,
            raw_image_similarity=round(r.score, 4) if source == "image_search" else 0.0,
        )

    async def search_text(self, vector: List[float], top_k: int = 10) -> List[RawCandidate]:
        response = self.client.query_points(
            collection_name=TEXT_COLLECTION,
            query=vector,
            limit=top_k,
            with_payload=True,
        )
        return [self._to_raw_candidate(r, "text_search") for r in response.points]

    async def search_image(self, vector: List[float], top_k: int = 10) -> List[RawCandidate]:
        response = self.client.query_points(
            collection_name=IMAGE_COLLECTION,
            query=vector,
            limit=top_k,
            with_payload=True,
        )
        return [self._to_raw_candidate(r, "image_search") for r in response.points]

    async def search_geo_time(
        self,
        issue_type: str,
        latitude: Optional[float],
        longitude: Optional[float],
        district: Optional[str],
        since_iso: str,
        radius_km: float = 1.0,
        top_k: int = 20,
    ) -> List[RawCandidate]:
        """
        Filter the text_embeddings collection by issue_type + location + time.
        Uses payload filtering (no vector distance — this is a structured search).
        """
        from datetime import datetime as _dt
        since_ts = _dt.fromisoformat(since_iso).timestamp()

        conditions = [
            FieldCondition(key="issue_type", match=MatchValue(value=issue_type)),
            FieldCondition(
                key="timestamp",
                range=Range(gte=since_ts),
            ),
        ]

        if latitude is not None and longitude is not None:
            # Approximate bounding box: 1 degree lat ≈ 111 km
            delta = radius_km / 111.0
            conditions.append(
                FieldCondition(
                    key="latitude",
                    range=Range(
                        gte=latitude - delta,
                        lte=latitude + delta,
                    ),
                )
            )
            conditions.append(
                FieldCondition(
                    key="longitude",
                    range=Range(
                        gte=longitude - delta,
                        lte=longitude + delta,
                    ),
                )
            )
        elif district:
            conditions.append(
                FieldCondition(key="district", match=MatchValue(value=district))
            )
        else:
            # No location info — skip geo-time search
            return []

        results = self.client.scroll(
            collection_name=TEXT_COLLECTION,
            scroll_filter=Filter(must=conditions),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )[0]

        candidates = []
        for r in results:
            c = self._to_raw_candidate(r, "geo_time_search")
            c.raw_text_similarity = 0.0   # no vector score from scroll
            candidates.append(c)
        return candidates


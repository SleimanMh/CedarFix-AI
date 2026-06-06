"""
Qdrant client wrapper — two collections for independent retrieval.

Collections:
  text_embeddings  (768-dim)  — one point per complaint (MPNet)
  clip_embeddings  (512-dim)  — multimodal CLIP-space points:
                                 one clip_text entry (always)
                                 one clip_image entry (when image is present)
                                 up to three clip_image_candidate caption entries
"""

import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)

from cedarfix_shared.schemas import RawCandidate, SeverityLevel, CanonicalLocationJSON
from cedarfix_shared.metrics import QDRANT_OPERATION_DURATION, QDRANT_OPERATION_ERRORS
from cedarfix_shared.qdrant import create_qdrant_client, qdrant_target_label

TEXT_COLLECTION = os.getenv("QDRANT_TEXT_COLLECTION", "text_embeddings")
CLIP_COLLECTION = os.getenv("QDRANT_CLIP_COLLECTION", "clip_embeddings")

TEXT_DIM = int(os.getenv("TEXT_EMBEDDING_DIM", "768"))
CLIP_DIM = int(os.getenv("CLIP_EMBEDDING_DIM", "512"))


def _stable_id(complaint_id: str) -> str:
    """Deterministic UUID for MPNet text_embeddings (one entry per complaint)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, complaint_id))


def _text_candidate_id(complaint_id: str, index: int) -> str:
    """Deterministic UUID for an image-candidate MPNet text entry."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"text_candidate_{complaint_id}_{index}"))


def _clip_text_id(complaint_id: str) -> str:
    """Deterministic UUID for the clip_text entry in clip_embeddings."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"clip_text_{complaint_id}"))


def _clip_image_id(complaint_id: str) -> str:
    """Deterministic UUID for the clip_image entry in clip_embeddings."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"clip_image_{complaint_id}"))


def _clip_candidate_id(complaint_id: str, index: int) -> str:
    """Deterministic UUID for an image-candidate CLIP text entry."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"clip_candidate_{complaint_id}_{index}"))


class QdrantStore:
    def __init__(self):
        self.client = create_qdrant_client()
        print(f"[IEP-3] Qdrant connected at {qdrant_target_label()}")

    async def init_collections(self):
        start = time.time()
        try:
            existing = {c.name for c in self.client.get_collections().collections}
        except Exception:
            QDRANT_OPERATION_ERRORS.labels(operation="get_collections", collection="all").inc()
            raise
        finally:
            QDRANT_OPERATION_DURATION.labels(operation="get_collections", collection="all").observe(
                time.time() - start
            )
        specs = [
            (TEXT_COLLECTION, TEXT_DIM),
            (CLIP_COLLECTION, CLIP_DIM),
        ]
        for name, dim in specs:
            if name not in existing:
                start = time.time()
                try:
                    self.client.create_collection(
                        collection_name=name,
                        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                    )
                except Exception:
                    QDRANT_OPERATION_ERRORS.labels(operation="create_collection", collection=name).inc()
                    raise
                finally:
                    QDRANT_OPERATION_DURATION.labels(
                        operation="create_collection", collection=name
                    ).observe(time.time() - start)
                print(f"[IEP-3] Created Qdrant collection: {name} ({dim}-dim)")

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    async def store_text(self, complaint_id: str, vector: List[float], payload: Dict):
        start = time.time()
        try:
            self.client.upsert(
                collection_name=TEXT_COLLECTION,
                points=[PointStruct(
                    id=_stable_id(complaint_id),
                    vector=vector,
                    payload={"complaint_id": complaint_id, **payload},
                )],
            )
        except Exception:
            QDRANT_OPERATION_ERRORS.labels(operation="upsert_text", collection=TEXT_COLLECTION).inc()
            raise
        finally:
            QDRANT_OPERATION_DURATION.labels(
                operation="upsert_text", collection=TEXT_COLLECTION
            ).observe(time.time() - start)

    async def store_text_candidate(self, complaint_id: str, index: int, vector: List[float], payload: Dict):
        """Store MPNet text encoding for one VLM image issue candidate."""
        self.client.upsert(
            collection_name=TEXT_COLLECTION,
            points=[PointStruct(
                id=_text_candidate_id(complaint_id, index),
                vector=vector,
                payload={
                    "complaint_id": complaint_id,
                    "vector_type": "image_candidate_text",
                    "candidate_index": index,
                    **payload,
                },
            )],
        )

    async def store_clip_text(self, complaint_id: str, vector: List[float], payload: Dict):
        """Store the CLIP text encoding of a complaint's text in clip_embeddings."""
        start = time.time()
        try:
            self.client.upsert(
                collection_name=CLIP_COLLECTION,
                points=[PointStruct(
                    id=_clip_text_id(complaint_id),
                    vector=vector,
                    payload={"complaint_id": complaint_id, "vector_type": "clip_text", **payload},
                )],
            )
        except Exception:
            QDRANT_OPERATION_ERRORS.labels(operation="upsert_clip_text", collection=CLIP_COLLECTION).inc()
            raise
        finally:
            QDRANT_OPERATION_DURATION.labels(
                operation="upsert_clip_text", collection=CLIP_COLLECTION
            ).observe(time.time() - start)

    async def store_clip_image(self, complaint_id: str, vector: List[float], payload: Dict):
        """Store the CLIP image encoding of a complaint's image in clip_embeddings."""
        start = time.time()
        try:
            self.client.upsert(
                collection_name=CLIP_COLLECTION,
                points=[PointStruct(
                    id=_clip_image_id(complaint_id),
                    vector=vector,
                    payload={"complaint_id": complaint_id, "vector_type": "clip_image", **payload},
                )],
            )
        except Exception:
            QDRANT_OPERATION_ERRORS.labels(operation="upsert_clip_image", collection=CLIP_COLLECTION).inc()
            raise
        finally:
            QDRANT_OPERATION_DURATION.labels(
                operation="upsert_clip_image", collection=CLIP_COLLECTION
            ).observe(time.time() - start)

    async def store_clip_image_candidate(self, complaint_id: str, index: int, vector: List[float], payload: Dict):
        """Store CLIP text encoding for one VLM image issue candidate caption."""
        self.client.upsert(
            collection_name=CLIP_COLLECTION,
            points=[PointStruct(
                id=_clip_candidate_id(complaint_id, index),
                vector=vector,
                payload={
                    "complaint_id": complaint_id,
                    "vector_type": "clip_image_candidate",
                    "candidate_index": index,
                    **payload,
                },
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
                if isinstance(ts_str, (int, float)):
                    timestamp = datetime.fromtimestamp(ts_str)
                else:
                    timestamp = datetime.fromisoformat(str(ts_str))
            except Exception:
                pass
        return RawCandidate(
            complaint_id=p.get("complaint_id", str(r.id)),
            cluster_id=p.get("cluster_id"),
            summary=p.get("summary", ""),
            issue_type=str(p.get("issue_type", "unknown")),
            subcategory=p.get("subcategory", ""),
            location=loc,
            timestamp=timestamp,
            severity=p.get("severity", SeverityLevel.LOW),
            sources=[source],
            raw_text_similarity=round(r.score, 4) if source == "text_search" else 0.0,
            raw_mpnet_text_sim=round(r.score, 4) if source == "text_search" else 0.0,
        )

    async def search_text(self, vector: List[float], top_k: int = 10) -> List[RawCandidate]:
        start = time.time()
        try:
            response = self.client.query_points(
                collection_name=TEXT_COLLECTION,
                query=vector,
                limit=top_k,
                with_payload=True,
            )
        except Exception:
            QDRANT_OPERATION_ERRORS.labels(operation="search_text", collection=TEXT_COLLECTION).inc()
            raise
        finally:
            QDRANT_OPERATION_DURATION.labels(
                operation="search_text", collection=TEXT_COLLECTION
            ).observe(time.time() - start)
        return [self._to_raw_candidate(r, "text_search") for r in response.points]

    async def search_clip(
        self,
        query_vector: List[float],
        query_type: str,
        top_k: int = 10,
    ) -> List[RawCandidate]:
        """
        Search the unified clip_embeddings collection.

        query_type: "clip_text" or "clip_image" — describes what kind of vector
                    is being used as the query. Used to detect cross-modal hits.

        Cross-modal detection:
          - query_type="clip_text" + hit vector_type="clip_image" → cross-modal text→image
          - query_type="clip_image" + hit vector_type="clip_text" → cross-modal image→text
        """
        start = time.time()
        try:
            response = self.client.query_points(
                collection_name=CLIP_COLLECTION,
                query=query_vector,
                limit=top_k,
                with_payload=True,
            )
        except Exception:
            QDRANT_OPERATION_ERRORS.labels(operation=f"search_{query_type}", collection=CLIP_COLLECTION).inc()
            raise
        finally:
            QDRANT_OPERATION_DURATION.labels(
                operation=f"search_{query_type}", collection=CLIP_COLLECTION
            ).observe(time.time() - start)
        candidates = []
        for r in response.points:
            c = self._to_raw_candidate(r, f"{query_type}_search")
            hit_vector_type = (r.payload or {}).get("vector_type", "")
            score = round(r.score, 4)
            if query_type == "clip_text":
                c.raw_clip_text_sim = score
                c.clip_text_is_xmodal = (hit_vector_type in {"clip_image", "clip_image_candidate"})
            else:  # clip_image
                c.raw_clip_image_sim = score
                c.clip_image_is_xmodal = (hit_vector_type in {"clip_text", "clip_image_candidate"})
            candidates.append(c)
        return candidates

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

        start = time.time()
        try:
            results = self.client.scroll(
                collection_name=TEXT_COLLECTION,
                scroll_filter=Filter(must=conditions),
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )[0]
        except Exception:
            QDRANT_OPERATION_ERRORS.labels(operation="search_geo_time", collection=TEXT_COLLECTION).inc()
            raise
        finally:
            QDRANT_OPERATION_DURATION.labels(
                operation="search_geo_time", collection=TEXT_COLLECTION
            ).observe(time.time() - start)

        candidates = []
        for r in results:
            c = self._to_raw_candidate(r, "geo_time_search")
            c.raw_text_similarity = 0.0   # no vector score from scroll
            candidates.append(c)
        return candidates


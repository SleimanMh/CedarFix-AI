"""
Qdrant client wrapper for the embedding service.
"""

import os
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, SearchRequest,
)
from cedarfix_shared.schemas import SimilarComplaint, SeverityLevel, ComplaintType
import uuid

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION = os.getenv("QDRANT_COLLECTION", "complaints")
FUSED_DIM = int(os.getenv("FUSED_EMBEDDING_DIM", "768"))


class QdrantStore:
    def __init__(self):
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    async def init_collection(self):
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION not in existing:
            self.client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=FUSED_DIM, distance=Distance.COSINE),
            )
            print(f"[IEP-3] Created Qdrant collection: {COLLECTION}")

    async def store(self, complaint_id: str, vector: List[float]):
        point = PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, complaint_id)),
            vector=vector,
            payload={"complaint_id": complaint_id},
        )
        self.client.upsert(collection_name=COLLECTION, points=[point])

    async def search(self, vector: List[float], top_k: int = 10) -> List[SimilarComplaint]:
        results = self.client.search(
            collection_name=COLLECTION,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
        )
        similar = []
        for r in results:
            payload = r.payload or {}
            similar.append(SimilarComplaint(
                complaint_id=payload.get("complaint_id", str(r.id)),
                similarity_score=round(r.score, 4),
                complaint_type=payload.get("complaint_type", ComplaintType.OTHER),
                severity=payload.get("severity", SeverityLevel.LOW),
                created_at=payload.get("created_at", "2024-01-01T00:00:00"),
            ))
        return similar

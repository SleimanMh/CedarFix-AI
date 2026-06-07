from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from cedarfix_shared.schemas import CanonicalComplaint, CanonicalLocationJSON, RawCandidate


class Hit:
    def __init__(self, *, complaint_id="c2", score=0.9, vector_type="clip_image", **payload):
        self.id = complaint_id
        self.score = score
        self.payload = {
            "complaint_id": complaint_id,
            "vector_type": vector_type,
            "summary": "Broken road",
            "issue_type": "road_damage",
            "severity": "HIGH",
            "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp(),
            **payload,
        }


class QueryResponse:
    def __init__(self, points):
        self.points = points


class FakeClient:
    def __init__(self):
        self.queries = []
        self.scrolls = []

    def query_points(self, **kwargs):
        self.queries.append(kwargs)
        return QueryResponse([Hit(vector_type="clip_image_candidate", score=0.88)])

    def scroll(self, **kwargs):
        self.scrolls.append(kwargs)
        return [Hit(vector_type="text", score=0.0, district="Beirut")], None


class FakeQdrant:
    def __init__(self):
        self.calls = []

    async def search_text(self, vector, top_k):
        self.calls.append(("text", vector, top_k))
        return [
            RawCandidate(complaint_id="self", sources=["text_search"], raw_mpnet_text_sim=0.99),
            RawCandidate(complaint_id="text-hit", sources=["text_search"], raw_mpnet_text_sim=0.86),
        ]

    async def search_clip(self, vector, query_type, top_k):
        self.calls.append((query_type, vector, top_k))
        return [
            RawCandidate(complaint_id="self", sources=[f"{query_type}_search"]),
            RawCandidate(
                complaint_id="clip-hit",
                sources=[f"{query_type}_search"],
                raw_clip_text_sim=0.81 if query_type == "clip_text" else 0.0,
                raw_clip_image_sim=0.83 if query_type == "clip_image" else 0.0,
            ),
        ]

    async def search_geo_time(self, **kwargs):
        self.calls.append(("geo", kwargs))
        return [
            RawCandidate(complaint_id="self", sources=["geo_time_search"]),
            RawCandidate(complaint_id="geo-hit", sources=["geo_time_search"]),
        ]


def _canonical():
    return CanonicalComplaint(
        complaint_id="self",
        issue_type="road_damage",
        location=CanonicalLocationJSON(district="Beirut", latitude=33.9, longitude=35.5),
    )


def test_qdrant_store_search_clip_sets_cross_modal_candidate_flags(import_service_module):
    qdrant_mod = import_service_module("embedding_service", "app.qdrant_client", qdrant=True)
    store = qdrant_mod.QdrantStore.__new__(qdrant_mod.QdrantStore)
    store.client = FakeClient()

    candidates = asyncio.run(store.search_clip([0.1, 0.2], query_type="clip_text", top_k=5))

    assert store.client.queries[0]["collection_name"] == qdrant_mod.CLIP_COLLECTION
    assert store.client.queries[0]["limit"] == 5
    assert candidates[0].sources == ["clip_text_search"]
    assert candidates[0].raw_clip_text_sim == 0.88
    assert candidates[0].clip_text_is_xmodal is True


def test_qdrant_store_geo_time_filters_by_district_and_skips_missing_location(import_service_module):
    qdrant_mod = import_service_module("embedding_service", "app.qdrant_client", qdrant=True)
    store = qdrant_mod.QdrantStore.__new__(qdrant_mod.QdrantStore)
    store.client = FakeClient()

    candidates = asyncio.run(
        store.search_geo_time(
            issue_type="road_damage",
            latitude=None,
            longitude=None,
            district="Beirut",
            since_iso="2026-01-01T00:00:00+00:00",
        )
    )
    filter_conditions = store.client.scrolls[0]["scroll_filter"].must
    assert any(getattr(condition, "key", None) == "district" for condition in filter_conditions)
    assert candidates[0].sources == ["geo_time_search"]

    store.client.scrolls.clear()
    assert asyncio.run(
        store.search_geo_time(
            issue_type="road_damage",
            latitude=None,
            longitude=None,
            district=None,
            since_iso="2026-01-01T00:00:00+00:00",
        )
    ) == []
    assert store.client.scrolls == []


def test_candidate_retriever_excludes_self_and_uses_active_sources(import_service_module):
    retrieval = import_service_module("embedding_service", "app.retrieval", qdrant=True)
    fake_qdrant = FakeQdrant()
    retriever = retrieval.CandidateRetriever(fake_qdrant)

    candidates = asyncio.run(
        retriever.retrieve(
            canonical=_canonical(),
            text_embedding=[0.1],
            image_embedding=[0.2],
            clip_text_embedding=[0.3],
            image_present=True,
        )
    )

    ids = {candidate.complaint_id for candidate in candidates}
    assert "self" not in ids
    assert {"text-hit", "clip-hit", "geo-hit"} <= ids
    assert ("clip_image", [0.2], retrieval.TOP_K) in fake_qdrant.calls


def test_candidate_retriever_skips_image_search_when_image_absent(import_service_module):
    retrieval = import_service_module("embedding_service", "app.retrieval", qdrant=True)
    fake_qdrant = FakeQdrant()
    retriever = retrieval.CandidateRetriever(fake_qdrant)

    asyncio.run(
        retriever.retrieve(
            canonical=_canonical(),
            text_embedding=[0.1],
            image_embedding=[0.2],
            clip_text_embedding=[0.3],
            image_present=False,
        )
    )

    call_names = [call[0] for call in fake_qdrant.calls]
    assert "clip_image" not in call_names
    assert call_names.count("clip_text") == 1

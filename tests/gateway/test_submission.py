from __future__ import annotations

import asyncio
import sys
import types

from cedarfix_shared.schemas import (
    ComplaintDecision,
    ComplaintSplitItem,
    ComplaintSplitResult,
)


def _install_gateway_main_import_stubs(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    python_multipart = types.ModuleType("python_multipart")
    python_multipart.__version__ = "0.0-test"
    multipart = types.ModuleType("multipart")
    multipart.__version__ = "0.0-test"
    multipart_sub = types.ModuleType("multipart.multipart")
    multipart_sub.parse_options_header = lambda _value: (b"", {})
    multipart.multipart = multipart_sub
    monkeypatch.setitem(sys.modules, "python_multipart", python_multipart)
    monkeypatch.setitem(sys.modules, "multipart", multipart)
    monkeypatch.setitem(sys.modules, "multipart.multipart", multipart_sub)

    import sqlalchemy.ext.asyncio as sqlalchemy_async

    class FakeAsyncConnection:
        async def run_sync(self, *_args, **_kwargs):
            return None

        async def execute(self, *_args, **_kwargs):
            return None

    class FakeBegin:
        async def __aenter__(self):
            return FakeAsyncConnection()

        async def __aexit__(self, *_args):
            return False

    class FakeAsyncEngine:
        def begin(self):
            return FakeBegin()

    monkeypatch.setattr(sqlalchemy_async, "create_async_engine", lambda *_args, **_kwargs: FakeAsyncEngine())


def _single_split(text: str) -> ComplaintSplitResult:
    return ComplaintSplitResult(
        original_text=text,
        is_multi=False,
        source="single",
        complaints=[ComplaintSplitItem(complaint_text=text, confidence=1.0)],
    )


def _multi_split(text: str) -> ComplaintSplitResult:
    return ComplaintSplitResult(
        original_text=text,
        is_multi=True,
        source="heuristic",
        complaints=[
            ComplaintSplitItem(complaint_text="Pothole blocking traffic near Hamra", confidence=0.8),
            ComplaintSplitItem(complaint_text="Garbage overflowing beside the school", confidence=0.8),
        ],
        confidence=0.8,
        review_reason="Heuristic split from explicit list/enumeration.",
    )


def test_submit_complaint_returns_single_submission_contract(import_service_module, monkeypatch):
    _install_gateway_main_import_stubs(monkeypatch)
    main = import_service_module("gateway", "app.main")
    calls = []

    async def normalize(**_kwargs):
        return {
            "normalized": "Verdun",
            "municipality": "Beirut",
            "district": "Beirut",
            "governorate": "Beirut Governorate",
            "latitude": 33.885,
            "longitude": 35.482,
            "source": "text_lookup",
            "confidence": 0.8,
        }

    async def split(text):
        return _single_split(text)

    async def run_pipeline(complaint_id, request):
        calls.append((complaint_id, request))
        return ComplaintDecision(
            complaint_id=complaint_id,
            original_text=request.text,
            user_id=request.user_id,
            location=request.location,
            location_input_mode=request.location_input_mode,
            split_source=request.split_source,
        )

    async def save_complaint(decision):
        saved.append(decision)

    async def save_retraining_record(decision):
        saved.append(("retrain", decision.complaint_id))

    saved = []
    monkeypatch.setattr(main.uuid, "uuid4", lambda: "submission-1")
    monkeypatch.setattr(main, "normalize_location", normalize)
    monkeypatch.setattr(main, "split_complaint_text", split)
    monkeypatch.setattr(main, "run_pipeline", run_pipeline)
    monkeypatch.setattr(main, "save_complaint", save_complaint)
    monkeypatch.setattr(main, "save_retraining_record", save_retraining_record)

    response = asyncio.run(
        main.submit_complaint(
            text="There is flooding on the road in Verdun",
            latitude=None,
            longitude=None,
            address_hint="Verdun",
            district=None,
            location_input_mode=None,
            user_id="form-user",
            image=None,
            current_user={"user_id": "auth-user"},
        )
    )

    assert response.submission_id == "submission-1"
    assert response.mode == "single"
    assert response.complaint_count == 1
    assert response.primary_decision.complaint_id == "submission-1"
    assert calls[0][1].user_id == "auth-user"
    assert calls[0][1].location_input_mode == "manual_text"
    assert calls[0][1].location.normalized == "Verdun"
    assert calls[0][1].location.municipality == "Beirut"
    assert saved[0].complaint_id == "submission-1"


def test_submit_complaint_links_multi_children_under_parent_submission(import_service_module, monkeypatch):
    _install_gateway_main_import_stubs(monkeypatch)
    main = import_service_module("gateway", "app.main")
    ids = iter(["submission-1", "child-1", "child-2"])
    calls = []

    async def split(text):
        return _multi_split(text)

    async def run_pipeline(complaint_id, request):
        calls.append((complaint_id, request))
        return ComplaintDecision(
            complaint_id=complaint_id,
            original_text=request.text,
            user_id=request.user_id,
            parent_submission_id=request.parent_submission_id,
            split_index=request.split_index,
            split_total=request.split_total,
            split_source=request.split_source,
            original_submission_text=request.original_submission_text,
        )

    async def save_complaint(decision):
        saved.append(decision)

    async def save_retraining_record(_decision):
        return None

    saved = []
    monkeypatch.setattr(main.uuid, "uuid4", lambda: next(ids))
    monkeypatch.setattr(main, "split_complaint_text", split)
    monkeypatch.setattr(main, "run_pipeline", run_pipeline)
    monkeypatch.setattr(main, "save_complaint", save_complaint)
    monkeypatch.setattr(main, "save_retraining_record", save_retraining_record)

    original = "1. Pothole blocking traffic near Hamra. 2. Garbage overflowing beside the school."
    response = asyncio.run(
        main.submit_complaint(
            text=original,
            latitude=None,
            longitude=None,
            address_hint=None,
            district=None,
            location_input_mode=None,
            user_id="anonymous",
            image=None,
            current_user=None,
        )
    )

    assert response.submission_id == "submission-1"
    assert response.mode == "multi"
    assert response.is_multi is True
    assert response.complaint_count == 2
    assert [decision.complaint_id for decision in response.complaints] == ["child-1", "child-2"]
    assert [request.parent_submission_id for _cid, request in calls] == ["submission-1", "submission-1"]
    assert [request.split_index for _cid, request in calls] == [1, 2]
    assert [request.split_total for _cid, request in calls] == [2, 2]
    assert all(request.original_submission_text == original for _cid, request in calls)
    assert [decision.complaint_id for decision in saved] == ["child-1", "child-2"]

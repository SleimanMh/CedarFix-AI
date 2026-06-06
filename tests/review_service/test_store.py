from __future__ import annotations

import asyncio
from datetime import datetime

from cedarfix_shared.schemas import AdminCorrection, RoutingEntity, SeverityLevel


class FakeMappings:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class FakeResult:
    def __init__(self, *, rows=None, scalar_value=None, row=None):
        self._rows = rows or []
        self._scalar = scalar_value
        self._row = row

    def mappings(self):
        return FakeMappings(self._rows)

    def scalar(self):
        return self._scalar

    def fetchone(self):
        return self._row


class FakeRow:
    def __init__(self, data):
        self._mapping = data


class FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.executed = []
        self.added = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params or {}))
        return self.results.pop(0)

    def add(self, record):
        self.added.append(record)

    def commit(self):
        self.committed = True


def _patch_session(monkeypatch, store, session):
    monkeypatch.setattr(store, "Session", lambda: session)


def test_get_review_queue_returns_serializable_rows(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    store = import_service_module("review_service", "app.store")
    session = FakeSession([
        FakeResult(rows=[{"id": 1, "complaint_type": "pothole", "routing_confidence": 0.4}])
    ])
    _patch_session(monkeypatch, store, session)

    result = asyncio.run(store.get_review_queue(limit=5))

    assert result == {"queue": [{"id": 1, "complaint_type": "pothole", "routing_confidence": 0.4}], "total": 1}
    assert session.executed[0][1] == {"limit": 5}


def test_add_and_resolve_human_review_items(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    store = import_service_module("review_service", "app.store")
    add_session = FakeSession([FakeResult(scalar_value=42)])
    _patch_session(monkeypatch, store, add_session)

    row_id = asyncio.run(
        store.add_human_review_item(
            complaint_id="c1",
            validation_status="human_review",
            review_reason="low confidence",
            original_text="broken pipe",
            image_filename=None,
            image_detected_type=None,
            text_detected_type="water_pipe",
        )
    )

    assert row_id == 42
    assert add_session.committed is True
    assert add_session.executed[0][1]["complaint_id"] == "c1"

    resolve_session = FakeSession([FakeResult()])
    _patch_session(monkeypatch, store, resolve_session)
    asyncio.run(store.resolve_human_review_item(42, "fixed", "admin"))
    assert resolve_session.committed is True
    assert resolve_session.executed[0][1] == {"id": 42, "notes": "fixed", "admin_id": "admin"}


def test_get_retraining_record_and_missing_record(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    store = import_service_module("review_service", "app.store")
    row = FakeRow({"complaint_id": "c1", "created_at": datetime(2026, 1, 1), "complaint_text": "x"})
    session = FakeSession([FakeResult(row=row)])
    _patch_session(monkeypatch, store, session)

    assert store.get_retraining_record("c1")["complaint_id"] == "c1"

    empty_session = FakeSession([FakeResult(row=None)])
    _patch_session(monkeypatch, store, empty_session)
    assert store.get_retraining_record("missing") is None


def test_retraining_queue_export_and_save_review(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    store = import_service_module("review_service", "app.store")
    queue_session = FakeSession([
        FakeResult(rows=[{"id": 1, "complaint_id": "c1"}]),
        FakeResult(scalar_value=1),
    ])
    _patch_session(monkeypatch, store, queue_session)
    assert store.get_retraining_queue(limit=10, offset=5)["total"] == 1

    export_session = FakeSession([
        FakeResult(rows=[{"id": 1, "complaint_id": "c1"}]),
        FakeResult(),
    ])
    _patch_session(monkeypatch, store, export_session)
    exported = store.get_retraining_export(mark_exported=True)
    assert exported["total"] == 1
    assert export_session.committed is True

    review_session = FakeSession([FakeResult()])
    _patch_session(monkeypatch, store, review_session)
    store.save_retraining_review(
        complaint_id="c1",
        admin_id="admin",
        admin_decision="can_be_processed",
        admin_notes="ok",
        corrected_text_json={"issue_type": "pothole"},
        corrected_image_json=None,
        corrected_rag_response={"entity": "MPWT"},
    )
    params = review_session.executed[0][1]
    assert params["usable"] is True
    assert params["text_json"] == '{"issue_type": "pothole"}'


def test_save_correction_persists_model_and_marks_complaint(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    store = import_service_module("review_service", "app.store")
    session = FakeSession([FakeResult()])
    _patch_session(monkeypatch, store, session)
    correction = AdminCorrection(
        complaint_id="original",
        admin_id="admin",
        corrected_routing=RoutingEntity.OGERO,
        corrected_severity=SeverityLevel.HIGH,
    )

    asyncio.run(store.save_correction(correction))

    assert session.added[0].complaint_id == "original"
    assert session.added[0].admin_id == "admin"
    assert session.committed is True


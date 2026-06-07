from __future__ import annotations

import asyncio
import sys
import types

import pytest
from pydantic import ValidationError

from cedarfix_shared import location, storage
from cedarfix_shared.schemas import (
    ComplaintDecision,
    ComplaintRequest,
    ComplaintSplitItem,
    ComplaintSplitResult,
    ComplaintSubmissionResponse,
    LocationInput,
    PriorityResult,
    RoutingEntity,
    RoutingResult,
    SeverityLevel,
)


def test_location_input_rejects_out_of_range_coordinates():
    with pytest.raises(ValidationError):
        LocationInput(latitude=91, longitude=35)
    with pytest.raises(ValidationError):
        LocationInput(latitude=33, longitude=-181)
    manual = LocationInput(address_hint="Verdun", normalized="Verdun", municipality="Beirut")
    assert manual.latitude is None
    assert manual.normalized == "Verdun"


def test_complaint_request_enforces_text_length():
    with pytest.raises(ValidationError):
        ComplaintRequest(text="too short")
    request = ComplaintRequest(text="Large pothole on Hamra main road")
    assert request.text.startswith("Large pothole")


def test_split_submission_schemas_preserve_parent_child_contract():
    split = ComplaintSplitResult(
        original_text="1. pothole near Hamra 2. garbage near school",
        is_multi=True,
        source="heuristic",
        complaints=[
            ComplaintSplitItem(complaint_text="Large pothole near Hamra"),
            ComplaintSplitItem(complaint_text="Garbage overflowing near school"),
        ],
    )
    first = ComplaintDecision(
        complaint_id="child-1",
        original_text="Large pothole near Hamra",
        parent_submission_id="submission-1",
        split_index=1,
        split_total=2,
        split_source="heuristic",
        original_submission_text=split.original_text,
    )
    second = ComplaintDecision(
        complaint_id="child-2",
        original_text="Garbage overflowing near school",
        parent_submission_id="submission-1",
        split_index=2,
        split_total=2,
        split_source="heuristic",
        original_submission_text=split.original_text,
    )
    response = ComplaintSubmissionResponse(
        submission_id="submission-1",
        mode="multi",
        is_multi=True,
        complaint_count=2,
        split_result=split,
        complaints=[first, second],
        primary_decision=first,
    )

    assert response.primary_decision.parent_submission_id == "submission-1"
    assert response.split_result.complaints[1].complaint_text == "Garbage overflowing near school"
    assert response.complaints[0].split_index == 1


def test_result_schemas_validate_confidence_bounds():
    with pytest.raises(ValidationError):
        PriorityResult(
            complaint_id="c1",
            severity=SeverityLevel.LOW,
            priority_score=1.2,
            confidence=0.8,
            processing_ms=0,
        )

    result = RoutingResult(
        complaint_id="c1",
        primary_entity=RoutingEntity.HUMAN_REVIEW,
        primary_confidence=0.0,
        auto_routed=False,
        requires_review=True,
        processing_ms=0,
    )
    assert result.primary_entity == RoutingEntity.HUMAN_REVIEW


def test_storage_backend_defaults_and_env_override(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    assert storage.storage_backend() == "local"

    monkeypatch.setenv("GCS_BUCKET", "cedarfix-images")
    assert storage.storage_backend() == "gcs"

    monkeypatch.setenv("STORAGE_BACKEND", "local")
    assert storage.storage_backend() == "local"


def test_local_storage_roundtrip_and_filename_safety(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    ref = storage.save_image_ref("../unsafe.jpg", b"img", uploads_dir=str(tmp_path))
    assert ref == "local://unsafe.jpg"
    assert storage.read_image_bytes(ref, uploads_dir=str(tmp_path)) == b"img"
    assert storage.local_image_path(ref, uploads_dir=str(tmp_path)) == tmp_path / "unsafe.jpg"

    with pytest.raises(ValueError):
        storage.save_image_ref("..", b"bad", uploads_dir=str(tmp_path))


def test_gcs_reference_helpers(monkeypatch):
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    assert storage._gcs_bucket_name("gcs://bucket-name/complaints/a.jpg") == "bucket-name"
    assert storage._gcs_object_name("gcs://bucket-name/complaints/a.jpg") == "complaints/a.jpg"
    with pytest.raises(RuntimeError):
        storage._gcs_bucket_name()


class FakeBlob:
    objects = {}

    def __init__(self, bucket_name, object_name):
        self.bucket_name = bucket_name
        self.object_name = object_name

    def upload_from_string(self, data, content_type):
        self.objects[(self.bucket_name, self.object_name)] = {
            "data": data,
            "content_type": content_type,
        }

    def download_as_bytes(self):
        return self.objects[(self.bucket_name, self.object_name)]["data"]

    def generate_signed_url(self, expiration, method, version):
        assert method == "GET"
        assert version == "v4"
        assert int(expiration.total_seconds()) == 60
        return f"https://signed.example/{self.bucket_name}/{self.object_name}"


class FakeBucket:
    def __init__(self, name):
        self.name = name

    def blob(self, object_name):
        return FakeBlob(self.name, object_name)


class FakeClient:
    def bucket(self, name):
        return FakeBucket(name)


def _install_fake_gcs(monkeypatch):
    google = types.ModuleType("google")
    cloud = types.ModuleType("google.cloud")
    gcs = types.ModuleType("google.cloud.storage")
    gcs.Client = FakeClient
    cloud.storage = gcs
    google.cloud = cloud
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", gcs)


def test_gcs_storage_save_read_and_signed_url(monkeypatch):
    _install_fake_gcs(monkeypatch)
    FakeBlob.objects.clear()
    monkeypatch.setenv("STORAGE_BACKEND", "gcs")
    monkeypatch.setenv("GCS_BUCKET", "cedarfix-images")

    ref = storage.save_image_ref("../unsafe.png", b"image-bytes", content_type="image/png")

    assert ref == "gcs://cedarfix-images/complaints/unsafe.png"
    assert FakeBlob.objects[("cedarfix-images", "complaints/unsafe.png")]["content_type"] == "image/png"
    assert storage.read_image_bytes(ref) == b"image-bytes"
    assert storage.signed_image_url(ref, expiration_seconds=60) == (
        "https://signed.example/cedarfix-images/complaints/unsafe.png"
    )


def test_location_lookup_exact_substring_and_fuzzy():
    assert location.lookup_text("hamra")["name"] == "Hamra"
    assert location.lookup_text("broken pipe near mar mikhael street")["name"] == "Mar Mikhael"
    assert location.lookup_text("achrafieh", min_score=0.70)["name"] == "Ashrafieh"
    assert location.lookup_text("not a known place", min_score=0.95) is None


def test_normalize_location_priority_paths(monkeypatch):
    async def no_reverse(_lat, _lng):
        return None

    monkeypatch.setattr(location, "reverse_geocode", no_reverse)

    gps = asyncio.run(location.normalize_location(lat=33.8938, lng=35.4881))
    assert gps["normalized"] == "Hamra"
    assert gps["source"] == "gps"

    raw = asyncio.run(location.normalize_location(raw_text="water leak in Verdun"))
    assert raw["normalized"] == "Verdun"
    assert raw["municipality"] == "Beirut"
    assert raw["source"] == "text_lookup"

    hint = asyncio.run(location.normalize_location(user_hint="Tripoli"))
    assert hint["district"] == "Tripoli"
    assert hint["source"] == "user_hint"

    llm = asyncio.run(
        location.normalize_location(
            raw_text="somewhere",
            llm_extracted_district="Unknown District",
            llm_extracted_governorate="Unknown Governorate",
            llm_confidence=0.9,
        )
    )
    assert llm["source"] == "llm_extracted"
    assert llm["confidence"] == 0.65

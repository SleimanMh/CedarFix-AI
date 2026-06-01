"""EEP request / response schemas.

These are *transport* schemas for the HTTP API — separate from the SQLAlchemy
models in db.py and from the shared IEP1LanguageSignal contract in
src/shared/schemas.py.
"""
from __future__ import annotations

import base64
import binascii
import json
from functools import lru_cache
from pathlib import Path
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


ROOT = Path(__file__).resolve().parents[2]
GPS_BOUNDS_PATH = ROOT / "data" / "knowledge_base" / "gps_bounds.json"


@lru_cache(maxsize=1)
def _load_gps_bounds() -> dict:
    return json.loads(GPS_BOUNDS_PATH.read_text(encoding="utf-8"))["lebanon"]
VALID_LANGUAGE_HINTS = {"ar", "arabizi", "en", "fr", "mixed"}


class ComplaintState(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    PARTIALLY_PROCESSED = "PARTIALLY_PROCESSED"
    FULLY_PROCESSED = "FULLY_PROCESSED"
    ROUTED = "ROUTED"
    AUTO_ROUTED = "AUTO_ROUTED"
    HITL_REQUIRED = "HITL_REQUIRED"
    HITL_IN_REVIEW = "HITL_IN_REVIEW"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class ComplaintRequest(BaseModel):
    """Citizen complaint submission payload."""

    text: str = Field(..., min_length=5, max_length=2000)
    image_b64: Optional[str] = Field(
        None,
        description="Base64-encoded JPEG or PNG, decoded size must be ≤ 4 MB.",
    )
    gps_lat: Optional[float] = Field(None, ge=-90.0, le=90.0)
    gps_lon: Optional[float] = Field(None, ge=-180.0, le=180.0)
    language_hint: Optional[str] = Field(
        None,
        description="Caller-supplied ISO hint: ar, en, fr, arabizi, mixed.",
        max_length=16,
    )

    @field_validator("image_b64")
    @classmethod
    def _check_image_size(cls, v: Optional[str]) -> Optional[str]:
        # base64 is ~4/3× the binary size; 4 MB decoded ≈ 5.5 MB base64
        if v is None:
            return v
        if len(v) > 5_500_000:
            raise ValueError("image_b64 exceeds the 4 MB decoded size limit")
        try:
            decoded = base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image_b64 must be valid base64") from exc
        if len(decoded) > 4_000_000:
            raise ValueError("image_b64 exceeds the 4 MB decoded size limit")
        if not (decoded.startswith(b"\xff\xd8\xff") or decoded.startswith(b"\x89PNG\r\n\x1a\n")):
            raise ValueError("image_b64 must decode to JPEG or PNG bytes")
        return v

    @field_validator("language_hint")
    @classmethod
    def _check_language_hint(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        lowered = v.strip().lower()
        if lowered not in VALID_LANGUAGE_HINTS:
            raise ValueError(f"language_hint must be one of {sorted(VALID_LANGUAGE_HINTS)}")
        return lowered

    @model_validator(mode="after")
    def _check_gps_pair_and_lebanon_bounds(self) -> "ComplaintRequest":
        if (self.gps_lat is None) ^ (self.gps_lon is None):
            raise ValueError("gps_lat and gps_lon must be provided together")
        if self.gps_lat is None or self.gps_lon is None:
            return self
        bounds = _load_gps_bounds()
        if not (bounds["lat_min"] <= self.gps_lat <= bounds["lat_max"]):
            raise ValueError("gps_lat is outside Lebanon bounds")
        if not (bounds["lon_min"] <= self.gps_lon <= bounds["lon_max"]):
            raise ValueError("gps_lon is outside Lebanon bounds")
        return self


class ComplaintAccepted(BaseModel):
    """202 Accepted response body."""

    complaint_id: str
    status: ComplaintState = ComplaintState.PROCESSING
    status_url: str


class ComplaintStatus(BaseModel):
    """Full pipeline status for GET /complaints/{id}/status."""

    complaint_id: str
    status: ComplaintState

    # IEP-1 fields
    language: Optional[str] = None
    language_confidence: Optional[float] = None
    drift_score: Optional[int] = None
    issue_type: Optional[str] = None
    issue_type_confidence: Optional[float] = None
    iep1_signal_json: Optional[dict] = None

    # IEP-2 fields
    is_duplicate: Optional[bool] = None
    incident_id: Optional[str] = None
    iep2_incident_json: Optional[dict] = None

    # IEP-6 fields
    image_issue_type: Optional[str] = None
    image_fusion_json: Optional[dict] = None

    # IEP-3 fields
    routing_sector: Optional[str] = None
    routing_entity: Optional[str] = None
    routing_confidence: Optional[float] = None
    priority_score: Optional[float] = None
    hitl_required: Optional[bool] = None
    hitl_reason: Optional[str] = None
    iep3_routing_json: Optional[dict] = None

    # IEP-4 fields
    citizen_explanation: Optional[str] = None
    admin_explanation: Optional[str] = None
    iep4_explanation_json: Optional[dict] = None

    error_flags: list[str] = Field(default_factory=list)


# ── Dossier (AI decision trace) ───────────────────────────────────────────────

class DossierLayer(BaseModel):
    """A single AI layer's decision trace within the full dossier."""
    layer: str
    decision: Optional[str] = None
    confidence: Optional[float] = None
    evidence: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)


class ComplaintDossier(BaseModel):
    """Full AI decision dossier for GET /complaints/{id}/dossier."""
    complaint_id: str
    status: ComplaintState
    submitted_text: str
    pipeline_complete: bool
    layers: list[DossierLayer] = Field(default_factory=list)
    final_sector: Optional[str] = None
    final_entity: Optional[str] = None
    final_decision: str = "PENDING"
    hitl_reason: Optional[str] = None
    routing_confidence: Optional[float] = None
    drift_score: Optional[int] = None
    priority_score: Optional[float] = None


# ── Active learning feedback ───────────────────────────────────────────────────

class ComplaintFeedback(BaseModel):
    """Human correction submitted via POST /complaints/{id}/feedback.

    The human reviewer (operator or HITL agent) provides the corrected routing
    decision.  The EEP persists a RetrainingCandidate record so that periodic
    model retraining can incorporate the correction.
    """
    corrected_sector: Optional[str] = Field(
        None, description="Sector the reviewer believes is correct (e.g. 'WATER')."
    )
    corrected_entity: Optional[str] = Field(
        None, description="Primary entity the reviewer selected (e.g. 'BWE')."
    )
    correction_notes: Optional[str] = Field(
        None,
        max_length=512,
        description="Free-text notes from the reviewer explaining the correction.",
    )
    reviewer_id: Optional[str] = Field(
        None,
        max_length=64,
        description="Identifier for the human reviewer (anonymised).",
    )


class RetrainingQueueItem(BaseModel):
    """One entry in the active learning retraining queue."""
    candidate_id: str
    complaint_id: str
    source: str
    reason: Optional[str] = None
    original_routing: Optional[dict] = None
    status: str
    created_at: str


class RetrainingQueue(BaseModel):
    """Response body for GET /retraining-queue."""
    count: int
    items: list[RetrainingQueueItem]


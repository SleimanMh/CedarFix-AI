"""EEP request / response schemas.

These are *transport* schemas for the HTTP API — separate from the SQLAlchemy
models in db.py and from the shared IEP1LanguageSignal contract in
src/shared/schemas.py.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ComplaintState(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    PARTIALLY_PROCESSED = "PARTIALLY_PROCESSED"
    FULLY_PROCESSED = "FULLY_PROCESSED"
    ROUTED = "ROUTED"
    HITL_REQUIRED = "HITL_REQUIRED"
    RESOLVED = "RESOLVED"
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
        if v is not None and len(v) > 5_500_000:
            raise ValueError("image_b64 exceeds the 4 MB decoded size limit")
        return v


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

    # IEP-2 fields
    is_duplicate: Optional[bool] = None
    incident_id: Optional[str] = None

    # IEP-3 fields
    routing_sector: Optional[str] = None
    routing_entity: Optional[str] = None
    routing_confidence: Optional[float] = None
    priority_score: Optional[float] = None
    hitl_required: Optional[bool] = None
    hitl_reason: Optional[str] = None

    # IEP-4 fields
    citizen_explanation: Optional[str] = None

    error_flags: list[str] = Field(default_factory=list)

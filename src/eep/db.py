"""Async SQLAlchemy setup and Complaint ORM model.

The single Complaint table is owned by EEP and written to by all IEPs.
IEPs never expose their own DB — they write back via the shared table.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text, func, inspect, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://cedarfix:cedarfix@localhost:5432/cedarfix",
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True, pool_size=10)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Complaint(Base):
    __tablename__ = "complaints"

    # ── Identity ─────────────────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="RECEIVED")

    # ── Ingestion fields (written by EEP on submit) ───────────────────────────
    text_raw: Mapped[str] = mapped_column(Text, nullable=False)
    image_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    language_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # ── IEP-1 outputs ─────────────────────────────────────────────────────────
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    language_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    drift_score: Mapped[int | None] = mapped_column(nullable=True)
    issue_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    issue_type_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_embedding_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    text_embedding_vector: Mapped[list | None] = mapped_column(JSON, nullable=True)
    iep1_signal_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── IEP-2 outputs ─────────────────────────────────────────────────────────
    is_duplicate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    incident_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    iep2_incident_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    image_issue_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ── IEP-6 image fusion output ──────────────────────────────────────────────
    image_fusion_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── IEP-3 outputs ─────────────────────────────────────────────────────────
    routing_sector: Mapped[str | None] = mapped_column(String(32), nullable=True)
    routing_entity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    routing_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hitl_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    hitl_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shap_top3: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    iep3_routing_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── IEP-4 outputs ─────────────────────────────────────────────────────────
    citizen_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    iep4_explanation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── IEP-8 grounded resolution co-pilot ────────────────────────────────────
    iep8_resolution_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Audit / operations ────────────────────────────────────────────────────
    error_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Incident(Base):
    """Current-state projection of an incident cluster (owned by IEP-5)."""

    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    current_state: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    complaint_count: Mapped[int] = mapped_column(default=0, nullable=False)
    reopen_count: Mapped[int] = mapped_column(default=0, nullable=False)
    routing_sector: Mapped[str | None] = mapped_column(String(32), nullable=True)
    routing_entity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_routing_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class IncidentLifecycleEvent(Base):
    """Append-only lifecycle transition log (event-sourced history)."""

    __tablename__ = "incident_lifecycle_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    incident_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    complaint_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RetrainingCandidate(Base):
    """Captured signal that the model should be retrained (reopen/drift/oov)."""

    __tablename__ = "retraining_candidates"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    complaint_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    incident_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    original_routing: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CalibrationMetric(Base):
    """Per-sector calibration snapshot written by IEP-7."""

    __tablename__ = "calibration_metrics"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    sector: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    n: Mapped[int] = mapped_column(default=0, nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mean_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ece: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    brier: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bins_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


async def init_db() -> None:
    """Create tables on first startup. Idempotent."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_runtime_columns)


def _ensure_runtime_columns(sync_conn) -> None:
    """Add JSON columns introduced after the initial demo schema."""
    columns = {column["name"] for column in inspect(sync_conn).get_columns("complaints")}
    json_type = "JSONB" if sync_conn.dialect.name == "postgresql" else "JSON"
    missing_columns = {
        "text_embedding_vector": json_type,
        "iep2_incident_json": json_type,
        "iep3_routing_json": json_type,
        "image_fusion_json": json_type,
        "iep4_explanation_json": json_type,
        "iep8_resolution_json": json_type,
    }
    for column_name, column_type in missing_columns.items():
        if column_name not in columns:
            sync_conn.execute(text(f"ALTER TABLE complaints ADD COLUMN {column_name} {column_type}"))


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session

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

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text, func, update
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
    iep1_signal_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── IEP-2 outputs ─────────────────────────────────────────────────────────
    is_duplicate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    incident_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    image_issue_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ── IEP-3 outputs ─────────────────────────────────────────────────────────
    routing_sector: Mapped[str | None] = mapped_column(String(32), nullable=True)
    routing_entity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    routing_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hitl_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    hitl_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shap_top3: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── IEP-4 outputs ─────────────────────────────────────────────────────────
    citizen_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

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


async def init_db() -> None:
    """Create tables on first startup. Idempotent."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session

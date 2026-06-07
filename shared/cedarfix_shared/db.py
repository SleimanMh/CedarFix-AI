"""
SQLAlchemy database models — PostgreSQL schema for CedarFix AI.
Each table corresponds to a stage in the pipeline.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, Text, JSON, Enum as SAEnum
)
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://cedarfix:cedarfix_secret@postgres:5432/cedarfix")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------

class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    status = Column(String, default="pending")

    # Raw input
    original_text = Column(Text, nullable=False)
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)
    location_district = Column(String, nullable=True)
    image_filename = Column(String, nullable=True)
    user_id = Column(String, nullable=True)
    parent_submission_id = Column(String, nullable=True)
    split_index = Column(Integer, nullable=True)
    split_total = Column(Integer, nullable=True)

    # IEP-1 results
    detected_language = Column(String, nullable=True)
    complaint_type = Column(String, nullable=True)
    complaint_type_confidence = Column(Float, nullable=True)
    extracted_keywords = Column(JSON, nullable=True)
    location_mentions = Column(JSON, nullable=True)
    qdrant_point_id = Column(String, nullable=True)

    # IEP-4 results
    duplicate_status = Column(String, default="NEW")
    duplicate_of = Column(String, nullable=True)
    cluster_id = Column(String, nullable=True)
    escalation_signal = Column(Boolean, default=False)

    # IEP-5 results
    severity = Column(String, nullable=True)
    priority_score = Column(Float, nullable=True)

    # IEP-6 results
    assigned_entity = Column(String, nullable=True)
    routing_confidence = Column(Float, nullable=True)
    auto_routed = Column(Boolean, nullable=True)
    requires_review = Column(Boolean, default=False)

    # Metadata
    total_pipeline_ms = Column(Integer, nullable=True)
    full_decision_json = Column(JSON, nullable=True)  # Full ComplaintDecision snapshot


class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    complaint_type = Column(String, nullable=True)
    dominant_district = Column(String, nullable=True)
    member_count = Column(Integer, default=0)
    trend = Column(String, default="stable")
    last_run_at = Column(DateTime, nullable=True)


class AdminCorrection(Base):
    __tablename__ = "admin_corrections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    complaint_id = Column(String, nullable=False)
    admin_id = Column(String, nullable=False)
    correction_timestamp = Column(DateTime, default=_utcnow)
    corrected_routing = Column(String, nullable=True)
    corrected_severity = Column(String, nullable=True)
    corrected_complaint_type = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    applied_to_training = Column(Boolean, default=False)


class ModelPerformanceLog(Base):
    __tablename__ = "model_performance_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    logged_at = Column(DateTime, default=_utcnow)
    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=True)
    metric_name = Column(String, nullable=False)
    metric_value = Column(Float, nullable=False)
    window_days = Column(Integer, default=7)

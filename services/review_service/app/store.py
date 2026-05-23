"""Database operations for the review service."""

import os
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from cedarfix_shared.db import AdminCorrection as AdminCorrectionModel, SessionLocal
from cedarfix_shared.schemas import AdminCorrection

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://cedarfix:cedarfix_secret@postgres:5432/cedarfix")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)


async def get_review_queue(limit: int = 20):
    with Session() as session:
        result = session.execute(
            text("""
                SELECT id, complaint_type, severity, assigned_entity, routing_confidence,
                       original_text, created_at
                FROM complaints
                WHERE requires_review = TRUE
                  AND status != 'corrected'
                ORDER BY routing_confidence ASC NULLS LAST
                LIMIT :limit
            """),
            {"limit": limit},
        )
        rows = result.mappings().all()
        return {"queue": [dict(r) for r in rows], "total": len(rows)}


async def save_correction(correction: AdminCorrection):
    with Session() as session:
        record = AdminCorrectionModel(
            complaint_id=correction.complaint_id,
            admin_id=correction.admin_id,
            corrected_routing=correction.corrected_routing,
            corrected_severity=correction.corrected_severity,
            corrected_complaint_type=correction.corrected_complaint_type,
            notes=correction.notes,
        )
        session.add(record)

        # Mark complaint as having received a correction
        session.execute(
            text("UPDATE complaints SET status = 'corrected' WHERE id = :id"),
            {"id": correction.complaint_id},
        )
        session.commit()


# ---------------------------------------------------------------------------
# Human Review Queue
# ---------------------------------------------------------------------------

async def add_human_review_item(
    complaint_id: str,
    validation_status: str,
    review_reason: str,
    original_text: str,
    image_filename: Optional[str],
    image_detected_type: Optional[str],
    text_detected_type: Optional[str],
) -> int:
    with Session() as session:
        result = session.execute(
            text("""
                INSERT INTO human_review_queue
                    (complaint_id, validation_status, review_reason, original_text,
                     image_filename, image_detected_type, text_detected_type)
                VALUES
                    (:complaint_id, :validation_status, :review_reason, :original_text,
                     :image_filename, :image_detected_type, :text_detected_type)
                RETURNING id
            """),
            {
                "complaint_id": complaint_id,
                "validation_status": validation_status,
                "review_reason": review_reason,
                "original_text": original_text,
                "image_filename": image_filename,
                "image_detected_type": image_detected_type,
                "text_detected_type": text_detected_type,
            },
        )
        row_id = result.scalar()
        session.commit()
        return row_id


async def get_human_review_queue(limit: int = 50):
    with Session() as session:
        result = session.execute(
            text("""
                SELECT id, complaint_id, validation_status, review_reason,
                       original_text, image_filename, image_detected_type,
                       text_detected_type, resolved, resolution_notes,
                       resolved_by, created_at, resolved_at
                FROM human_review_queue
                WHERE resolved = FALSE
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )
        rows = result.mappings().all()
        return {"queue": [dict(r) for r in rows], "total": len(rows)}


async def resolve_human_review_item(item_id: int, resolution_notes: str, admin_id: str):
    with Session() as session:
        session.execute(
            text("""
                UPDATE human_review_queue
                SET resolved = TRUE,
                    resolution_notes = :notes,
                    resolved_at = NOW(),
                    resolved_by = :admin_id
                WHERE id = :id
            """),
            {"id": item_id, "notes": resolution_notes, "admin_id": admin_id},
        )
        session.commit()

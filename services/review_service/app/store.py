"""Database operations for the review service."""

import os
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

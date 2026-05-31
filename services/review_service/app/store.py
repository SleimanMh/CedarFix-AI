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


# ---------------------------------------------------------------------------
# Retraining Store
# ---------------------------------------------------------------------------

import json as _json
from typing import List


def get_retraining_queue(
    pending_only: bool = True,
    rag_no_match_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    filters = []
    if pending_only:
        filters.append("admin_reviewed = FALSE")
    if rag_no_match_only:
        filters.append("rag_no_match = TRUE")
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with Session() as session:
        result = session.execute(
            text(f"""
                SELECT id, complaint_id, created_at, complaint_text, image_filename,
                       pipeline_status, rag_no_match, hitl_flag_reason,
                       admin_reviewed, admin_decision, admin_notes,
                       usable_for_finetuning, finetuning_exported
                FROM retraining_store
                {where}
                ORDER BY created_at DESC
                LIMIT :lim OFFSET :off
            """),
            {"lim": limit, "off": offset},
        )
        rows = result.mappings().all()
        total_result = session.execute(
            text(f"SELECT COUNT(*) FROM retraining_store {where}")
        )
        total = total_result.scalar() or 0
    return {"records": [dict(r) for r in rows], "total": total}


def get_retraining_record(complaint_id: str) -> Optional[dict]:
    with Session() as session:
        result = session.execute(
            text("""
                SELECT id, complaint_id, created_at, complaint_text, image_filename,
                       text_classification_json, image_classification_json,
                       rag_routing_response, pipeline_status,
                       rag_no_match, hitl_flag_reason,
                       admin_reviewed, admin_reviewed_at, admin_reviewed_by,
                       admin_decision, admin_notes,
                       corrected_text_json, corrected_image_json, corrected_rag_response,
                       usable_for_finetuning, finetuning_exported
                FROM retraining_store
                WHERE complaint_id = :cid
            """),
            {"cid": complaint_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return dict(row._mapping)


def save_retraining_review(
    complaint_id: str,
    admin_id: str,
    admin_decision: str,
    admin_notes: Optional[str],
    corrected_text_json: Optional[dict],
    corrected_image_json: Optional[dict],
    corrected_rag_response: Optional[dict],
) -> None:
    usable = admin_decision == "can_be_processed"
    with Session() as session:
        session.execute(
            text("""
                UPDATE retraining_store
                SET admin_reviewed        = TRUE,
                    admin_reviewed_at     = NOW(),
                    admin_reviewed_by     = :admin_id,
                    admin_decision        = :decision,
                    admin_notes           = :notes,
                    corrected_text_json   = :text_json,
                    corrected_image_json  = :image_json,
                    corrected_rag_response = :rag_json,
                    usable_for_finetuning = :usable
                WHERE complaint_id = :cid
            """),
            {
                "cid":      complaint_id,
                "admin_id": admin_id,
                "decision": admin_decision,
                "notes":    admin_notes,
                "text_json":  _json.dumps(corrected_text_json)  if corrected_text_json  else None,
                "image_json": _json.dumps(corrected_image_json) if corrected_image_json else None,
                "rag_json":   _json.dumps(corrected_rag_response) if corrected_rag_response else None,
                "usable":   usable,
            },
        )
        session.commit()


def get_retraining_export(mark_exported: bool = False) -> dict:
    with Session() as session:
        result = session.execute(
            text("""
                SELECT id, complaint_id, created_at, complaint_text, image_filename,
                       text_classification_json, image_classification_json,
                       rag_routing_response, pipeline_status,
                       rag_no_match, hitl_flag_reason,
                       admin_reviewed_by, admin_decision, admin_notes,
                       corrected_text_json, corrected_image_json, corrected_rag_response
                FROM retraining_store
                WHERE usable_for_finetuning = TRUE
                  AND finetuning_exported   = FALSE
                ORDER BY created_at ASC
            """)
        )
        rows = result.mappings().all()
        records = [dict(r) for r in rows]

        if mark_exported and records:
            ids = [r["id"] for r in records]
            session.execute(
                text(
                    "UPDATE retraining_store SET finetuning_exported = TRUE "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": ids},
            )
            session.commit()

    return {"records": records, "total": len(records)}

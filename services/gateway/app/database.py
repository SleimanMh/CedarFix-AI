"""Database helpers for the Gateway service."""

import json
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from cedarfix_shared.db import Base
from cedarfix_shared.schemas import ComplaintDecision, PipelineStatus
from .config import settings

# Use asyncpg for async Postgres support in the gateway
async_db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
async_engine = create_async_engine(async_db_url, echo=False)
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255)"))
        await conn.execute(text("ALTER TABLE complaints ADD COLUMN IF NOT EXISTS parent_submission_id VARCHAR(36)"))
        await conn.execute(text("ALTER TABLE complaints ADD COLUMN IF NOT EXISTS split_index INTEGER"))
        await conn.execute(text("ALTER TABLE complaints ADD COLUMN IF NOT EXISTS split_total INTEGER"))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_complaints_parent_submission_id
            ON complaints(parent_submission_id)
        """))
        # Dedicated store for admin-edited review outcomes and corrected JSON payloads.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS admin_review_edits (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT NOW(),
                review_item_id INTEGER,
                complaint_id VARCHAR(36) NOT NULL,
                admin_id VARCHAR(100) NOT NULL,
                resolution_notes TEXT,
                admin_decision VARCHAR(50),
                image_text_match BOOLEAN,
                text_llm_json JSONB,
                image_llm_json JSONB,
                routing_json JSONB
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS moderation_text_hashes (
                text_hash VARCHAR(64) PRIMARY KEY,
                first_seen_at TIMESTAMP DEFAULT NOW(),
                last_seen_at TIMESTAMP DEFAULT NOW(),
                seen_count INTEGER DEFAULT 1,
                last_user_id VARCHAR(100)
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_moderation_text_hashes_last_seen
            ON moderation_text_hashes(last_seen_at)
        """))

    await _try_create_unique_index(
        "idx_users_username_lower",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_lower
        ON users (LOWER(username))
        """,
    )
    await _try_create_unique_index(
        "idx_users_email_lower",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower
        ON users (LOWER(email))
        WHERE email IS NOT NULL
        """,
    )


async def _try_create_unique_index(name: str, sql: str) -> None:
    try:
        async with async_engine.begin() as conn:
            await conn.execute(text(sql))
    except Exception as exc:
        print(f"[WARN] Skipping optional unique index {name}: {exc}")


async def save_complaint(decision: ComplaintDecision):
    from cedarfix_shared.db import Complaint
    status_value = decision.status.value if hasattr(decision.status, "value") else str(decision.status)
    requires_review = (
        status_value == PipelineStatus.REVIEW_REQUIRED.value
        or (
            (decision.routing.requires_review or decision.routing.rag_no_candidates)
            if decision.routing else False
        )
    )
    async with AsyncSessionLocal() as session:
        record = Complaint(
            id=decision.complaint_id,
            user_id=decision.user_id,
            status=decision.status,
            original_text=decision.original_text,
            location_lat=decision.location.latitude if decision.location else None,
            location_lng=decision.location.longitude if decision.location else None,
            location_district=decision.location.district if decision.location else None,
            image_filename=decision.image_filename,
            parent_submission_id=decision.parent_submission_id,
            split_index=decision.split_index,
            split_total=decision.split_total,
            detected_language=decision.text_analysis.language if decision.text_analysis else None,
            complaint_type=decision.complaint_type,
            complaint_type_confidence=decision.text_analysis.confidence if decision.text_analysis else None,
            extracted_keywords=decision.text_analysis.urgency_keywords if decision.text_analysis else [],
            duplicate_status=decision.clustering.duplicate_status if decision.clustering else "NEW",
            duplicate_of=decision.clustering.duplicate_of if decision.clustering else None,
            cluster_id=decision.clustering.cluster_id if decision.clustering else None,
            severity=decision.severity,
            priority_score=decision.priority_score,
            assigned_entity=decision.assigned_entity,
            routing_confidence=decision.routing_confidence,
            auto_routed=decision.routing.auto_routed if decision.routing else None,
            requires_review=requires_review,
            total_pipeline_ms=decision.total_pipeline_ms,
            full_decision_json=json.loads(decision.json()),
        )
        await session.merge(record)
        await session.commit()


async def fetch_complaint(complaint_id: str):
    from sqlalchemy import select
    from cedarfix_shared.db import Complaint
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Complaint).where(Complaint.id == complaint_id))
        row = result.scalar_one_or_none()
        if row and row.full_decision_json:
            return ComplaintDecision(**row.full_decision_json)
        return None


# ---------------------------------------------------------------------------
# User authentication
# ---------------------------------------------------------------------------

async def create_user(username: str, email: str, password_hash: str, role: str = "user") -> Optional[dict]:
    username = normalize_username(username)
    email = normalize_email(email)
    user_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "INSERT INTO users (id, username, email, password_hash, role) "
                "VALUES (:id, :username, :email, :password_hash, :role) "
                "ON CONFLICT DO NOTHING "
                "RETURNING id, username, email, role"
            ),
            {"id": user_id, "username": username, "email": email, "password_hash": password_hash, "role": role},
        )
        await session.commit()
        row = result.fetchone()
        if row:
            return {"id": row[0], "username": row[1], "email": row[2], "role": row[3]}
    return None


async def get_user_by_username(username: str) -> Optional[dict]:
    username = normalize_username(username)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, username, email, password_hash, role "
                "FROM users "
                "WHERE LOWER(username) = :u "
                "ORDER BY created_at ASC "
                "LIMIT 1"
            ),
            {"u": username},
        )
        row = result.fetchone()
        if row:
            return {"id": row[0], "username": row[1], "email": row[2], "password_hash": row[3], "role": row[4]}
    return None


async def get_user_by_email(email: str) -> Optional[dict]:
    email = normalize_email(email)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, username, email, password_hash, role "
                "FROM users "
                "WHERE LOWER(email) = :email "
                "ORDER BY created_at ASC "
                "LIMIT 1"
            ),
            {"email": email},
        )
        row = result.fetchone()
        if row:
            return {"id": row[0], "username": row[1], "email": row[2], "password_hash": row[3], "role": row[4]}
    return None


async def get_user_by_login(identifier: str) -> Optional[dict]:
    identifier = (identifier or "").strip()
    if "@" in identifier:
        return await get_user_by_email(identifier)
    return await get_user_by_username(identifier)


async def update_last_login(user_id: str):
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE users SET last_login = NOW() WHERE id = :id"),
            {"id": user_id},
        )
        await session.commit()


# ---------------------------------------------------------------------------
# User-scoped complaint queries
# ---------------------------------------------------------------------------

async def fetch_user_complaints(user_id: str, page: int = 1, limit: int = 20) -> dict:
    offset = (page - 1) * limit
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, created_at, status, complaint_type, severity,
                       assigned_entity, duplicate_status, requires_review,
                       priority_score, location_district,
                       LEFT(original_text, 120) AS text_preview,
                       full_decision_json->'routing'->>'secondary_entity' AS secondary_entity,
                       full_decision_json->'routing'->>'secondary_confidence' AS secondary_confidence,
                       full_decision_json->'text_analysis'->>'subcategory' AS subcategory,
                       full_decision_json->'text_analysis'->>'category' AS category
                FROM complaints
                WHERE user_id = :uid
                ORDER BY created_at DESC
                LIMIT :lim OFFSET :off
            """),
            {"uid": user_id, "lim": limit, "off": offset},
        )
        cols = list(result.keys())
        rows = [dict(zip(cols, r)) for r in result.fetchall()]
        count = await session.execute(
            text("SELECT COUNT(*) FROM complaints WHERE user_id = :uid"), {"uid": user_id}
        )
        total = count.scalar() or 0
    return {"complaints": rows, "total": total, "page": page, "limit": limit}


# ---------------------------------------------------------------------------
# Admin queries
# ---------------------------------------------------------------------------

async def fetch_admin_stats() -> dict:
    async with AsyncSessionLocal() as session:
        stats: dict = {}
        for key, q in [
            ("total",          "SELECT COUNT(*) FROM complaints"),
            ("pending_review", "SELECT COUNT(*) FROM complaints WHERE requires_review = true"),
            ("duplicates",     "SELECT COUNT(*) FROM complaints WHERE duplicate_status != 'NEW'"),
            ("auto_routed",    "SELECT COUNT(*) FROM complaints WHERE auto_routed = true"),
            ("open_reviews",   "SELECT COUNT(*) FROM human_review_queue WHERE resolved = false"),
        ]:
            r = await session.execute(text(q))
            stats[key] = r.scalar() or 0
    return stats


async def fetch_all_complaints_admin(page: int = 1, limit: int = 50) -> dict:
    offset = (page - 1) * limit
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, created_at, status, complaint_type, severity,
                       assigned_entity, duplicate_status, requires_review,
                       priority_score, user_id, location_district,
                       LEFT(original_text, 120) AS text_preview,
                       full_decision_json->'text_analysis'->>'subcategory' AS subcategory,
                       full_decision_json->'text_analysis'->>'category' AS category
                FROM complaints
                ORDER BY created_at DESC
                LIMIT :lim OFFSET :off
            """),
            {"lim": limit, "off": offset},
        )
        cols = list(result.keys())
        rows = [dict(zip(cols, r)) for r in result.fetchall()]
        count = await session.execute(text("SELECT COUNT(*) FROM complaints"))
        total = count.scalar() or 0
    return {"complaints": rows, "total": total, "page": page, "limit": limit}


async def fetch_review_queue_admin() -> list:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, created_at, complaint_id, validation_status, review_reason,
                       LEFT(original_text, 120) AS text_preview, resolved
                FROM human_review_queue
                WHERE resolved = false
                ORDER BY created_at DESC
            """)
        )
        cols = list(result.keys())
        return [dict(zip(cols, r)) for r in result.fetchall()]


async def fetch_resolved_review_admin(limit: int = 200) -> list:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT q.id, q.created_at, q.resolved_at, q.complaint_id,
                       q.validation_status, q.review_reason,
                       q.resolved_by, q.resolution_notes,
                       LEFT(q.original_text, 120) AS text_preview,
                       e.admin_decision, e.image_text_match,
                       e.created_at AS admin_edit_created_at
                FROM human_review_queue q
                LEFT JOIN LATERAL (
                    SELECT admin_decision, image_text_match, created_at
                    FROM admin_review_edits e
                    WHERE e.review_item_id = q.id
                    ORDER BY e.id DESC
                    LIMIT 1
                ) e ON TRUE
                WHERE q.resolved = true
                ORDER BY q.resolved_at DESC NULLS LAST, q.created_at DESC
                LIMIT :lim
            """),
            {"lim": limit},
        )
        cols = list(result.keys())
        return [dict(zip(cols, r)) for r in result.fetchall()]


async def fetch_duplicates_admin(page: int = 1, limit: int = 50) -> dict:
    offset = (page - 1) * limit
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, created_at, complaint_type, duplicate_status,
                       duplicate_of, cluster_id, assigned_entity, severity,
                       LEFT(original_text, 120) AS text_preview,
                       full_decision_json->'text_analysis'->>'subcategory' AS subcategory,
                       full_decision_json->'text_analysis'->>'category' AS category
                FROM complaints
                WHERE duplicate_status != 'NEW'
                ORDER BY created_at DESC
                LIMIT :lim OFFSET :off
            """),
            {"lim": limit, "off": offset},
        )
        cols = list(result.keys())
        rows = [dict(zip(cols, r)) for r in result.fetchall()]
        count = await session.execute(
            text("SELECT COUNT(*) FROM complaints WHERE duplicate_status != 'NEW'")
        )
        total = count.scalar() or 0
    return {"complaints": rows, "total": total}


async def resolve_review_item(
    item_id: int,
    resolved_by: str,
    notes: str = "",
    admin_decision: Optional[str] = None,
    corrected_text_json: Optional[dict] = None,
    corrected_image_json: Optional[dict] = None,
    corrected_rag_response: Optional[dict] = None,
    image_text_match: Optional[bool] = None,
    text_llm_json: Optional[dict] = None,
    image_llm_json: Optional[dict] = None,
    routing_json: Optional[dict] = None,
) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                UPDATE human_review_queue
                SET resolved = true, resolved_at = NOW(),
                    resolved_by = :by, resolution_notes = :notes
                WHERE id = :id
                RETURNING complaint_id
            """),
            {"id": item_id, "by": resolved_by, "notes": notes},
        )

        row = result.fetchone()
        complaint_id = row[0] if row else None

        if complaint_id:
            await session.execute(
                text("""
                    INSERT INTO admin_review_edits
                        (review_item_id, complaint_id, admin_id, resolution_notes,
                         admin_decision, image_text_match, text_llm_json,
                         image_llm_json, routing_json)
                    VALUES
                        (:review_item_id, :complaint_id, :admin_id, :resolution_notes,
                         :admin_decision, :image_text_match, :text_llm_json,
                         :image_llm_json, :routing_json)
                """),
                {
                    "review_item_id": item_id,
                    "complaint_id": complaint_id,
                    "admin_id": resolved_by,
                    "resolution_notes": notes,
                    "admin_decision": admin_decision,
                    "image_text_match": image_text_match,
                    "text_llm_json": json.dumps(text_llm_json) if text_llm_json else None,
                    "image_llm_json": json.dumps(image_llm_json) if image_llm_json else None,
                    "routing_json": json.dumps(routing_json) if routing_json else None,
                },
            )

        # Optional: push admin feedback into the existing retraining feedback loop.
        # This lets reviewers close the queue item and label data in one action.
        if complaint_id and admin_decision:
            usable = admin_decision == "can_be_processed"
            await session.execute(
                text("""
                    UPDATE retraining_store
                    SET admin_reviewed         = TRUE,
                        admin_reviewed_at      = NOW(),
                        admin_reviewed_by      = :admin_id,
                        admin_decision         = :admin_decision,
                        admin_notes            = COALESCE(:admin_notes, admin_notes),
                        corrected_text_json    = :text_json,
                        corrected_image_json   = :image_json,
                        corrected_rag_response = :rag_json,
                        usable_for_finetuning  = :usable
                    WHERE complaint_id = :cid
                """),
                {
                    "cid": complaint_id,
                    "admin_id": resolved_by,
                    "admin_decision": admin_decision,
                    "admin_notes": notes,
                    "text_json": json.dumps(corrected_text_json) if corrected_text_json else None,
                    "image_json": json.dumps(corrected_image_json) if corrected_image_json else None,
                    "rag_json": json.dumps(corrected_rag_response) if corrected_rag_response else None,
                    "usable": usable,
                },
            )

        await session.commit()


# ---------------------------------------------------------------------------
# Retraining Store
# ---------------------------------------------------------------------------

async def save_retraining_record(decision: ComplaintDecision) -> None:
    """
    Writes a retraining_store row right after a complaint is processed.
    Stores the raw IEP-1, IEP-2, and IEP-6 outputs so that admin corrections
    can later turn these into gold-label fine-tuning examples.
    """
    routing = decision.routing
    rag_no_match: bool = bool(getattr(routing, "rag_no_candidates", False)) if routing else False
    hitl_reason: Optional[str] = (
        routing.review_reason if routing and routing.requires_review else None
    )

    text_json = json.dumps(decision.text_analysis.dict()) if decision.text_analysis else None
    image_json = json.dumps(decision.image_analysis.dict()) if decision.image_analysis else None
    rag_json   = json.dumps(routing.dict()) if routing else None

    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO retraining_store
                    (complaint_id, complaint_text, image_filename,
                     text_classification_json, image_classification_json,
                     rag_routing_response, pipeline_status,
                     rag_no_match, hitl_flag_reason)
                VALUES
                    (:complaint_id, :complaint_text, :image_filename,
                     :text_json, :image_json,
                     :rag_json, :pipeline_status,
                     :rag_no_match, :hitl_reason)
                ON CONFLICT (complaint_id) DO NOTHING
            """),
            {
                "complaint_id":   decision.complaint_id,
                "complaint_text": decision.original_text,
                "image_filename": decision.image_filename,
                "text_json":      text_json,
                "image_json":     image_json,
                "rag_json":       rag_json,
                "pipeline_status": str(decision.status.value if hasattr(decision.status, "value") else decision.status),
                "rag_no_match":   rag_no_match,
                "hitl_reason":    hitl_reason,
            },
        )
        await session.commit()


async def fetch_retraining_queue(
    pending_only: bool = True,
    rag_no_match_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Returns retraining_store rows awaiting admin review (or all rows)."""
    filters = []
    if pending_only:
        filters.append("admin_reviewed = FALSE")
    if rag_no_match_only:
        filters.append("rag_no_match = TRUE")
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    async with AsyncSessionLocal() as session:
        result = await session.execute(
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
        cols = list(result.keys())
        rows = [dict(zip(cols, r)) for r in result.fetchall()]
        count_result = await session.execute(
            text(f"SELECT COUNT(*) FROM retraining_store {where}")
        )
        total = count_result.scalar() or 0
    return {"records": rows, "total": total, "limit": limit, "offset": offset}


async def fetch_retraining_record(complaint_id: str) -> Optional[dict]:
    """Returns a single full retraining_store row including all JSONB columns."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
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
        cols = list(result.keys())
        return dict(zip(cols, row))


async def submit_retraining_review(
    complaint_id: str,
    admin_id: str,
    admin_decision: str,
    admin_notes: Optional[str],
    corrected_text_json: Optional[dict],
    corrected_image_json: Optional[dict],
    corrected_rag_response: Optional[dict],
) -> None:
    """Saves an admin review decision to retraining_store."""
    usable = admin_decision == "can_be_processed"

    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                UPDATE retraining_store
                SET admin_reviewed        = TRUE,
                    admin_reviewed_at     = NOW(),
                    admin_reviewed_by     = :admin_id,
                    admin_decision        = :admin_decision,
                    admin_notes           = :admin_notes,
                    corrected_text_json   = :text_json,
                    corrected_image_json  = :image_json,
                    corrected_rag_response = :rag_json,
                    usable_for_finetuning = :usable
                WHERE complaint_id = :cid
            """),
            {
                "cid":            complaint_id,
                "admin_id":       admin_id,
                "admin_decision": admin_decision,
                "admin_notes":    admin_notes,
                "text_json":      json.dumps(corrected_text_json) if corrected_text_json else None,
                "image_json":     json.dumps(corrected_image_json) if corrected_image_json else None,
                "rag_json":       json.dumps(corrected_rag_response) if corrected_rag_response else None,
                "usable":         usable,
            },
        )
        await session.commit()


async def fetch_retraining_export(mark_exported: bool = False) -> dict:
    """
    Returns all records where usable_for_finetuning=TRUE and finetuning_exported=FALSE.
    If mark_exported=True, marks them as exported atomically.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
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
        cols = list(result.keys())
        rows = [dict(zip(cols, r)) for r in result.fetchall()]

        if mark_exported and rows:
            ids = [r["id"] for r in rows]
            await session.execute(
                text(
                    "UPDATE retraining_store SET finetuning_exported = TRUE "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": ids},
            )
            await session.commit()

    return {"records": rows, "total": len(rows)}

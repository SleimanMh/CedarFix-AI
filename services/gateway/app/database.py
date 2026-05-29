"""Database helpers for the Gateway service."""

import json
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from cedarfix_shared.db import Base
from cedarfix_shared.schemas import ComplaintDecision
from .config import settings

# Use asyncpg for async Postgres support in the gateway
async_db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
async_engine = create_async_engine(async_db_url, echo=False)
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def save_complaint(decision: ComplaintDecision):
    from cedarfix_shared.db import Complaint
    async with AsyncSessionLocal() as session:
        record = Complaint(
            id=decision.complaint_id,
            status=decision.status,
            original_text=decision.original_text,
            location_lat=decision.location.latitude if decision.location else None,
            location_lng=decision.location.longitude if decision.location else None,
            location_district=decision.location.district if decision.location else None,
            image_filename=decision.image_filename,
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
            requires_review=decision.routing.requires_review if decision.routing else False,
            total_pipeline_ms=decision.total_pipeline_ms,
            full_decision_json=json.loads(decision.json()),
        )
        session.add(record)
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

async def create_user(username: str, password_hash: str, role: str = "user") -> dict:
    user_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, username, password_hash, role) "
                "VALUES (:id, :username, :password_hash, :role)"
            ),
            {"id": user_id, "username": username, "password_hash": password_hash, "role": role},
        )
        await session.commit()
    return {"id": user_id, "username": username, "role": role}


async def get_user_by_username(username: str) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT id, username, password_hash, role FROM users WHERE username = :u"),
            {"u": username},
        )
        row = result.fetchone()
        if row:
            return {"id": row[0], "username": row[1], "password_hash": row[2], "role": row[3]}
    return None


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
                       LEFT(original_text, 120) AS text_preview
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
                       LEFT(original_text, 120) AS text_preview
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


async def fetch_duplicates_admin(page: int = 1, limit: int = 50) -> dict:
    offset = (page - 1) * limit
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, created_at, complaint_type, duplicate_status,
                       duplicate_of, cluster_id, assigned_entity, severity,
                       LEFT(original_text, 120) AS text_preview
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


async def resolve_review_item(item_id: int, resolved_by: str, notes: str = "") -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                UPDATE human_review_queue
                SET resolved = true, resolved_at = NOW(),
                    resolved_by = :by, resolution_notes = :notes
                WHERE id = :id
            """),
            {"id": item_id, "by": resolved_by, "notes": notes},
        )
        await session.commit()

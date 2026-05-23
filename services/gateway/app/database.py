"""Database helpers for the Gateway service."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from cedarfix_shared.db import Base
from cedarfix_shared.schemas import ComplaintDecision
from .config import settings
import json

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

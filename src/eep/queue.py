"""Redis Streams publisher for EEP → IEP job queues.

Stream keys follow the convention  cedarfix:{service}:jobs
Consumer groups are created lazily by each worker on startup.
"""
from __future__ import annotations

import os

from redis.asyncio import Redis

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Stream keys (shared constants so workers import from here)
STREAM_IEP1 = "cedarfix:iep1:jobs"
STREAM_IEP2 = "cedarfix:iep2:jobs"
STREAM_IEP3 = "cedarfix:iep3:jobs"
STREAM_IEP4 = "cedarfix:iep4:jobs"
STREAM_IEP5 = "cedarfix:iep5:jobs"
STREAM_IEP6 = "cedarfix:iep6:jobs"
STREAM_IEP7 = "cedarfix:iep7:jobs"
STREAM_IEP8 = "cedarfix:iep8:jobs"

_redis: Redis | None = None


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def enqueue_iep1(
    complaint_id: str,
    text: str,
    language_hint: str | None = None,
) -> str:
    """Publish a new complaint to the IEP-1 stream. Returns the Redis message ID."""
    r = await get_redis()
    msg_id: str = await r.xadd(
        STREAM_IEP1,
        {
            "complaint_id": complaint_id,
            "text": text,
            "language_hint": language_hint or "",
        },
    )
    return msg_id


async def enqueue_iep5(
    complaint_id: str,
    incident_id: str,
    event: str = "route",
    routing_json: str = "",
) -> str:
    """Publish a lifecycle event to the IEP-5 stream."""
    r = await get_redis()
    msg_id: str = await r.xadd(
        STREAM_IEP5,
        {
            "complaint_id": complaint_id,
            "incident_id": incident_id or "",
            "event": event,
            "routing_json": routing_json or "",
        },
    )
    return msg_id


async def enqueue_iep6(complaint_id: str, image_b64: str) -> str:
    """Publish an image-bearing complaint to the IEP-6 vision stream."""
    r = await get_redis()
    msg_id: str = await r.xadd(
        STREAM_IEP6,
        {
            "complaint_id": complaint_id,
            "image_b64": image_b64 or "",
        },
    )
    return msg_id


async def enqueue_iep8(
    complaint_id: str,
    routing_sector: str = "",
    routing_entity: str = "",
    text: str = "",
) -> str:
    """Publish a routed complaint to the IEP-8 grounded-resolution stream."""
    r = await get_redis()
    msg_id: str = await r.xadd(
        STREAM_IEP8,
        {
            "complaint_id": complaint_id,
            "routing_sector": routing_sector or "",
            "routing_entity": routing_entity or "",
            "text": text or "",
        },
    )
    return msg_id

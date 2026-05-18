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

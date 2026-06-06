"""Qdrant connection helpers for local and managed deployments."""

from __future__ import annotations

import os

from qdrant_client import QdrantClient


def create_qdrant_client() -> QdrantClient:
    """Create a Qdrant client for either local host/port or Qdrant Cloud URL."""
    url = os.getenv("QDRANT_URL", "").strip()
    api_key = os.getenv("QDRANT_API_KEY", "").strip() or None
    timeout = float(os.getenv("QDRANT_TIMEOUT", "20"))

    if url:
        return QdrantClient(url=url, api_key=api_key, timeout=timeout)

    host = os.getenv("QDRANT_HOST", "qdrant")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    return QdrantClient(host=host, port=port, api_key=api_key, timeout=timeout)


def qdrant_target_label() -> str:
    url = os.getenv("QDRANT_URL", "").strip()
    if url:
        return url
    return f"{os.getenv('QDRANT_HOST', 'qdrant')}:{os.getenv('QDRANT_PORT', '6333')}"

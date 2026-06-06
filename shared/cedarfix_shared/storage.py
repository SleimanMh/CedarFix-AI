"""Stable image storage references for local and cloud deployments."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

StorageBackend = Literal["local", "gcs"]


def storage_backend() -> StorageBackend:
    configured = os.getenv("STORAGE_BACKEND", "").strip().lower()
    if configured in {"local", "gcs"}:
        return configured  # type: ignore[return-value]
    return "gcs" if os.getenv("GCS_BUCKET", "").strip() else "local"


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name or name in {".", ".."}:
        raise ValueError("Invalid image filename")
    return name


def _uploads_dir(uploads_dir: str | None = None) -> Path:
    return Path(uploads_dir or os.getenv("UPLOADS_DIR", "/data/uploads"))


def _gcs_bucket_name(ref: str | None = None) -> str:
    if ref and ref.startswith("gcs://"):
        parsed = urlparse(ref)
        return parsed.netloc
    bucket = os.getenv("GCS_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("GCS_BUCKET is required for GCS image storage")
    return bucket


def _gcs_object_name(filename_or_ref: str) -> str:
    if filename_or_ref.startswith("gcs://"):
        parsed = urlparse(filename_or_ref)
        return parsed.path.lstrip("/")
    return f"complaints/{_safe_filename(filename_or_ref)}"


def save_image_ref(
    filename: str,
    data: bytes,
    *,
    content_type: str = "image/jpeg",
    uploads_dir: str | None = None,
) -> str:
    """Persist image bytes and return a stable reference string."""
    name = _safe_filename(filename)
    if storage_backend() == "gcs":
        from google.cloud import storage as gcs

        bucket_name = _gcs_bucket_name()
        object_name = _gcs_object_name(name)
        client = gcs.Client()
        blob = client.bucket(bucket_name).blob(object_name)
        blob.upload_from_string(data, content_type=content_type)
        return f"gcs://{bucket_name}/{object_name}"

    target_dir = _uploads_dir(uploads_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / name).write_bytes(data)
    return f"local://{name}"


def read_image_bytes(image_ref: str, *, uploads_dir: str | None = None) -> bytes:
    """Load image bytes from a stable image reference."""
    if image_ref.startswith(("http://", "https://")):
        import httpx

        resp = httpx.get(image_ref, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        return resp.content

    if image_ref.startswith("gcs://"):
        from google.cloud import storage as gcs

        bucket_name = _gcs_bucket_name(image_ref)
        object_name = _gcs_object_name(image_ref)
        client = gcs.Client()
        return client.bucket(bucket_name).blob(object_name).download_as_bytes()

    name = image_ref.removeprefix("local://")
    path = _uploads_dir(uploads_dir) / _safe_filename(name)
    return path.read_bytes()


def local_image_path(image_ref: str, *, uploads_dir: str | None = None) -> Path | None:
    """Return a local filesystem path for local refs; None for cloud/URL refs."""
    if image_ref.startswith(("http://", "https://", "gcs://")):
        return None
    name = image_ref.removeprefix("local://")
    return _uploads_dir(uploads_dir) / _safe_filename(name)


def signed_image_url(image_ref: str, *, expiration_seconds: int = 3600) -> str:
    """Return a browser-readable URL for a URL or GCS ref."""
    if image_ref.startswith(("http://", "https://")):
        return image_ref
    if not image_ref.startswith("gcs://"):
        raise ValueError("Signed URL is only available for GCS or URL image refs")

    from datetime import timedelta
    from google.cloud import storage as gcs

    bucket_name = _gcs_bucket_name(image_ref)
    object_name = _gcs_object_name(image_ref)
    client = gcs.Client()
    blob = client.bucket(bucket_name).blob(object_name)
    return blob.generate_signed_url(
        expiration=timedelta(seconds=expiration_seconds),
        method="GET",
        version="v4",
    )

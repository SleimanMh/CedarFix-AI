from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text


pytestmark = [pytest.mark.integration, pytest.mark.db]


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    return (
        os.getenv("CEDARFIX_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()


def test_live_database_accepts_read_only_probe_query():
    if not _truthy_env("CEDARFIX_RUN_DB_TESTS"):
        pytest.skip("Set CEDARFIX_RUN_DB_TESTS=true and CEDARFIX_DATABASE_URL to probe a live database.")

    url = _database_url()
    if not url:
        pytest.fail("CEDARFIX_DATABASE_URL or DATABASE_URL must be set for DB readiness tests.")

    sync_url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    engine = create_engine(sync_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException


def test_password_hashing_and_token_payload_round_trip(import_service_module):
    auth = import_service_module("gateway", "app.auth")

    hashed = auth.hash_password("correct horse")
    assert auth.verify_password("correct horse", hashed) is True
    assert auth.verify_password("wrong", hashed) is False

    token = auth.create_token("u1", "maya", "admin", "maya@example.com")
    payload = auth.decode_token(token)

    assert payload["user_id"] == "u1"
    assert payload["sub"] == "maya"
    assert payload["role"] == "admin"
    assert payload["email"] == "maya@example.com"
    assert "exp" in payload


def test_auth_dependencies_reject_missing_invalid_and_non_admin_tokens(import_service_module):
    auth = import_service_module("gateway", "app.auth")

    with pytest.raises(HTTPException) as missing:
        asyncio.run(auth.require_user(None))
    assert missing.value.status_code == 401

    with pytest.raises(HTTPException) as invalid:
        asyncio.run(auth.require_user("not-a-token"))
    assert invalid.value.status_code == 401

    user_token = auth.create_token("u2", "sami", "user", "sami@example.com")
    with pytest.raises(HTTPException) as forbidden:
        asyncio.run(auth.require_admin(user_token))
    assert forbidden.value.status_code == 403

    admin_token = auth.create_token("u3", "rana", "admin", "rana@example.com")
    admin_payload = asyncio.run(auth.require_admin(admin_token))
    assert admin_payload["user_id"] == "u3"
    assert admin_payload["role"] == "admin"


def test_get_current_user_tolerates_absent_and_bad_tokens(import_service_module):
    auth = import_service_module("gateway", "app.auth")

    assert asyncio.run(auth.get_current_user(None)) is None
    assert asyncio.run(auth.get_current_user("not-a-token")) is None

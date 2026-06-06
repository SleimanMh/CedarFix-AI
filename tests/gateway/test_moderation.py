from __future__ import annotations

import asyncio

from cedarfix_shared.schemas import ModerationDecisionEnum


def test_heuristic_check_flags_spam_caps_and_rejects_blocked_keywords(import_service_module):
    moderation = import_service_module("gateway", "app.moderation")

    assert moderation._heuristic_check("short")[0] == ModerationDecisionEnum.FLAG
    assert moderation._heuristic_check("THIS ROAD IS BROKEN PLEASE FIX IT")[0] == ModerationDecisionEnum.FLAG
    assert moderation._heuristic_check("aaaaaaaa broken road")[0] == ModerationDecisionEnum.FLAG
    assert moderation._heuristic_check("kill everyone on this street")[0] == ModerationDecisionEnum.REJECT


def test_moderate_disabled_returns_pass(import_service_module, monkeypatch):
    moderation = import_service_module("gateway", "app.moderation")
    monkeypatch.setattr(moderation, "MODERATION_ENABLED", False)

    result = asyncio.run(moderation.moderate("THIS WOULD OTHERWISE BE FLAGGED"))

    assert result.decision == ModerationDecisionEnum.PASS
    assert result.reason == "Moderation disabled"


def test_moderate_records_duplicate_hash_without_crashing(import_service_module, monkeypatch):
    moderation = import_service_module("gateway", "app.moderation")
    monkeypatch.setattr(moderation, "MODERATION_ENABLED", True)
    monkeypatch.setattr(moderation, "QWEN_BASE_URL", "")

    async def duplicate(_text, _user_id):
        return True

    monkeypatch.setattr(moderation, "_record_text_hash", duplicate)

    result = asyncio.run(moderation.moderate("Broken road near Hamra", user_id="u1"))

    assert result.decision == ModerationDecisionEnum.FLAG
    assert "exact_duplicate" in result.heuristic_flags


def test_moderate_normalizes_uppercase_llm_decision_and_downgrades_political_reject(import_service_module, monkeypatch):
    moderation = import_service_module("gateway", "app.moderation")
    monkeypatch.setattr(moderation, "MODERATION_ENABLED", True)
    monkeypatch.setattr(moderation, "QWEN_BASE_URL", "http://qwen")
    monkeypatch.setattr(moderation, "LLM_THRESHOLD", 0.75)

    async def not_duplicate(_text, _user_id):
        return False

    async def llm(_text):
        return {
            "is_spam": False,
            "is_abusive": False,
            "is_political": True,
            "decision": "REJECT",
            "confidence": 0.99,
            "reason": "Political complaint about infrastructure.",
        }

    monkeypatch.setattr(moderation, "_record_text_hash", not_duplicate)
    monkeypatch.setattr(moderation, "_llm_moderate_text", llm)

    result = asyncio.run(moderation.moderate("BROKEN ROAD NEEDS FIXING NOW"))

    assert result.decision == ModerationDecisionEnum.FLAG
    assert result.llm_checked is True
    assert "downgraded" in result.reason


def test_moderate_harmful_image_escalates_flag_to_reject(import_service_module, monkeypatch):
    moderation = import_service_module("gateway", "app.moderation")
    monkeypatch.setattr(moderation, "MODERATION_ENABLED", True)
    monkeypatch.setattr(moderation, "QWEN_BASE_URL", "")

    async def not_duplicate(_text, _user_id):
        return False

    async def harmful(_image_ref):
        return {"is_harmful": True, "reason": "violent content"}

    monkeypatch.setattr(moderation, "_record_text_hash", not_duplicate)
    monkeypatch.setattr(moderation, "_vlm_moderate_image", harmful)

    result = asyncio.run(moderation.moderate("short", image_filename="local://x.jpg"))

    assert result.decision == ModerationDecisionEnum.REJECT
    assert result.vlm_checked is True
    assert "Harmful image" in result.reason


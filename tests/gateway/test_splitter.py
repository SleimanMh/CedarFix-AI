from __future__ import annotations

import asyncio

from cedarfix_shared.schemas import ComplaintSplitItem


def test_splitter_uses_heuristics_when_llm_is_not_configured(import_service_module, monkeypatch):
    splitter = import_service_module("gateway", "app.splitter")
    monkeypatch.setattr(splitter, "SPLITTER_LLM_ENABLED", False)
    monkeypatch.setattr(splitter, "QWEN_BASE_URL", "")

    result = asyncio.run(
        splitter.split_complaint_text(
            "1. Large pothole blocking cars near Hamra. "
            "2. Garbage pile overflowing beside the public school."
        )
    )

    assert result.is_multi is True
    assert result.source == "heuristic"
    assert [item.complaint_text for item in result.complaints] == [
        "Large pothole blocking cars near Hamra.",
        "Garbage pile overflowing beside the public school.",
    ]


def test_splitter_keeps_causal_same_issue_as_single(import_service_module, monkeypatch):
    splitter = import_service_module("gateway", "app.splitter")
    monkeypatch.setattr(splitter, "SPLITTER_LLM_ENABLED", False)
    text = "A broken water pipe has been leaking for days and now the road is collapsing around it"

    result = asyncio.run(splitter.split_complaint_text(text))

    assert result.is_multi is False
    assert result.source == "single"
    assert result.complaints[0].complaint_text == text


def test_splitter_llm_failure_records_fallback_single_result(import_service_module, monkeypatch):
    splitter = import_service_module("gateway", "app.splitter")
    monkeypatch.setattr(splitter, "SPLITTER_LLM_ENABLED", True)
    monkeypatch.setattr(splitter, "QWEN_BASE_URL", "http://qwen.test/v1")

    async def fail(_text):
        raise RuntimeError("offline")

    monkeypatch.setattr(splitter, "_split_with_llm", fail)

    result = asyncio.run(splitter.split_complaint_text("Power is out and garbage is piling up near Hamra"))

    assert result.is_multi is False
    assert result.source == "fallback"
    assert "RuntimeError" in result.review_reason
    assert result.complaints[0].complaint_text == "Power is out and garbage is piling up near Hamra"


def test_splitter_coerces_llm_output_with_dedupe_and_child_limit(import_service_module):
    splitter = import_service_module("gateway", "app.splitter")
    output = splitter._LLMSplitOutput(
        is_multi=True,
        complaints=[
            ComplaintSplitItem(complaint_text=f"Independent complaint number {idx}", confidence=0.8)
            for idx in range(1, 7)
        ]
        + [ComplaintSplitItem(complaint_text="Independent complaint number 1", confidence=0.8)],
        confidence=0.9,
    )

    result = splitter._coerce_result("original text with many issues", "llm", output)

    assert result.is_multi is True
    assert result.source == "llm"
    assert len(result.complaints) == splitter.SPLITTER_MAX_CHILDREN
    assert len({item.complaint_text.casefold() for item in result.complaints}) == len(result.complaints)

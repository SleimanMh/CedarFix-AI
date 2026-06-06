#!/usr/bin/env python3
"""Validate compiled CedarFix routing knowledge docs."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "RAG Data" / "compiled" / "routing_knowledge_compiled_production.json"
DEFAULT_REPORT = REPO_ROOT / "RAG Data" / "validation_report.md"

sys.path.insert(0, str(REPO_ROOT / "shared"))
from cedarfix_shared.schemas import RoutingEntity, RoutingKnowledgeDoc  # noqa: E402


REQUIRED = {
    "doc_id",
    "entity_name",
    "entity_enum",
    "entity_type",
    "short_name",
    "governs_nationally",
    "governorates",
    "districts",
    "municipalities",
    "complaint_types",
    "keywords",
    "not_responsible_for",
    "description",
    "confidence_prior",
    "hotline",
}


def _load(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8-sig")
    stripped = raw.lstrip()
    if not stripped:
        return []
    if stripped.startswith("["):
        loaded = json.loads(raw)
        if not isinstance(loaded, list):
            raise ValueError(f"{path}: expected a JSON array of documents")
        docs: list[dict[str, Any]] = []
        for idx, item in enumerate(loaded, 1):
            if not isinstance(item, dict):
                raise ValueError(f"{path}: item {idx} is not a JSON object")
            item["_line_no"] = idx
            docs.append(item)
        return docs

    docs: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except Exception as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        doc["_line_no"] = line_no
        docs.append(doc)
    return docs


def validate(path: Path) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, Any]]:
    docs = _load(path)
    valid_entities = {e.value for e in RoutingEntity}
    manual_review_modes = {
        "human_review_gate",
        "human_review_user_assist",
        "manual_review_only",
    }
    errors: list[str] = []
    warnings: list[str] = []
    doc_ids: Counter[str] = Counter()

    for doc in docs:
        line = doc.get("_line_no", "?")
        doc_id = doc.get("doc_id", f"line-{line}")
        doc_ids[str(doc_id)] += 1
        missing = sorted(REQUIRED - set(doc))
        if missing:
            errors.append(f"{doc_id}: missing required fields {missing}")
        try:
            RoutingKnowledgeDoc(**{k: v for k, v in doc.items() if not k.startswith("_")})
        except Exception as exc:
            errors.append(f"{doc_id}: RoutingKnowledgeDoc validation failed: {exc}")
        if doc.get("entity_enum") not in valid_entities:
            errors.append(f"{doc_id}: entity_enum '{doc.get('entity_enum')}' is not a RoutingEntity value")
        if not str(doc.get("description", "")).strip():
            errors.append(f"{doc_id}: empty description")
        elif len(str(doc.get("description", ""))) < 80:
            warnings.append(f"{doc_id}: description is short")
        if not isinstance(doc.get("complaint_types"), list) or not doc.get("complaint_types"):
            errors.append(f"{doc_id}: complaint_types must be a non-empty list")
        if not isinstance(doc.get("keywords"), list) or len(doc.get("keywords", [])) < 3:
            warnings.append(f"{doc_id}: fewer than 3 keywords")
        for keyword in doc.get("keywords", []):
            if len(str(keyword)) > 100:
                warnings.append(f"{doc_id}: keyword longer than 100 chars")
        try:
            conf = float(doc.get("confidence_prior"))
            if not 0.0 <= conf <= 1.0:
                errors.append(f"{doc_id}: confidence_prior out of range")
        except (TypeError, ValueError):
            errors.append(f"{doc_id}: confidence_prior is not numeric")
        if not doc.get("source_ids") and not doc.get("source_files"):
            warnings.append(f"{doc_id}: no source_ids preserved")
        for source_file in doc.get("source_files", []):
            source_text = str(source_file)
            if ":\\" in source_text or source_text.startswith("/"):
                warnings.append(f"{doc_id}: source_file is not portable: {source_text}")
        route_mode = str(doc.get("route_mode", "")).strip()
        route_authority = str(doc.get("route_authority", "")).strip()
        if route_mode in manual_review_modes and doc.get("entity_enum") != RoutingEntity.HUMAN_REVIEW.value:
            errors.append(f"{doc_id}: manual review docs must route to Human Review Queue")
        if route_mode == "contact_fallback_only" and not bool(doc.get("hitl_always_required")):
            errors.append(f"{doc_id}: contact fallback docs must require human review")
        if route_authority in {"blocker", "manual_review_gate"} and not bool(doc.get("hitl_always_required")):
            warnings.append(f"{doc_id}: blocker/manual authority should normally require human review")

    for doc_id, count in doc_ids.items():
        if count > 1:
            errors.append(f"{doc_id}: duplicate doc_id appears {count} times")

    stats = {
        "doc_count": len(docs),
        "entity_count": len({d.get("source_entity_id", d.get("entity_enum")) for d in docs}),
        "routing_entities": dict(Counter(d.get("entity_enum") for d in docs)),
        "source_entities": dict(Counter(d.get("source_entity_id", "unknown") for d in docs)),
        "responsibility_levels": dict(Counter(d.get("responsibility_level", "unknown") for d in docs)),
        "doc_types": dict(Counter(d.get("doc_type", "unknown") for d in docs)),
        "route_modes": dict(Counter(d.get("route_mode", "unknown") for d in docs)),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    return docs, errors, warnings, stats


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _write_report(path: Path, source_path: Path, errors: list[str], warnings: list[str], stats: dict[str, Any]) -> None:
    lines = [
        "# Routing Knowledge Validation Report",
        "",
        f"Source: `{_display_path(source_path)}`",
        f"Documents: {stats['doc_count']}",
        f"Source entities: {stats['entity_count']}",
        f"Errors: {len(errors)}",
        f"Warnings: {len(warnings)}",
        "",
        "## Responsibility Levels",
        "",
    ]
    for key, value in sorted(stats["responsibility_levels"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Document Types", ""])
    for key, value in sorted(stats["doc_types"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Route Modes", ""])
    for key, value in sorted(stats["route_modes"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Routing Entities", ""])
    for key, value in sorted(stats["routing_entities"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Source Entities", ""])
    for key, value in sorted(stats["source_entities"].items()):
        lines.append(f"- `{key}`: {value}")
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {err}" for err in errors)
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warn}" for warn in warnings[:200])
        if len(warnings) > 200:
            lines.append(f"- ... {len(warnings) - 200} more warnings omitted")
    if not errors:
        lines.extend(["", "## Result", "", "PASS"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate compiled CedarFix routing knowledge docs.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Compiled JSONL path.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Markdown report path.")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    report_path = Path(args.report).resolve()
    _, errors, warnings, stats = validate(input_path)
    _write_report(report_path, input_path, errors, warnings, stats)
    print(f"Validated {stats['doc_count']} routing docs.")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    print(f"Wrote {report_path}")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()

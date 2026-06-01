"""IEP-8 planner — grounded resolution synthesis + faithfulness verification.

Pipeline (all pure given a retriever):

1. **Retrieve** the most relevant verified facts for the complaint.
2. **Synthesise** candidate resolution steps *extractively* from those facts —
   every step carries the ``fact_id`` / ``source_ids`` it came from.
3. **Verify** each step against its cited evidence (lexical entailment proxy).
   Unsupported steps — the signature of a hallucination — are dropped.
4. **Decide**: auto-issue the grounded plan, or **abstain** to human review
   when the sector is life-safety, the KB does not cover the complaint, or the
   verified groundedness is too low.

No step ever asserts a contact, deadline or instruction that is not present in
retrieved evidence. That is the anti-hallucination guarantee IEP-8 provides on
top of the rest of the pipeline.
"""
from __future__ import annotations

import logging
import re

from src.iep8.retriever import EntityKnowledgeBase, get_kb
from src.shared.resolution_schemas import (
    ABSTAIN_SECTORS,
    CONFLICT_FACT_TYPES,
    MIN_GROUNDEDNESS,
    MIN_RETRIEVAL_SCORE,
    SECTOR_EXPECTED_FACT_TYPES,
    SUPPORT_THRESHOLD,
    ConflictFlag,
    EvidenceChunk,
    EvidenceGap,
    GroundedResolutionPlan,
    ResolutionStep,
    coverage_score,
    groundedness,
    plan_confidence_score,
    support_score,
    tokenize,
)

logger = logging.getLogger("iep8.planner")

# Facts of these types become citizen/ops action steps.
_ACTION_TYPES = {"legal_responsibility", "complaint_process", "service_area"}
_CONTACT_TYPES = {"operational_contact"}
_SAFETY_TYPES = {"emergency_instruction"}
_BOUNDARY_MARKERS = ("not responsible", "boundary condition", "route instead", "do not route")

# A "critical value" inside a fact that must not silently contradict a sibling
# fact of the same type: hotline / phone numbers and SLA day-or-hour counts.
_PHONE_RE = re.compile(r"\b\d[\d\-\s]{2,}\d\b")
_SLA_RE = re.compile(r"\b(\d+)\s*(business\s+day|working\s+day|day|hour|week|month)s?\b", re.I)


def _clean(value: str, max_len: int = 240) -> str:
    """Turn a dense KB fact value into a short, readable instruction."""
    text = " ".join(value.replace("\n", " ").split())
    # Keep the leading, human-readable clause before machine-encoded tails.
    for sep in (" Complaint domains encoded", " Channel types:", " Required fields", " Ticket/reference"):
        idx = text.find(sep)
        if idx > 40:
            text = text[:idx]
            break
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip(",;: ") + "…"
    return text


def _kind_for(chunk: EvidenceChunk) -> str | None:
    lowered = chunk.text.lower()
    if chunk.fact_type in _SAFETY_TYPES:
        return "safety"
    if chunk.fact_type in _CONTACT_TYPES:
        return "contact"
    if any(marker in lowered for marker in _BOUNDARY_MARKERS):
        return "boundary"
    if chunk.fact_type in _ACTION_TYPES:
        return "action"
    return None


def _candidate_steps(evidence: list[EvidenceChunk]) -> list[ResolutionStep]:
    """Build extractive candidate steps (one per usable fact, de-duplicated)."""
    steps: list[ResolutionStep] = []
    seen: set[str] = set()
    # Stable, useful ordering: safety → action → contact → boundary.
    order = {"safety": 0, "action": 1, "contact": 2, "boundary": 3}
    for chunk in evidence:
        kind = _kind_for(chunk)
        if kind is None:
            continue
        # Do not auto-assert facts the KB itself flags as unverified.
        if chunk.human_review_required or chunk.confidence == "low":
            continue
        text = _clean(chunk.text)
        key = (kind, text[:80])
        if key in seen:
            continue
        seen.add(key)
        steps.append(
            ResolutionStep(
                kind=kind,
                text=text,
                cited_fact_ids=[chunk.fact_id],
                cited_source_ids=list(chunk.source_ids[:3]),
            )
        )
    steps.sort(key=lambda s: order.get(s.kind, 9))
    return steps


def verify_steps(
    steps: list[ResolutionStep],
    evidence_by_fact: dict[str, EvidenceChunk],
    threshold: float = SUPPORT_THRESHOLD,
) -> list[ResolutionStep]:
    """Faithfulness check: score each step against its cited evidence.

    Returns new steps with ``support`` / ``supported`` populated. A step whose
    asserted tokens are not present in its cited evidence (a hallucination) gets
    ``supported=False`` and is excluded from the issued plan downstream.
    """
    verified: list[ResolutionStep] = []
    for step in steps:
        evidence_texts = [
            evidence_by_fact[fid].text for fid in step.cited_fact_ids if fid in evidence_by_fact
        ]
        best = max((support_score(step.text, ev) for ev in evidence_texts), default=0.0)
        verified.append(
            step.model_copy(update={"support": round(best, 4), "supported": best >= threshold})
        )
    return verified


def _critical_signals(fact_type: str, text: str) -> frozenset[str]:
    """Extract the normalised values that must agree across sibling facts."""
    signals: set[str] = set()
    if fact_type == "deadline_or_sla":
        for num, unit in _SLA_RE.findall(text):
            unit = unit.lower().replace("working", "business").split()[0]
            signals.add(f"{int(num)}{unit}")
    else:  # operational_contact / emergency_instruction → compare phone/hotlines
        for raw in _PHONE_RE.findall(text):
            digits = re.sub(r"\D", "", raw)
            if 3 <= len(digits) <= 12:
                signals.add(digits)
    return frozenset(signals)


def detect_conflicts(evidence: list[EvidenceChunk]) -> list[ConflictFlag]:
    """Flag same-entity, same-type facts whose critical values contradict.

    Conservative by design (high precision): a conflict is only raised when two
    facts of a sensitive type both carry critical values and those value sets
    are *disjoint* — i.e. they genuinely disagree rather than one elaborating
    the other. This is KB self-consistency checking on top of entailment.
    """
    by_group: dict[tuple[str, str], list[tuple[str, frozenset[str]]]] = {}
    for chunk in evidence:
        if chunk.fact_type not in CONFLICT_FACT_TYPES:
            continue
        sigs = _critical_signals(chunk.fact_type, chunk.text)
        if not sigs:
            continue
        by_group.setdefault((chunk.entity_id, chunk.fact_type), []).append((chunk.fact_id, sigs))

    conflicts: list[ConflictFlag] = []
    for (entity_id, fact_type), items in by_group.items():
        if len(items) < 2:
            continue
        union = frozenset().union(*(sigs for _fid, sigs in items))
        # A shared value anywhere means the facts are reconcilable → no conflict.
        if any(a[1] & b[1] for i, a in enumerate(items) for b in items[i + 1 :]):
            continue
        if len(union) < 2:
            continue
        conflicts.append(
            ConflictFlag(
                entity_id=entity_id,
                fact_type=fact_type,
                fact_ids=sorted(fid for fid, _ in items),
                detail=f"{len(union)} differing {fact_type} values: {', '.join(sorted(union))}"[:200],
            )
        )
    return sorted(conflicts, key=lambda c: (c.entity_id, c.fact_type))


def _infer_evidence_gap(
    sector: str | None,
    entity: str | None,
    complaint_text: str,
    evidence: list[EvidenceChunk],
    reason: str,
) -> EvidenceGap:
    """Diagnose *what* is missing so the failure becomes an acquisition task."""
    sector_u = (sector or "").upper()
    covered_types = {c.fact_type for c in evidence}
    expected = SECTOR_EXPECTED_FACT_TYPES.get(sector_u, ())
    missing = [t for t in expected if t not in covered_types] or list(expected)
    evidence_terms: set[str] = set()
    for c in evidence:
        evidence_terms |= tokenize(c.text)
    uncovered = sorted(tokenize(complaint_text) - evidence_terms)
    severity = "high" if sector_u in ABSTAIN_SECTORS else "medium"
    return EvidenceGap(
        sector=sector_u,
        entity=(entity or None),
        missing_fact_types=missing[:5],
        query_terms=uncovered[:8],
        reason=reason,
        severity=severity,
    )


def _citizen_summary(entity: str | None, sector: str | None, steps: list[ResolutionStep]) -> str:
    who = entity or (sector.title() if sector else "the responsible authority")
    contact = next((s for s in steps if s.kind == "contact"), None)
    action = next((s for s in steps if s.kind == "action"), None)
    parts = [f"This {sector.lower() if sector else 'infrastructure'} issue is handled by {who}."]
    if action:
        parts.append(action.text)
    if contact:
        parts.append(f"How to reach them: {contact.text}")
    return " ".join(parts)[:1900]


def _ops_brief(steps: list[ResolutionStep], evidence_by_fact: dict[str, EvidenceChunk]) -> str:
    """Operations-facing briefing where every line shows its citation.

    Unlike the plain-language citizen summary, this is auditable: a reviewer can
    trace each instruction straight back to ``[fact_id · source]``.
    """
    lines: list[str] = []
    for step in steps:
        cites = " ".join(
            evidence_by_fact[fid].citation for fid in step.cited_fact_ids if fid in evidence_by_fact
        )
        lines.append(f"- ({step.kind}) {step.text} {cites}".rstrip())
    return "\n".join(lines)[:2300]


def build_plan(
    complaint_id: str,
    routing_sector: str | None,
    routing_entity: str | None,
    complaint_text: str,
    routing_confidence: float | None = None,
    hitl_required: bool = False,
    kb: EntityKnowledgeBase | None = None,
    k: int = 8,
) -> GroundedResolutionPlan:
    """Retrieve → synthesise → verify → decide. Deterministic."""
    kb = kb or get_kb()
    query = complaint_text or ""
    evidence = kb.retrieve(query, sector=routing_sector, entity=routing_entity, k=k)
    top_score = evidence[0].score if evidence else 0.0

    candidates = _candidate_steps(evidence)
    evidence_by_fact = {c.fact_id: c for c in evidence}
    verified = verify_steps(candidates, evidence_by_fact)
    plan_groundedness = groundedness(verified)
    issued = [s for s in verified if s.supported]
    conflicts = detect_conflicts(evidence)
    cover = coverage_score(query, [c.text for c in evidence])

    plan = GroundedResolutionPlan(
        complaint_id=complaint_id,
        routing_sector=routing_sector,
        routing_entity=routing_entity,
        groundedness=round(plan_groundedness, 4),
        top_retrieval_score=round(top_score, 6),
        coverage=round(cover, 4),
        plan_confidence=plan_confidence_score(plan_groundedness, top_score, routing_confidence),
        evidence=evidence,
        conflicts=conflicts,
    )

    # ── Abstention policy (never auto-advise when not trustworthy) ──────────
    sector_u = (routing_sector or "").upper()
    safety_conflict = any(c.fact_type in _SAFETY_TYPES for c in conflicts)
    if sector_u in ABSTAIN_SECTORS:
        plan.abstained = True
        plan.force_hitl = True
        plan.abstain_reason = f"safety_sector_requires_human_review:{sector_u}"
    elif not evidence or top_score < MIN_RETRIEVAL_SCORE:
        plan.abstained = True
        plan.force_hitl = True
        plan.abstain_reason = "no_kb_coverage_for_complaint"
    elif safety_conflict:
        # Contradictory life-safety instructions must never be auto-issued.
        plan.abstained = True
        plan.force_hitl = True
        plan.abstain_reason = "conflicting_evidence"
    elif not issued or plan_groundedness < MIN_GROUNDEDNESS:
        plan.abstained = True
        plan.force_hitl = True
        plan.abstain_reason = f"low_groundedness:{plan_groundedness:.2f}<{MIN_GROUNDEDNESS}"
    elif hitl_required or conflicts:
        # Upstream routed to a human, or the KB disagrees with itself on a
        # non-safety detail: issue a grounded *draft* but keep a human in loop.
        plan.force_hitl = True

    # Always attach the verified steps (a human reviewer benefits from them too).
    plan.steps = issued if issued else verified
    if not plan.abstained:
        plan.citizen_summary = _citizen_summary(routing_entity, routing_sector, issued)
        plan.ops_brief = _ops_brief(plan.steps, evidence_by_fact)
    else:
        plan.citizen_summary = ""
        plan.ops_brief = _ops_brief(plan.steps, evidence_by_fact)
        # Turn the failure into a ranked acquisition signal.
        if plan.abstain_reason in {"no_kb_coverage_for_complaint", "conflicting_evidence"} or (
            plan.abstain_reason.startswith("low_groundedness")
        ):
            plan.evidence_gaps = [
                _infer_evidence_gap(
                    routing_sector, routing_entity, query, evidence, plan.abstain_reason
                )
            ]
    return plan

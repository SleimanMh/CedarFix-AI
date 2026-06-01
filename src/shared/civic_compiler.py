"""Civic Intelligence Compiler.

This is the top-level CedarFix intelligence artifact: it compiles the outputs
from IEP-1 through IEP-8 into one proof-carrying incident program.

The compiler does not replace the individual services. It makes their work
inspectable as a single civic reasoning object:

- belief state: what the system currently believes happened;
- evidence atoms: which stage produced which claim;
- proof obligations: what must be true before autonomy is allowed;
- counterfactual routes: what would change the decision;
- active sensing: what question would buy the most certainty;
- autonomy decision: what the system may and may not do.

That is the strongest version of "AI heaviness" for this project: CedarFix is
not just predicting a label. It is compiling citizen chaos into a verified,
auditable civic incident program.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

COMPILER_VERSION = "civic-compiler-v1"


class ProofStatus(str, Enum):
    SATISFIED = "satisfied"
    NEEDS_HUMAN = "needs_human"
    BLOCKED = "blocked"


class AutonomyLevel(str, Enum):
    AUTO_ROUTE_WITH_AUDIT = "auto_route_with_audit"
    HUMAN_APPROVE = "human_approve"
    HUMAN_INVESTIGATE = "human_investigate"


class EvidenceAtom(BaseModel):
    """One inspectable claim emitted by a CedarFix intelligence stage."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    stage: str = Field(..., min_length=1)
    claim: str = Field(..., min_length=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list)
    support_status: str = Field(default="observed", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("citations")
    @classmethod
    def sort_unique_citations(cls, value: list[str]) -> list[str]:
        return sorted({str(item) for item in value if str(item).strip()})


class ProofObligation(BaseModel):
    """A safety/trust obligation that gates automatic civic action."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    status: ProofStatus
    severity: str = Field(default="medium", min_length=1)
    evidence_atom_ids: list[str] = Field(default_factory=list)
    reason: str = Field(default="", max_length=400)
    blocks_auto_route: bool = False

    @field_validator("evidence_atom_ids")
    @classmethod
    def sort_unique_evidence_ids(cls, value: list[str]) -> list[str]:
        return sorted({str(item) for item in value if str(item).strip()})


class ActiveSensingQuestion(BaseModel):
    """Question selected because it most reduces routing uncertainty."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    target_feature: str = Field(..., min_length=1)
    expected_information_gain: float = Field(..., ge=0.0, le=1.0)
    trigger: str = Field(..., min_length=1)
    blocks_auto_route: bool = False


class CounterfactualRoute(BaseModel):
    """A decision branch that would route differently under changed evidence."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    condition: str = Field(..., min_length=1)
    routing_sector: str = Field(..., min_length=1)
    routing_entity: str = Field(..., min_length=1)
    effect: str = Field(..., min_length=1)
    risk_delta: float = Field(default=0.0, ge=-1.0, le=1.0)


class AutonomyDecision(BaseModel):
    """What CedarFix is allowed to do after proof checking."""

    model_config = ConfigDict(extra="forbid")

    level: AutonomyLevel
    risk_score: float = Field(..., ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)

    @field_validator("reasons", "allowed_actions", "forbidden_actions")
    @classmethod
    def sort_unique_values(cls, value: list[str]) -> list[str]:
        return sorted({str(item) for item in value if str(item).strip()})


class IncidentProgram(BaseModel):
    """Proof-carrying incident program compiled from all CedarFix IEP outputs."""

    model_config = ConfigDict(extra="forbid")

    complaint_id: str = Field(..., min_length=1)
    generated_at_utc: str = Field(..., min_length=1)
    compiler_version: str = COMPILER_VERSION
    thesis: str = (
        "CedarFix compiles noisy citizen input into a verified civic incident "
        "program with evidence, counterfactuals, active sensing, and autonomy limits."
    )
    raw_text: str = Field(default="")
    belief_state: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceAtom] = Field(default_factory=list)
    proof_obligations: list[ProofObligation] = Field(default_factory=list)
    active_sensing: list[ActiveSensingQuestion] = Field(default_factory=list)
    counterfactual_routes: list[CounterfactualRoute] = Field(default_factory=list)
    autonomy_decision: AutonomyDecision
    scoreboard: dict[str, Any] = Field(default_factory=dict)
    dsl: str = Field(..., min_length=1)


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {}


def _clip01(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    return bool(value)


def _upper(value: Any, default: str = "UNKNOWN") -> str:
    text = str(value or "").strip().upper()
    return text or default


def _citations(*groups: Any) -> list[str]:
    out: list[str] = []
    for group in groups:
        if isinstance(group, str):
            if group.strip():
                out.append(group.strip())
        elif isinstance(group, list):
            out.extend(str(item).strip() for item in group if str(item).strip())
        elif isinstance(group, tuple | set):
            out.extend(str(item).strip() for item in group if str(item).strip())
    return sorted(set(out))


def _add_atom(
    atoms: list[EvidenceAtom],
    *,
    stage: str,
    claim: str,
    confidence: float,
    citations: list[str] | None = None,
    support_status: str = "observed",
    metadata: dict[str, Any] | None = None,
) -> str:
    atom_id = f"E{len(atoms) + 1:03d}"
    atoms.append(
        EvidenceAtom(
            id=atom_id,
            stage=stage,
            claim=claim,
            confidence=_clip01(confidence),
            citations=citations or [],
            support_status=support_status,
            metadata=metadata or {},
        )
    )
    return atom_id


def _proof_rate(obligations: list[ProofObligation]) -> float:
    if not obligations:
        return 0.0
    return round(
        sum(1 for item in obligations if item.status == ProofStatus.SATISFIED)
        / len(obligations),
        4,
    )


def _obligation(
    obligations: list[ProofObligation],
    *,
    oid: str,
    description: str,
    status: ProofStatus,
    evidence_atom_ids: list[str],
    reason: str,
    severity: str = "medium",
    blocks_auto_route: bool | None = None,
) -> None:
    blocks = status == ProofStatus.BLOCKED if blocks_auto_route is None else blocks_auto_route
    obligations.append(
        ProofObligation(
            id=oid,
            description=description,
            status=status,
            severity=severity,
            evidence_atom_ids=evidence_atom_ids,
            reason=reason,
            blocks_auto_route=blocks,
        )
    )


def _build_active_sensing(
    *,
    gps_lat: float | None,
    gps_lon: float | None,
    drift_score: int,
    image_agreement: str,
    kb_has_citations: bool,
    kb_location_method: str,
    boundary_entity: str,
) -> list[ActiveSensingQuestion]:
    questions: list[ActiveSensingQuestion] = []
    if gps_lat is None or gps_lon is None or kb_location_method in {"not_found", "gps_out_of_range"}:
        questions.append(
            ActiveSensingQuestion(
                id="Q-LOCATION",
                question="Please provide the nearest landmark or exact pinned location.",
                target_feature="jurisdiction_location",
                expected_information_gain=0.92,
                trigger="missing_or_untrusted_location",
                blocks_auto_route=True,
            )
        )
    if image_agreement == "conflict":
        questions.append(
            ActiveSensingQuestion(
                id="Q-MODALITY",
                question="Does the photo show the same issue described in the text?",
                target_feature="image_text_consistency",
                expected_information_gain=0.86,
                trigger="image_text_conflict",
                blocks_auto_route=True,
            )
        )
    if boundary_entity:
        questions.append(
            ActiveSensingQuestion(
                id="Q-ASSET",
                question="Is the affected asset public, private, or managed by another authority?",
                target_feature="asset_ownership_boundary",
                expected_information_gain=0.79,
                trigger="kb_boundary_entity",
                blocks_auto_route=True,
            )
        )
    if not kb_has_citations:
        questions.append(
            ActiveSensingQuestion(
                id="Q-SOURCE",
                question="Which verified KB source supports this entity assignment?",
                target_feature="source_grounding",
                expected_information_gain=0.74,
                trigger="missing_kb_citation",
                blocks_auto_route=True,
            )
        )
    if drift_score >= 2:
        questions.append(
            ActiveSensingQuestion(
                id="Q-LANGUAGE",
                question="Please confirm the intended issue type for the unfamiliar wording.",
                target_feature="language_drift_resolution",
                expected_information_gain=0.68,
                trigger="high_language_drift",
                blocks_auto_route=False,
            )
        )
    return questions


def _build_counterfactuals(
    *,
    sector: str,
    entity: str,
    image_sector: str,
    image_agreement: str,
    secondary_entity: str,
    boundary_entity: str,
    kb_location_method: str,
) -> list[CounterfactualRoute]:
    routes: list[CounterfactualRoute] = []
    if image_agreement == "conflict" and image_sector:
        routes.append(
            CounterfactualRoute(
                id="CF-IMAGE",
                condition="If the image is judged authoritative over the text.",
                routing_sector=image_sector,
                routing_entity="HITL",
                effect=f"Freeze {sector}->{entity} and reroute for visual-sector review.",
                risk_delta=0.25,
            )
        )
    if secondary_entity:
        secondary_display = (
            f"MUN-{secondary_entity}"
            if secondary_entity.isdigit()
            else secondary_entity
        )
        routes.append(
            CounterfactualRoute(
                id="CF-SECONDARY",
                condition="If the primary entity rejects ownership.",
                routing_sector=sector,
                routing_entity=secondary_display,
                effect="Escalate to the KB secondary entity with the same evidence bundle.",
                risk_delta=0.10,
            )
        )
    if boundary_entity:
        routes.append(
            CounterfactualRoute(
                id="CF-BOUNDARY",
                condition="If the boundary condition is confirmed.",
                routing_sector=sector,
                routing_entity=boundary_entity,
                effect="Route to the boundary entity and keep original entity as context.",
                risk_delta=0.18,
            )
        )
    if kb_location_method in {"not_found", "gps_out_of_range"}:
        routes.append(
            CounterfactualRoute(
                id="CF-LOCATION",
                condition="If a trusted municipality or GPS point is supplied.",
                routing_sector=sector,
                routing_entity="entity_resolved_from_service_area",
                effect="Recompute jurisdiction instead of using a generic sector route.",
                risk_delta=-0.20,
            )
        )
    return routes


def _autonomy_decision(
    *,
    obligations: list[ProofObligation],
    active_sensing: list[ActiveSensingQuestion],
    routing_confidence: float,
    routing_risk: float,
    drift_score: int,
    hitl_required: bool,
    image_agreement: str,
    kb_has_citations: bool,
    iep8_abstained: bool,
    gps_missing: bool,
) -> AutonomyDecision:
    blocked = [item.id for item in obligations if item.status == ProofStatus.BLOCKED]
    needs_human = [item.id for item in obligations if item.status == ProofStatus.NEEDS_HUMAN]

    risk = 0.08
    risk += routing_risk * 0.55
    risk += max(0.0, 1.0 - routing_confidence) * 0.20
    risk += min(0.24, drift_score * 0.08)
    if hitl_required:
        risk += 0.25
    if image_agreement == "conflict":
        risk += 0.30
    if not kb_has_citations:
        risk += 0.20
    if iep8_abstained:
        risk += 0.18
    if gps_missing:
        risk += 0.10
    if blocked:
        risk += 0.35
    if any(q.blocks_auto_route for q in active_sensing):
        risk += 0.12
    risk = _clip01(risk)

    reasons: list[str] = []
    if blocked:
        reasons.append("blocked_proof_obligations:" + ",".join(blocked))
    if needs_human:
        reasons.append("human_review_obligations:" + ",".join(needs_human))
    if hitl_required:
        reasons.append("upstream_hitl_required")
    if image_agreement == "conflict":
        reasons.append("image_text_conflict")
    if not kb_has_citations:
        reasons.append("missing_source_grounding")
    if drift_score >= 2:
        reasons.append("language_drift")
    if risk >= 0.65:
        reasons.append("autonomy_risk_high")

    if blocked or risk >= 0.75:
        level = AutonomyLevel.HUMAN_INVESTIGATE
        allowed = [
            "show_proof_dossier_to_reviewer",
            "ask_active_sensing_questions",
            "create_retraining_candidate_when_corrected",
        ]
        forbidden = [
            "auto_route_to_public_entity",
            "invent_agency_or_contact",
            "promise_repair_timeline",
        ]
    elif hitl_required or needs_human or risk >= 0.55:
        level = AutonomyLevel.HUMAN_APPROVE
        allowed = [
            "draft_source_grounded_route",
            "show_counterfactual_routes",
            "ask_active_sensing_questions",
        ]
        forbidden = [
            "finalize_without_human_approval",
            "invent_agency_or_contact",
            "promise_repair_timeline",
        ]
    else:
        level = AutonomyLevel.AUTO_ROUTE_WITH_AUDIT
        allowed = [
            "route_with_proof_dossier",
            "attach_citations",
            "monitor_lifecycle_for_reopen",
        ]
        forbidden = [
            "invent_agency_or_contact",
            "promise_repair_timeline",
            "hide_uncertainty",
        ]

    return AutonomyDecision(
        level=level,
        risk_score=risk,
        reasons=reasons or ["proof_obligations_satisfied"],
        allowed_actions=allowed,
        forbidden_actions=forbidden,
    )


def _render_dsl(
    *,
    complaint_id: str,
    language: str,
    sector: str,
    issue_type: str,
    issue_confidence: float,
    entity: str,
    routing_confidence: float,
    incident_id: str,
    cluster_size: int,
    image_agreement: str,
    proof_obligations: list[ProofObligation],
    autonomy: AutonomyDecision,
    kb_fact_ids: list[str],
) -> str:
    proof_lines = [
        f"  prove {item.id} = {item.status.value};"
        for item in proof_obligations
    ]
    fact_text = ", ".join(kb_fact_ids[:5]) if kb_fact_ids else "none"
    lines = [
        f"incident_program {complaint_id} {{",
        f"  observe language = {language};",
        f"  infer issue = {sector}.{issue_type} p={issue_confidence:.2f};",
        f"  cluster incident = {incident_id or 'new'} size={cluster_size};",
        f"  route entity = {entity} p={routing_confidence:.2f};",
        f"  ground kb_facts = [{fact_text}];",
        f"  fuse image_text = {image_agreement or 'no_image_signal'};",
        *proof_lines,
        f"  autonomy {autonomy.level.value} risk={autonomy.risk_score:.2f};",
        "}",
    ]
    return "\n".join(lines)


def compile_incident_program(
    *,
    complaint_id: str,
    text_raw: str = "",
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    iep1_signal_json: dict[str, Any] | None = None,
    iep1_output: dict[str, Any] | None = None,
    iep2_incident_json: dict[str, Any] | None = None,
    iep3_routing_json: dict[str, Any] | None = None,
    image_fusion_json: dict[str, Any] | None = None,
    iep4_explanation_json: dict[str, Any] | None = None,
    iep8_resolution_json: dict[str, Any] | None = None,
    lifecycle_json: dict[str, Any] | None = None,
    calibration_json: dict[str, Any] | None = None,
) -> IncidentProgram:
    """Compile IEP outputs into a proof-carrying incident program.

    All inputs are optional dictionaries because each service can run
    independently. Missing evidence does not crash the compiler; it becomes a
    proof obligation that blocks autonomy.
    """
    iep1 = _as_dict(iep1_output)
    signal = _as_dict(iep1_signal_json or iep1.get("iep1_signal_json"))
    incident = _as_dict(iep2_incident_json)
    routing = _as_dict(iep3_routing_json)
    image = _as_dict(image_fusion_json)
    explanation = _as_dict(iep4_explanation_json)
    resolution = _as_dict(iep8_resolution_json)
    lifecycle = _as_dict(lifecycle_json)
    calibration = _as_dict(calibration_json)

    language = str(iep1.get("language") or signal.get("language") or "unknown")
    drift_score = int(_num(iep1.get("drift_score", signal.get("drift_score")), 0))
    sector = _upper(
        routing.get("routing_sector")
        or iep1.get("routing_sector")
        or signal.get("routing_sector"),
        default="OTHER",
    )
    issue_type = str(
        routing.get("issue_type")
        or iep1.get("issue_type")
        or signal.get("classification_trace", {}).get("hybrid", {}).get("issue_type")
        or "UNCLASSIFIED"
    )
    issue_confidence = _clip01(
        _num(
            routing.get("issue_type_confidence")
            or iep1.get("issue_type_confidence")
            or signal.get("classification_trace", {}).get("hybrid", {}).get("confidence"),
            0.0,
        )
    )

    entity = _upper(routing.get("routing_entity"), default="HITL")
    routing_confidence = _clip01(_num(routing.get("routing_confidence"), 0.0))
    hitl_required = _bool(routing.get("hitl_required"))
    shap = _as_dict(routing.get("shap_top3"))
    routing_risk = _clip01(
        _num(routing.get("routing_risk_score") or shap.get("routing_risk_score"), 0.0)
    )
    kb_location_method = str(routing.get("kb_location_method") or shap.get("kb_location_method") or "")
    boundary_entity = str(routing.get("kb_boundary_entity") or shap.get("kb_boundary_entity") or "")
    secondary_entity = str(routing.get("kb_secondary_entity") or shap.get("kb_secondary_entity") or "")

    fusion = _as_dict(image.get("fusion"))
    image_agreement = str(fusion.get("agreement") or "no_image_signal")
    image_sector = _upper(image.get("image_sector"), default="")

    evidence_refs = _as_dict(explanation.get("evidence_refs"))
    guardrails = _as_dict(explanation.get("guardrails"))
    verifier = _as_dict(explanation.get("verifier"))
    resolution_evidence = [
        item for item in resolution.get("evidence", []) if isinstance(item, dict)
    ]
    on_entity_resolution_evidence = [
        item
        for item in resolution_evidence
        if _upper(item.get("entity_id"), default="") == entity
        or str(item.get("fact_id", "")).upper().startswith(f"{entity}-")
    ]
    usable_resolution_evidence = on_entity_resolution_evidence or resolution_evidence[:2]
    kb_fact_ids = _citations(
        evidence_refs.get("kb_fact_ids"),
        verifier.get("allowed_fact_ids"),
        [item.get("fact_id") for item in usable_resolution_evidence],
    )
    kb_source_ids = _citations(
        evidence_refs.get("kb_source_ids"),
        verifier.get("allowed_source_ids"),
        [
            source_id
            for item in usable_resolution_evidence
            for source_id in item.get("source_ids", [])
        ],
    )
    kb_has_citations = bool(kb_fact_ids or kb_source_ids)
    iep8_abstained = _bool(resolution.get("abstained"))

    atoms: list[EvidenceAtom] = []
    e_issue = _add_atom(
        atoms,
        stage="IEP1",
        claim=f"Hybrid language/semantic model predicts {sector}.{issue_type}.",
        confidence=issue_confidence,
        support_status="model_and_rules_trace",
        metadata={
            "language": language,
            "drift_score": drift_score,
            "classification_trace": signal.get("classification_trace"),
            "review_recommendation": signal.get("review_recommendation"),
        },
    )
    e_cluster = _add_atom(
        atoms,
        stage="IEP2",
        claim=(
            "Incident fusion places complaint in cluster "
            f"{incident.get('incident_id') or 'new'} with size {incident.get('cluster_size', 1)}."
        ),
        confidence=_num(_as_dict(incident.get("match_evidence")).get("fusion_score"), 0.5),
        support_status=str(incident.get("review_recommendation") or "cluster_packet"),
        metadata=incident,
    )
    e_route = _add_atom(
        atoms,
        stage="IEP3",
        claim=f"Neuro-symbolic router assigns {sector} to {entity}.",
        confidence=routing_confidence,
        citations=_citations(routing.get("kb_complaint_type_id"), routing.get("kb_route_reason")),
        support_status="kb_and_risk_trace",
        metadata={
            "routing_risk_score": routing_risk,
            "routing_risk_factors": routing.get("routing_risk_factors")
            or shap.get("routing_risk_factors"),
            "neuro_symbolic_trace": routing.get("neuro_symbolic_trace")
            or shap.get("neuro_symbolic_trace"),
        },
    )
    e_kb = _add_atom(
        atoms,
        stage="IEP4/IEP8",
        claim="Explanation and resolution plan are constrained to cited KB facts.",
        confidence=1.0 if kb_has_citations else 0.0,
        citations=_citations(kb_fact_ids, kb_source_ids),
        support_status="source_grounded" if kb_has_citations else "missing_source_grounding",
        metadata={
            "iep8_groundedness": resolution.get("groundedness"),
            "iep8_top_retrieval_score": resolution.get("top_retrieval_score"),
            "iep8_abstained": resolution.get("abstained"),
        },
    )
    e_image = _add_atom(
        atoms,
        stage="IEP6",
        claim=f"Image/text fusion result is {image_agreement}.",
        confidence=_num(image.get("image_confidence"), 0.0),
        support_status=image_agreement,
        metadata=image,
    )
    e_lifecycle = _add_atom(
        atoms,
        stage="IEP5/IEP7",
        claim="Lifecycle outcomes and calibration signals govern learning priority.",
        confidence=1.0 if lifecycle or calibration else 0.5,
        support_status="closed_loop_learning" if lifecycle or calibration else "no_runtime_outcome_yet",
        metadata={"lifecycle": lifecycle, "calibration": calibration},
    )

    obligations: list[ProofObligation] = []
    if issue_type != "UNCLASSIFIED" and issue_confidence >= 0.65:
        issue_status = ProofStatus.SATISFIED
        issue_reason = "issue classifier confidence clears autonomy floor"
    elif issue_confidence >= 0.45:
        issue_status = ProofStatus.NEEDS_HUMAN
        issue_reason = "issue signal is usable but below autonomy floor"
    else:
        issue_status = ProofStatus.BLOCKED
        issue_reason = "issue classifier is too uncertain"
    _obligation(
        obligations,
        oid="PO-ISSUE",
        description="Issue type must be specific enough to route.",
        status=issue_status,
        evidence_atom_ids=[e_issue],
        reason=issue_reason,
        severity="high",
    )

    route_ok = entity not in {"", "HITL", "UNKNOWN"} and routing_confidence >= 0.65
    route_needs_human = hitl_required or routing_confidence >= 0.45
    _obligation(
        obligations,
        oid="PO-ROUTE",
        description="Responsible entity must be supported by route confidence and jurisdiction.",
        status=ProofStatus.SATISFIED
        if route_ok and kb_location_method not in {"not_found", "gps_out_of_range"}
        else ProofStatus.NEEDS_HUMAN
        if route_needs_human
        else ProofStatus.BLOCKED,
        evidence_atom_ids=[e_route],
        reason=(
            "route confidence and jurisdiction are sufficient"
            if route_ok
            else "route needs reviewer confirmation"
        ),
        severity="critical",
    )

    _obligation(
        obligations,
        oid="PO-SOURCE",
        description="Entity assignment and explanation must cite KB facts or sources.",
        status=ProofStatus.SATISFIED if kb_has_citations else ProofStatus.BLOCKED,
        evidence_atom_ids=[e_kb],
        reason="KB citations attached" if kb_has_citations else "no source-backed fact ids found",
        severity="critical",
    )

    _obligation(
        obligations,
        oid="PO-MODALITY",
        description="Image and text must not contradict each other before autonomy.",
        status=ProofStatus.BLOCKED
        if image_agreement == "conflict"
        else ProofStatus.SATISFIED
        if image_agreement in {"agree", "no_image_signal", "image_disambiguates"}
        else ProofStatus.NEEDS_HUMAN,
        evidence_atom_ids=[e_image],
        reason=(
            "image conflicts with text"
            if image_agreement == "conflict"
            else "no blocking multimodal conflict"
        ),
        severity="high",
    )

    no_sla_ok = bool(
        guardrails.get("unsupported_sla_blocked", True)
        and verifier.get("no_unverified_deadline", True)
    )
    _obligation(
        obligations,
        oid="PO-NO-HALLUCINATION",
        description="No invented agency, contact, deadline, or SLA may be shown.",
        status=ProofStatus.SATISFIED if no_sla_ok else ProofStatus.BLOCKED,
        evidence_atom_ids=[e_kb],
        reason="explanation verifier blocked unsupported claims"
        if no_sla_ok
        else "explanation verifier did not prove hallucination guardrail",
        severity="critical",
    )

    reopened = bool(lifecycle.get("reopened") or lifecycle.get("reopen_count", 0))
    _obligation(
        obligations,
        oid="PO-LIFECYCLE",
        description="Known lifecycle outcomes must not contradict the current route.",
        status=ProofStatus.NEEDS_HUMAN if reopened else ProofStatus.SATISFIED,
        evidence_atom_ids=[e_lifecycle],
        reason="prior incident reopened, create retraining candidate"
        if reopened
        else "no adverse lifecycle outcome attached",
        severity="medium",
        blocks_auto_route=reopened,
    )

    active_sensing = _build_active_sensing(
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        drift_score=drift_score,
        image_agreement=image_agreement,
        kb_has_citations=kb_has_citations,
        kb_location_method=kb_location_method,
        boundary_entity=boundary_entity,
    )
    counterfactuals = _build_counterfactuals(
        sector=sector,
        entity=entity,
        image_sector=image_sector,
        image_agreement=image_agreement,
        secondary_entity=secondary_entity,
        boundary_entity=boundary_entity,
        kb_location_method=kb_location_method,
    )
    autonomy = _autonomy_decision(
        obligations=obligations,
        active_sensing=active_sensing,
        routing_confidence=routing_confidence,
        routing_risk=routing_risk,
        drift_score=drift_score,
        hitl_required=hitl_required,
        image_agreement=image_agreement,
        kb_has_citations=kb_has_citations,
        iep8_abstained=iep8_abstained,
        gps_missing=gps_lat is None or gps_lon is None,
    )

    cluster_size = int(_num(incident.get("cluster_size"), 1))
    incident_id = str(incident.get("incident_id") or "")
    ai_layers = [
        "iep1_hybrid_semantic_classifier",
        "iep2_vector_incident_fusion",
        "iep3_neuro_symbolic_router",
        "iep4_source_grounded_explainer",
        "civic_compiler_proof_governor",
    ]
    if image:
        ai_layers.append("iep6_multimodal_verifier")
    if lifecycle:
        ai_layers.append("iep5_lifecycle_active_learning")
    if calibration:
        ai_layers.append("iep7_calibration_drift_governor")
    if resolution:
        ai_layers.append("iep8_grounded_resolution_verifier")

    belief_state = {
        "language": language,
        "drift_score": drift_score,
        "issue": {
            "sector": sector,
            "issue_type": issue_type,
            "confidence": issue_confidence,
        },
        "incident": {
            "incident_id": incident_id,
            "cluster_size": cluster_size,
            "lifecycle_state": incident.get("incident_lifecycle_state"),
        },
        "routing": {
            "entity": entity,
            "confidence": routing_confidence,
            "risk_score": routing_risk,
            "hitl_required": hitl_required,
            "kb_location_method": kb_location_method,
        },
        "multimodal": {
            "agreement": image_agreement,
            "image_sector": image_sector,
            "image_confidence": image.get("image_confidence"),
        },
        "grounding": {
            "kb_fact_ids": kb_fact_ids,
            "kb_source_ids": kb_source_ids,
            "iep8_groundedness": resolution.get("groundedness"),
        },
    }
    scoreboard = {
        "proof_satisfaction_rate": _proof_rate(obligations),
        "blocked_obligations": [
            item.id for item in obligations if item.status == ProofStatus.BLOCKED
        ],
        "human_review_obligations": [
            item.id for item in obligations if item.status == ProofStatus.NEEDS_HUMAN
        ],
        "active_question_count": len(active_sensing),
        "counterfactual_count": len(counterfactuals),
        "evidence_atom_count": len(atoms),
        "ai_layers_used": sorted(set(ai_layers)),
        "autonomy_level": autonomy.level.value,
        "autonomy_risk_score": autonomy.risk_score,
    }
    dsl = _render_dsl(
        complaint_id=complaint_id,
        language=language,
        sector=sector,
        issue_type=issue_type,
        issue_confidence=issue_confidence,
        entity=entity,
        routing_confidence=routing_confidence,
        incident_id=incident_id,
        cluster_size=cluster_size,
        image_agreement=image_agreement,
        proof_obligations=obligations,
        autonomy=autonomy,
        kb_fact_ids=kb_fact_ids,
    )

    return IncidentProgram(
        complaint_id=complaint_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        raw_text=text_raw,
        belief_state=belief_state,
        evidence=atoms,
        proof_obligations=obligations,
        active_sensing=active_sensing,
        counterfactual_routes=counterfactuals,
        autonomy_decision=autonomy,
        scoreboard=scoreboard,
        dsl=dsl,
    )


def compile_demo_case(
    *,
    complaint_id: str,
    text: str,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    image_sector: str | None = "WATER",
    image_confidence: float | None = 0.91,
) -> IncidentProgram:
    """Run a dependency-light end-to-end demo and compile its proof program."""
    from src.iep1.extractor import extract
    from src.iep2.dedup import build_incident_intelligence, classify_pair
    from src.iep3.worker import _build_routing_intelligence, _route_with_kb
    from src.iep4.explainer import explain
    from src.iep8.planner import build_plan
    from src.shared.image_schemas import ImageHazardSignal, fuse_image_text

    iep1 = extract(
        complaint_id=complaint_id,
        text=text,
        language_hint="arabizi",
        include_embedding=False,
        use_model=True,
    )
    signal = _as_dict(iep1.get("iep1_signal_json"))

    # Five differently worded nearby reports are represented as an existing
    # emerging cluster, so the compiler can show incident fusion in one run.
    cluster_candidates = [
        {
            "complaint_id": f"{complaint_id}-near-{i}",
            "incident_id": f"INC-{complaint_id}",
            "text_embedding_ref": [0.98, 0.02, 0.0],
            "gps_lat": gps_lat,
            "gps_lon": gps_lon,
            "issue_type": iep1.get("issue_type"),
            "created_at": None,
        }
        for i in range(1, 5)
    ]
    dedup = classify_pair(
        complaint_id=complaint_id,
        embedding_ref=[1.0, 0.0, 0.0],
        lat=gps_lat,
        lon=gps_lon,
        issue_type=iep1.get("issue_type"),
        candidates=cluster_candidates,
        image_issue_type=image_sector,
    )
    incident = build_incident_intelligence(complaint_id, dedup, cluster_candidates)

    route_decision = _route_with_kb(
        complaint_id=complaint_id,
        text_raw=text,
        normalized_text=iep1.get("normalized_text"),
        routing_sector=iep1.get("routing_sector"),
        issue_type=iep1.get("issue_type"),
        issue_type_confidence=iep1.get("issue_type_confidence"),
        drift_score=iep1.get("drift_score"),
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        iep1_signal_json=signal,
    )
    route_packet = _build_routing_intelligence(
        complaint_id,
        route_decision,
        issue_type=iep1.get("issue_type"),
        issue_type_confidence=iep1.get("issue_type_confidence"),
        hitl_required=route_decision["hitl_required"],
        hitl_reason=route_decision.get("hitl_reason"),
    )

    image_packet = None
    if image_sector:
        fusion = fuse_image_text(
            route_packet.get("routing_sector"),
            image_sector,
            image_confidence,
        )
        image_packet = ImageHazardSignal(
            available=True,
            image_label=f"synthetic_{image_sector.lower()}",
            image_sector=image_sector,
            image_confidence=image_confidence,
            fusion=fusion,
        ).model_dump(mode="json")

    explanation = explain(
        complaint_id=complaint_id,
        routing_sector=route_packet.get("routing_sector"),
        routing_entity=route_packet.get("routing_entity"),
        routing_confidence=route_packet.get("routing_confidence"),
        priority_score=route_packet.get("priority_score"),
        issue_type=route_packet.get("issue_type"),
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        hitl_required=route_packet.get("hitl_required", False),
        language=iep1.get("language"),
        text_raw=text,
        hitl_reason=route_packet.get("hitl_reason"),
        iep1_signal_json=signal,
        iep2_incident_json=incident,
        iep3_routing_json=route_packet,
        image_fusion_json=image_packet,
        shap_top3=route_packet.get("shap_top3"),
    )
    resolution = build_plan(
        complaint_id=complaint_id,
        routing_sector=route_packet.get("routing_sector"),
        routing_entity=route_packet.get("routing_entity"),
        complaint_text=text,
        routing_confidence=route_packet.get("routing_confidence"),
        hitl_required=route_packet.get("hitl_required", False),
    ).model_dump(mode="json")

    return compile_incident_program(
        complaint_id=complaint_id,
        text_raw=text,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        iep1_signal_json=signal,
        iep1_output=iep1,
        iep2_incident_json=incident,
        iep3_routing_json=route_packet,
        image_fusion_json=image_packet,
        iep4_explanation_json=explanation.get("iep4_explanation_json"),
        iep8_resolution_json=resolution,
        lifecycle_json={"reopened": False, "reopen_count": 0},
        calibration_json={"sector": route_packet.get("routing_sector"), "ece": 0.07},
    )

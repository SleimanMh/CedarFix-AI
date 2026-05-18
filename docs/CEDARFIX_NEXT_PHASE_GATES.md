# CedarFix Next-Phase Gates

Version 1.0 | Purpose: apply the same ruthless evidence standard to the full
project that we applied to Arabizi.

## Run

```bash
python scripts/audit_cedarfix_next_phase_gates.py
python scripts/audit_rubric_readiness.py
```

Artifacts:

```bash
data/eval/cedarfix_next_phase_gates_v1.json
data/eval/rubric_readiness_v1.json
```

## Gate Philosophy

Every high-grade claim needs:

- a working artifact
- an evaluation artifact
- a regression test
- a documented professor defense

If any one of those is missing, the feature is not final. It may be promising,
but it is not yet grade-proof.

## Current Build Order

| Rank | Build | Rubric unlocked | Why |
| ---: | --- | --- | --- |
| 1 | IEP-2 dedup/cluster service | T3, T4, T5, D3 | This is the core CedarFix originality beyond a complaint dashboard |
| 2 | IEP-3 calibrated routing/priority | T1, T5, M2, D3 | Calibration makes escalation defensible |
| 3 | Batch 002 Arabizi and hard negatives | P2, T5, Q2, M2 | Better validation beats clever architecture |
| 4 | IEP-4 explanation/HITL service | T4, D2, D3, M4 | Makes AI decisions understandable and auditable |
| 5 | MLflow + Prometheus/Grafana | M1, M2, M3, S4 | Turns models into lifecycle evidence |
| 6 | Public cloud EEP | GT2, S5, D1 | Hard gate for grading |

## Final Release Gates

The project is not final until these pass:

- EEP + IEP-1 foundation
- IEP-2 duplicate/cluster service
- IEP-3 calibrated routing and priority
- IEP-4 explanation/HITL service
- MLOps lifecycle and experiment evidence
- Observability
- Public cloud EEP readiness
- Demo evidence package
- QA breadth

## Honest Claim Boundary

Before IEP-2/IEP-3 are implemented:

> CedarFix has a strong ingestion and Arabizi reliability foundation.

After IEP-2/IEP-3 are implemented and evaluated:

> CedarFix converts fragmented multilingual reports into clustered, prioritized,
> explainable incidents with measured dedup/routing tradeoffs.

After cloud, MLflow, monitoring, and demo artifacts pass:

> CedarFix is a production-style AI engineering system with end-to-end
> orchestration, validation, observability, and professor-defensible evidence.

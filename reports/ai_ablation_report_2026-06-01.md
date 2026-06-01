# CedarFix AI Ablation Report

Generated: 2026-06-01T02:52:51

Systems compared:

- Rules-only: production vocabulary/keyword baseline.
- Model-only: learned hashed char-gram classifier over noisy multilingual text.
- Hybrid: model + rules arbitration with HITL on disagreement and low confidence.

Eval set: **locked held-out test only** (`cidarfix_v29_batch7_model_final_test_locked.jsonl`). The learned model trains on `batch8_train` only, so these numbers are leakage-free.

Auto-route **coverage** = share of cases the system auto-routes without HITL. Auto-route **precision** = sector accuracy *within* those auto-routed cases. The hybrid goal is high auto-route precision at safe coverage, not raw accuracy.

| System | N | Sector acc | Label acc | Review/HITL | Auto-route coverage | Auto-route precision | False auto-routes |
|---|---:|---:|---:|---:|---:|---:|---:|
| rules_only | 1000 | 66.8% | 0.0% | 58.8% | 41.2% | 67.0% | 136 |
| model_only | 1000 | 100.0% | 99.2% | 78.6% | 21.4% | 100.0% | 0 |
| hybrid | 1000 | 96.4% | 83.3% | 99.6% | 0.4% | 100.0% | 0 |

Top hybrid confusions:

- FLOODING -> WATER: 8
- FLOODING -> ROADS: 4
- SAFETY -> ROADS: 3
- WASTE -> ROADS: 2
- FLOODING -> WASTE: 2
- ROADS -> TELECOM: 2
- ELECTRICITY -> SAFETY: 2
- FLOODING -> SAFETY: 2
- ELECTRICITY -> ROADS: 1
- FLOODING -> OTHER: 1
- WATER -> WASTE: 1
- ROADS -> SAFETY: 1
- ELECTRICITY -> WATER: 1
- ROADS -> WASTE: 1
- SAFETY -> TELECOM: 1
- SAFETY -> ELECTRICITY: 1
- WATER -> FLOODING: 1
- SAFETY -> WATER: 1
- FLOODING -> TELECOM: 1

Interpretation: CedarFix should present the hybrid row, not a standalone model claim. The model provides semantic reach; rules and HITL provide safety.
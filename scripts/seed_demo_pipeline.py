"""Seed a realistic CedarFix demo dataset directly into the database.

Purpose
-------
The two flagship new services — IEP-5 (incident lifecycle) and IEP-7
(calibration & drift) — derive everything from rows in the database. Without
data, ``GET /incidents/{id}/timeline`` and ``GET /calibration/latest`` return
empty results on stage. This script populates a small but *honest* synthetic
dataset so those endpoints (and the Grafana calibration panels) show real
numbers during a demo, **without** standing up Redis/Postgres/the async stack.

It is synthetic demo data only: no real citizens, addresses, or public-sector
contacts are invented. Sectors and entity codes reuse the project taxonomy.

Usage
-----
    $env:PYTHONUTF8=1
    .venv/Scripts/python.exe scripts/seed_demo_pipeline.py

By default it writes to a local SQLite file (``cedarfix_demo.db``) so it runs
with zero infrastructure. Point it at the real stack by exporting DATABASE_URL
(e.g. ``postgresql+asyncpg://...``) before running.
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Default to a standalone SQLite database so the seed runs without Docker.
os.environ.setdefault(
    "DATABASE_URL", "sqlite+aiosqlite:///./cedarfix_demo.db"
)
# Calibration needs a reasonable per-sector sample size; keep the demo brisk.
os.environ.setdefault("IEP7_MIN_SECTOR_SAMPLES", "20")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eep.db import (  # noqa: E402
    CalibrationMetric,
    Complaint,
    Incident,
    IncidentLifecycleEvent,
    RetrainingCandidate,
    SessionLocal,
    init_db,
)
from src.iep7.worker import compute_calibration  # noqa: E402
from src.iep5.risk import score_retraining_priority  # noqa: E402
from src.shared.lifecycle_schemas import IncidentState, LifecycleEventType  # noqa: E402

RNG = random.Random(503)

# (sector, entity, samples, reopen_fraction, overconfidence)
# overconfidence > 0 means the model is more confident than it is accurate in
# that sector → produces a non-trivial ECE so IEP-7 has something to flag.
SECTORS = [
    ("WATER", "BWE", 24, 0.25, 0.18),
    ("ELECTRICITY", "EDL", 24, 0.12, 0.05),
    ("ROADS", "MUN", 22, 0.18, 0.10),
    ("WASTE", "MUN", 22, 0.30, 0.22),
]


async def _seed() -> dict:
    await init_db()
    now = datetime.now(timezone.utc)
    totals = {"complaints": 0, "incidents": 0, "reopens": 0, "retrain": 0}

    async with SessionLocal() as session:
        for sector, entity, n, reopen_frac, overconf in SECTORS:
            for i in range(n):
                reopened = RNG.random() < reopen_frac
                # Correct routing held unless the incident was reopened.
                correct = not reopened
                # Confidence: high when correct; for reopened cases inject
                # overconfidence so the sector is poorly calibrated.
                if correct:
                    confidence = round(RNG.uniform(0.70, 0.97), 4)
                else:
                    confidence = round(min(0.99, RNG.uniform(0.55, 0.80) + overconf), 4)

                complaint_id = str(uuid.uuid4())
                incident_id = str(uuid.uuid4())
                created = now - timedelta(hours=RNG.randint(6, 240))

                session.add(
                    Complaint(
                        id=complaint_id,
                        state="PROCESSED",
                        text_raw=f"[demo] {sector.lower()} issue #{i} (seeded)",
                        language="ar-LB",
                        language_confidence=0.9,
                        drift_score=RNG.randint(0, 1),
                        issue_type=sector,
                        issue_type_confidence=confidence,
                        routing_sector=sector,
                        routing_entity=entity,
                        routing_confidence=confidence,
                        priority_score=float(RNG.randint(30, 95)),
                        hitl_required=reopened,
                        hitl_reason="incident_reopened" if reopened else None,
                        incident_id=incident_id,
                        error_flags=[],
                    )
                )

                resolved_at = created + timedelta(hours=RNG.randint(2, 48))
                session.add(
                    Incident(
                        incident_id=incident_id,
                        current_state=IncidentState.RESOLVED.value,
                        complaint_count=1 + (1 if reopened else 0),
                        reopen_count=1 if reopened else 0,
                        routing_sector=sector,
                        routing_entity=entity,
                        last_routing_json={
                            "routing_sector": sector,
                            "routing_entity": entity,
                            "routing_confidence": confidence,
                        },
                        first_seen_at=created,
                        resolved_at=resolved_at,
                        last_event_at=resolved_at,
                    )
                )

                # Event-sourced timeline: open -> route -> resolve (-> reopen -> resolve).
                events = [
                    (None, IncidentState.OPEN, LifecycleEventType.OPEN, "first report"),
                    (IncidentState.OPEN, IncidentState.ROUTED, LifecycleEventType.ROUTE, f"routed to {entity}"),
                    (IncidentState.ROUTED, IncidentState.RESOLVED, LifecycleEventType.RESOLVE, "field crew closed"),
                ]
                if reopened:
                    events.append(
                        (IncidentState.RESOLVED, IncidentState.REOPENED, LifecycleEventType.REOPEN, "citizen re-reported")
                    )
                    events.append(
                        (IncidentState.REOPENED, IncidentState.RESOLVED, LifecycleEventType.RESOLVE, "re-resolved after rework")
                    )
                for offset, (frm, to, ev, reason) in enumerate(events):
                    session.add(
                        IncidentLifecycleEvent(
                            id=str(uuid.uuid4()),
                            incident_id=incident_id,
                            complaint_id=complaint_id,
                            from_state=frm.value if frm else None,
                            to_state=to.value,
                            event=ev.value,
                            reason=reason,
                            actor="seed",
                            created_at=created + timedelta(hours=offset),
                        )
                    )

                if reopened:
                    totals["reopens"] += 1
                    priority = score_retraining_priority(
                        source="reopen",
                        reason="incident reopened after resolution",
                        original_routing={
                            "routing_sector": sector,
                            "routing_entity": entity,
                            "routing_confidence": confidence,
                        },
                    )
                    session.add(
                        RetrainingCandidate(
                            id=str(uuid.uuid4()),
                            complaint_id=complaint_id,
                            incident_id=incident_id,
                            source="reopen",
                            reason="incident reopened after resolution",
                            original_routing={
                                "routing_sector": sector,
                                "routing_entity": entity,
                                "routing_confidence": confidence,
                                **priority,
                            },
                            status="pending",
                        )
                    )
                    totals["retrain"] += 1

                totals["complaints"] += 1
                totals["incidents"] += 1

        await session.commit()

    # Run IEP-7 to derive calibration snapshots from the seeded outcomes.
    reports = await compute_calibration()
    return {"totals": totals, "calibration_sectors": len(reports), "reports": reports}


async def _summary() -> None:
    result = await _seed()
    t = result["totals"]
    print("\n=== CedarFix demo seed complete ===")
    print(f"  DATABASE_URL          : {os.environ['DATABASE_URL']}")
    print(f"  complaints seeded     : {t['complaints']}")
    print(f"  incidents seeded      : {t['incidents']}")
    print(f"  reopens (retraining)  : {t['reopens']}")
    print(f"  calibration sectors   : {result['calibration_sectors']}")
    for r in result["reports"]:
        print(
            f"    - {r.sector:<12} n={r.n:<3} acc={r.accuracy:.2f} "
            f"ece={r.ece:.3f}->{r.calibrated_ece:.3f} "
            f"brier={r.brier:.3f}->{r.calibrated_brier:.3f} "
            f"T={r.calibration_temperature:.2f}"
        )
    print("\nNow: GET /incidents/{id}/timeline (IEP-5) and "
          "GET /calibration/latest (IEP-7) return real data.\n")


if __name__ == "__main__":
    asyncio.run(_summary())

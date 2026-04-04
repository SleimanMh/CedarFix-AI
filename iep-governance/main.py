import json
import os
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import mlflow
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from metrics import (
    setup_metrics,
    ev_governance_mae_kw,
    ev_governance_mae_baseline_kw,
    ev_governance_psi,
    ev_governance_drift_detected,
    ev_governance_retrain_recommended,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "./mlruns")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

MAE_BASELINE_DEFAULT = 3.5  # kW

MODELS_DIR = Path(__file__).parent.parent / "iep-forecast" / "models"

app = FastAPI(title="IEP Governance Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
_last_governance_state: Optional[dict] = None

setup_metrics(app, "iep-governance")

class ForecastRecord(BaseModel):
    slot_start: str
    predicted_kw: float
    actual_kw: float


class GovernanceStatusRequest(BaseModel):
    records: list[ForecastRecord]


class GovernanceStatusResponse(BaseModel):
    mae: float
    mae_baseline: float
    mae_degradation_pct: float
    psi: float
    drift_detected: bool
    retrain_recommended: bool
    n_records: int
    window_days: int
    decision: str


def _load_baseline_mae() -> float:
    metrics_path = MODELS_DIR / "metrics.json"
    if metrics_path.exists():
        try:
            with open(metrics_path) as f:
                data = json.load(f)
            return float(data["mae"])
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            logger.warning("Could not parse metrics.json: %s. Using default baseline.", e)
    return MAE_BASELINE_DEFAULT


def _compute_psi(actual: np.ndarray, predicted: np.ndarray, n_bins: int = 10) -> float:
    min_val = actual.min()
    max_val = actual.max()
    if min_val == max_val:
        return 0.0

    bin_edges = np.linspace(min_val, max_val, n_bins + 1)
    actual_counts, _ = np.histogram(actual, bins=bin_edges)
    predicted_counts, _ = np.histogram(predicted, bins=bin_edges)

    actual_frac = actual_counts / len(actual)
    predicted_frac = predicted_counts / len(predicted)

    psi = np.sum(
        (predicted_frac - actual_frac) * np.log((predicted_frac + 1e-10) / (actual_frac + 1e-10))
    )
    return float(psi)


def _infer_window_days(records: list[ForecastRecord]) -> int:
    if len(records) < 2:
        return 1
    try:
        from datetime import datetime
        times = [datetime.fromisoformat(r.slot_start) for r in records]
        delta = max(times) - min(times)
        return max(1, int(delta.days) + 1)
    except Exception:
        return 7


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/governance/status", response_model=GovernanceStatusResponse)
def post_governance_status(request: GovernanceStatusRequest):
    global _last_governance_state
    if not request.records:
        raise HTTPException(status_code=422, detail="records list cannot be empty")
    actual = np.array([r.actual_kw for r in request.records])
    predicted = np.array([r.predicted_kw for r in request.records])

    mae = float(np.mean(np.abs(predicted - actual)))
    mae_baseline = _load_baseline_mae()
    mae_degradation_pct = (mae - mae_baseline) / mae_baseline * 100

    psi = _compute_psi(actual, predicted)

    drift_detected = psi > 0.2 or mae_degradation_pct > 15.0
    retrain_recommended = drift_detected
    window_days = _infer_window_days(request.records)

    if retrain_recommended:
        decision = f"RETRAIN: MAE={mae:.2f}kW ({mae_degradation_pct:+.1f}% vs baseline), PSI={psi:.3f}"
    else:
        decision = f"OK: MAE={mae:.2f}kW ({mae_degradation_pct:+.1f}% vs baseline), PSI={psi:.3f}"

    try:
        mlflow.set_experiment("iep-governance")
        with mlflow.start_run():
            mlflow.log_metrics({"mae": mae, "psi": psi, "mae_degradation_pct": mae_degradation_pct})
            mlflow.set_tags(
                {
                    "drift_detected": str(drift_detected),
                    "retrain_recommended": str(retrain_recommended),
                }
            )
    except Exception as e:
        logger.warning("MLflow logging failed: %s", e)

    # Update Prometheus gauges
    ev_governance_mae_kw.set(mae)
    ev_governance_mae_baseline_kw.set(mae_baseline)
    ev_governance_psi.set(psi)
    ev_governance_drift_detected.set(int(drift_detected))
    ev_governance_retrain_recommended.set(int(retrain_recommended))

    response = GovernanceStatusResponse(
        mae=mae,
        mae_baseline=mae_baseline,
        mae_degradation_pct=mae_degradation_pct,
        psi=psi,
        drift_detected=drift_detected,
        retrain_recommended=retrain_recommended,
        n_records=len(request.records),
        window_days=window_days,
        decision=decision,
    )

    _last_governance_state = response.model_dump()
    return response


@app.get("/governance/status")
def get_governance_status():
    if _last_governance_state is None:
        return {"status": "no_data", "message": "No governance checks have been run yet"}
    return _last_governance_state


# ---------------------------------------------------------------------------
# Retrain logic — same hyperparameters & features as iep-forecast/train.py
# ---------------------------------------------------------------------------
FORECAST_SERVICE_URL = os.getenv("FORECAST_URL", "http://iep-forecast:8001")

DATA_DIR = Path(__file__).parent.parent / "data" / "processed"
TRAIN_PATH = DATA_DIR / "demand_train.parquet"
HOLDOUT_PATH = DATA_DIR / "demand_holdout.parquet"

FORECAST_FEATURES = [
    "hour_sin", "hour_cos", "dow_sin", "dow_cos",
    "month_sin", "month_cos", "is_weekend", "is_summer",
    "slot_of_day", "lag_4", "lag_16", "lag_96", "lag_672",
    "rolling_mean_1h", "rolling_std_1h",
]
TARGET = "total_kw"
GBR_PARAMS = {"n_estimators": 200, "max_depth": 5, "learning_rate": 0.05}

# ---------------------------------------------------------------------------
# Promotion gate thresholds (applied to holdout metrics)
# ---------------------------------------------------------------------------
PROMOTION_MAX_MAE_KW = 10.0       # reject if holdout MAE exceeds this
PROMOTION_MAX_RMSE_KW = 20.0      # reject if holdout RMSE exceeds this
PROMOTION_MIN_COVERAGE_PCT = 70.0  # reject if 80% PI covers < 70% of actuals
PROMOTION_MAX_MAE_REGRESSION = 0.20  # reject if MAE > 20% worse than current
HOLDOUT_METRICS_PATH = MODELS_DIR / "holdout_metrics.json"


def _load_production_holdout() -> dict | None:
    """Load current production holdout metrics, or None if unavailable."""
    if not HOLDOUT_METRICS_PATH.exists():
        return None
    try:
        with open(HOLDOUT_METRICS_PATH) as f:
            prod = json.load(f)
        # Normalise key variants
        return {
            "mae_kw": prod.get("mae_kw") or prod.get("holdout_mae_kw"),
            "rmse_kw": prod.get("rmse_kw") or prod.get("holdout_rmse_kw"),
            "coverage_pct": prod.get("interval_coverage_pct") or prod.get("holdout_coverage_pct"),
        }
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Could not read production holdout metrics: %s", exc)
        return None


def _check_promotion_gate(
    holdout_metrics: dict,
    production: dict | None,
) -> tuple[bool, list[dict]]:
    """Decide whether newly trained models should replace production.

    Returns (promoted, gate_checks) where gate_checks is a list of dicts,
    each with keys: gate, passed, detail.
    """
    gate_checks: list[dict] = []
    mae = holdout_metrics.get("holdout_mae_kw")
    rmse = holdout_metrics.get("holdout_rmse_kw")
    cov = holdout_metrics.get("holdout_coverage_pct")

    if mae is None or rmse is None or cov is None:
        gate_checks.append({
            "gate": "holdout_completeness",
            "passed": False,
            "detail": "holdout metrics incomplete — cannot promote without evaluation",
        })
        return False, gate_checks

    # Gate 1: absolute MAE ceiling
    gate_checks.append({
        "gate": "mae_ceiling",
        "passed": mae <= PROMOTION_MAX_MAE_KW,
        "detail": f"holdout MAE {mae:.4f} kW vs ceiling {PROMOTION_MAX_MAE_KW} kW",
    })

    # Gate 2: absolute RMSE ceiling
    gate_checks.append({
        "gate": "rmse_ceiling",
        "passed": rmse <= PROMOTION_MAX_RMSE_KW,
        "detail": f"holdout RMSE {rmse:.4f} kW vs ceiling {PROMOTION_MAX_RMSE_KW} kW",
    })

    # Gate 3: coverage floor
    gate_checks.append({
        "gate": "coverage_floor",
        "passed": cov >= PROMOTION_MIN_COVERAGE_PCT,
        "detail": f"holdout coverage {cov:.2f}% vs floor {PROMOTION_MIN_COVERAGE_PCT}%",
    })

    # Gate 4: regression vs production
    if production and production.get("mae_kw") and production["mae_kw"] > 0:
        prod_mae = production["mae_kw"]
        regression = (mae - prod_mae) / prod_mae
        gate_checks.append({
            "gate": "mae_regression",
            "passed": regression <= PROMOTION_MAX_MAE_REGRESSION,
            "detail": (
                f"candidate MAE {mae:.4f} vs production {prod_mae:.4f} "
                f"({regression:+.1%}), max allowed {PROMOTION_MAX_MAE_REGRESSION:+.0%}"
            ),
        })
    else:
        gate_checks.append({
            "gate": "mae_regression",
            "passed": True,
            "detail": "no production baseline — regression check skipped",
        })

    promoted = all(g["passed"] for g in gate_checks)
    return promoted, gate_checks


def _run_retrain() -> dict:
    """Train 3 GBR models, evaluate on holdout, promote only if gate passes."""
    import joblib
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    import httpx

    # ── Load training data ────────────────────────────────────────────────
    if not TRAIN_PATH.exists():
        raise FileNotFoundError(f"Training data not found: {TRAIN_PATH}")
    df_train = pd.read_parquet(TRAIN_PATH)
    df_train = df_train[FORECAST_FEATURES + [TARGET]].dropna()
    X_train = df_train[FORECAST_FEATURES]
    y_train = df_train[TARGET]
    logger.info("Retrain: loaded %d training rows", len(X_train))

    # ── Train 3 models ────────────────────────────────────────────────────
    model_mean = GradientBoostingRegressor(**GBR_PARAMS, random_state=42)
    model_mean.fit(X_train, y_train)

    model_lower = GradientBoostingRegressor(
        loss="quantile", alpha=0.1, **GBR_PARAMS, random_state=42
    )
    model_lower.fit(X_train, y_train)

    model_upper = GradientBoostingRegressor(
        loss="quantile", alpha=0.9, **GBR_PARAMS, random_state=42
    )
    model_upper.fit(X_train, y_train)
    logger.info("Retrain: 3 GBR models trained")

    # ── Evaluate on holdout ───────────────────────────────────────────────
    holdout_metrics = {}
    if HOLDOUT_PATH.exists():
        df_hold = pd.read_parquet(HOLDOUT_PATH)
        df_hold = df_hold[FORECAST_FEATURES + [TARGET]].dropna()
        X_hold = df_hold[FORECAST_FEATURES]
        y_hold = df_hold[TARGET]
        y_pred = model_mean.predict(X_hold)
        y_lo = model_lower.predict(X_hold)
        y_hi = model_upper.predict(X_hold)
        mae = float(mean_absolute_error(y_hold, y_pred))
        rmse = float(np.sqrt(mean_squared_error(y_hold, y_pred)))
        coverage = float(np.mean((y_hold >= y_lo) & (y_hold <= y_hi)) * 100)
        holdout_metrics = {
            "holdout_rows": len(X_hold),
            "holdout_mae_kw": round(mae, 4),
            "holdout_rmse_kw": round(rmse, 4),
            "holdout_coverage_pct": round(coverage, 2),
        }
        logger.info("Retrain holdout: mae=%.4f rmse=%.4f coverage=%.1f%%", mae, rmse, coverage)
    else:
        logger.warning("No holdout parquet found at %s — skipping holdout eval", HOLDOUT_PATH)

    # ── Training-set metrics (for baseline MAE) ───────────────────────────
    y_pred_train = model_mean.predict(X_train)
    train_mae = float(mean_absolute_error(y_train, y_pred_train))
    train_rmse = float(np.sqrt(mean_squared_error(y_train, y_pred_train)))

    # ── Load production holdout for comparison ────────────────────────────
    production = _load_production_holdout()

    # ── Promotion gate ────────────────────────────────────────────────────
    promoted, gate_checks = _check_promotion_gate(holdout_metrics, production)
    failed_gates = [g["gate"] for g in gate_checks if not g["passed"]]
    promotion_decision = (
        "PROMOTED: all gates passed"
        if promoted
        else f"REJECTED: {', '.join(failed_gates)}"
    )
    logger.info("Promotion gate: %s", promotion_decision)

    # ── Build production-vs-candidate comparison ──────────────────────────
    comparison: dict = {"candidate": holdout_metrics}
    if production:
        comparison["production"] = production
        if holdout_metrics.get("holdout_mae_kw") and production.get("mae_kw"):
            comparison["mae_change_pct"] = round(
                (holdout_metrics["holdout_mae_kw"] - production["mae_kw"])
                / production["mae_kw"] * 100, 2
            )
        if holdout_metrics.get("holdout_rmse_kw") and production.get("rmse_kw"):
            comparison["rmse_change_pct"] = round(
                (holdout_metrics["holdout_rmse_kw"] - production["rmse_kw"])
                / production["rmse_kw"] * 100, 2
            )
        if holdout_metrics.get("holdout_coverage_pct") and production.get("coverage_pct"):
            comparison["coverage_change_pct"] = round(
                holdout_metrics["holdout_coverage_pct"] - production["coverage_pct"], 2
            )

    # ── Save / skip based on gate result ──────────────────────────────────
    reload_status = "not_attempted"

    if promoted:
        # ── Save artifacts safely (write-to-tmp → backup old → rename) ────
        artifact_files = {
            "forecast_model.joblib": lambda p: joblib.dump(model_mean, p),
            "forecast_lower.joblib": lambda p: joblib.dump(model_lower, p),
            "forecast_upper.joblib": lambda p: joblib.dump(model_upper, p),
            "metrics.json": lambda p: p.write_text(
                json.dumps({"mae": round(train_mae, 4), "rmse": round(train_rmse, 4)}, indent=2)
            ),
            "feature_list.json": lambda p: p.write_text(
                json.dumps(FORECAST_FEATURES, indent=2)
            ),
            "holdout_metrics.json": lambda p: p.write_text(
                json.dumps({
                    "holdout_mae_kw": holdout_metrics["holdout_mae_kw"],
                    "holdout_rmse_kw": holdout_metrics["holdout_rmse_kw"],
                    "holdout_coverage_pct": holdout_metrics["holdout_coverage_pct"],
                    "holdout_rows": holdout_metrics["holdout_rows"],
                }, indent=2)
            ),
        }

        tmp_paths = {}
        try:
            for name, writer in artifact_files.items():
                tmp = MODELS_DIR / f"{name}.tmp"
                writer(tmp)
                tmp_paths[name] = tmp
        except Exception:
            for tmp in tmp_paths.values():
                tmp.unlink(missing_ok=True)
            raise

        bak_paths = {}
        for name, tmp in tmp_paths.items():
            final = MODELS_DIR / name
            bak = MODELS_DIR / f"{name}.bak"
            if final.exists():
                final.rename(bak)
                bak_paths[name] = bak
            tmp.rename(final)

        for bak in bak_paths.values():
            bak.unlink(missing_ok=True)

        logger.info("Retrain: artifacts promoted to %s", MODELS_DIR)

        # Notify forecast service to reload
        try:
            resp = httpx.post(f"{FORECAST_SERVICE_URL}/models/reload", timeout=10.0)
            reload_status = "ok" if resp.status_code == 200 else f"http_{resp.status_code}"
        except Exception as exc:
            reload_status = f"failed: {exc}"
            logger.warning("Could not reload forecast models: %s", exc)
    else:
        logger.info("Retrain: model rejected — current production artifacts unchanged")

    # ── MLflow logging ────────────────────────────────────────────────────
    try:
        mlflow.set_experiment("iep-governance")
        with mlflow.start_run():
            mlflow.set_tag("event", "retrain_promoted" if promoted else "retrain_rejected")
            mlflow.set_tag("promoted", str(promoted))
            mlflow.log_metric("retrain_train_mae", train_mae)
            mlflow.log_metric("retrain_train_rmse", train_rmse)
            if holdout_metrics:
                mlflow.log_metric("candidate_holdout_mae", holdout_metrics["holdout_mae_kw"])
                mlflow.log_metric("candidate_holdout_rmse", holdout_metrics["holdout_rmse_kw"])
                mlflow.log_metric("candidate_holdout_coverage", holdout_metrics["holdout_coverage_pct"])
            if production:
                if production.get("mae_kw"):
                    mlflow.log_metric("production_holdout_mae", production["mae_kw"])
                if production.get("rmse_kw"):
                    mlflow.log_metric("production_holdout_rmse", production["rmse_kw"])
                if production.get("coverage_pct"):
                    mlflow.log_metric("production_holdout_coverage", production["coverage_pct"])
            if "mae_change_pct" in comparison:
                mlflow.log_metric("mae_change_pct", comparison["mae_change_pct"])
            if not promoted:
                mlflow.set_tag("rejected_gates", ",".join(failed_gates))
    except Exception as e:
        logger.warning("MLflow logging failed: %s", e)

    return {
        "train_rows": len(X_train),
        "train_mae": round(train_mae, 4),
        "train_rmse": round(train_rmse, 4),
        **holdout_metrics,
        "promoted": promoted,
        "promotion_decision": promotion_decision,
        "gate_checks": gate_checks,
        "comparison": comparison,
        "artifacts_dir": str(MODELS_DIR) if promoted else None,
        "forecast_reload": reload_status,
    }


@app.post("/governance/retrain")
def post_governance_retrain():
    try:
        result = _run_retrain()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Retrain failed")
        raise HTTPException(status_code=500, detail=f"Retrain failed: {e}")
    return {"status": "completed", **result}


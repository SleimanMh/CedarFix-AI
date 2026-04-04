"""
IEP Grid Compatibility FastAPI service.

Two-stage ML pipeline:
  Stage 1 — Classifier: predicts compatibility_class from grid config only
             (no OpenDSS simulation outputs used as features)
  Stage 2 — Regressor: predicts recommended_max_active_chargers,
             only runs when Stage 1 result is compatible or conditional

Endpoints:
  POST /predict  – run both stages, return full recommendation
  GET  /health   – liveness / readiness probe

Port: 8004
"""

from contextlib import asynccontextmanager
from pathlib import Path

import json

import joblib
import numpy as np
import pandas as pd
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from metrics import (
    setup_metrics,
    grid_compat_requests_total,
    grid_compat_inference_seconds,
    grid_compat_class_gauge,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
MODELS_DIR = Path(__file__).parent / "models"
CLASSIFIER_PATH = MODELS_DIR / "compatibility_classifier.joblib"
REGRESSOR_PATH  = MODELS_DIR / "max_chargers_regressor.joblib"
CLASSIFIER_METRICS_PATH = MODELS_DIR / "classifier_metrics.json"
REGRESSOR_METRICS_PATH  = MODELS_DIR / "regressor_metrics.json"

# ── Feature lists (must match train_classifier.py / train_regressor.py) ───────
NUMERIC_FEATURES = [
    "transformer_kva", "base_load_kw", "feeder_length_km",
    "r1", "x1", "r0", "x0",
    "num_chargers_installed", "num_chargers_active", "charger_power_kw",
    "nominal_load_ratio", "nominal_headroom_kw",
]
CATEGORICAL_FEATURES = ["cable_type", "phase_balance_class"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

COMPATIBLE_CLASSES = {"compatible", "conditional"}

# ── Module-level state ────────────────────────────────────────────────────────
classifier = None
regressor  = None
models_loaded: bool = False


# ── Startup / shutdown ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(application: FastAPI):
    _load_models()
    yield


def _load_models() -> None:
    global classifier, regressor, models_loaded
    try:
        if not CLASSIFIER_PATH.exists():
            raise FileNotFoundError(f"Classifier not found: {CLASSIFIER_PATH}")
        if not REGRESSOR_PATH.exists():
            raise FileNotFoundError(f"Regressor not found: {REGRESSOR_PATH}")
        classifier = joblib.load(CLASSIFIER_PATH)
        regressor  = joblib.load(REGRESSOR_PATH)

        # Sandbox/runtime safety: avoid spawning worker pools in constrained envs.
        # Supports both plain estimators and sklearn Pipelines.
        for model in (classifier, regressor):
            try:
                params = model.get_params(deep=True)
            except Exception:
                params = {}
            for key in ("n_jobs", "classifier__n_jobs", "regressor__n_jobs"):
                if key in params:
                    try:
                        model.set_params(**{key: 1})
                    except Exception:
                        pass

        models_loaded = True
        print(f"[startup] Models loaded from {MODELS_DIR}")
    except Exception as exc:
        models_loaded = False
        print(f"[startup] WARNING – models not loaded: {exc}")


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="IEP Grid Compatibility Service",
    version="1.0",
    description="Predicts EV charging compatibility class and max charger recommendation "
                "from grid configuration inputs only.",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
setup_metrics(app, "iep-grid-compatibility")


# ── Pydantic models ───────────────────────────────────────────────────────────
CABLE_TYPES        = {"A_strong", "B_medium", "C_weak"}
PHASE_BALANCE_TYPES = {"balanced", "mildly_unbalanced", "heavily_unbalanced"}

class GridConfigRequest(BaseModel):
    # Transformer
    transformer_kva: float = Field(..., gt=0, description="Transformer capacity in kVA")
    base_load_kw: float    = Field(..., ge=0, description="Existing base load in kW")

    # Feeder / cable
    feeder_length_km: float = Field(..., gt=0, description="Feeder length in km")
    cable_type: str         = Field(..., description="Cable type: A_strong | B_medium | C_weak")
    r1: float               = Field(..., ge=0, description="Positive-sequence resistance (ohm/km)")
    x1: float               = Field(..., ge=0, description="Positive-sequence reactance (ohm/km)")
    r0: float               = Field(..., ge=0, description="Zero-sequence resistance (ohm/km)")
    x0: float               = Field(..., ge=0, description="Zero-sequence reactance (ohm/km)")
    phase_balance_class: str = Field(
        ..., description="Phase balance: balanced | mildly_unbalanced | heavily_unbalanced"
    )

    # Chargers
    num_chargers_installed: int = Field(..., ge=0, description="Total chargers installed")
    num_chargers_active: int    = Field(..., ge=0, description="Chargers active simultaneously")
    charger_power_kw: float     = Field(..., gt=0, description="Power per charger in kW")

    @model_validator(mode="after")
    def validate_enums(self) -> "GridConfigRequest":
        if self.cable_type not in CABLE_TYPES:
            raise ValueError(f"cable_type must be one of {sorted(CABLE_TYPES)}")
        if self.phase_balance_class not in PHASE_BALANCE_TYPES:
            raise ValueError(
                f"phase_balance_class must be one of {sorted(PHASE_BALANCE_TYPES)}"
            )
        if self.num_chargers_active > self.num_chargers_installed:
            raise ValueError(
                "num_chargers_active cannot exceed num_chargers_installed"
            )
        return self


class CompatibilityResponse(BaseModel):
    compatibility_class: str
    confidence: float = Field(description="Classifier probability for predicted class")
    class_probabilities: dict[str, float]
    recommended_max_active_chargers: int
    stage2_applied: bool = Field(
        description="True if Stage 2 regressor ran (class was compatible or conditional)"
    )
    nominal_load_ratio: float = Field(
        description="(base_load + total_charger_demand) / transformer_kva"
    )
    nominal_headroom_kw: float = Field(
        description="transformer_kva - base_load - total_charger_demand"
    )


# ── Helper ────────────────────────────────────────────────────────────────────
def _engineer(req: GridConfigRequest) -> pd.DataFrame:
    """Convert request to a single-row DataFrame with engineered features."""
    total_charger_kw = req.num_chargers_active * req.charger_power_kw
    row = {
        "transformer_kva":       req.transformer_kva,
        "base_load_kw":          req.base_load_kw,
        "feeder_length_km":      req.feeder_length_km,
        "r1": req.r1, "x1": req.x1, "r0": req.r0, "x0": req.x0,
        "num_chargers_installed": req.num_chargers_installed,
        "num_chargers_active":   req.num_chargers_active,
        "charger_power_kw":      req.charger_power_kw,
        "nominal_load_ratio":    (req.base_load_kw + total_charger_kw) / req.transformer_kva,
        "nominal_headroom_kw":   req.transformer_kva - req.base_load_kw - total_charger_kw,
        "cable_type":            req.cable_type,
        "phase_balance_class":   req.phase_balance_class,
    }
    return pd.DataFrame([row])


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "models_loaded": models_loaded}


@app.post("/predict", response_model=CompatibilityResponse)
def predict(request: GridConfigRequest) -> CompatibilityResponse:
    import time
    if not models_loaded:
        raise HTTPException(status_code=503, detail="Models are not loaded.")

    t0 = time.perf_counter()
    df = _engineer(request)

    # ── Stage 1: classify ─────────────────────────────────────────────────────
    pred_class = classifier.predict(df[ALL_FEATURES])[0]
    proba      = classifier.predict_proba(df[ALL_FEATURES])[0]
    classes    = classifier.classes_
    class_probs = {cls: round(float(p), 4) for cls, p in zip(classes, proba)}
    confidence  = round(float(proba[list(classes).index(pred_class)]), 4)

    # ── Stage 2: regress only if meaningful ───────────────────────────────────
    stage2_applied = pred_class in COMPATIBLE_CLASSES
    if stage2_applied:
        raw_pred = regressor.predict(df[ALL_FEATURES])[0]
        max_chargers = int(np.clip(round(raw_pred), 0, request.num_chargers_installed))
    else:
        max_chargers = 0

    duration = time.perf_counter() - t0

    # ── Prometheus ────────────────────────────────────────────────────────────
    grid_compat_requests_total.labels(predicted_class=pred_class).inc()
    grid_compat_inference_seconds.observe(duration)
    grid_compat_class_gauge.labels(compatibility_class=pred_class).set(1)

    return CompatibilityResponse(
        compatibility_class=pred_class,
        confidence=confidence,
        class_probabilities=class_probs,
        recommended_max_active_chargers=max_chargers,
        stage2_applied=stage2_applied,
        nominal_load_ratio=round(float(df["nominal_load_ratio"].iloc[0]), 4),
        nominal_headroom_kw=round(float(df["nominal_headroom_kw"].iloc[0]), 2),
    )


@app.get("/model-info")
def model_info() -> dict:
    """Returns model metrics from last training run."""
    info: dict = {}
    for label, path in [
        ("classifier", CLASSIFIER_METRICS_PATH),
        ("regressor", REGRESSOR_METRICS_PATH),
    ]:
        if path.exists():
            with open(path) as fh:
                info[label] = json.load(fh)
        else:
            info[label] = None
    return info

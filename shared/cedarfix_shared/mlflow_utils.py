"""
MLflow utility helpers — used by every IEP that runs model inference.
Centralizes logging conventions so all services log consistently.
"""

import mlflow
import os
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Dict, Optional


MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)


def get_or_create_experiment(experiment_name: str) -> str:
    """Return experiment ID, creating it if it doesn't exist."""
    exp = mlflow.get_experiment_by_name(experiment_name)
    if exp is None:
        return mlflow.create_experiment(experiment_name)
    return exp.experiment_id


@contextmanager
def log_inference(
    experiment_name: str,
    run_name: str,
    model_name: str,
    model_version: Optional[str] = None,
    extra_params: Optional[Dict[str, Any]] = None,
):
    """
    Context manager for logging a single inference call to MLflow.
    Use this around every IEP model call to create an audit trail.

    Usage:
        with log_inference("cedarfix/routing", "route_complaint", "cedarfix-routing") as run:
            result = model.predict(...)
            run["confidence"] = result.confidence
    """
    exp_id = get_or_create_experiment(experiment_name)
    log_data: Dict[str, Any] = {}

    with mlflow.start_run(experiment_id=exp_id, run_name=run_name) as active_run:
        mlflow.set_tags({
            "model_name": model_name,
            "model_version": model_version or "unknown",
            "service": experiment_name.split("/")[-1],
        })
        if extra_params:
            mlflow.log_params(extra_params)

        start = time.time()
        try:
            yield log_data
            duration_ms = int((time.time() - start) * 1000)
            mlflow.log_metrics({
                "inference_ms": duration_ms,
                **{k: v for k, v in log_data.items() if isinstance(v, (int, float))},
            })
        except Exception as e:
            mlflow.set_tag("error", str(e))
            raise


def load_production_model(model_registry_name: str):
    """Load the current Production model from MLflow Model Registry."""
    model_uri = f"models:/{model_registry_name}/Production"
    return mlflow.pyfunc.load_model(model_uri)

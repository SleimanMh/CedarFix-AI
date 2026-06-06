from __future__ import annotations

import contextlib
import importlib
import base64
import json
import os
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
SERVICES = ROOT / "services"


def _prepend_once(path: Path) -> None:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


_prepend_once(SHARED)


def _clear_app_modules() -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)


@contextlib.contextmanager
def _temporary_path(path: Path):
    text = str(path)
    sys.path.insert(0, text)
    try:
        yield
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(text)


def _install_qdrant_stub() -> None:
    if "qdrant_client" in sys.modules:
        return
    qdrant_client = types.ModuleType("qdrant_client")

    class QdrantClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    qdrant_client.QdrantClient = QdrantClient

    models = types.ModuleType("qdrant_client.models")

    class _Model:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    for name in (
        "Distance",
        "FieldCondition",
        "Filter",
        "MatchValue",
        "PointStruct",
        "Range",
        "VectorParams",
    ):
        setattr(models, name, _Model)
    models.Distance.COSINE = "Cosine"

    qdrant_client.models = models
    sys.modules["qdrant_client"] = qdrant_client
    sys.modules["qdrant_client.models"] = models


def _install_ml_stubs() -> None:
    if "torch" not in sys.modules:
        torch = types.ModuleType("torch")
        torch.no_grad = lambda: contextlib.nullcontext()
        sys.modules["torch"] = torch
    if "transformers" not in sys.modules:
        transformers = types.ModuleType("transformers")

        class CLIPModel:
            pass

        class CLIPProcessor:
            pass

        class CLIPTokenizer:
            @classmethod
            def from_pretrained(cls, *_args, **_kwargs):
                return cls()

            def __call__(self, *_args, **_kwargs):
                return {}

        class CLIPTextModelWithProjection:
            @classmethod
            def from_pretrained(cls, *_args, **_kwargs):
                return cls()

            def eval(self):
                return self

        transformers.CLIPModel = CLIPModel
        transformers.CLIPProcessor = CLIPProcessor
        transformers.CLIPTokenizer = CLIPTokenizer
        transformers.CLIPTextModelWithProjection = CLIPTextModelWithProjection
        sys.modules["transformers"] = transformers
    if "sentence_transformers" not in sys.modules:
        sentence_transformers = types.ModuleType("sentence_transformers")

        class _Vector(list):
            def tolist(self):
                return list(self)

        class SentenceTransformer:
            def __init__(self, model_name):
                self.model_name = model_name

            def encode(self, text):
                return _Vector([float(len(str(text)) % 10), 0.25, 0.5])

        sentence_transformers.SentenceTransformer = SentenceTransformer
        sys.modules["sentence_transformers"] = sentence_transformers


def _install_text_stubs() -> None:
    if "langdetect" not in sys.modules:
        langdetect = types.ModuleType("langdetect")

        class LangDetectException(Exception):
            pass

        def detect(text):
            lowered = str(text).lower()
            if any(token in lowered for token in ("bonjour", "route cassee", "cassée")):
                return "fr"
            return "en"

        langdetect.detect = detect
        langdetect.LangDetectException = LangDetectException
        sys.modules["langdetect"] = langdetect

    if "openai" not in sys.modules:
        openai = types.ModuleType("openai")

        class AsyncOpenAI:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        openai.AsyncOpenAI = AsyncOpenAI
        sys.modules["openai"] = openai


def _install_pydantic_settings_stub() -> None:
    if "pydantic_settings" in sys.modules:
        return
    pydantic_settings = types.ModuleType("pydantic_settings")

    class BaseSettings:
        def __init__(self, **kwargs):
            annotations = {}
            for cls in reversed(type(self).mro()):
                annotations.update(getattr(cls, "__annotations__", {}))
            for name in annotations:
                env_value = os.getenv(name.upper())
                setattr(self, name, kwargs.get(name, env_value if env_value is not None else getattr(type(self), name, None)))

    pydantic_settings.BaseSettings = BaseSettings
    pydantic_settings.SettingsConfigDict = lambda **kwargs: dict(kwargs)
    sys.modules["pydantic_settings"] = pydantic_settings


def _install_gateway_auth_stubs() -> None:
    if "jose" not in sys.modules:
        jose = types.ModuleType("jose")

        class JWTError(Exception):
            pass

        class _Jwt:
            @staticmethod
            def encode(payload, secret, algorithm):
                encoded_payload = {}
                for key, value in payload.items():
                    encoded_payload[key] = value.timestamp() if hasattr(value, "timestamp") else value
                data = json.dumps(encoded_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
                token = base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
                return f"{token}.{algorithm}.{secret}"

            @staticmethod
            def decode(token, secret, algorithms):
                try:
                    payload_part, algorithm, token_secret = token.rsplit(".", 2)
                    if token_secret != secret or algorithm not in algorithms:
                        raise JWTError("invalid token")
                    padding = "=" * (-len(payload_part) % 4)
                    return json.loads(base64.urlsafe_b64decode(payload_part + padding).decode("utf-8"))
                except JWTError:
                    raise
                except Exception as exc:
                    raise JWTError("invalid token") from exc

        jose.JWTError = JWTError
        jose.jwt = _Jwt
        sys.modules["jose"] = jose

    if "passlib.context" not in sys.modules:
        passlib = types.ModuleType("passlib")
        context = types.ModuleType("passlib.context")

        class CryptContext:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def hash(self, password):
                return f"test-hash::{password}"

            def verify(self, plain, hashed):
                return hashed == self.hash(plain)

        context.CryptContext = CryptContext
        passlib.context = context
        sys.modules["passlib"] = passlib
        sys.modules["passlib.context"] = context


def _install_mlflow_stub() -> None:
    if "mlflow" in sys.modules:
        return
    mlflow = types.ModuleType("mlflow")
    mlflow.set_tracking_uri = lambda *_args, **_kwargs: None
    mlflow.set_tags = lambda *_args, **_kwargs: None
    mlflow.log_metric = lambda *_args, **_kwargs: None

    class _Run:
        class info:
            run_id = "test-run"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    mlflow.start_run = lambda *_args, **_kwargs: _Run()
    sys.modules["mlflow"] = mlflow


@pytest.fixture
def import_service_module():
    def _import(service: str, module: str, *, qdrant: bool = False, ml: bool = False):
        _clear_app_modules()
        if service == "text_understanding":
            _install_text_stubs()
        if qdrant:
            _install_qdrant_stub()
        if ml:
            _install_ml_stubs()
        if service == "gateway":
            _install_pydantic_settings_stub()
            _install_gateway_auth_stubs()
        if service == "monitoring_service":
            _install_mlflow_stub()
        with _temporary_path(SERVICES / service):
            return importlib.import_module(module)

    return _import

from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path

import pytest


TEST_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TEST_ROOT.parent
SHARED_ROOT = REPO_ROOT / "shared"

for path in (REPO_ROOT, SHARED_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

os.environ.setdefault("QWEN_ENABLED", "false")
os.environ.setdefault("QWEN_BASE_URL", "")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("MEDIA_ALIGNMENT_LLM_ENABLED", "false")
os.environ.setdefault("MULTI_COMPLAINT_SPLITTER_LLM_ENABLED", "false")
os.environ.setdefault("VLM_ENABLED", "false")


def _install_qdrant_stub() -> None:
    if "qdrant_client" in sys.modules:
        return
    try:
        importlib.import_module("qdrant_client")
        return
    except ModuleNotFoundError:
        pass

    qdrant_client = types.ModuleType("qdrant_client")

    class QdrantClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    qdrant_client.QdrantClient = QdrantClient

    models = types.ModuleType("qdrant_client.models")

    class MatchValue:
        def __init__(self, value):
            self.value = value

    class FieldCondition:
        def __init__(self, key, match):
            self.key = key
            self.match = match

    class Filter:
        def __init__(self, must=None, should=None, must_not=None):
            self.must = must or []
            self.should = should or []
            self.must_not = must_not or []

    class PayloadSchemaType:
        KEYWORD = "keyword"

    models.MatchValue = MatchValue
    models.FieldCondition = FieldCondition
    models.Filter = Filter
    models.PayloadSchemaType = PayloadSchemaType

    qdrant_client.models = models
    sys.modules["qdrant_client"] = qdrant_client
    sys.modules["qdrant_client.models"] = models


def _install_openai_stub() -> None:
    if "openai" in sys.modules:
        return
    try:
        importlib.import_module("openai")
        return
    except ModuleNotFoundError:
        pass

    openai = types.ModuleType("openai")

    class AsyncOpenAI:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    openai.AsyncOpenAI = AsyncOpenAI
    sys.modules["openai"] = openai


def _install_langdetect_stub() -> None:
    if "langdetect" in sys.modules:
        return
    try:
        importlib.import_module("langdetect")
        return
    except ModuleNotFoundError:
        pass

    langdetect = types.ModuleType("langdetect")

    class LangDetectException(Exception):
        pass

    def detect(text: str) -> str:
        lower = (text or "").lower()
        if any(token in lower for token in ("bonjour", "route cassée", "eau")):
            return "fr"
        return "en"

    langdetect.detect = detect
    langdetect.LangDetectException = LangDetectException
    sys.modules["langdetect"] = langdetect


def _install_pydantic_settings_stub() -> None:
    if "pydantic_settings" in sys.modules:
        return
    try:
        importlib.import_module("pydantic_settings")
        return
    except ModuleNotFoundError:
        pass

    pydantic_settings = types.ModuleType("pydantic_settings")

    class BaseSettings:
        def __init__(self, **values):
            for key, value in values.items():
                setattr(self, key, value)

    pydantic_settings.BaseSettings = BaseSettings
    sys.modules["pydantic_settings"] = pydantic_settings


def _install_sqlalchemy_stub() -> None:
    if "sqlalchemy" in sys.modules:
        return
    try:
        importlib.import_module("sqlalchemy")
        return
    except ModuleNotFoundError:
        pass

    sqlalchemy = types.ModuleType("sqlalchemy")
    sqlalchemy.text = lambda value: value
    sys.modules["sqlalchemy"] = sqlalchemy


def _install_native_ml_stubs() -> None:
    if os.getenv("CEDARFIX_TEST_USE_REAL_ML", "false").lower() == "true":
        return

    if "torch" not in sys.modules:
        torch = types.ModuleType("torch")
        torch.cuda = types.SimpleNamespace(is_available=lambda: False)
        torch.no_grad = lambda: types.SimpleNamespace(
            __enter__=lambda self: None,
            __exit__=lambda self, exc_type, exc, tb: None,
        )
        sys.modules["torch"] = torch

    if "transformers" not in sys.modules:
        transformers = types.ModuleType("transformers")

        class CLIPModel:
            @classmethod
            def from_pretrained(cls, *args, **kwargs):
                raise AssertionError("Unit tests must not load CLIPModel weights")

        class CLIPProcessor:
            @classmethod
            def from_pretrained(cls, *args, **kwargs):
                raise AssertionError("Unit tests must not load CLIPProcessor weights")

        transformers.CLIPModel = CLIPModel
        transformers.CLIPProcessor = CLIPProcessor
        sys.modules["transformers"] = transformers


_install_qdrant_stub()
_install_openai_stub()
_install_langdetect_stub()
_install_pydantic_settings_stub()
_install_sqlalchemy_stub()
_install_native_ml_stubs()


def import_or_skip(module_name: str):
    try:
        return importlib.import_module(module_name)
    except (ImportError, ModuleNotFoundError, OSError) as exc:
        pytest.skip(f"{module_name} unavailable: {exc}")


@pytest.fixture
def schemas():
    return import_or_skip("cedarfix_shared.schemas")


@pytest.fixture
def router_module():
    return import_or_skip("services.routing_engine.app.router")


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT

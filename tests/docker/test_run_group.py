from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_run_group():
    path = Path(__file__).resolve().parents[2] / "docker" / "run_group.py"
    spec = importlib.util.spec_from_file_location("run_group_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_start_builds_expected_uvicorn_command(monkeypatch):
    run_group = _load_run_group()
    captured = {}

    class FakePopen:
        def __init__(self, cmd):
            captured["cmd"] = cmd

    monkeypatch.setattr(run_group.subprocess, "Popen", FakePopen)
    process = run_group._start("api=app.main:app:8000")

    assert isinstance(process, FakePopen)
    assert captured["cmd"][1:4] == ["-m", "uvicorn", "app.main:app"]
    assert captured["cmd"][-1] == "8000"


def test_start_rejects_bad_service_spec():
    run_group = _load_run_group()
    with pytest.raises(SystemExit):
        run_group._start("not-a-service")


def test_terminate_all_terminates_then_kills_timeout_processes(monkeypatch):
    run_group = _load_run_group()

    class FakeProcess:
        def __init__(self):
            self.terminated = False
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            raise run_group.subprocess.TimeoutExpired("cmd", timeout)

        def kill(self):
            self.killed = True

    process = FakeProcess()
    run_group.processes[:] = [process]
    run_group._terminate_all()

    assert run_group.shutting_down is True
    assert process.terminated is True
    assert process.killed is True


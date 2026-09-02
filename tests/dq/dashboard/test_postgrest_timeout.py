"""httpx timeouts on ``build_client``; ledger inserts do not abandon a worker."""

from __future__ import annotations

import importlib.util
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import yaml
from digiquant.research.supabase_io import SupabaseConfig, build_client
from digiquant.portfolio.writers import ledger_io
from digiquant.dashboard.postgrest_timeout import (
    CONNECT_TIMEOUT_SECONDS,
    POOL_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
    WRITE_TIMEOUT_SECONDS,
)

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_WORKFLOW = _REPO / ".github" / "workflows" / "pipeline-digiquant.yml"
_AT_OPEN = _REPO / "digiquant" / "scripts" / "research" / "execute_at_open.py"


def test_httpx_timeout_constants() -> None:
    assert CONNECT_TIMEOUT_SECONDS == 10.0
    assert READ_TIMEOUT_SECONDS == 60.0
    assert WRITE_TIMEOUT_SECONDS == 30.0
    assert POOL_TIMEOUT_SECONDS == 10.0


def test_insert_execute_runs_on_the_caller_thread() -> None:
    caller = threading.get_ident()
    seen: list[int] = []

    class _Client:
        def table(self, _name: str) -> _Client:
            return self

        def insert(self, _rows: list[dict[str, Any]]) -> _Client:
            return self

        def execute(self) -> SimpleNamespace:
            seen.append(threading.get_ident())
            return SimpleNamespace(data=[])

    ledger_io._insert(
        client=_Client(),
        table="broker_orders",
        rows=[{"id": "row-1", "workspace_id": "ws"}],
    )
    assert seen == [caller]


def test_build_client_passes_httpx_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("supabase")
    import supabase

    captured: dict[str, Any] = {}

    def fake_create(url: str, key: str, options: Any = None) -> dict[str, str]:
        captured["url"] = url
        captured["key"] = key
        captured["options"] = options
        return {"client": "fake"}

    monkeypatch.setattr(supabase, "create_client", fake_create)
    out = build_client(SupabaseConfig(url="https://example.supabase.co", service_key="sk"))
    assert out == {"client": "fake"}
    options = captured["options"]
    assert options is not None
    timeout = options.postgrest_client_timeout
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == CONNECT_TIMEOUT_SECONDS
    assert timeout.read == READ_TIMEOUT_SECONDS
    assert timeout.write == WRITE_TIMEOUT_SECONDS
    assert timeout.pool == POOL_TIMEOUT_SECONDS


def test_execute_at_open_sb_uses_build_client(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location("execute_at_open_timeout", _AT_OPEN)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    captured: dict[str, Any] = {}

    def fake_build(cfg: SupabaseConfig) -> dict[str, str]:
        captured["cfg"] = cfg
        return {"client": "timed"}

    monkeypatch.setattr(mod, "build_client", fake_build)
    monkeypatch.setenv("CORE_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("CORE_SUPABASE_SERVICE_KEY", "sk")
    assert mod._sb() == {"client": "timed"}
    cfg = captured["cfg"]
    assert cfg.url == "https://example.supabase.co"
    assert cfg.service_key == "sk"


def test_research_pipeline_run_step_has_per_attempt_timeout() -> None:
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    job = doc["jobs"]["run"]
    job_timeout = job["timeout-minutes"]
    assert job_timeout == 240
    [step] = [s for s in job["steps"] if isinstance(s, dict) and s.get("id") == "run"]
    step_timeout = step["timeout-minutes"]
    assert isinstance(step_timeout, int)
    assert step_timeout < job_timeout
    script = step["run"]
    assert "ATTEMPT_TIMEOUT=70m" in script
    assert "timeout --kill-after=30s" in script
    assert "${ATTEMPT_TIMEOUT}" in script
    assert "MAX_OUTER_ATTEMPTS=3" in script

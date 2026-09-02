"""httpx timeouts on ``build_client``; ledger inserts do not abandon a worker."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client
from digiquant.olympus.hermes.writers import ledger_io
from digiquant.olympus.postgrest_timeout import (
    CONNECT_TIMEOUT_SECONDS,
    POOL_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
    WRITE_TIMEOUT_SECONDS,
)

pytestmark = pytest.mark.unit

_WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "pipeline-olympus.yml"


def test_httpx_timeout_constants() -> None:
    assert CONNECT_TIMEOUT_SECONDS == 10.0
    assert READ_TIMEOUT_SECONDS == 60.0
    assert WRITE_TIMEOUT_SECONDS == 30.0
    assert POOL_TIMEOUT_SECONDS == 10.0


def test_execute_and_insert_do_not_abandon_a_worker() -> None:
    combined = inspect.getsource(ledger_io._execute) + inspect.getsource(ledger_io._insert)
    assert "run_with_deadline" not in combined
    assert "Thread(" not in combined


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


def test_research_pipeline_run_step_has_timeout_minutes() -> None:
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    job = doc["jobs"]["run"]
    assert job["timeout-minutes"] == 240
    steps = [s for s in job["steps"] if isinstance(s, dict) and s.get("id") == "run"]
    assert len(steps) == 1
    step_timeout = steps[0].get("timeout-minutes")
    assert step_timeout is not None
    assert int(step_timeout) < 240

"""PostgREST I/O is bounded by httpx on ``build_client``, not a thread deadline (#3426)."""

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

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pipeline-olympus.yml"


def test_httpx_timeout_constants_are_minutes_not_hours() -> None:
    assert CONNECT_TIMEOUT_SECONDS == 10.0
    assert READ_TIMEOUT_SECONDS == 60.0
    assert WRITE_TIMEOUT_SECONDS == 30.0
    assert POOL_TIMEOUT_SECONDS == 10.0
    assert READ_TIMEOUT_SECONDS < 5 * 60


def test_timeout_module_has_no_abandon_deadline() -> None:
    import digiquant.olympus.postgrest_timeout as timeout_mod

    assert not hasattr(timeout_mod, "run_with_deadline")
    assert not hasattr(timeout_mod, "EXECUTE_DEADLINE_SECONDS")


def test_execute_does_not_wrap_inserts_in_a_thread_deadline() -> None:
    src = inspect.getsource(ledger_io._execute)
    assert "run_with_deadline" not in src
    insert_src = inspect.getsource(ledger_io._insert)
    assert "run_with_deadline" not in insert_src


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
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = doc["jobs"]["run"]
    assert job["timeout-minutes"] == 240
    steps = [s for s in job["steps"] if isinstance(s, dict) and s.get("id") == "run"]
    assert len(steps) == 1, "expected the research pipeline run step (id: run)"
    step_timeout = steps[0].get("timeout-minutes")
    assert step_timeout is not None, "run step needs timeout-minutes under the 240m job cap"
    assert int(step_timeout) < 240

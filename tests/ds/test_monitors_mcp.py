"""Phase C monitor MCP tools (#4065, Task 7).

Pins the §4.7 surface: ``monitors_create_watch``, ``monitors_list_watches``,
``monitors_trigger_watch``, ``monitors_get_runs`` — registration on the
singleton, the same JSON the HTTP routes return, the one-time delivery secret
(R8), create-time cron validation shared with the HTTP gate (a bad cron would
otherwise make ``is_due`` raise at tick time and silently never run), and the
fail-closed disabled string when the store cannot be opened.

Offline only: the runner's shallow-recall boundary is stubbed (the Task 4
seam), and the store is a fresh ``MonitorStore`` in ``tmp_path`` — the tool
call opens it on its own thread, exactly like production.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from digisearch.web_exa import WebSearchData

pytestmark = pytest.mark.unit

_TOOL_NAMES = {
    "monitors_create_watch",
    "monitors_list_watches",
    "monitors_trigger_watch",
    "monitors_get_runs",
}


@pytest.fixture(autouse=True)
def _stub_shallow_recall(monkeypatch):
    """Keep every monitor MCP test offline at the runner's recall boundary."""
    from digisearch.monitors import runner as runner_mod

    monkeypatch.setattr(
        runner_mod,
        "_invoke_shallow_recall",
        lambda **kwargs: WebSearchData.model_validate(
            {"results": [{"url": "https://example.com/a", "title": "A", "text": "alpha"}]}
        ),
    )


@pytest.fixture
def _store(monkeypatch, tmp_path):
    """Point the MCP store seam at a fresh per-call store in tmp_path."""
    from digisearch.monitors.store import MonitorStore

    from digisearch import mcp_server

    monkeypatch.setattr(
        mcp_server, "get_store", lambda: MonitorStore(db_path=str(tmp_path / "m.sqlite3"))
    )


@pytest.mark.unit
def test_monitors_tools_registered_on_mcp_singleton():
    pytest.importorskip("mcp.server.fastmcp")
    from digisearch import mcp_server

    sync_names = {tool.name for tool in mcp_server.mcp._tool_manager.list_tools()}
    assert _TOOL_NAMES <= sync_names
    async_tools = asyncio.run(mcp_server.mcp.list_tools())
    assert _TOOL_NAMES <= {tool.name for tool in async_tools}


@pytest.mark.unit
def test_create_list_trigger_get_runs_round_trip(_store):
    from digisearch import mcp_server

    created = json.loads(
        mcp_server.monitors_create_watch(query="etf flows", interval_seconds=3600, num_results=5)
    )
    assert set(created) == {"watch", "delivery_secret"}  # R8: secret only here
    wid = created["watch"]["watch_id"]
    assert created["watch"]["name"] == "etf flows"
    assert created["watch"]["schedule"] == {
        "mode": "interval",
        "cron": None,
        "interval_seconds": 3600,
        "enabled": True,
        "timezone": "UTC",
    }

    listed = mcp_server.monitors_list_watches()
    assert [w["watch_id"] for w in json.loads(listed)["watches"]] == [wid]
    assert "delivery_secret" not in listed  # R8: never on reads

    run = json.loads(mcp_server.monitors_trigger_watch(wid, mode="poll"))
    assert run["watch_id"] == wid
    assert run["status"] == "ok"
    assert run["trigger"] == "poll"

    runs = json.loads(mcp_server.monitors_get_runs(wid, limit=5))
    assert [r["run_id"] for r in runs["runs"]] == [run["run_id"]]
    assert runs["next_cursor"] is None


@pytest.mark.unit
def test_create_accepts_cron_and_rejects_bad_cron_without_persisting(_store):
    from digisearch import mcp_server

    ok = json.loads(
        mcp_server.monitors_create_watch(query="etf flows", schedule_cron="*/5 * * * *")
    )
    assert ok["watch"]["schedule"]["mode"] == "cron"
    assert ok["watch"]["schedule"]["cron"] == "*/5 * * * *"

    rejected = mcp_server.monitors_create_watch(query="etf flows", schedule_cron="not a cron")
    assert "invalid_cron" in rejected
    watches = json.loads(mcp_server.monitors_list_watches())["watches"]
    assert [w["watch_id"] for w in watches] == [ok["watch"]["watch_id"]]


@pytest.mark.unit
def test_create_rejects_interval_below_floor_without_raising(_store):
    """An out-of-range interval is the documented error string, not a raise.

    ``WatchSchedule.interval_seconds`` has ``ge=60``; the MCP surface must catch
    that pydantic ``ValidationError`` (HTTP returns 422 for the same input) and
    flatten it into the ``[monitors create error: ...]`` convention.
    """
    from digisearch import mcp_server

    out = mcp_server.monitors_create_watch(query="etf flows", interval_seconds=30)
    assert out.startswith("[monitors create error:") and out.endswith("]")
    assert json.loads(mcp_server.monitors_list_watches())["watches"] == []


@pytest.mark.unit
def test_create_requires_a_schedule(_store):
    from digisearch import mcp_server

    out = mcp_server.monitors_create_watch(query="etf flows")
    assert "schedule_cron or interval_seconds" in out
    assert json.loads(mcp_server.monitors_list_watches())["watches"] == []


@pytest.mark.unit
def test_create_webhook_mode_without_targets_rejected(_store):
    from digisearch import mcp_server

    out = mcp_server.monitors_create_watch(
        query="etf flows", interval_seconds=3600, delivery_mode="webhook"
    )
    assert "webhook_url_required" in out


@pytest.mark.unit
def test_trigger_returns_persisted_failed_run(_store, monkeypatch):
    from digisearch.monitors import runner as runner_mod

    from digisearch import mcp_server

    created = json.loads(mcp_server.monitors_create_watch(query="etf flows", interval_seconds=3600))
    wid = created["watch"]["watch_id"]

    def _boom(**kwargs):
        raise RuntimeError("recall exploded")

    monkeypatch.setattr(runner_mod, "_invoke_shallow_recall", _boom)
    run = json.loads(mcp_server.monitors_trigger_watch(wid))
    assert run["status"] == "failed"
    assert run["error"] == "recall exploded"
    assert json.loads(mcp_server.monitors_get_runs(wid))["runs"][0]["run_id"] == run["run_id"]


@pytest.mark.unit
def test_trigger_missing_watch_surfaces_store_error(_store):
    from digisearch import mcp_server

    out = mcp_server.monitors_trigger_watch("nope")
    assert "watch_not_found" in out


@pytest.mark.unit
def test_tools_fail_closed_without_a_store(monkeypatch):
    from digisearch import mcp_server

    def _boom():
        raise OSError("store home is not writable")

    monkeypatch.setattr(mcp_server, "get_store", _boom)
    outputs = (
        mcp_server.monitors_create_watch(query="etf flows", interval_seconds=3600),
        mcp_server.monitors_list_watches(),
        mcp_server.monitors_trigger_watch("w"),
        mcp_server.monitors_get_runs("w"),
    )
    for out in outputs:
        assert "disabled" in out

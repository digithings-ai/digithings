"""MCP wiring for the Slapper tearsheet generator (#1493).

``digiquant_generate_slapper_tearsheet`` must route every strategy through
``run_strategy_isolated`` (one spawned process per strategy): NautilusTrader's
Rust logging can only initialize once per process (#1389), so an in-process
``run_and_write`` loop would SIGABRT the MCP server on the second strategy.
It must also resolve a calibration source — ``run_and_write`` requires the
keyword-only ``cal_source`` — and report per-strategy failures in its JSON
result instead of crashing the server. These tests exercise the tool path with
the runner mocked — no backtest runs, but patching calibrations_loader imports
digiquant.strategies (→ nautilus), so conftest collect_ignore skips this file
when the [nautilus] extra is absent.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digiquant.mcp_server import create_mcp_server  # noqa: E402

_SCRIPT = Path(__file__).resolve().parents[2] / "digiquant" / "scripts" / "generate_tearsheets.py"


def _gts():
    """The ``sys.modules["generate_tearsheets"]`` entry, loading it if needed.

    The MCP tool does ``import generate_tearsheets`` after putting the scripts
    dir on ``sys.path``, so patches must land on the exact module object the
    tool will resolve. Other test modules (test_tearsheet_isolation.py) replace
    the ``sys.modules`` entry with their own copy at collection time — resolve
    it at patch time, never cache a module-scope reference.
    """
    mod = sys.modules.get("generate_tearsheets")
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location("generate_tearsheets", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["generate_tearsheets"] = mod
    spec.loader.exec_module(mod)
    return mod


pytestmark = pytest.mark.unit


def _tool_fn(name: str):
    server = create_mcp_server()
    if hasattr(server, "list_tools_sync"):
        tools = server.list_tools_sync()
    else:
        tools = server._tool_manager.list_tools()
    for t in tools:
        if t.name == name:
            return t.fn
    raise AssertionError(f"tool {name!r} not registered; got {sorted(t.name for t in tools)}")


def _strategy_ids() -> list[str]:
    return list(json.loads(_gts().SETTINGS_PATH.read_text())["strategies"])


def _fake_runner(fail: set[str]):
    calls: list[dict] = []

    def runner(
        strategy: str,
        symbol: str,
        settings: dict,
        cache_dir: Path,
        output_dir: Path,
        *,
        cal_source: str,
        push_supabase: bool = False,
        signal_delay_days: int = 0,
    ) -> tuple[dict | None, str | None]:
        calls.append(
            {
                "strategy": strategy,
                "symbol": symbol,
                "cache_dir": cache_dir,
                "output_dir": output_dir,
                "cal_source": cal_source,
                "push_supabase": push_supabase,
                "signal_delay_days": signal_delay_days,
            }
        )
        if strategy in fail:
            return None, "backtest process died before reporting (killed by SIGABRT)"
        return {"strategy": strategy}, None

    return runner, calls


def _patch_tool_wiring(monkeypatch: pytest.MonkeyPatch, runner) -> None:
    """Keep the tool hermetic: no .env load, no calibration probing, mocked runner."""
    import digiquant.strategies.calibrations_loader as cal_loader

    mod = _gts()
    monkeypatch.setattr(mod, "load_repo_env", lambda: None)
    monkeypatch.setattr(mod, "run_strategy_isolated", runner)
    monkeypatch.setattr(cal_loader, "pick_calibration_source", lambda **_: "example")


def test_tearsheet_tool_registered() -> None:
    _tool_fn("digiquant_generate_slapper_tearsheet")


def test_all_strategies_route_through_isolated_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    strategies = _strategy_ids()
    runner, calls = _fake_runner(fail=set())
    _patch_tool_wiring(monkeypatch, runner)

    fn = _tool_fn("digiquant_generate_slapper_tearsheet")
    out = json.loads(fn(cache_dir=str(tmp_path)))

    assert [c["strategy"] for c in calls] == strategies
    for c in calls:
        assert c["cal_source"] == "example"  # resolved source is threaded to every run
        assert c["cache_dir"] == tmp_path
        assert c["output_dir"] == _gts().FRONTEND_STRATEGIES
        assert c["push_supabase"] is False
        assert c["signal_delay_days"] == 0  # internal tool: no public delay (#1462)
    assert [e["strategy"] for e in out["written"]] == strategies
    assert out["failures"] == []


def test_single_strategy_runs_only_that_strategy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    strategies = _strategy_ids()
    runner, calls = _fake_runner(fail=set())
    _patch_tool_wiring(monkeypatch, runner)

    fn = _tool_fn("digiquant_generate_slapper_tearsheet")
    out = json.loads(fn(strategy=strategies[0], cache_dir=str(tmp_path)))

    assert [c["strategy"] for c in calls] == [strategies[0]]
    assert [e["strategy"] for e in out["written"]] == [strategies[0]]


def test_crashed_strategy_reported_without_killing_the_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    strategies = _strategy_ids()
    assert len(strategies) >= 3
    failing = strategies[1]  # a middle strategy: the rest must still run
    runner, calls = _fake_runner(fail={failing})
    _patch_tool_wiring(monkeypatch, runner)

    fn = _tool_fn("digiquant_generate_slapper_tearsheet")
    out = json.loads(fn(cache_dir=str(tmp_path)))  # must not raise

    assert [c["strategy"] for c in calls] == strategies
    assert [e["strategy"] for e in out["written"]] == [s for s in strategies if s != failing]
    assert out["failures"] == [
        {
            "strategy": failing,
            "error": "backtest process died before reporting (killed by SIGABRT)",
        }
    ]


def test_unknown_strategy_returns_json_error(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, calls = _fake_runner(fail=set())
    _patch_tool_wiring(monkeypatch, runner)

    fn = _tool_fn("digiquant_generate_slapper_tearsheet")
    out = json.loads(fn(strategy="not_a_slapper"))

    assert "Unknown strategy" in out["error"]
    assert calls == []


def test_missing_calibrations_surface_as_json_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import digiquant.strategies.calibrations_loader as cal_loader

    def _boom(**_: object) -> str:
        raise FileNotFoundError("calibrations.json missing and no Supabase calibrations")

    runner, calls = _fake_runner(fail=set())
    mod = _gts()
    monkeypatch.setattr(mod, "load_repo_env", lambda: None)
    monkeypatch.setattr(mod, "run_strategy_isolated", runner)
    monkeypatch.setattr(cal_loader, "pick_calibration_source", _boom)

    fn = _tool_fn("digiquant_generate_slapper_tearsheet")
    out = json.loads(fn())

    assert out["error"].startswith("FileNotFoundError")
    assert calls == []  # no backtest attempted without a calibration source

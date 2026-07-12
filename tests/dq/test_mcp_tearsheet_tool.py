"""MCP slapper-tearsheet tool wiring against the current tearsheet API (#1495).

``digiquant_generate_slapper_tearsheet`` predated ``cal_source`` (#1064) and the
#1389 spawn-per-strategy isolation, so every call raised ``TypeError`` — and an
in-process fix would SIGABRT the long-lived MCP server on the second strategy
(Nautilus Rust logging initializes once per process). These tests pin the
repaired wiring with the backtest mocked out: per-strategy
``run_strategy_isolated`` calls with ``cal_source`` and ``signal_delay_days``
threaded through, per-strategy failures surfaced as JSON (never an exception),
and input validation for unknown strategies / negative delays.

Runs with or without the ``[nautilus]`` extra: ``generate_tearsheets`` imports
Nautilus lazily, and ``calibrations_loader`` (whose package ``__init__`` pulls
Nautilus strategies) is stubbed into ``sys.modules`` when the real import fails.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import ModuleType

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digiquant.mcp_server import create_mcp_server  # noqa: E402

_SCRIPTS = Path(__file__).resolve().parents[2] / "digiquant" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

pytestmark = pytest.mark.unit


def _tearsheet_tool():
    """The raw tool function (bypasses MCP transport for direct unit calls)."""
    server = create_mcp_server()
    return server._tool_manager.get_tool("digiquant_generate_slapper_tearsheet").fn


@pytest.fixture()
def cal_loader(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """``digiquant.strategies.calibrations_loader`` as the tool will import it.

    The real module's package ``__init__`` imports Nautilus strategies; when the
    ``[nautilus]`` extra is absent (CI excludes it — see conftest/#42) a stub is
    registered in ``sys.modules`` so the tool's lazy import still resolves.
    """
    try:
        import digiquant.strategies.calibrations_loader as real

        return real
    except ModuleNotFoundError:
        stub = types.ModuleType("digiquant.strategies.calibrations_loader")
        stub.pick_calibration_source = lambda **_: "example"  # type: ignore[attr-defined]
        pkg = types.ModuleType("digiquant.strategies")
        pkg.calibrations_loader = stub  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "digiquant.strategies", pkg)
        monkeypatch.setitem(sys.modules, "digiquant.strategies.calibrations_loader", stub)
        return stub


@pytest.fixture()
def gt(monkeypatch: pytest.MonkeyPatch, cal_loader: ModuleType) -> ModuleType:
    """The ``generate_tearsheets`` module *as the MCP tool will import it*.

    Resolved at test time (not file-import time): test_tearsheet_isolation.py
    replaces ``sys.modules["generate_tearsheets"]`` during collection, so a
    module object captured at import time may not be the one the tool sees —
    monkeypatches on a stale object would silently spawn real backtests.
    Hermetic by default: no .env load, no calibration file/Supabase probing.
    """
    import generate_tearsheets

    # ``import`` hands back the *current* sys.modules entry, so this is always
    # the object the tool's own ``import generate_tearsheets`` will resolve to.
    module = generate_tearsheets
    monkeypatch.setattr(module, "load_repo_env", lambda: None)
    monkeypatch.setattr(cal_loader, "pick_calibration_source", lambda **_: "example")
    return module


def _strategy_ids(gt: ModuleType) -> list[str]:
    return list(json.loads(gt.SETTINGS_PATH.read_text())["strategies"])


def _fake_runner(fail: set[str]):
    """Stand-in for ``run_strategy_isolated`` recording every call's args/kwargs."""
    calls: list[tuple[tuple, dict]] = []

    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        strategy = args[0]
        if strategy in fail:
            return None, "backtest process died before reporting (killed by SIGABRT)"
        return {"strategy": strategy}, None

    return runner, calls


def test_all_strategies_run_isolated_with_cal_source(
    gt: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, calls = _fake_runner(fail=set())
    monkeypatch.setattr(gt, "run_strategy_isolated", runner)

    result = json.loads(_tearsheet_tool()(signal_delay_days=3))

    strategies = _strategy_ids(gt)
    assert [args[0] for args, _ in calls] == strategies
    for args, kwargs in calls:
        # Current run_strategy_isolated API: cal_source is keyword-only and
        # required; signal_delay_days threads through; output dir is the
        # digiquant.io frontend.
        assert kwargs["cal_source"] == "example"
        assert kwargs["signal_delay_days"] == 3
        assert args[4] == gt.FRONTEND_STRATEGIES
    assert [e["strategy"] for e in result["entries"]] == strategies
    assert result["failures"] == {}


def test_single_strategy_failure_surfaced_as_json(
    gt: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = _strategy_ids(gt)[0]
    runner, calls = _fake_runner(fail={target})
    monkeypatch.setattr(gt, "run_strategy_isolated", runner)

    result = json.loads(_tearsheet_tool()(strategy=target, cache_dir=str(tmp_path)))

    assert [args[0] for args, _ in calls] == [target]
    assert calls[0][0][3] == tmp_path  # explicit cache_dir honored
    assert result["entries"] == []
    assert "SIGABRT" in result["failures"][target]


def test_unknown_strategy_rejected_before_running(
    gt: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, calls = _fake_runner(fail=set())
    monkeypatch.setattr(gt, "run_strategy_isolated", runner)

    result = json.loads(_tearsheet_tool()(strategy="nope_slapper"))

    assert calls == []
    assert "nope_slapper" in result["error"]


def test_negative_signal_delay_rejected(gt: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    runner, calls = _fake_runner(fail=set())
    monkeypatch.setattr(gt, "run_strategy_isolated", runner)

    result = json.loads(_tearsheet_tool()(signal_delay_days=-1))

    assert calls == []
    assert "signal_delay_days" in result["error"]


def test_missing_calibrations_surface_as_json_error(
    gt: ModuleType, cal_loader: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_source(**_: object) -> str:
        raise FileNotFoundError("Missing calibrations.json and no Supabase calibrations")

    monkeypatch.setattr(cal_loader, "pick_calibration_source", _no_source)
    runner, calls = _fake_runner(fail=set())
    monkeypatch.setattr(gt, "run_strategy_isolated", runner)

    result = json.loads(_tearsheet_tool()())

    assert calls == []
    assert "FileNotFoundError" in result["error"]

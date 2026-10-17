"""The lab's MCP tool surface, and the rails-fitter mapping it depends on.

Two things are pinned here. First, that the lab declares its MCP tools through
the ``digiquant.mcp_tools`` entry-point group and that the declaration actually
registers the names the module claims — an entry point that resolves to nothing
is worse than no entry point, because the surface looks published. Second, that
``rails_fitter_for`` sends ``btc_power_law`` to the window-local fitter and not
to the coefficients loader, which is the difference between a fold fit and a
full-history fit leaking into every fold (#3173).
"""

from __future__ import annotations

import importlib
import json
import tomllib
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from digiquant.strategies.lab import golden_path, mcp_tools, presets

import digiquant

pytestmark = pytest.mark.unit

PYPROJECT = Path(digiquant.__file__).resolve().parents[2] / "pyproject.toml"

DECLARED_ENTRY_POINT = "digiquant.strategies.lab.mcp_tools:register_mcp_tools"


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def _synthetic(row_count: int = 400, seed: int = 7):
    """A seeded geometric random walk — deterministic across runs."""
    import random
    from datetime import date, timedelta

    rng = random.Random(seed)
    start = date(2023, 1, 1)
    dates = [start + timedelta(days=offset) for offset in range(row_count)]
    price = 20_000.0
    prices: list[float] = []
    for _ in range(row_count):
        price *= 1.0 + rng.uniform(-0.02, 0.022)
        prices.append(price)
    return dates, prices


def _capture_tools(registrar: Any) -> dict[str, Any]:
    """Run a ``register_mcp_tools(mcp, maybe_tool)`` object and capture the tools.

    Mirrors the dispatch in ``digiquant.plugin.register_plugin_mcp_tools``: a
    callable registrar is invoked with the server and the decorator, and the host
    decorator is called with a name and returns a registering decorator.
    """
    captured: dict[str, Any] = {}

    def _maybe_tool(name: str):
        def _register(fn):
            captured[name] = fn
            return fn

        return _register

    class _CaptureMCP:
        @staticmethod
        def tool(name: str | None = None, **_kwargs):
            def _register(fn):
                captured[name or getattr(fn, "__name__", "?")] = fn
                return fn

            return _register

    registrar(_CaptureMCP(), _maybe_tool)
    return captured


def _tool_names(server) -> set[str]:
    if hasattr(server, "list_tools_sync"):
        tools = server.list_tools_sync()
    else:
        tools = server._tool_manager.list_tools()
    return {t.name for t in tools}


@pytest.fixture()
def lab_tools() -> dict[str, Any]:
    return _capture_tools(mcp_tools.register_mcp_tools)


@pytest.fixture()
def ohlcv_dir(tmp_path: Path) -> Path:
    """A directory holding ``TEST.csv`` as a full OHLCV frame."""
    dates, prices = _synthetic()
    pl.DataFrame(
        {
            "timestamp": pl.Series(dates, dtype=pl.Date),
            "open": pl.Series(prices, dtype=pl.Float64),
            "high": pl.Series(prices, dtype=pl.Float64),
            "low": pl.Series(prices, dtype=pl.Float64),
            "close": pl.Series(prices, dtype=pl.Float64),
            "volume": pl.Series([1_000.0] * len(dates), dtype=pl.Float64),
        }
    ).write_csv(tmp_path / "TEST.csv")
    return tmp_path


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def test_registration_declares_exactly_the_advertised_names(lab_tools):
    assert tuple(lab_tools) == mcp_tools.TOOL_NAMES
    assert len(mcp_tools.TOOL_NAMES) == 3


def test_tool_names_are_unprefixed_by_the_canonicaliser():
    """``lab_*`` is not a legacy prefix, so the host must not rewrite the names."""
    from digiquant.tool_names import canonical_tool_name

    for name in mcp_tools.TOOL_NAMES:
        assert canonical_tool_name(name) == name


def test_pyproject_declares_the_lab_mcp_entry_point():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    groups = data["project"]["entry-points"]
    assert groups["digiquant.mcp_tools"]["lab"] == DECLARED_ENTRY_POINT


def test_the_declared_entry_point_resolves_to_a_callable():
    module_path, _, attribute = DECLARED_ENTRY_POINT.partition(":")
    resolved = getattr(importlib.import_module(module_path), attribute)
    assert callable(resolved)
    assert tuple(_capture_tools(resolved)) == mcp_tools.TOOL_NAMES


def test_create_mcp_server_gains_exactly_the_plugin_tools(monkeypatch):
    """The host path, end to end, without needing the entry point installed.

    ``plugin.discover`` is patched rather than the distribution reinstalled: the
    installed dist-info lives in the shared venv, so an entry point declared in
    this worktree is not visible to ``importlib.metadata`` until someone
    reinstalls, which is not this test's business.
    """
    pytest.importorskip("mcp.server.fastmcp")
    from digiquant.mcp_server import create_mcp_server

    from digiquant import plugin

    baseline = _tool_names(create_mcp_server())

    class _FakeEntryPoint:
        name = "lab"

        @staticmethod
        def load():
            return mcp_tools.register_mcp_tools

    def _discover(group):
        if group == plugin.MCP_TOOLS_GROUP:
            return [_FakeEntryPoint()]
        return []

    monkeypatch.setattr(plugin, "discover", _discover)
    patched = _tool_names(create_mcp_server())

    assert patched - baseline == set(mcp_tools.TOOL_NAMES)
    assert baseline - patched == set()


def test_lab_tools_stay_off_the_read_scope(monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    from digiquant.mcp_server import create_mcp_server

    from digiquant import plugin

    class _FakeEntryPoint:
        name = "lab"

        @staticmethod
        def load():
            return mcp_tools.register_mcp_tools

    monkeypatch.setattr(
        plugin,
        "discover",
        lambda group: [_FakeEntryPoint()] if group == plugin.MCP_TOOLS_GROUP else [],
    )
    read = _tool_names(create_mcp_server(scope="read"))
    assert not (set(mcp_tools.TOOL_NAMES) & read)


# --------------------------------------------------------------------------- #
# Tool payloads
# --------------------------------------------------------------------------- #


def test_lab_list_presets_returns_the_preset_names(lab_tools):
    payload = json.loads(lab_tools["lab_list_presets"]())
    assert payload["presets"] == presets.list_presets()
    assert payload["count"] == len(payload["presets"])
    assert payload["count"] > 0


def test_lab_describe_preset_returns_nodes_and_flags(lab_tools):
    payload = json.loads(lab_tools["lab_describe_preset"]("balanced"))
    preset = presets.load_preset("balanced")
    assert payload["curve_nodes"] == list(preset.curve_nodes)
    assert payload["long_only"] == preset.long_only
    assert payload["description"]


def test_lab_describe_preset_reports_an_unknown_name_without_raising(lab_tools):
    payload = json.loads(lab_tools["lab_describe_preset"]("no-such-preset"))
    assert "error" in payload
    assert payload["known"] == presets.list_presets()


def test_lab_run_golden_path_reports_the_non_authoritative_caveat(lab_tools, ohlcv_dir):
    payload = json.loads(
        lab_tools["lab_run_golden_path"](
            symbol="TEST",
            data_dir=str(ohlcv_dir),
            risk_model="rolling_z",
            preset="balanced",
        )
    )
    assert "error" not in payload, payload
    assert payload["backtest"]["authoritative"] is False
    assert payload["backtest"]["caveat"]
    assert payload["range"]["rows"] > 300
    assert payload["optimize_ran"] is False
    assert payload["stages"] == ["research", "backtest", "optimize", "tearsheet"]


def test_lab_run_golden_path_reports_failures_as_json(lab_tools, tmp_path: Path):
    payload = json.loads(lab_tools["lab_run_golden_path"](symbol="MISSING", data_dir=str(tmp_path)))
    assert "error" in payload


def test_lab_run_golden_path_optimize_stage_uses_the_window_fitter(lab_tools, ohlcv_dir):
    """A short window must make the fold fitter refuse, not load coefficients.

    The 400-row fixture is below the 730-observation floor, so the only fitting
    path can answer with a ValueError. A loader would have succeeded here, which
    is exactly the leak ``rails_fitter_for`` exists to prevent.
    """
    payload = json.loads(
        lab_tools["lab_run_golden_path"](
            symbol="TEST",
            data_dir=str(ohlcv_dir),
            risk_model="btc_power_law",
            preset="balanced",
            trials_json=json.dumps([{"buy_knee_risk": 30.0}]),
        )
    )
    assert "error" in payload
    assert "730" in payload["error"]


# --------------------------------------------------------------------------- #
# rails_fitter_for
# --------------------------------------------------------------------------- #


def test_rails_fitter_for_maps_btc_power_law_to_the_fold_fitter():
    from digiquant.strategies.lab.optimize import btc_power_law_rails_fitter

    assert golden_path.rails_fitter_for("btc_power_law") is btc_power_law_rails_fitter


def test_rails_fitter_for_rejects_unknown_names():
    with pytest.raises(ValueError, match="unknown SDCA risk model"):
        golden_path.rails_fitter_for("not-a-model")


@pytest.mark.parametrize("name", ["generic_valuation", "rolling_z"])
def test_rails_fitter_for_fits_from_the_window_without_loading_coefficients(name, monkeypatch):
    """The closure must call the resolver with ``coefficients_path=None``."""
    seen: dict[str, Any] = {}
    sentinel = object()

    def _fake_resolver(model_name, **kwargs):
        seen["name"] = model_name
        seen["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(golden_path, "resolve_sdca_risk_model", _fake_resolver)
    fitter = golden_path.rails_fitter_for(name)
    dates, prices = _synthetic(40)
    assert fitter(dates, prices) is sentinel

    assert seen["name"] == name
    assert seen["kwargs"]["coefficients_path"] is None
    assert isinstance(seen["kwargs"]["dates"], pl.Series)
    assert isinstance(seen["kwargs"]["price"], pl.Series)
    assert seen["kwargs"]["dates"].len() == len(dates)
    assert fitter.__name__ == f"{name}_rails_fitter"


def test_the_btc_fitter_refuses_a_short_window_while_the_resolver_succeeds():
    """The discriminator: same model name, opposite answers on 400 rows."""
    from digiquant.strategies.lab.providers import resolve_sdca_risk_model

    dates, prices = _synthetic(400)
    with pytest.raises(ValueError, match="730"):
        golden_path.rails_fitter_for("btc_power_law")(dates, prices)

    loaded = resolve_sdca_risk_model(
        "btc_power_law",
        dates=pl.Series("date", dates, dtype=pl.Date),
        price=pl.Series("close", prices, dtype=pl.Float64),
    )
    assert loaded is not None


def test_facade_exposes_the_rails_fitter_mapping():
    import digiquant.strategies.lab as lab

    assert lab.rails_fitter_for is golden_path.rails_fitter_for

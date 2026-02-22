"""Unit tests for optimize and export modules."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from digiquant.export import run_export
from digiquant.optimize import run_optimize
from digiquant.sweep import run_sweep
from digiquant.tradingview import export_to_pine, import_from_pine


@pytest.mark.unit
class TestRunOptimize:
    """run_optimize returns OptimizeResult. Requires Nautilus."""

    def test_returns_optimize_result(self) -> None:
        pytest.importorskip("nautilus_trader")
        r = run_optimize(strategy_name="ema", symbols=["AAPL"])
        assert r.run_id.startswith("optimize-")
        assert r.strategy_name == "ema"
        assert r.num_evaluations >= 1
        assert r.best_backtest is not None
        assert r.status == "ok"

    def test_with_param_grid(self) -> None:
        pytest.importorskip("nautilus_trader")
        r = run_optimize(strategy_name="s", symbols=["X"], param_grid=[{}, {}])
        assert r.num_evaluations == 2


@pytest.mark.unit
class TestRunExport:
    """run_export writes artifact and returns ExportResult."""

    def test_returns_export_result(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            r = run_export("my_strategy", target="nautilus", output_dir=d)
            assert r.run_id.startswith("export-")
            assert r.target == "nautilus"
            assert r.artifact_path is not None
            assert Path(r.artifact_path).exists()
            assert r.status == "ok"

    def test_unsupported_target_returns_error_status(self) -> None:
        r = run_export("x", target="unknown")
        assert r.status == "error"


@pytest.mark.unit
class TestRunSweep:
    """run_sweep returns list of BacktestResult. Requires Nautilus."""

    def test_returns_list(self) -> None:
        pytest.importorskip("nautilus_trader")
        results = run_sweep(strategy_name="s", symbols=["AAPL"], param_grid=[{}, {}])
        assert len(results) == 2
        assert all(hasattr(r, "run_id") for r in results)


@pytest.mark.unit
class TestTradingViewNotImplemented:
    """TradingView/PyneCore export/import not implemented; return success=False."""

    def test_export_to_pine_not_implemented(self) -> None:
        r = export_to_pine("ema_cross")
        assert r.success is False
        assert "not implemented" in r.message.lower()

    def test_import_from_pine_not_implemented(self) -> None:
        r = import_from_pine("/fake/path.pine")
        assert r.success is False
        assert r.strategy_name is None
        assert "not implemented" in r.message.lower()

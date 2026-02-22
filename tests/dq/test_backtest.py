"""Unit tests for DigiQuant backtest module (real Nautilus or raised error)."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from digiquant.backtest import run_backtest
from digiquant.models import BacktestResult


@pytest.mark.unit
class TestRunBacktest:
    """run_backtest() requires Nautilus; returns real result or raises."""

    def test_raises_when_nautilus_unavailable(self) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest", return_value=None):
            with pytest.raises(RuntimeError, match="Nautilus backtest unavailable"):
                run_backtest(strategy_name="x", symbols=["A"])

    def test_message_contains_install_hint(self) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest", return_value=None):
            with pytest.raises(RuntimeError) as exc_info:
                run_backtest(strategy_name="x", symbols=["A"])
            assert "digiquant[nautilus]" in str(exc_info.value)

    def test_default_symbols_when_none(self) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest") as m:
            m.return_value = None
            with pytest.raises(RuntimeError):
                run_backtest(strategy_name="s", symbols=None)
            m.assert_called_once()
            call_kw = m.call_args[1]
            assert call_kw["symbols"] == ["AAPL", "MSFT", "GOOGL"]

    def test_default_symbols_when_empty_list(self) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest") as m:
            m.return_value = None
            with pytest.raises(RuntimeError):
                run_backtest(strategy_name="s", symbols=[])
            call_kw = m.call_args[1]
            assert call_kw["symbols"] == ["AAPL", "MSFT", "GOOGL"]

    def test_passes_through_strategy_and_symbols(self) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest") as m:
            m.return_value = None
            with pytest.raises(RuntimeError):
                run_backtest(strategy_name="my_strat", symbols=["AAPL", "MSFT"])
            m.assert_called_once_with(strategy_name="my_strat", symbols=["AAPL", "MSFT"])


@pytest.mark.unit
class TestRunBacktestReal:
    """Run real Nautilus backtest when nautilus_trader and test data are available."""

    def test_returns_backtest_result_with_nautilus_run_id(self) -> None:
        pytest.importorskip("nautilus_trader")
        result = run_backtest(strategy_name="mean_reversion_tech", symbols=["AAPL", "MSFT"])
        assert isinstance(result, BacktestResult)
        assert result.status == "ok"
        assert result.run_id.startswith("nautilus-")

    def test_returns_in_reasonable_time(self) -> None:
        pytest.importorskip("nautilus_trader")
        start = time.monotonic()
        run_backtest(strategy_name="x", symbols=["A"])
        elapsed = time.monotonic() - start
        assert elapsed < 60.0, f"Real backtest should finish in < 60s, took {elapsed:.2f}s"

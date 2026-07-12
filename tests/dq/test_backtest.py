"""Unit tests for DigiQuant backtest module (real Nautilus or raised error)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from digiquant.backtest import run_backtest
from digiquant.data.loader import generate_synthetic_ohlcv
from digiquant.models import BacktestResult
from tests.dq.conftest import SKIP_NATIVE_CRASH


@pytest.mark.unit
class TestRunBacktest:
    """run_backtest() requires data_path or data_dir+symbols; fails if data unavailable."""

    def test_raises_when_no_data_provided(self) -> None:
        with pytest.raises(RuntimeError, match="requires data_path"):
            run_backtest(strategy_name="ema_cross", symbols=["A"])

    def test_raises_when_data_dir_without_symbols(self) -> None:
        with pytest.raises(RuntimeError, match="symbols required"):
            run_backtest(strategy_name="ema_cross", symbols=[], data_dir="/tmp")

    def test_raises_when_data_unavailable(self) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest", return_value=None):
            with pytest.raises(RuntimeError, match="Backtest failed"):
                run_backtest(
                    strategy_name="ema_cross",
                    symbols=["AAPL"],
                    data_dir="/nonexistent",
                )

    def test_message_contains_install_hint_when_fails(self) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest", return_value=None):
            with pytest.raises(RuntimeError) as exc_info:
                run_backtest(
                    strategy_name="ema_cross",
                    symbols=["AAPL"],
                    data_dir="/tmp",
                )
            assert "digiquant[nautilus]" in str(exc_info.value)

    def test_passes_through_strategy_and_symbols(self) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest") as m:
            m.return_value = BacktestResult(
                run_id="nautilus-x",
                strategy_name="my_strat",
                symbols=["AAPL", "MSFT"],
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-12-31T00:00:00Z",
                total_pnl=0.0,
                total_return_pct=0.0,
                num_trades=0,
                status="ok",
            )
            import tempfile

            df = generate_synthetic_ohlcv(["AAPL"], freq="1d")
            with tempfile.TemporaryDirectory() as tmp:
                df.write_csv(Path(tmp) / "AAPL.csv")
                run_backtest(
                    strategy_name="ema_cross",
                    symbols=["AAPL", "MSFT"],
                    data_dir=tmp,
                )
            m.assert_called_once_with(
                strategy_name="ema_cross",
                symbols=["AAPL", "MSFT"],
                data_path=None,
                data_dir=m.call_args[1]["data_dir"],
                tearsheet_path=None,
                strategy_params=None,
                full_tearsheet=True,
            )

    def test_passes_data_path_and_data_dir(self) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest") as m:
            m.return_value = BacktestResult(
                run_id="nautilus-x",
                strategy_name="ema_cross",
                symbols=["AAPL"],
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-12-31T00:00:00Z",
                total_pnl=0.0,
                total_return_pct=0.0,
                num_trades=0,
                status="ok",
            )
            run_backtest(
                strategy_name="ema_cross",
                symbols=["AAPL"],
                data_path="/path/to/AAPL.csv",
            )
            m.assert_called_once_with(
                strategy_name="ema_cross",
                symbols=["AAPL"],
                data_path="/path/to/AAPL.csv",
                data_dir=None,
                tearsheet_path=None,
                strategy_params=None,
                full_tearsheet=True,
            )


@SKIP_NATIVE_CRASH
@pytest.mark.unit
class TestRunBacktestReal:
    """Run real Nautilus backtest when nautilus_trader and test data are available."""

    def test_returns_backtest_result_with_nautilus_run_id(self) -> None:
        pytest.importorskip("nautilus_trader")
        import tempfile

        df = generate_synthetic_ohlcv(["AAPL"], freq="1d")
        with tempfile.TemporaryDirectory() as tmp:
            df.write_csv(Path(tmp) / "AAPL.csv")
            result = run_backtest(
                strategy_name="mean_reversion_tech",
                symbols=["AAPL"],
                data_dir=tmp,
            )
        assert isinstance(result, BacktestResult)
        assert result.status == "ok"
        assert result.run_id.startswith("nautilus-")

    def test_returns_in_reasonable_time(self) -> None:
        pytest.importorskip("nautilus_trader")
        import tempfile

        df = generate_synthetic_ohlcv(["AAPL"], freq="1d")
        with tempfile.TemporaryDirectory() as tmp:
            df.write_csv(Path(tmp) / "AAPL.csv")
            start = time.monotonic()
            run_backtest(strategy_name="ema_cross", symbols=["AAPL"], data_dir=tmp)
            elapsed = time.monotonic() - start
        assert elapsed < 60.0, f"Real backtest should finish in < 60s, took {elapsed:.2f}s"

    def test_runs_on_user_ohlcv_data(self) -> None:
        """When data_dir provided with symbol CSV, backtest runs on that data."""
        pytest.importorskip("nautilus_trader")
        import tempfile

        df = generate_synthetic_ohlcv(["AAPL"], freq="1d")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "AAPL.csv"
            df.write_csv(path)
            result = run_backtest(
                strategy_name="mean_reversion_tech",
                symbols=["AAPL"],
                data_dir=tmp,
            )
        assert isinstance(result, BacktestResult)
        assert result.status == "ok"
        assert result.run_id.startswith("nautilus-")
        assert "AAPL" in result.symbols
        assert "OHLCV" in result.message or "user" in result.message.lower()

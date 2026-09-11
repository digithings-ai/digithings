"""Unit tests for digiquant.nautilus_runner — result parsers and helpers."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import polars as pl
import pytest
from digiquant.models import BacktestResult
from digiquant.nautilus_runner import (
    _build_result,
    _extract_pnl,
    _run_multi_symbol_backtest,
    run_nautilus_backtest,
)


def _ohlcv_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [1_700_000_000_000_000_000, 1_700_086_400_000_000_000],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.0, 101.0],
            "volume": [1000.0, 1000.0],
        }
    )


def _stub_bars() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(ts_init=1_700_000_000_000_000_000, close=100.0),
        SimpleNamespace(ts_init=1_700_086_400_000_000_000, close=101.0),
    ]


class _StubAnalyzer:
    def __init__(
        self,
        *,
        returns_stats: dict | None = None,
        pnls_stats: dict | None = None,
        raise_on_returns: bool = False,
    ) -> None:
        self._returns_stats = returns_stats
        self._pnls_stats = pnls_stats
        self._raise_on_returns = raise_on_returns

    def get_performance_stats_returns(self):
        if self._raise_on_returns:
            raise ValueError("returns analyzer exploded")
        return self._returns_stats

    def get_performance_stats_pnls(self):
        return self._pnls_stats

    def get_performance_stats_general(self):
        return {}

    def returns(self):
        return pd.Series(dtype="float64")

    def realized_pnls(self, usd):
        return pd.Series(dtype="float64")


class _StubTrader:
    def __init__(self, account_report) -> None:
        self._account_report = account_report

    def generate_order_fills_report(self):
        return pd.DataFrame([{"qty": 1.0}])

    def generate_account_report(self, venue):
        return self._account_report


class _StubEngine:
    def __init__(self, analyzer, account_report) -> None:
        self.portfolio = SimpleNamespace(analyzer=analyzer)
        self.trader = _StubTrader(account_report)

    def dispose(self) -> None:
        pass


@contextmanager
def _patched_single_run(engine):
    with (
        patch(
            "digiquant.nautilus_runner._load_ohlcv_for_backtest",
            return_value=(_ohlcv_df(), "BTC"),
        ),
        patch(
            "digiquant.nautilus_runner._prepare_bar_data",
            return_value=(object(), object(), _stub_bars(), None),
        ),
        patch("digiquant.nautilus_runner._build_engine", return_value=engine),
    ):
        yield


def _symbol_result(
    symbol: str,
    *,
    status: str = "ok",
    sharpe: float | None = 1.0,
    dd: float | None = -10.0,
    pnl: float = 100.0,
) -> BacktestResult:
    return BacktestResult(
        run_id=f"r-{symbol}",
        strategy_name="s",
        symbols=[symbol],
        start_time="2023-11-14T00:00:00Z",
        end_time="2023-11-15T00:00:00Z",
        total_pnl=pnl,
        total_return_pct=1.0,
        sharpe_ratio=sharpe,
        max_drawdown_pct=dd,
        num_trades=3,
        status=status,
        message=f"({symbol})",
    )


# ---------------------------------------------------------------------------
# _extract_pnl
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractPnl:
    def _report(self, **kwargs) -> pd.DataFrame:
        """Build a minimal account-report DataFrame."""
        return pd.DataFrame([kwargs])

    def test_none_report_returns_zeros(self) -> None:
        pnl, ret = _extract_pnl(None)
        assert pnl == 0.0
        assert ret == 0.0

    def test_empty_dataframe_returns_zeros(self) -> None:
        pnl, ret = _extract_pnl(pd.DataFrame())
        assert pnl == 0.0
        assert ret == 0.0

    def test_total_column_numeric(self) -> None:
        report = self._report(total=1_050_000.0)
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(50_000.0)
        assert ret == pytest.approx(5.0)

    def test_balance_column_numeric(self) -> None:
        report = self._report(balance=900_000.0)
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(-100_000.0)
        assert ret == pytest.approx(-10.0)

    def test_equity_column_numeric(self) -> None:
        report = self._report(equity=1_000_000.0)
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(0.0)
        assert ret == pytest.approx(0.0)

    def test_total_column_string_with_currency(self) -> None:
        """Nautilus may return balance as '1100000.00 USD'."""
        report = self._report(total="1100000.00 USD")
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(100_000.0)
        assert ret == pytest.approx(10.0)

    def test_string_with_scientific_notation(self) -> None:
        report = self._report(total="1.05e6 USD")
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(50_000.0)

    def test_priority_total_over_balance(self) -> None:
        """'total' takes priority over 'balance'."""
        report = self._report(total=1_200_000.0, balance=800_000.0)
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(200_000.0)

    def test_no_recognised_column_returns_zeros(self) -> None:
        report = self._report(unrealised_pnl=5000.0)
        pnl, ret = _extract_pnl(report)
        assert pnl == 0.0
        assert ret == 0.0

    def test_multi_row_uses_last_row(self) -> None:
        """Account report may have multiple rows; last row is final balance."""
        report = pd.DataFrame([{"total": 900_000.0}, {"total": 1_100_000.0}])
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(100_000.0)

    def test_malformed_string_returns_zeros(self) -> None:
        report = self._report(total="not-a-number")
        pnl, ret = _extract_pnl(report)
        assert pnl == 0.0
        assert ret == 0.0


# ---------------------------------------------------------------------------
# _build_result
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildResult:
    _BASE_NS = 1_700_000_000_000_000_000  # ~2023-11 in nanoseconds
    _END_NS = _BASE_NS + 86_400 * int(1e9)  # +1 day

    def _perf(self, sharpe=None, max_dd=None):
        return {
            "sharpe": sharpe,
            "max_dd": max_dd,
            "stats_returns": None,
            "stats_pnls": None,
            "stats_general": None,
            "returns_series": None,
            "realized_pnls_series": None,
        }

    def test_basic_fields(self) -> None:
        r = _build_result(
            run_id="test-abc",
            strategy_name="sma_cross",
            symbols_echo=["AAPL"],
            symbol="AAPL",
            start_ts=self._BASE_NS,
            end_ts=self._END_NS,
            total_pnl=5000.0,
            total_return_pct=0.5,
            num_trades=10,
            perf=self._perf(),
        )
        assert r.run_id == "test-abc"
        assert r.strategy_name == "sma_cross"
        assert r.symbols == ["AAPL"]
        assert r.num_trades == 10
        assert r.total_pnl == pytest.approx(5000.0)
        assert r.total_return_pct == pytest.approx(0.5)
        assert r.status == "ok"

    def test_timestamps_iso_format(self) -> None:
        r = _build_result(
            run_id="x",
            strategy_name="s",
            symbols_echo=[],
            symbol="BTC",
            start_ts=self._BASE_NS,
            end_ts=self._END_NS,
            total_pnl=0.0,
            total_return_pct=0.0,
            num_trades=0,
            perf=self._perf(),
        )
        assert r.start_time.endswith("Z")
        assert "T" in r.start_time
        assert r.end_time.endswith("Z")

    def test_perf_fields_propagated(self) -> None:
        r = _build_result(
            run_id="y",
            strategy_name="rsi",
            symbols_echo=["ETH"],
            symbol="ETH",
            start_ts=self._BASE_NS,
            end_ts=self._END_NS,
            total_pnl=1000.0,
            total_return_pct=0.1,
            num_trades=5,
            perf=self._perf(sharpe=1.5, max_dd=12.3),
        )
        assert r.sharpe_ratio == pytest.approx(1.5)
        assert r.max_drawdown_pct == pytest.approx(-12.3)

    def test_nan_pnl_becomes_zero(self) -> None:
        r = _build_result(
            run_id="z",
            strategy_name="s",
            symbols_echo=[],
            symbol="X",
            start_ts=self._BASE_NS,
            end_ts=self._END_NS,
            total_pnl=float("nan"),
            total_return_pct=float("nan"),
            num_trades=0,
            perf=self._perf(),
        )
        assert r.total_pnl == 0.0
        assert r.total_return_pct == 0.0

    def test_symbols_echo_empty_uses_symbol(self) -> None:
        r = _build_result(
            run_id="q",
            strategy_name="s",
            symbols_echo=[],
            symbol="MSFT",
            start_ts=self._BASE_NS,
            end_ts=self._END_NS,
            total_pnl=0.0,
            total_return_pct=0.0,
            num_trades=0,
            perf=self._perf(),
        )
        assert r.symbols == ["MSFT"]


# ---------------------------------------------------------------------------
# Honest status: no fabricated success when extraction fails
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHonestStatusOnExtractionFailure:
    def test_pnl_parse_failure_is_error_not_ok(self) -> None:
        analyzer = _StubAnalyzer(
            returns_stats={"Sharpe Ratio (252 days)": 1.2},
            pnls_stats={"Max Drawdown %": -5.0},
        )
        engine = _StubEngine(analyzer, pd.DataFrame([{"total": "not-a-number"}]))
        with _patched_single_run(engine):
            result = run_nautilus_backtest(strategy_name="s", symbols=["BTC"], data_path="BTC.csv")
        assert result is not None
        assert result.status == "error"
        assert result.total_pnl == 0.0
        assert "pnl" in result.message.lower()

    def test_analyzer_exception_is_partial_and_names_missing_metrics(self) -> None:
        analyzer = _StubAnalyzer(returns_stats=None, pnls_stats=None, raise_on_returns=True)
        engine = _StubEngine(analyzer, pd.DataFrame([{"total": 1_050_000.0}]))
        with _patched_single_run(engine):
            result = run_nautilus_backtest(strategy_name="s", symbols=["BTC"], data_path="BTC.csv")
        assert result is not None
        assert result.status == "partial"
        assert result.total_pnl == pytest.approx(50_000.0)
        assert result.sharpe_ratio is None
        assert result.max_drawdown_pct is None
        assert "sharpe_ratio" in result.message
        assert "max_drawdown_pct" in result.message

    def test_unparseable_perf_stats_is_partial(self) -> None:
        analyzer = _StubAnalyzer(
            returns_stats={"Sharpe Ratio (252 days)": "n/a"},
            pnls_stats={"Max Drawdown %": "n/a"},
        )
        engine = _StubEngine(analyzer, pd.DataFrame([{"total": 1_100_000.0}]))
        with _patched_single_run(engine):
            result = run_nautilus_backtest(strategy_name="s", symbols=["BTC"], data_path="BTC.csv")
        assert result is not None
        assert result.status == "partial"
        assert "sharpe_ratio" in result.message
        assert "max_drawdown_pct" in result.message

    def test_healthy_run_stays_ok(self) -> None:
        analyzer = _StubAnalyzer(
            returns_stats={"Sharpe Ratio (252 days)": 1.5},
            pnls_stats={"Max Drawdown %": -8.0},
        )
        engine = _StubEngine(analyzer, pd.DataFrame([{"total": 1_200_000.0}]))
        with _patched_single_run(engine):
            result = run_nautilus_backtest(strategy_name="s", symbols=["BTC"], data_path="BTC.csv")
        assert result is not None
        assert result.status == "ok"
        assert result.total_pnl == pytest.approx(200_000.0)
        assert result.sharpe_ratio == pytest.approx(1.5)
        assert result.max_drawdown_pct == pytest.approx(-8.0)


# ---------------------------------------------------------------------------
# Multi-symbol aggregation honesty
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMultiSymbolHonestStatus:
    def _run(self, by_symbol: dict[str, BacktestResult | None]):
        def _fake(ohlcv_df, symbol, **kwargs):
            return by_symbol[symbol]

        with patch("digiquant.nautilus_runner._run_backtest_ohlcv", side_effect=_fake):
            return _run_multi_symbol_backtest(
                symbol_dfs={"AAA": _ohlcv_df(), "BBB": _ohlcv_df()},
                strategy_name="s",
                symbols=["AAA", "BBB"],
            )

    def test_dropped_symbol_surfaces_as_partial(self) -> None:
        result = self._run({"AAA": _symbol_result("AAA"), "BBB": None})
        assert result is not None
        assert result.status == "partial"
        assert "BBB" in result.message
        assert set(result.per_symbol_pnl) == {"AAA"}

    def test_worst_per_symbol_drawdown_is_reported_not_nil(self) -> None:
        result = self._run(
            {
                "AAA": _symbol_result("AAA", dd=-5.0),
                "BBB": _symbol_result("BBB", dd=-30.0),
            }
        )
        assert result is not None
        assert result.max_drawdown_pct == pytest.approx(-30.0)
        assert "worst" in result.message.lower()

    def test_averaged_sharpe_is_labeled(self) -> None:
        result = self._run(
            {
                "AAA": _symbol_result("AAA", sharpe=1.0),
                "BBB": _symbol_result("BBB", sharpe=3.0),
            }
        )
        assert result is not None
        assert result.sharpe_ratio == pytest.approx(2.0)
        assert "average" in result.message.lower()

    def test_error_symbol_is_never_aggregated_as_zero(self) -> None:
        result = self._run(
            {
                "AAA": _symbol_result("AAA", pnl=100.0),
                "BBB": _symbol_result("BBB", status="error", pnl=0.0),
            }
        )
        assert result is not None
        assert result.status == "partial"
        assert result.per_symbol_pnl == pytest.approx({"AAA": 100.0})
        assert "BBB" in result.message

    def test_all_healthy_multi_symbol_is_ok(self) -> None:
        result = self._run(
            {
                "AAA": _symbol_result("AAA", sharpe=1.0, dd=-5.0),
                "BBB": _symbol_result("BBB", sharpe=3.0, dd=-30.0),
            }
        )
        assert result is not None
        assert result.status == "ok"
        assert result.sharpe_ratio == pytest.approx(2.0)
        assert result.max_drawdown_pct == pytest.approx(-30.0)

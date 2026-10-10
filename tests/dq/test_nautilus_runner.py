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
    RETURNS_SERIES_MISSING,
    _account_balance_path,
    _balance_path_metrics,
    _build_result,
    _extract_pnl,
    _max_drawdown_from_balance_path,
    _run_multi_symbol_backtest,
    _series_is_portfolio_returns,
    _sharpe_from_balance_path,
    _verified_returns_series,
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


_UNSET = object()

# A plausible daily portfolio series: four days of small alternating returns.
_DEFAULT_RETURNS = [0.002, -0.001, 0.0015, 0.0005]


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype="float64")


class _StubAnalyzer:
    """An analyzer whose ``returns()`` alias *is* the portfolio series.

    Agreement is the only shape in which a series may be published, so it is the
    default here and tests about anything else do not have to think about the series.
    ``portfolio_series`` stages a disagreement: ``None`` is the empty portfolio series
    that triggers Nautilus' silent per-position fallback, and a list of a different
    length or different values is a mismatch.
    """

    def __init__(
        self,
        *,
        returns_stats: dict | None = None,
        pnls_stats: dict | None = None,
        raise_on_returns: bool = False,
        returns_series: list[float] | None = None,
        portfolio_series: list[float] | None | object = _UNSET,
    ) -> None:
        self._returns_stats = returns_stats
        self._pnls_stats = pnls_stats
        self._raise_on_returns = raise_on_returns
        self._returns_series = _series(
            _DEFAULT_RETURNS if returns_series is None else returns_series
        )
        self._portfolio_series = (
            self._returns_series if portfolio_series is _UNSET else portfolio_series
        )

    def get_performance_stats_returns(self):
        if self._raise_on_returns:
            raise ValueError("returns analyzer exploded")
        return self._returns_stats

    def get_performance_stats_pnls(self):
        return self._pnls_stats

    def get_performance_stats_general(self):
        return {}

    def portfolio_returns(self):
        if self._portfolio_series is None:
            return None
        return _series(self._portfolio_series)

    def returns(self):
        return self._returns_series

    def realized_pnls(self, usd):
        return pd.Series(dtype="float64")


class _PinnedStubAnalyzer:
    """The analyzer nautilus_trader 1.223.0 ships — and the version we pin.

    It has no ``portfolio_returns()``, so ``returns()`` can never be shown to be the
    portfolio series: it is the per-position fallback, always. It is a standalone class
    rather than a ``_StubAnalyzer`` subclass precisely because the attribute must be
    absent for ``hasattr`` to see the real world.
    """

    def __init__(self, *, returns_series: list[float] | None = None) -> None:
        self._returns_series = _series(
            _DEFAULT_RETURNS if returns_series is None else returns_series
        )

    def get_performance_stats_returns(self):
        return None

    def get_performance_stats_pnls(self):
        return None

    def get_performance_stats_general(self):
        return {}

    def returns(self):
        return self._returns_series

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
    missing: list[str] | None = None,
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
        missing=list(missing or []),
        status=status,
        message=f"({symbol})",
    )


# ---------------------------------------------------------------------------
# _extract_pnl
# ---------------------------------------------------------------------------


def _account_report(rows: list[dict], *, day_gap: float = 1.0) -> pd.DataFrame:
    """Account report shaped like the real one: one row per day, unnamed DatetimeIndex.

    The real ``generate_account_report()`` frame carries an unnamed UTC DatetimeIndex,
    which is what ``_account_timestamps`` has to resolve without a column name.
    """
    index = pd.DatetimeIndex(
        [
            pd.Timestamp("2024-01-02", tz="UTC") + pd.Timedelta(days=day_gap * i)
            for i in range(len(rows))
        ],
    )
    return pd.DataFrame(rows, index=index)


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
# Balance path: the single source of truth for Sharpe and max drawdown
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBalancePath:
    def test_none_report_has_no_metrics(self) -> None:
        assert _balance_path_metrics(None) == {"sharpe": None, "max_dd": None}

    def test_empty_report_has_no_metrics(self) -> None:
        assert _balance_path_metrics(pd.DataFrame()) == {"sharpe": None, "max_dd": None}

    def test_unparseable_balance_has_no_metrics(self) -> None:
        report = _account_report([{"total": "not-a-number"}])
        assert _balance_path_metrics(report) == {"sharpe": None, "max_dd": None}

    def test_total_takes_precedence_over_balance_and_equity(self) -> None:
        report = _account_report(
            [{"total": 1_000_000.0, "balance": 800_000.0, "equity": 700_000.0}],
        )
        balances, _ = _account_balance_path(report)
        assert balances == [1_000_000.0]

    def test_balance_used_when_total_absent(self) -> None:
        report = _account_report([{"balance": 900_000.0}, {"balance": 950_000.0}])
        balances, _ = _account_balance_path(report)
        assert balances == [900_000.0, 950_000.0]

    def test_string_balance_with_currency_suffix_is_parsed(self) -> None:
        report = _account_report([{"total": "1000000.00 USD"}, {"total": "1050000.00 USD"}])
        balances, _ = _account_balance_path(report)
        assert balances == [1_000_000.0, 1_050_000.0]

    def test_unnamed_datetime_index_supplies_timestamps(self) -> None:
        """The real report index is unnamed, so it must be read from pandas."""
        report = _account_report(
            [{"total": 1_000_000.0}, {"total": 1_100_000.0}, {"total": 1_200_000.0}],
        )
        _, seconds = _account_balance_path(report)
        assert seconds is not None
        assert len(seconds) == 3
        assert seconds[1] - seconds[0] == pytest.approx(86400.0)

    def test_named_index_is_found_as_a_column(self) -> None:
        report = _account_report(
            [{"total": 1_000_000.0}, {"total": 1_100_000.0}, {"total": 1_200_000.0}],
        )
        report.index.name = "ts_event"
        balances, seconds = _account_balance_path(report)
        assert len(balances) == 3
        assert seconds is not None
        assert seconds[-1] - seconds[0] == pytest.approx(2 * 86400.0)

    def test_range_index_leaves_sharpe_none_but_keeps_drawdown(self) -> None:
        """A bare RangeIndex has no elapsed time, so it cannot be annualised."""
        report = pd.DataFrame([{"total": 1_000_000.0}, {"total": 950_000.0}])
        metrics = _balance_path_metrics(report)
        assert metrics["sharpe"] is None
        assert metrics["max_dd"] == pytest.approx(-5.0)

    def test_fewer_than_two_returns_has_no_sharpe(self) -> None:
        assert _sharpe_from_balance_path([1_000_000.0], None) is None
        assert _sharpe_from_balance_path([1_000_000.0, 1_100_000.0], None) is None

    def test_zero_stdev_has_no_sharpe(self) -> None:
        seconds = [0.0, 86400.0, 2 * 86400.0]
        assert _sharpe_from_balance_path([1_000_000.0, 1_000_000.0, 1_000_000.0], seconds) is None

    def test_sharpe_is_annualised_by_observation_count_over_years(self) -> None:
        balances = [1_000_000.0, 1_010_000.0, 1_000_000.0, 1_040_000.0]
        seconds = [float(i * 86400) for i in range(len(balances))]
        returns = [(b - a) / a for a, b in zip(balances, balances[1:])]
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        years = (seconds[-1] - seconds[0]) / (365.25 * 86400.0)
        expected = mean / variance**0.5 * (len(returns) / years) ** 0.5
        assert _sharpe_from_balance_path(balances, seconds) == pytest.approx(expected)

    def test_flat_path_has_no_drawdown(self) -> None:
        assert _max_drawdown_from_balance_path([]) is None
        assert _max_drawdown_from_balance_path([1_000_000.0]) == pytest.approx(0.0)
        assert _max_drawdown_from_balance_path([1_000_000.0, 1_000_000.0]) == pytest.approx(0.0)

    def test_drawdown_is_worst_peak_to_trough(self) -> None:
        balances = [1_000_000.0, 1_100_000.0, 880_000.0, 1_050_000.0]
        assert _max_drawdown_from_balance_path(balances) == pytest.approx(-20.0)

    def test_drawdown_is_never_milder_than_the_end_state_loss(self) -> None:
        """Drawdown must be at least as bad as the final loss.

        This is the invariant that makes a -76% drawdown beside a -3.1% return
        impossible: the final balance sits inside the peak-to-trough window, so the
        worst drawdown can never be milder than where the account ended up.
        """
        balances = [1_000_000.0, 1_200_000.0, 969_000.0, 950_000.0]
        drawdown = _max_drawdown_from_balance_path(balances)
        total_return_pct = (balances[-1] - balances[0]) / balances[0] * 100.0
        assert drawdown <= total_return_pct + 1e-9

    def test_drawdown_covers_an_interior_trough_the_end_state_misses(self) -> None:
        """A trough below the end is still drawdown, even with a peak at the start.

        This is why the unconditional ``|dd| <= |total_return_pct|`` form is wrong:
        here the peak IS the starting balance and the drawdown is legitimately worse
        (-5.1%) than the start-to-end loss (-3.1%), the same shape as the AAPL golden row.
        """
        balances = [1_000_000.0, 949_000.0, 969_000.0]
        drawdown = _max_drawdown_from_balance_path(balances)
        total_return_pct = (balances[-1] - balances[0]) / balances[0] * 100.0
        assert drawdown == pytest.approx(-5.1)
        assert drawdown <= total_return_pct + 1e-9
        assert abs(drawdown) > abs(total_return_pct)


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

    def test_analyzer_exception_is_partial_but_balance_path_still_feeds_drawdown(self) -> None:
        analyzer = _StubAnalyzer(returns_stats=None, pnls_stats=None, raise_on_returns=True)
        engine = _StubEngine(
            analyzer,
            _account_report([{"total": 1_000_000.0}, {"total": 1_050_000.0}]),
        )
        with _patched_single_run(engine):
            result = run_nautilus_backtest(strategy_name="s", symbols=["BTC"], data_path="BTC.csv")
        assert result is not None
        assert result.status == "partial"
        assert result.total_pnl == pytest.approx(50_000.0)
        assert result.sharpe_ratio is None
        assert result.max_drawdown_pct == pytest.approx(0.0)
        assert "sharpe_ratio" in result.message
        assert "returns analyzer exploded" in result.message

    def test_analyzer_stats_never_feed_sharpe_or_drawdown(self) -> None:
        """The analyzer's own keys are ignored: both metrics come from the balance path."""
        analyzer = _StubAnalyzer(
            returns_stats={"Sortino Ratio": 0.5, "Sharpe Ratio (252 days)": 99.0},
            pnls_stats={"Max Drawdown %": -7.0},
        )
        engine = _StubEngine(
            analyzer,
            _account_report(
                [{"total": 1_000_000.0}, {"total": 900_000.0}, {"total": 1_100_000.0}],
            ),
        )
        with _patched_single_run(engine):
            result = run_nautilus_backtest(strategy_name="s", symbols=["BTC"], data_path="BTC.csv")
        assert result is not None
        assert result.status == "ok"
        assert result.total_pnl == pytest.approx(100_000.0)
        assert result.sharpe_ratio is not None
        assert result.sharpe_ratio != pytest.approx(99.0)
        assert result.max_drawdown_pct == pytest.approx(-10.0)

    def test_unparseable_perf_stats_is_partial(self) -> None:
        analyzer = _StubAnalyzer(
            returns_stats={"Sharpe Ratio (252 days)": "n/a"},
            pnls_stats={"Max Drawdown %": "n/a"},
        )
        engine = _StubEngine(
            analyzer,
            _account_report([{"total": 1_000_000.0}, {"total": 1_100_000.0}]),
        )
        with _patched_single_run(engine):
            result = run_nautilus_backtest(strategy_name="s", symbols=["BTC"], data_path="BTC.csv")
        assert result is not None
        assert result.status == "partial"
        assert "sharpe_ratio" in result.message
        assert result.sharpe_ratio is None
        assert result.max_drawdown_pct == pytest.approx(0.0)

    def test_healthy_run_stays_ok(self) -> None:
        analyzer = _StubAnalyzer(
            returns_stats={"Sharpe Ratio (252 days)": 1.5},
            pnls_stats={"Max Drawdown %": -8.0},
        )
        engine = _StubEngine(
            analyzer,
            _account_report(
                [{"total": 1_000_000.0}, {"total": 900_000.0}, {"total": 1_200_000.0}],
            ),
        )
        with _patched_single_run(engine):
            result = run_nautilus_backtest(strategy_name="s", symbols=["BTC"], data_path="BTC.csv")
        assert result is not None
        assert result.status == "ok"
        assert result.total_pnl == pytest.approx(200_000.0)
        assert result.sharpe_ratio is not None
        assert result.max_drawdown_pct == pytest.approx(-10.0)

    def test_single_balance_row_has_no_sharpe(self) -> None:
        """One balance row is not a return series, so the Sharpe stays None."""
        analyzer = _StubAnalyzer(returns_stats={"Sharpe Ratio (252 days)": 1.5})
        engine = _StubEngine(analyzer, _account_report([{"total": 1_200_000.0}]))
        with _patched_single_run(engine):
            result = run_nautilus_backtest(strategy_name="s", symbols=["BTC"], data_path="BTC.csv")
        assert result is not None
        assert result.sharpe_ratio is None
        assert result.status == "partial"
        assert "sharpe_ratio" in result.message
        assert result.max_drawdown_pct == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# The returns series is verified, never trusted
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVerifiedReturnsSeries:
    """``analyzer.returns()`` is an alias, and an alias can point at the wrong series.

    Where Nautilus keeps ``_returns`` and ``_portfolio_returns`` in sync it does so
    silently: when the portfolio series comes back empty the alias is repointed at the
    per-position returns and nothing says so. Those per-position returns are what
    ``charts/equity.py`` then compounds as ``(1 + r).cum_prod() * initial_balance``
    under a ``Daily Equity`` label, which is how a -3% run once drew -78%.
    """

    def _run(self, analyzer) -> BacktestResult:
        engine = _StubEngine(
            analyzer,
            _account_report(
                [{"total": 1_000_000.0}, {"total": 1_100_000.0}, {"total": 1_050_000.0}],
            ),
        )
        with _patched_single_run(engine):
            result = run_nautilus_backtest(
                strategy_name="s",
                symbols=["BTC"],
                data_path="BTC.csv",
            )
        assert result is not None
        return result

    def test_matching_alias_is_published(self) -> None:
        series, refusal = _verified_returns_series(_StubAnalyzer())
        assert refusal is None
        assert list(series) == _DEFAULT_RETURNS

    def test_no_portfolio_returns_to_confirm_against_is_refused(self) -> None:
        """The pinned 1.223.0 analyzer offers nothing to compare the alias to."""
        series, refusal = _verified_returns_series(_PinnedStubAnalyzer())
        assert series is None
        assert "portfolio_returns" in refusal

    def test_empty_portfolio_series_means_the_alias_fell_back(self) -> None:
        series, refusal = _verified_returns_series(_StubAnalyzer(portfolio_series=None))
        assert series is None
        assert "per-position fallback" in refusal

    def test_values_that_differ_are_refused(self) -> None:
        """Same length, same shape, one number off — still not the portfolio series."""
        series, refusal = _verified_returns_series(
            _StubAnalyzer(portfolio_series=[0.002, -0.001, 0.0015, -0.0005]),
        )
        assert series is None
        assert "does not match" in refusal

    def test_a_different_length_is_refused(self) -> None:
        series, refusal = _verified_returns_series(
            _StubAnalyzer(portfolio_series=[0.002, -0.001, 0.0015]),
        )
        assert series is None
        assert "4 values against 3" in refusal

    def test_nan_in_both_series_still_counts_as_a_match(self) -> None:
        assert _series_is_portfolio_returns(
            _series([0.001, float("nan")]), _series([0.001, float("nan")])
        )

    def test_unparseable_values_are_refused_rather_than_guessed(self) -> None:
        assert _series_is_portfolio_returns(_series([0.001]), ["not-a-number"]) is False

    def test_unverifiable_series_is_withheld_and_the_result_goes_partial(self) -> None:
        """The alias fell back, so the tearsheet draws nothing: a blank chart, not a wrong curve."""
        engine = _StubEngine(
            _PinnedStubAnalyzer(),
            _account_report(
                [{"total": 1_000_000.0}, {"total": 1_100_000.0}, {"total": 1_050_000.0}],
            ),
        )
        with (
            _patched_single_run(engine),
            patch("digiquant.tearsheet.create_tearsheet") as create_tearsheet,
        ):
            result = run_nautilus_backtest(
                strategy_name="s",
                symbols=["BTC"],
                data_path="BTC.csv",
                tearsheet_path="withheld-series.html",
            )
        assert result is not None
        assert create_tearsheet.call_args.kwargs["returns_series"] is None
        assert result.status == "partial"
        assert result.missing == [RETURNS_SERIES_MISSING]
        assert RETURNS_SERIES_MISSING in result.message
        # The metrics are untouched by the refusal — they come from the balance path.
        assert result.total_pnl == pytest.approx(50_000.0)
        assert result.sharpe_ratio is not None
        assert result.max_drawdown_pct == pytest.approx(-4.545454545454546)

    def test_confirmed_series_reaches_the_tearsheet_and_stays_ok(self) -> None:
        analyzer = _StubAnalyzer()
        engine = _StubEngine(
            analyzer,
            _account_report(
                [{"total": 1_000_000.0}, {"total": 1_100_000.0}, {"total": 1_050_000.0}],
            ),
        )
        with (
            _patched_single_run(engine),
            patch("digiquant.tearsheet.create_tearsheet") as create_tearsheet,
        ):
            result = run_nautilus_backtest(
                strategy_name="s",
                symbols=["BTC"],
                data_path="BTC.csv",
                tearsheet_path="verified-series.html",
            )
        assert result is not None
        assert list(create_tearsheet.call_args.kwargs["returns_series"]) == _DEFAULT_RETURNS
        assert result.status == "ok"
        assert result.missing == []


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

    def test_partial_symbol_is_excluded_from_aggregates_and_noted(self) -> None:
        result = self._run(
            {
                "AAA": _symbol_result("AAA", pnl=100.0),
                "BBB": _symbol_result("BBB", status="partial", pnl=999.0),
            }
        )
        assert result is not None
        assert result.status == "partial"
        assert result.per_symbol_pnl == pytest.approx({"AAA": 100.0})
        assert result.total_pnl == pytest.approx(100.0)
        assert "BBB" in result.message
        assert "excluded" in result.message.lower()

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

    def test_series_only_partial_stays_in_the_aggregates_and_is_named(self) -> None:
        """A withheld chart series costs a symbol neither its PnL nor its place.

        The aggregates read PnL, return, Sharpe, drawdown and trades — never a series —
        and the refusal fires on every run under the pinned nautilus_trader, so
        excluding on it here would return no aggregate at all.
        """
        result = self._run(
            {
                "AAA": _symbol_result(
                    "AAA",
                    status="partial",
                    pnl=100.0,
                    missing=[RETURNS_SERIES_MISSING],
                ),
                "BBB": _symbol_result("BBB", pnl=-50.0),
            }
        )
        assert result is not None
        assert result.per_symbol_pnl == pytest.approx({"AAA": 100.0, "BBB": -50.0})
        assert result.total_pnl == pytest.approx(25.0)
        assert result.status == "partial"
        assert result.missing == [f"{RETURNS_SERIES_MISSING} (1/2 symbols)"]
        assert f"{RETURNS_SERIES_MISSING} (1/2 symbols)" in result.message
        assert "excluded" not in result.message.lower()

    def test_partial_that_is_also_missing_a_metric_is_still_excluded(self) -> None:
        """The exemption is the series and nothing else."""
        result = self._run(
            {
                "AAA": _symbol_result(
                    "AAA",
                    status="partial",
                    pnl=100.0,
                    missing=[RETURNS_SERIES_MISSING, "sharpe_ratio"],
                ),
                "BBB": _symbol_result("BBB", pnl=-50.0),
            }
        )
        assert result is not None
        assert result.per_symbol_pnl == pytest.approx({"BBB": -50.0})
        assert result.status == "partial"
        assert "AAA" in result.message
        assert "excluded" in result.message.lower()

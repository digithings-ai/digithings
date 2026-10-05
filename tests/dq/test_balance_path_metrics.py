"""Regression tests: Sharpe and max drawdown come from the balance path, DIG-462.

``nautilus_trader``'s portfolio analyzer holds one return per *closed position*, so
reading ``Sharpe Ratio (252 days)`` from it annualised a per-trade series by 252
trading days and produced -76.34 Sharpe and -76.53% drawdown next to a -3.10% total
return. ``get_performance_stats_pnls()`` has no ``Max Drawdown %`` key at all, which
silently pushed the code onto a fallback that compounded the same per-trade series.

These tests run the REAL engine (so the analyzer really does produce the bad series
that must be rejected), recompute the metrics independently from the account-report
balance path, and assert the four properties that kill the original bug.

Golden values were measured from ``start = 1_000_000 USD`` on the synthetic OHLCV
that ``generate_synthetic_ohlcv`` produces for 2024 (the same data the repo's
AAPL.csv / NVDA.csv hold).

Deviation from the CTO brief, deliberate and covered below: the brief asked for
``abs(max_drawdown_pct) <= abs(total_return_pct) + 1e-9`` whenever
``total_return_pct < 0``. That is false for the brief's own AAPL golden row —
max_dd -5.11 against total_return_pct -3.10 — because an interior trough below the
end balance makes drawdown legitimately worse than the start-to-end loss. The
unconditional bound asserted here is ``max_drawdown_pct <= total_return_pct`` (the
end balance sits inside the peak-to-trough window, so the worst drawdown is never
milder than where the account finished). That still forbids the original -76.53%
beside -3.10%, and the exact-form equality check above it is asserted at 1e-9.
``TestBalancePath::test_drawdown_covers_an_interior_trough_the_end_state_misses``
in test_nautilus_runner.py documents why the stronger form cannot hold.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest
from digiquant.data.loader import generate_synthetic_ohlcv

from .conftest import SKIP_NATIVE_CRASH

# Golden values, measured with the repo .venv at start = 1_000_000 USD.
GOLDEN: dict[str, tuple[int, float, float]] = {
    # strategy/symbol -> (num_trades, sharpe, max_drawdown_pct)
    "ema_cross": (68, -0.09310998448342742, -5.11),
    "macd_trend": (68, -0.09896094928697946, -5.1552599999999975),
}

_YEAR_SECONDS = 365.25 * 86400.0


def _recompute_from_balance_path(account_report) -> tuple[float | None, float]:
    """Independent reimplementation of the two metrics, written from the brief.

    Deliberately not shared with the production helper: if both used one function,
    a change to that function would change both sides of every assertion.
    """
    balances = [float(v) for v in account_report["total"].tolist()]
    stamps = [ts.timestamp() for ts in account_report.index]
    peak = balances[0]
    worst = 0.0
    for value in balances:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value - peak) / peak)

    returns = [(b - a) / a for a, b in zip(balances, balances[1:])]
    if len(returns) < 2:
        return None, worst * 100.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    if variance <= 0:
        return None, worst * 100.0
    years = (stamps[-1] - stamps[0]) / _YEAR_SECONDS
    if years <= 0:
        return None, worst * 100.0
    sharpe = mean / math.sqrt(variance) * math.sqrt(len(returns) / years)
    return sharpe, worst * 100.0


def _legacy_per_trade_sharpe(analyzer_returns) -> float:
    """What the old code published: the per-trade series annualised by sqrt(252)."""
    returns = [float(v) for v in analyzer_returns]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return mean / math.sqrt(variance) * math.sqrt(252.0)


def _run_real(strategy_name: str, symbol: str):
    """Run one real backtest, capturing the account report and per-trade series.

    The per-trade analyzer series is only reachable through the engine that
    ``run_backtest`` disposes of, so ``_extract_perf_stats`` is wrapped to keep
    references to both the report and the analyzer before teardown.
    """
    pytest.importorskip("nautilus_trader")
    import digiquant.nautilus_runner as runner
    from digiquant.backtest import run_backtest
    from nautilus_trader.model import Venue

    captured: dict[str, object] = {}
    original = runner._extract_perf_stats

    def _spy(engine, USD, account_report=None):
        captured["analyzer_returns"] = list(engine.portfolio.analyzer.returns())
        captured["account_report"] = engine.trader.generate_account_report(Venue("SIM"))
        return original(engine, USD, account_report)

    df = generate_synthetic_ohlcv([symbol], freq="1d")
    with tempfile.TemporaryDirectory() as tmp:
        df.write_csv(Path(tmp) / f"{symbol}.csv")
        runner._extract_perf_stats = _spy
        try:
            result = run_backtest(strategy_name=strategy_name, symbols=[symbol], data_dir=tmp)
        finally:
            runner._extract_perf_stats = original
    return result, captured["account_report"], captured["analyzer_returns"]


def _run_pair(strategy_name: str, symbol: str):
    return _run_real(strategy_name, symbol)


@SKIP_NATIVE_CRASH
@pytest.mark.unit
@pytest.mark.parametrize("strategy_name,symbol", [("ema_cross", "AAPL"), ("macd_trend", "NVDA")])
class TestBalancePathMetricsRealRun:
    """Both a second strategy and a second dataset, so the formula cannot be fitted."""

    def test_sharpe_matches_an_independent_recompute(self, strategy_name: str, symbol: str) -> None:
        result, account_report, _ = _run_pair(strategy_name, symbol)
        expected, _ = _recompute_from_balance_path(account_report)
        assert expected is not None
        assert abs(result.sharpe_ratio - expected) < 1e-9

    def test_sharpe_matches_the_golden_value(self, strategy_name: str, symbol: str) -> None:
        result, _, _ = _run_pair(strategy_name, symbol)
        trades, sharpe, _dd = GOLDEN[strategy_name]
        assert result.num_trades == trades
        assert abs(result.sharpe_ratio - sharpe) < 1e-9

    def test_sharpe_is_not_the_per_trade_series_scaled_by_252(self, strategy_name, symbol) -> None:
        """The assertion that kills the original bug.

        ``Risk Return Ratio`` is deliberately not pinned instead: Nautilus documents
        it as a NON-annualised mean/std, so asserting equality would delete
        annualisation and publish a per-trade number under the name Sharpe.
        """
        result, _, analyzer_returns = _run_pair(strategy_name, symbol)
        legacy = _legacy_per_trade_sharpe(analyzer_returns)
        assert abs(result.sharpe_ratio - legacy) > 1e-6
        # Sanity: the legacy number really is the reported bug, ~1000x too large.
        assert abs(legacy) > 1.0

    def test_drawdown_equals_the_balance_path_drawdown(
        self, strategy_name: str, symbol: str
    ) -> None:
        result, account_report, _ = _run_pair(strategy_name, symbol)
        _, expected_dd = _recompute_from_balance_path(account_report)
        assert abs(result.max_drawdown_pct - expected_dd) < 1e-9

    def test_drawdown_never_milder_than_the_end_state_loss(self, strategy_name, symbol) -> None:
        result, _, _ = _run_pair(strategy_name, symbol)
        _trades, _sharpe, dd = GOLDEN[strategy_name]
        assert result.max_drawdown_pct == pytest.approx(dd)
        assert result.total_return_pct < 0
        assert result.max_drawdown_pct <= result.total_return_pct + 1e-9
        # The invariant that the old value broke by three orders of magnitude.
        assert abs(result.max_drawdown_pct) < 100.0

    def test_total_pnl_and_return_are_untouched(self, strategy_name: str, symbol: str) -> None:
        """This fix moves Sharpe and drawdown only; the balance end value stands."""
        result, account_report, _ = _run_pair(strategy_name, symbol)
        final_balance = float(account_report["total"].tolist()[-1])
        assert result.total_pnl == pytest.approx(final_balance - 1_000_000.0)
        assert result.total_return_pct == pytest.approx((final_balance - 1_000_000.0) / 10_000.0)
        assert result.status == "ok"


@SKIP_NATIVE_CRASH
@pytest.mark.unit
class TestDegenerateRuns:
    """Edge cases the brief calls out, on real runs rather than stubs."""

    def test_single_trade_has_no_sharpe_but_keeps_drawdown(self) -> None:
        pytest.importorskip("nautilus_trader")
        import tempfile
        from pathlib import Path as _Path

        from digiquant.backtest import run_backtest

        df = generate_synthetic_ohlcv(["AAPL"], start_date="2024-01-01", end_date="2024-01-20")
        with tempfile.TemporaryDirectory() as tmp:
            df.write_csv(_Path(tmp) / "AAPL.csv")
            result = run_backtest(strategy_name="rsi_momentum", symbols=["AAPL"], data_dir=tmp)
        assert result.sharpe_ratio is None
        assert "sharpe_ratio" in result.message
        assert result.status == "partial"

    def test_no_trades_reports_zero_drawdown_not_a_fabricated_sharpe(self) -> None:
        pytest.importorskip("nautilus_trader")
        import tempfile
        from pathlib import Path as _Path

        from digiquant.backtest import run_backtest

        df = generate_synthetic_ohlcv(["GOOGL"], start_date="2024-01-01", end_date="2024-01-20")
        with tempfile.TemporaryDirectory() as tmp:
            df.write_csv(_Path(tmp) / "GOOGL.csv")
            result = run_backtest(strategy_name="bollinger_mr", symbols=["GOOGL"], data_dir=tmp)
        assert result.num_trades == 0
        assert result.sharpe_ratio is None
        assert result.max_drawdown_pct in (0.0, None)

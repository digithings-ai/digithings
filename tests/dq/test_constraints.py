"""Unit tests for satisfies_constraints (optimize.py)."""

from __future__ import annotations

import pytest

from digiquant.models import BacktestResult, OptimizationConstraints
from digiquant.optimize import satisfies_constraints


def _bt(**overrides) -> BacktestResult:
    """Helper: BacktestResult with sensible defaults, 1-year window."""
    defaults = dict(
        run_id="r1",
        strategy_name="s1",
        symbols=["AAPL"],
        start_time="2023-01-01T00:00:00Z",
        end_time="2024-01-01T00:00:00Z",
        total_pnl=1000.0,
        total_return_pct=10.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=-5.0,
        num_trades=50,
        status="ok",
    )
    defaults.update(overrides)
    return BacktestResult(**defaults)


@pytest.mark.unit
class TestSatisfiesConstraints:
    def test_no_constraints_always_true(self) -> None:
        assert satisfies_constraints(_bt(), None) is True

    def test_empty_constraints_always_true(self) -> None:
        assert satisfies_constraints(_bt(), OptimizationConstraints()) is True

    def test_min_trades_passes(self) -> None:
        c = OptimizationConstraints(min_trades=10)
        assert satisfies_constraints(_bt(num_trades=50), c) is True

    def test_min_trades_fails(self) -> None:
        c = OptimizationConstraints(min_trades=100)
        assert satisfies_constraints(_bt(num_trades=50), c) is False

    def test_min_trades_exact_boundary_passes(self) -> None:
        c = OptimizationConstraints(min_trades=50)
        assert satisfies_constraints(_bt(num_trades=50), c) is True

    def test_max_drawdown_passes(self) -> None:
        # Drawdown -5% satisfies constraint max_drawdown_pct=-10% (must be > -10%)
        c = OptimizationConstraints(max_drawdown_pct=-10.0)
        assert satisfies_constraints(_bt(max_drawdown_pct=-5.0), c) is True

    def test_max_drawdown_fails(self) -> None:
        # Drawdown -15% violates max_drawdown_pct=-10% (must be > -10%)
        c = OptimizationConstraints(max_drawdown_pct=-10.0)
        assert satisfies_constraints(_bt(max_drawdown_pct=-15.0), c) is False

    def test_drawdown_none_in_result_skips_check(self) -> None:
        """When bt.max_drawdown_pct is None, constraint is skipped (not rejected)."""
        c = OptimizationConstraints(max_drawdown_pct=-10.0)
        assert satisfies_constraints(_bt(max_drawdown_pct=None), c) is True

    def test_min_sharpe_passes(self) -> None:
        c = OptimizationConstraints(min_sharpe=1.0)
        assert satisfies_constraints(_bt(sharpe_ratio=1.5), c) is True

    def test_min_sharpe_fails(self) -> None:
        c = OptimizationConstraints(min_sharpe=2.0)
        assert satisfies_constraints(_bt(sharpe_ratio=1.5), c) is False

    def test_sharpe_none_in_result_skips_check(self) -> None:
        """When bt.sharpe_ratio is None, min_sharpe constraint is skipped."""
        c = OptimizationConstraints(min_sharpe=2.0)
        assert satisfies_constraints(_bt(sharpe_ratio=None), c) is True

    def test_min_return_pct_passes(self) -> None:
        c = OptimizationConstraints(min_return_pct=5.0)
        assert satisfies_constraints(_bt(total_return_pct=10.0), c) is True

    def test_min_return_pct_fails(self) -> None:
        c = OptimizationConstraints(min_return_pct=15.0)
        assert satisfies_constraints(_bt(total_return_pct=10.0), c) is False

    def test_max_trades_per_year_passes(self) -> None:
        # 50 trades over 1 year = 50/year; cap 100/year passes
        c = OptimizationConstraints(max_trades_per_year=100.0)
        assert satisfies_constraints(_bt(num_trades=50), c) is True

    def test_max_trades_per_year_fails(self) -> None:
        # 200 trades over 1 year = 200/year; cap 100/year fails
        c = OptimizationConstraints(max_trades_per_year=100.0)
        assert satisfies_constraints(_bt(num_trades=200), c) is False

    def test_min_trades_per_year_passes(self) -> None:
        c = OptimizationConstraints(min_trades_per_year=10.0)
        assert satisfies_constraints(_bt(num_trades=50), c) is True

    def test_min_trades_per_year_fails(self) -> None:
        c = OptimizationConstraints(min_trades_per_year=100.0)
        assert satisfies_constraints(_bt(num_trades=5), c) is False

    def test_multiple_constraints_all_pass(self) -> None:
        c = OptimizationConstraints(
            min_trades=10,
            min_sharpe=1.0,
            min_return_pct=5.0,
            max_drawdown_pct=-20.0,
        )
        assert satisfies_constraints(_bt(), c) is True

    def test_multiple_constraints_one_fails(self) -> None:
        c = OptimizationConstraints(
            min_trades=10,
            min_sharpe=3.0,  # Fails: bt sharpe is 1.5
        )
        assert satisfies_constraints(_bt(), c) is False

    def test_bad_timestamp_graceful_fallback(self) -> None:
        """Malformed timestamps fall back to trades_per_year=0 without raising."""
        c = OptimizationConstraints(max_trades_per_year=200.0)
        bt = _bt()
        bt = bt.model_copy(update={"start_time": "not-a-date", "end_time": "also-not"})
        # Should not raise; trades_per_year=0 so max check passes
        result = satisfies_constraints(bt, c)
        assert isinstance(result, bool)

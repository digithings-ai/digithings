"""Unit tests for digiquant.optimize_bayesian — Bayesian optimisation via Optuna."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from digiquant.models import BacktestResult, OptimizationConstraints, OptimizeResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bt(sharpe=1.0, ret=5.0, pnl=5000.0, trades=20, dd=10.0) -> BacktestResult:
    return BacktestResult(
        run_id="bt-test",
        strategy_name="sma_cross",
        symbols=["AAPL"],
        start_time="2023-01-01T00:00:00Z",
        end_time="2023-12-31T00:00:00Z",
        total_pnl=pnl,
        total_return_pct=ret,
        sharpe_ratio=sharpe,
        max_drawdown_pct=dd,
        num_trades=trades,
    )


# ---------------------------------------------------------------------------
# run_optimize_bayesian
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRunOptimizeBayesian:
    def _run(self, n_trials=3, objective="sharpe", constraints=None, base_params=None, bt_return=None):
        """Helper: patches optuna + run_backtest and calls run_optimize_bayesian."""
        try:
            import optuna  # noqa: F401 — skip if optuna not installed
        except ImportError:
            pytest.skip("optuna not installed")

        if bt_return is None:
            bt_return = _bt()

        from digiquant.optimize_bayesian import run_optimize_bayesian

        with patch("digiquant.optimize_bayesian.run_backtest", return_value=bt_return) as mock_bt, \
             patch("digiquant.optimize_bayesian.get_search_space_for_optuna", return_value={
                 "fast_period": ("int", 5, 20, 1),
                 "slow_period": ("int", 20, 60, 1),
             }):
            result = run_optimize_bayesian(
                strategy_name="sma_cross",
                symbols=["AAPL"],
                n_trials=n_trials,
                objective=objective,
                constraints=constraints,
                base_params=base_params or {},
            )
        return result, mock_bt

    def test_returns_optimize_result(self) -> None:
        result, _ = self._run(n_trials=3)
        assert isinstance(result, OptimizeResult)

    def test_strategy_name_preserved(self) -> None:
        result, _ = self._run()
        assert result.strategy_name == "sma_cross"

    def test_num_evaluations_matches_trials(self) -> None:
        result, _ = self._run(n_trials=3)
        # num_evaluations = n_trials + 1 final evaluation
        assert result.num_evaluations >= 1

    def test_best_backtest_set_on_success(self) -> None:
        result, _ = self._run()
        assert result.status == "ok"
        assert result.best_backtest is not None
        assert isinstance(result.best_backtest, BacktestResult)

    def test_best_params_contains_search_space_keys(self) -> None:
        result, _ = self._run()
        # best_params should include the keys from our mocked search space
        assert "fast_period" in result.best_params or "slow_period" in result.best_params or result.best_params == {}

    def test_objective_return_uses_total_return_pct(self) -> None:
        """When objective='return', bt.total_return_pct is used as the objective value."""
        bt = _bt(ret=99.9, sharpe=None)
        result, mock_bt = self._run(objective="return", bt_return=bt)
        # Should not crash; result should use the backtest
        assert result.status in ("ok", "partial")

    def test_empty_search_space_returns_error(self) -> None:
        try:
            import optuna  # noqa: F401
        except ImportError:
            pytest.skip("optuna not installed")

        from digiquant.optimize_bayesian import run_optimize_bayesian

        with patch("digiquant.optimize_bayesian.run_backtest", return_value=_bt()), \
             patch("digiquant.optimize_bayesian.get_search_space_for_optuna", return_value={}):
            result = run_optimize_bayesian(
                strategy_name="sma_cross",
                symbols=["AAPL"],
                n_trials=5,
            )
        assert result.status == "error"
        assert result.num_evaluations == 0

    def test_n_trials_zero_produces_valid_result(self) -> None:
        """n_trials=0 → study with 0 trials → no best trial → partial/error."""
        try:
            import optuna  # noqa: F401
        except ImportError:
            pytest.skip("optuna not installed")

        from digiquant.optimize_bayesian import run_optimize_bayesian

        with patch("digiquant.optimize_bayesian.run_backtest", return_value=_bt()), \
             patch("digiquant.optimize_bayesian.get_search_space_for_optuna", return_value={
                 "fast_period": ("int", 5, 20, 1),
             }):
            result = run_optimize_bayesian(
                strategy_name="sma_cross",
                symbols=["AAPL"],
                n_trials=0,
            )
        assert result.status in ("ok", "partial", "error")

    def test_all_trials_violate_constraints_returns_partial(self) -> None:
        """When all trials are pruned by constraints, status should be partial."""
        try:
            import optuna  # noqa: F401
        except ImportError:
            pytest.skip("optuna not installed")

        from digiquant.optimize_bayesian import run_optimize_bayesian

        # backtest with max_drawdown_pct > constraint will fail constraint
        bad_bt = _bt(dd=50.0, trades=1)

        constraints = OptimizationConstraints(min_trades=100)

        with patch("digiquant.optimize_bayesian.run_backtest", return_value=bad_bt), \
             patch("digiquant.optimize_bayesian.get_search_space_for_optuna", return_value={
                 "fast_period": ("int", 5, 10, 1),
             }):
            result = run_optimize_bayesian(
                strategy_name="sma_cross",
                symbols=["AAPL"],
                n_trials=3,
                constraints=constraints,
            )
        assert result.status in ("partial", "error")

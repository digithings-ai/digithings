"""Parameter sweep: multiple backtests over a grid. Phase 2 (VectorBT Pro later)."""

from __future__ import annotations

from digiquant.backtest import run_backtest
from digiquant.models import BacktestResult


def run_sweep(
    strategy_name: str = "mean_reversion_tech",
    symbols: list[str] | None = None,
    param_grid: list[dict[str, float | int | str]] | None = None,
) -> list[BacktestResult]:
    """
    Run backtest for each param set in param_grid. Phase 2: uses run_backtest in a loop.
    VectorBT Pro integration for fast vectorized sweeps in a later phase.
    """
    symbols = symbols or ["AAPL", "MSFT", "GOOGL"]
    param_grid = param_grid or [{}]
    results: list[BacktestResult] = []
    for _ in param_grid:
        # Params not yet passed to backtest; same result per cell for now
        bt = run_backtest(strategy_name=strategy_name, symbols=symbols)
        results.append(bt)
    return results

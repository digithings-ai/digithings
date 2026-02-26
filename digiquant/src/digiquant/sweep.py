"""Parameter sweep: multiple backtests over a grid. Phase 2 (VectorBT Pro later)."""

from __future__ import annotations

from pathlib import Path

from digiquant.backtest import run_backtest
from digiquant.models import BacktestResult


def run_sweep(
    strategy_name: str,
    symbols: list[str],
    param_grid: list[dict[str, float | int | str]],
    data_path: str | Path | None = None,
    data_dir: str | Path | None = None,
) -> list[BacktestResult]:
    """
    Run backtest for each param set in param_grid. Requires strategy_name, symbols, param_grid, data_path or data_dir.
    """
    if not symbols:
        raise ValueError("symbols required (non-empty list).")
    if not param_grid:
        raise ValueError("param_grid required (non-empty list).")
    results: list[BacktestResult] = []
    for params in param_grid:
        bt = run_backtest(
            strategy_name=strategy_name,
            symbols=symbols,
            data_path=data_path,
            data_dir=data_dir,
            strategy_params=params or None,
        )
        results.append(bt)
    return results

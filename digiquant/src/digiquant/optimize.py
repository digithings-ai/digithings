"""Parameter optimization: grid over backtest runs. Phase 2."""

from __future__ import annotations

import uuid

from digiquant.backtest import run_backtest
from digiquant.models import BacktestResult, OptimizeResult


def run_optimize(
    strategy_name: str = "mean_reversion_tech",
    symbols: list[str] | None = None,
    param_grid: list[dict[str, float | int | str]] | None = None,
    objective: str = "sharpe",
) -> OptimizeResult:
    """
    Run a small grid over param sets; each set runs a backtest. Returns best by objective.
    Phase 2: param_grid is optional; when empty or None, runs a single backtest and returns it as "best".
    """
    symbols = symbols or ["AAPL", "MSFT", "GOOGL"]
    param_grid = param_grid or [{}]
    run_id = f"optimize-{uuid.uuid4().hex[:8]}"
    results: list[tuple[dict[str, float | int | str], BacktestResult]] = []

    for params in param_grid:
        # Phase 2: backtest doesn't accept params yet; we run same backtest per "param set"
        # so optimization is a no-op except we run N backtests and pick best
        bt = run_backtest(strategy_name=strategy_name, symbols=symbols)
        results.append((params, bt))

    if not results:
        return OptimizeResult(
            run_id=run_id,
            strategy_name=strategy_name,
            symbols=symbols,
            best_params={},
            best_backtest=None,
            num_evaluations=0,
            status="error",
            message="No evaluations run.",
        )

    def score(bt: BacktestResult) -> float:
        if objective == "sharpe" and bt.sharpe_ratio is not None:
            return bt.sharpe_ratio
        if objective == "return":
            return bt.total_return_pct
        return bt.total_pnl

    best_params, best_backtest = max(results, key=lambda x: score(x[1]))

    return OptimizeResult(
        run_id=run_id,
        strategy_name=strategy_name,
        symbols=symbols,
        best_params=best_params,
        best_backtest=best_backtest,
        num_evaluations=len(results),
        status="ok",
        message="Phase 2 grid optimization (param_grid applied in future).",
    )

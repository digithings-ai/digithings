"""Bayesian optimization via Optuna. Optional: pip install digiquant[optimize]."""

from __future__ import annotations

import uuid
from pathlib import Path

from digiquant.backtest import run_backtest
from digiquant.models import BacktestResult, OptimizeResult, OptimizationConstraints
from digiquant.strategy_specs import get_search_space_for_optuna


def run_optimize_bayesian(
    strategy_name: str,
    symbols: list[str],
    data_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    n_trials: int = 50,
    objective: str = "sharpe",
    constraints: OptimizationConstraints | None = None,
    base_params: dict[str, float | int | str] | None = None,
) -> OptimizeResult:
    """
    Run Bayesian optimization using Optuna.
    Suggests params from strategy search space; returns -inf when constraints fail.
    """
    import optuna

    base = dict(base_params or {})
    space = get_search_space_for_optuna(strategy_name, base_params=base)
    run_id = f"optimize-{uuid.uuid4().hex[:8]}"

    def _objective(trial: optuna.Trial) -> float:
        params = dict(base)
        for name, (suggest_type, lo, hi, step) in space.items():
            if suggest_type == "int":
                params[name] = trial.suggest_int(name, lo, hi, step=step)
            else:
                params[name] = trial.suggest_float(name, lo, hi, step=step)

        bt = run_backtest(
            strategy_name=strategy_name,
            symbols=symbols,
            data_path=data_path,
            data_dir=data_dir,
            strategy_params=params,
        )

        if not _satisfies(bt, constraints):
            raise optuna.TrialPruned()

        if objective == "sharpe":
            if bt.sharpe_ratio is None:
                raise optuna.TrialPruned()  # Exclude trials with invalid Sharpe (e.g. too few trades)
            return bt.sharpe_ratio
        if objective == "return":
            return bt.total_return_pct
        return bt.total_pnl

    def _satisfies(bt: BacktestResult, c: OptimizationConstraints | None) -> bool:
        if c is None:
            return True
        if c.min_trades is not None and bt.num_trades < c.min_trades:
            return False
        if c.max_drawdown_pct is not None and bt.max_drawdown_pct is not None:
            if bt.max_drawdown_pct < c.max_drawdown_pct:
                return False
        if c.min_sharpe is not None and bt.sharpe_ratio is not None:
            if bt.sharpe_ratio < c.min_sharpe:
                return False
        if c.min_return_pct is not None and bt.total_return_pct < c.min_return_pct:
            return False
        try:
            from datetime import datetime

            start = datetime.fromisoformat(bt.start_time.replace("Z", "+00:00"))
            end = datetime.fromisoformat(bt.end_time.replace("Z", "+00:00"))
            days = (end - start).total_seconds() / 86400
            years = days / 365.25 if days > 0 else 0
            trades_per_year = bt.num_trades / years if years > 0 else 0
        except Exception:
            trades_per_year = 0.0
        if c.max_trades_per_year is not None and trades_per_year > c.max_trades_per_year:
            return False
        if c.min_trades_per_year is not None and trades_per_year < c.min_trades_per_year:
            return False
        return True

    if not space:
        return OptimizeResult(
            run_id=run_id,
            strategy_name=strategy_name,
            symbols=symbols,
            best_params=base,
            best_backtest=None,
            num_evaluations=0,
            status="error",
            message="No tunable params in search space for this strategy.",
        )

    study = optuna.create_study(direction="maximize")
    study.optimize(_objective, n_trials=n_trials, show_progress_bar=False)

    if study.best_trial is None:
        return OptimizeResult(
            run_id=run_id,
            strategy_name=strategy_name,
            symbols=symbols,
            best_params=base,
            best_backtest=None,
            num_evaluations=len(study.trials),
            status="partial",
            message="No trial passed constraints.",
        )

    best_params = dict(base, **study.best_trial.params)
    bt = run_backtest(
        strategy_name=strategy_name,
        symbols=symbols,
        data_path=data_path,
        data_dir=data_dir,
        strategy_params=best_params,
    )

    return OptimizeResult(
        run_id=run_id,
        strategy_name=strategy_name,
        symbols=symbols,
        best_params=best_params,
        best_backtest=bt,
        num_evaluations=len(study.trials),
        status="ok",
        message=f"Bayesian optimization ({len(study.trials)} trials).",
    )

"""Bayesian optimization via Optuna. Optional: pip install digiquant[optimize]."""

from __future__ import annotations

import uuid
from pathlib import Path

from digiquant.backtest import run_backtest
from digiquant.constraints import satisfies_constraints
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

        if not satisfies_constraints(bt, constraints):
            raise optuna.TrialPruned()

        if objective == "sharpe":
            if bt.sharpe_ratio is None:
                raise optuna.TrialPruned()  # Exclude trials with invalid Sharpe (e.g. too few trades)
            return bt.sharpe_ratio
        if objective == "return":
            return bt.total_return_pct
        return bt.total_pnl

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

    # Optuna raises ValueError (not returns None) when no trials completed.
    try:
        best_trial = study.best_trial
    except ValueError:
        best_trial = None

    if best_trial is None:
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

    best_params = dict(base, **best_trial.params)
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

"""Parameter optimization: grid, random, and Bayesian over backtest runs. Phase 2."""

from __future__ import annotations

import itertools
import uuid
from datetime import datetime
from pathlib import Path

from digiquant.backtest import run_backtest
from digiquant.models import BacktestResult, OptimizeResult, OptimizationConstraints
from digiquant.strategy_specs import infer_param_grid, sample_random_params


def satisfies_constraints(
    bt: BacktestResult,
    constraints: OptimizationConstraints | None,
) -> bool:
    """Return True if backtest result satisfies all constraints."""
    if constraints is None:
        return True

    if constraints.min_trades is not None and bt.num_trades < constraints.min_trades:
        return False
    if constraints.max_drawdown_pct is not None and bt.max_drawdown_pct is not None:
        if bt.max_drawdown_pct < constraints.max_drawdown_pct:
            return False
    if constraints.min_sharpe is not None and bt.sharpe_ratio is not None:
        if bt.sharpe_ratio < constraints.min_sharpe:
            return False
    if constraints.min_return_pct is not None:
        if bt.total_return_pct < constraints.min_return_pct:
            return False

    # trades_per_year from backtest duration
    try:
        start = datetime.fromisoformat(bt.start_time.replace("Z", "+00:00"))
        end = datetime.fromisoformat(bt.end_time.replace("Z", "+00:00"))
        days = (end - start).total_seconds() / 86400
        years = days / 365.25 if days > 0 else 0
        trades_per_year = bt.num_trades / years if years > 0 else 0
    except Exception:
        trades_per_year = 0.0

    if constraints.max_trades_per_year is not None and trades_per_year > constraints.max_trades_per_year:
        return False
    if constraints.min_trades_per_year is not None and trades_per_year < constraints.min_trades_per_year:
        return False
    return True


def generate_param_grid(
    param_specs: dict[str, dict | tuple],
    base_params: dict[str, float | int | str] | None = None,
) -> list[dict[str, float | int | str]]:
    """
    Generate a param grid from ranges/steps. Nautilus has no built-in grid utils.

    Each param spec can be:
    - (min, max, step): linear range, e.g. (10, 30, 5) -> [10, 15, 20, 25, 30]
    - {"min": n, "max": m, "step": s}: same as tuple
    - {"default": d, "step": s, "num_steps": n}: centered around default, e.g.
      default=20, step=5, num_steps=2 -> [10, 15, 20, 25, 30]
    - [a, b, c]: explicit values

    Returns Cartesian product of all param values. base_params merged into each combo.
    """
    base = dict(base_params or {})
    param_values: dict[str, list[float | int | str]] = {}

    for name, spec in param_specs.items():
        if isinstance(spec, (list, tuple)) and len(spec) == 3 and all(
            isinstance(x, (int, float)) for x in spec
        ):
            # (min, max, step)
            lo, hi, step = spec[0], spec[1], spec[2]
            vals = []
            v = lo
            while v <= hi:
                vals.append(int(v) if isinstance(lo, int) and isinstance(step, int) else v)
                v += step
            param_values[name] = vals
        elif isinstance(spec, dict):
            if "default" in spec:
                # Centered around default
                d, s = spec["default"], spec["step"]
                n = spec.get("num_steps", 2)
                vals = [d + (i - n) * s for i in range(2 * n + 1)]
                param_values[name] = [int(x) if isinstance(d, int) else x for x in vals]
            elif "min" in spec and "max" in spec:
                lo, hi = spec["min"], spec["max"]
                step = spec.get("step", 1)
                vals = []
                v = lo
                while v <= hi:
                    vals.append(int(v) if isinstance(lo, int) else v)
                    v += step
                param_values[name] = vals
            else:
                raise ValueError(f"Invalid spec for {name}: {spec}")
        elif isinstance(spec, (list, tuple)):
            param_values[name] = list(spec)
        else:
            raise ValueError(f"Invalid spec for {name}: {spec}")

    names = list(param_values.keys())
    value_lists = [param_values[n] for n in names]
    grids: list[dict[str, float | int | str]] = []
    for combo in itertools.product(*value_lists):
        grids.append({**base, **dict(zip(names, combo))})
    return grids


def _score(bt: BacktestResult, objective: str) -> float:
    if objective == "sharpe" and bt.sharpe_ratio is not None:
        return bt.sharpe_ratio
    if objective == "return":
        return bt.total_return_pct
    return bt.total_pnl


def run_optimize(
    strategy_name: str,
    symbols: list[str],
    param_grid: list[dict[str, float | int | str]] | None = None,
    method: str = "grid",
    n_trials: int = 50,
    objective: str = "sharpe",
    constraints: OptimizationConstraints | None = None,
    data_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    base_params: dict[str, float | int | str] | None = None,
) -> OptimizeResult:
    """
    Run parameter optimization. method: grid | bayesian | random.
    Requires strategy_name and symbols. When param_grid is None, auto-infers from strategy specs.
    Constraints filter candidates before scoring.
    """
    if not symbols:
        raise ValueError("symbols required (non-empty list).")
    run_id = f"optimize-{uuid.uuid4().hex[:8]}"

    if param_grid is not None:
        # Explicit grid: use it (method ignored)
        trials = param_grid
    elif method == "bayesian":
        from digiquant.optimize_bayesian import run_optimize_bayesian

        return run_optimize_bayesian(
            strategy_name=strategy_name,
            symbols=symbols,
            data_path=data_path,
            data_dir=data_dir,
            n_trials=n_trials,
            objective=objective,
            constraints=constraints,
            base_params=base_params,
        )
    elif method == "random":
        trials = sample_random_params(strategy_name, n_trials, base_params=base_params)
    else:
        # grid: auto-infer
        trials = infer_param_grid(strategy_name, base_params=base_params, num_points_per_param=3)

    results: list[tuple[dict[str, float | int | str], BacktestResult]] = []
    for params in trials:
        bt = run_backtest(
            strategy_name=strategy_name,
            symbols=symbols,
            data_path=data_path,
            data_dir=data_dir,
            strategy_params=params or None,
        )
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

    valid = [(p, bt) for p, bt in results if satisfies_constraints(bt, constraints)]
    if objective == "sharpe":
        valid = [(p, bt) for p, bt in valid if bt.sharpe_ratio is not None]
    if not valid:
        return OptimizeResult(
            run_id=run_id,
            strategy_name=strategy_name,
            symbols=symbols,
            best_params={},
            best_backtest=None,
            num_evaluations=len(results),
            status="partial",
            message=f"All {len(results)} evaluations violated constraints.",
        )

    best_params, best_backtest = max(valid, key=lambda x: _score(x[1], objective))
    return OptimizeResult(
        run_id=run_id,
        strategy_name=strategy_name,
        symbols=symbols,
        best_params=best_params,
        best_backtest=best_backtest,
        num_evaluations=len(results),
        status="ok",
        message=f"{method} optimization ({len(valid)}/{len(results)} passed constraints).",
    )

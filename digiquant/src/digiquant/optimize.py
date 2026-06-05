"""Parameter optimization: grid, random, and Bayesian over backtest runs. Phase 2."""

from __future__ import annotations

import itertools
import logging
import os
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from digiquant.backtest import run_backtest
from digiquant.constraints import satisfies_constraints
from digiquant.models import BacktestResult, OptimizeResult, OptimizationConstraints
from digiquant.strategy_specs import infer_param_grid, sample_random_params

logger = logging.getLogger(__name__)

# Number of parallel workers for grid/random optimization.
# Default: os.cpu_count() or 1. Override with DIGIQUANT_OPTIMIZE_WORKERS env var.
_DEFAULT_WORKERS = int(os.environ.get("DIGIQUANT_OPTIMIZE_WORKERS", os.cpu_count() or 1))


def _run_trial(args: tuple) -> tuple[dict, BacktestResult]:
    """Top-level picklable worker for ProcessPoolExecutor."""
    strategy_name, symbols, params, data_path, data_dir = args
    from digiquant.backtest import run_backtest as _run

    bt = _run(
        strategy_name=strategy_name,
        symbols=symbols,
        data_path=data_path,
        data_dir=data_dir,
        strategy_params=params or None,
    )
    return params, bt


def _run_trials_parallel(
    strategy_name: str,
    symbols: list[str],
    trials: list[dict],
    data_path: str | Path | None,
    data_dir: str | Path | None,
    max_workers: int,
) -> list[tuple[dict, BacktestResult]]:
    """Run backtest trials in parallel using ProcessPoolExecutor.

    Falls back to sequential execution if multiprocessing is unavailable
    (e.g. spawn issues on macOS, or when max_workers=1).
    """
    if max_workers <= 1 or len(trials) <= 1:
        results = []
        for i, params in enumerate(trials):
            logger.info("Trial %d/%d: %s", i + 1, len(trials), params)
            bt = run_backtest(
                strategy_name=strategy_name,
                symbols=symbols,
                data_path=data_path,
                data_dir=data_dir,
                strategy_params=params or None,
            )
            results.append((params, bt))
        return results

    args_list = [
        (strategy_name, symbols, params, data_path, data_dir) for params in trials
    ]
    results: list[tuple[dict, BacktestResult]] = [None] * len(trials)  # type: ignore
    try:
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            future_to_idx = {
                pool.submit(_run_trial, args): i for i, args in enumerate(args_list)
            }
            for future in as_completed(future_to_idx):
                i = future_to_idx[future]
                params, bt = future.result()
                results[i] = (params, bt)
                logger.info(
                    "Trial %d/%d done: Sharpe=%s Return=%.2f%%",
                    i + 1,
                    len(trials),
                    f"{bt.sharpe_ratio:.3f}" if bt.sharpe_ratio is not None else "N/A",
                    bt.total_return_pct,
                )
    except (BrokenProcessPool, OSError, RuntimeError) as exc:
        logger.warning(
            "Parallel optimization failed (%s); falling back to sequential.", exc
        )
        results = []
        for i, params in enumerate(trials):
            logger.info("Trial %d/%d (sequential): %s", i + 1, len(trials), params)
            bt = run_backtest(
                strategy_name=strategy_name,
                symbols=symbols,
                data_path=data_path,
                data_dir=data_dir,
                strategy_params=params or None,
            )
            results.append((params, bt))
    return results


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
    max_workers: int | None = None,
) -> OptimizeResult:
    """
    Run parameter optimization. method: grid | bayesian | random.
    Requires strategy_name and symbols. When param_grid is None, auto-infers from strategy specs.
    Constraints filter candidates before scoring.

    max_workers: parallel processes for grid/random (default: DIGIQUANT_OPTIMIZE_WORKERS or cpu_count).
    """
    if not symbols:
        raise ValueError("symbols required (non-empty list).")
    run_id = f"optimize-{uuid.uuid4().hex[:8]}"
    workers = max_workers if max_workers is not None else _DEFAULT_WORKERS

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

    logger.info(
        "Starting %s optimization: %d trials, %d workers, strategy=%s",
        method,
        len(trials),
        workers,
        strategy_name,
    )
    results = _run_trials_parallel(
        strategy_name=strategy_name,
        symbols=symbols,
        trials=trials,
        data_path=data_path,
        data_dir=data_dir,
        max_workers=workers,
    )

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

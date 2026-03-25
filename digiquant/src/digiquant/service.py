"""Shared entrypoints for HTTP, CLI, and MCP (single implementation path)."""

from __future__ import annotations

from digiquant.backtest import run_backtest
from digiquant.export import run_export
from digiquant.models import BacktestResult, ExportResult, OptimizationConstraints, OptimizeResult
from digiquant.optimize import run_optimize
from digiquant.strategies.registry import list_strategies


def service_run_backtest(
    *,
    strategy_name: str,
    symbols: list[str],
    data_path: str | None,
    data_dir: str | None,
    strategy_params: dict[str, float | int | str] | None = None,
    tearsheet_path: str | None = None,
    full_tearsheet: bool = True,
) -> BacktestResult:
    return run_backtest(
        strategy_name=strategy_name,
        symbols=symbols,
        data_path=data_path,
        data_dir=data_dir,
        strategy_params=strategy_params,
        tearsheet_path=tearsheet_path,
        full_tearsheet=full_tearsheet,
    )


def service_run_optimize(
    *,
    strategy_name: str,
    symbols: list[str],
    data_path: str | None,
    data_dir: str | None,
    param_grid: list[dict[str, float | int | str]] | None = None,
    method: str = "grid",
    n_trials: int = 50,
    objective: str = "sharpe",
    constraints: OptimizationConstraints | None = None,
) -> OptimizeResult:
    return run_optimize(
        strategy_name=strategy_name,
        symbols=symbols,
        data_path=data_path,
        data_dir=data_dir,
        param_grid=param_grid,
        method=method,
        n_trials=n_trials,
        objective=objective,
        constraints=constraints,
    )


def service_run_export(
    *,
    strategy_name: str,
    params: dict[str, float | int | str] | None,
    target: str,
    output_dir: str | None = None,
) -> ExportResult:
    return run_export(
        strategy_name=strategy_name,
        params=params,
        target=target,
        output_dir=output_dir,
    )


def service_list_strategies() -> list[dict]:
    return list_strategies()

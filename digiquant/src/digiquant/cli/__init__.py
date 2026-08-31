"""digiquant CLI: backtest, optimize, export. No fallbacks; raises on failure."""

from __future__ import annotations

import json
from pathlib import Path

import click


def _parse_params(
    ctx: click.Context, param: click.Parameter, value: tuple[str, ...]
) -> dict[str, float | int | str]:
    """Parse repeated --param key=value into a dict. Tries float, then int, then str."""
    out: dict[str, float | int | str] = {}
    for s in value:
        if "=" not in s:
            raise click.BadParameter(f"Invalid param: {s!r}. Use key=value.")
        k, v = s.split("=", 1)
        k = k.strip()
        try:
            out[k] = int(v)
            continue
        except ValueError:
            pass
        try:
            out[k] = float(v)
            continue
        except ValueError:
            pass
        out[k] = v
    return out


@click.group()
def main() -> None:
    """digiquant – high-perf quant pipeline. Backtest, optimize, export."""


# Register subcommand groups.
def _register_subgroups() -> None:
    from digiquant.cli.prices import prices as _prices_group
    from digiquant.olympus.replay.cli import policy_replay as _policy_replay_group

    main.add_command(_prices_group)
    main.add_command(_policy_replay_group)


_register_subgroups()


@main.command()
@click.option(
    "--strategy", "-s", required=True, help="Strategy name (e.g. bollinger_mr, ema_cross)"
)
@click.option("--symbols", "-S", required=True, help="Comma-separated symbols (e.g. BTC-USD,AAPL)")
@click.option(
    "--data-path", "-d", type=click.Path(exists=True, path_type=Path), help="Path to OHLCV CSV"
)
@click.option(
    "--data-dir",
    type=click.Path(exists=True, path_type=Path),
    help="Path to directory with {symbol}.csv files",
)
@click.option(
    "--tearsheet", "-t", type=click.Path(path_type=Path), help="Output path for HTML tearsheet"
)
@click.option(
    "--param",
    "-p",
    "params",
    multiple=True,
    callback=_parse_params,
    help="Strategy param: key=value (repeat for multiple)",
)
def backtest(
    strategy: str,
    symbols: str,
    data_path: Path | None,
    data_dir: Path | None,
    tearsheet: Path | None,
    params: dict[str, float | int | str],
) -> None:
    """Run backtest. Requires --data-path or --data-dir."""
    if not data_path and not data_dir:
        raise click.UsageError("Either --data-path or --data-dir is required.")
    from digiquant.backtest import run_backtest
    from digiquant.paths import resolve_under_data_root

    if data_path is not None:
        try:
            data_path = resolve_under_data_root(data_path, label="--data-path")
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
    if data_dir is not None:
        try:
            data_dir = resolve_under_data_root(data_dir, label="--data-dir")
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
    if tearsheet is not None:
        tearsheet = tearsheet.expanduser().resolve()

    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        raise click.UsageError("--symbols must be non-empty.")
    bt = run_backtest(
        strategy_name=strategy,
        symbols=sym_list,
        data_path=data_path,
        data_dir=data_dir,
        tearsheet_path=tearsheet,
        strategy_params=params or None,
    )
    click.echo(
        f"Trades: {bt.num_trades} | Return: {bt.total_return_pct:.2f}% | Sharpe: {bt.sharpe_ratio}"
    )
    if tearsheet:
        click.echo(f"Tearsheet: {tearsheet}")


@main.command()
@click.option("--strategy", "-s", required=True, help="Strategy name")
@click.option("--symbols", "-S", required=True, help="Comma-separated symbols")
@click.option(
    "--data-path", "-d", type=click.Path(exists=True, path_type=Path), help="Path to OHLCV CSV"
)
@click.option(
    "--data-dir",
    type=click.Path(exists=True, path_type=Path),
    help="Path to directory with {symbol}.csv",
)
@click.option(
    "--method",
    "-m",
    type=click.Choice(["grid", "random", "bayesian"]),
    default="bayesian",
    help="Optimization method",
)
@click.option("--n-trials", "-n", type=int, default=100, help="Number of trials (random/bayesian)")
@click.option("--objective", "-o", type=click.Choice(["sharpe", "return"]), default="sharpe")
@click.option(
    "--param",
    "-p",
    "base_params",
    multiple=True,
    callback=_parse_params,
    help="Base param: key=value (repeat)",
)
def optimize(
    strategy: str,
    symbols: str,
    data_path: Path | None,
    data_dir: Path | None,
    method: str,
    n_trials: int,
    objective: str,
    base_params: dict[str, float | int | str],
) -> None:
    """Run parameter optimization. Requires --data-path or --data-dir."""
    if not data_path and not data_dir:
        raise click.UsageError("Either --data-path or --data-dir is required.")
    from digiquant.optimize import run_optimize
    from digiquant.paths import resolve_under_data_root

    if data_path is not None:
        try:
            data_path = resolve_under_data_root(data_path, label="--data-path")
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
    if data_dir is not None:
        try:
            data_dir = resolve_under_data_root(data_dir, label="--data-dir")
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc

    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        raise click.UsageError("--symbols must be non-empty.")
    opt = run_optimize(
        strategy_name=strategy,
        symbols=sym_list,
        data_path=data_path,
        data_dir=data_dir,
        param_grid=None,
        method=method,
        n_trials=n_trials,
        objective=objective,
        base_params=base_params or None,
    )
    if opt.status == "error":
        raise RuntimeError(opt.message or "Optimization failed.")
    sharpe = opt.best_backtest.sharpe_ratio if opt.best_backtest else None
    click.echo(f"Evaluations: {opt.num_evaluations} | Best Sharpe: {sharpe}")
    click.echo(f"Best params: {json.dumps(opt.best_params)}")


@main.command()
@click.option("--strategy", "-s", required=True, help="Strategy name")
@click.option(
    "--target",
    "-t",
    type=click.Choice(["nautilus", "tradingview", "alpaca", "quantconnect"]),
    default="nautilus",
)
@click.option(
    "--output-dir", "-o", type=click.Path(path_type=Path), help="Output directory for artifact"
)
@click.option(
    "--param",
    "-p",
    "params",
    multiple=True,
    callback=_parse_params,
    help="Strategy param: key=value (repeat)",
)
def export(
    strategy: str,
    target: str,
    output_dir: Path | None,
    params: dict[str, float | int | str],
) -> None:
    """Export strategy + params to target artifact."""
    from digiquant.export import run_export

    exp = run_export(
        strategy_name=strategy,
        params=params or None,
        target=target,
        output_dir=output_dir,
    )
    if exp.status != "ok":
        raise RuntimeError(exp.message or "Export failed.")
    click.echo(f"Artifact: {exp.artifact_path}")


@main.command("sdca-optimize-curve")
@click.option(
    "--cache-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("data/price-history"),
    show_default=True,
    help="Coinbase/FRED cache (BTC-USD.csv plus M2SL/DTWEXBGS siblings)",
)
@click.option("--signal-delay-days", type=int, default=3, show_default=True)
@click.option("--trade-start", type=str, default="2018-01-01", show_default=True)
@click.option("--initial-cash", type=float, default=1000.0, show_default=True)
@click.option(
    "--n-random",
    type=int,
    default=400,
    show_default=True,
    help="Extra seeded random trials",
)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option("--no-grid", is_flag=True, help="Skip the coarse grid (random + published only)")
@click.option(
    "--sidecar",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the search result JSON (default: package sidecar path)",
)
@click.option(
    "--persist-preset",
    is_flag=True,
    help="Write btc_optimized only if the winner beats return AND fill concentration",
)
def sdca_optimize_curve(
    cache_dir: Path,
    signal_delay_days: int,
    trade_start: str,
    initial_cash: float,
    n_random: int,
    seed: int,
    no_grid: bool,
    sidecar: Path | None,
    persist_preset: bool,
) -> None:
    """Search remaining-book curve params on the frozen published composite.

    Index weights are read from settings.json and not searched. Objective is
    highest backtest return with cheap-buy / rich-sell / 2025-sell gates.
    Does not --push-supabase. beats_flat_dca_oos is never set true here.
    """
    from digiquant.strategies.sdca.curve_optimize import (
        persist_curve_winner,
        run_published_curve_search,
    )

    result = run_published_curve_search(
        cache_dir,
        signal_delay_days=signal_delay_days,
        trade_start=trade_start,
        initial_cash=initial_cash,
        n_random=n_random,
        seed=seed,
        include_grid=not no_grid,
    )
    wrote = persist_curve_winner(result, sidecar_path=sidecar, persist=persist_preset)
    shape = result.best.shape
    conc = result.best.concentration
    click.echo(
        f"evals={result.num_evaluations} feasible={result.num_feasible} "
        f"persist_ok={result.persist_ok} wrote_preset={wrote} "
        f"evaluator={result.evaluator} beats_flat_dca_oos={result.beats_flat_dca_oos}"
    )
    click.echo(
        f"baseline return={result.baseline.total_return_pct:.2f}% "
        f"vs_lump={result.baseline.vs_lump_pct:.2f}% "
        f"buy_mean_risk={result.baseline.concentration.buy_mean_risk} "
        f"sell_mean_risk={result.baseline.concentration.sell_mean_risk} "
        f"sell_days_2025={result.baseline.concentration.sell_days_2025}"
    )
    click.echo(
        f"best return={result.best.total_return_pct:.2f}% "
        f"vs_lump={result.best.vs_lump_pct:.2f}% "
        f"vs_flat_logged={result.best.vs_flat_dca_pct:.2f}% "
        f"unconstrained_return={result.unconstrained_return_pct:.2f}% "
        f"feasible={result.best.feasible} reasons={result.best.reject_reasons}"
    )
    click.echo(
        "best shape: "
        f"buy_max={shape.buy_max_rate:g} buy_knee={shape.buy_knee_risk:g} "
        f"sell_knee={shape.sell_knee_risk:g} sell_max={shape.sell_max_rate:g} "
        f"buy_curv={shape.buy_curvature:g} sell_curv={shape.sell_curvature:g}"
    )
    click.echo(
        f"best concentration: buy_mean_risk={conc.buy_mean_risk} "
        f"sell_mean_risk={conc.sell_mean_risk} "
        f"buy_frac_cheap={conc.buy_frac_cheap:.3f} sell_frac_rich={conc.sell_frac_rich:.3f} "
        f"buy_frac_deep={conc.buy_frac_deep:.3f} sell_frac_deep={conc.sell_frac_deep:.3f} "
        f"sell_days_2025={conc.sell_days_2025}"
    )


if __name__ == "__main__":
    main()

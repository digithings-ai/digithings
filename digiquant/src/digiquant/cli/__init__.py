"""digiquant CLI: backtest, optimize, export, strategy, prices, onchain. No fallbacks."""

from __future__ import annotations

import json
from pathlib import Path

import click


def _coerce_param_value(v: str) -> float | int | str:
    """Parse one --param value: int, then float, then keep the raw string."""
    for convert in (int, float):
        try:
            return convert(v)
        except ValueError:
            # This conversion does not apply to v, so try the next one; a value
            # that is neither an int nor a float is kept as the raw string.
            continue
    return v


def _parse_params(
    ctx: click.Context, param: click.Parameter, value: tuple[str, ...]
) -> dict[str, float | int | str]:
    """Parse repeated --param key=value into a dict. Tries int, then float, then str."""
    out: dict[str, float | int | str] = {}
    for s in value:
        if "=" not in s:
            raise click.BadParameter(f"Invalid param: {s!r}. Use key=value.")
        k, v = s.split("=", 1)
        out[k.strip()] = _coerce_param_value(v)
    return out


@click.group()
def main() -> None:
    """digiquant – high-perf quant pipeline. Backtest, optimize, export."""


# Register subcommand groups.
def _register_subgroups() -> None:
    from digiquant.cli.onchain import onchain as _onchain_group
    from digiquant.cli.prices import prices as _prices_group
    from digiquant.cli.strategy import strategy as _strategy_group
    from digiquant.cli.web_search import web_search as _web_search_group
    from digiquant.dashboard.replay.cli import policy_replay as _policy_replay_group

    main.add_command(_prices_group)
    main.add_command(_onchain_group)
    main.add_command(_strategy_group)
    main.add_command(_web_search_group)
    main.add_command(_policy_replay_group)

    # Repo-split 1.2 (DIG-3691): SDCA subcommands (sdca-stage0,
    # sdca-optimize-curve) register through the ``digiquant.cli`` entry-point
    # group. Fail-closed (warn-and-skip).
    try:
        from digiquant import plugin as _plugin

        _plugin.register_plugin_cli(main)
    except Exception:
        pass


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
    from digiquant import plugin as _plugin
    from digiquant.paths import resolve_under_data_root

    # Repo-split 1.2 (DIG-3691): `digiquant.optimize` is R1. The command stays
    # in R0 because it is the documented public surface; the implementation
    # arrives through the plugin, and its absence is a clear usage error rather
    # than an ImportError traceback.
    run_optimize = _plugin.get_run_optimize_hook()
    if run_optimize is None:
        raise click.UsageError(
            "the optimiser is not installed; install the digiquant strategies plugin "
            "to run `digiquant optimize`"
        )

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




if __name__ == "__main__":
    main()

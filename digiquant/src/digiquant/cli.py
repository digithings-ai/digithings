"""DigiQuant CLI: backtest, optimize, export. No fallbacks; raises on failure."""

from __future__ import annotations

import json
from pathlib import Path

import click


def _parse_params(ctx: click.Context, param: click.Parameter, value: tuple[str, ...]) -> dict[str, float | int | str]:
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
    """DigiQuant – high-perf quant pipeline. Backtest, optimize, export."""


@main.command()
@click.option("--strategy", "-s", required=True, help="Strategy name (e.g. bollinger_mr, ema_cross)")
@click.option("--symbols", "-S", required=True, help="Comma-separated symbols (e.g. BTC-USD,AAPL)")
@click.option("--data-path", "-d", type=click.Path(exists=True, path_type=Path), help="Path to OHLCV CSV")
@click.option("--data-dir", type=click.Path(exists=True, path_type=Path), help="Path to directory with {symbol}.csv files")
@click.option("--tearsheet", "-t", type=click.Path(path_type=Path), help="Output path for HTML tearsheet")
@click.option("--param", "-p", "params", multiple=True, callback=_parse_params, help="Strategy param: key=value (repeat for multiple)")
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
    click.echo(f"Trades: {bt.num_trades} | Return: {bt.total_return_pct:.2f}% | Sharpe: {bt.sharpe_ratio}")
    if tearsheet:
        click.echo(f"Tearsheet: {tearsheet}")


@main.command()
@click.option("--strategy", "-s", required=True, help="Strategy name")
@click.option("--symbols", "-S", required=True, help="Comma-separated symbols")
@click.option("--data-path", "-d", type=click.Path(exists=True, path_type=Path), help="Path to OHLCV CSV")
@click.option("--data-dir", type=click.Path(exists=True, path_type=Path), help="Path to directory with {symbol}.csv")
@click.option("--method", "-m", type=click.Choice(["grid", "random", "bayesian"]), default="bayesian", help="Optimization method")
@click.option("--n-trials", "-n", type=int, default=100, help="Number of trials (random/bayesian)")
@click.option("--objective", "-o", type=click.Choice(["sharpe", "return"]), default="sharpe")
@click.option("--param", "-p", "base_params", multiple=True, callback=_parse_params, help="Base param: key=value (repeat)")
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
@click.option("--target", "-t", type=click.Choice(["nautilus", "tradingview", "alpaca", "quantconnect"]), default="nautilus")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), help="Output directory for artifact")
@click.option("--param", "-p", "params", multiple=True, callback=_parse_params, help="Strategy param: key=value (repeat)")
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

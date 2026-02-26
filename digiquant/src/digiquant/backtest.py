"""Backtest entrypoint: NautilusTrader only. No stub; requires digiquant[nautilus] and OHLCV data."""

from __future__ import annotations

from pathlib import Path

from digiquant.models import BacktestResult
from digiquant.nautilus_runner import run_nautilus_backtest

NAUTILUS_UNAVAILABLE_MSG = (
    "Nautilus backtest unavailable. Install digiquant[nautilus]."
)
DATA_REQUIRED_MSG = (
    "Backtest requires data_path (single OHLCV CSV) or data_dir with symbols. "
    "Specify strategy, symbols, and data source."
)
DATA_NOT_FOUND_MSG = (
    "Backtest failed: no OHLCV data found for symbol(s) (check data_path exists or data_dir "
    "contains {{symbol}}.csv), or NautilusTrader not installed (pip install digiquant[nautilus])."
)


def run_backtest(
    strategy_name: str,
    symbols: list[str],
    data_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    tearsheet_path: str | Path | None = None,
    strategy_params: dict | None = None,
) -> BacktestResult:
    """
    Entrypoint for backtest. Used by HTTP API and MCP tool.
    Requires strategy_name, symbols, and data_path or data_dir. Fails if data unavailable.
    """
    if not symbols:
        raise RuntimeError("symbols required (non-empty list).")
    if data_path is None and data_dir is None:
        raise RuntimeError(DATA_REQUIRED_MSG)
    result = run_nautilus_backtest(
        strategy_name=strategy_name,
        symbols=symbols,
        data_path=data_path,
        data_dir=data_dir,
        tearsheet_path=tearsheet_path,
        strategy_params=strategy_params,
    )
    if result is not None:
        return result
    raise RuntimeError(DATA_NOT_FOUND_MSG)

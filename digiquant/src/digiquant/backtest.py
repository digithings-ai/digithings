"""Backtest entrypoint: NautilusTrader only. No stub; requires digiquant[nautilus] and test data."""

from __future__ import annotations

from digiquant.models import BacktestResult
from digiquant.nautilus_runner import run_nautilus_backtest

NAUTILUS_UNAVAILABLE_MSG = (
    "Nautilus backtest unavailable. Install digiquant[nautilus] and ensure test data is available."
)


def run_backtest(
    strategy_name: str = "mean_reversion_tech",
    symbols: list[str] | None = None,
) -> BacktestResult:
    """
    Entrypoint for backtest. Used by HTTP API and MCP tool.
    Runs real NautilusTrader backtest. Raises if Nautilus or test data is unavailable.
    """
    symbols = symbols or ["AAPL", "MSFT", "GOOGL"]
    result = run_nautilus_backtest(strategy_name=strategy_name, symbols=symbols)
    if result is not None:
        return result
    raise RuntimeError(NAUTILUS_UNAVAILABLE_MSG)

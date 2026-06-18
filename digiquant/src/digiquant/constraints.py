"""Shared constraint checking for DigiQuant optimization."""

from __future__ import annotations

from datetime import datetime

from digiquant.models import BacktestResult, OptimizationConstraints


def normalize_drawdown_pct(value: float | None) -> float | None:
    """Normalize drawdown to negative percent (Nautilus may emit positive magnitudes)."""
    if value is None:
        return None
    if value > 0:
        return -abs(value)
    return value


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
        bt_dd = normalize_drawdown_pct(bt.max_drawdown_pct)
        limit = normalize_drawdown_pct(constraints.max_drawdown_pct)
        if bt_dd is not None and limit is not None and bt_dd < limit:
            return False
    if constraints.min_sharpe is not None and bt.sharpe_ratio is not None:
        if bt.sharpe_ratio < constraints.min_sharpe:
            return False
    if constraints.min_return_pct is not None:
        if bt.total_return_pct < constraints.min_return_pct:
            return False

    try:
        start = datetime.fromisoformat(bt.start_time.replace("Z", "+00:00"))
        end = datetime.fromisoformat(bt.end_time.replace("Z", "+00:00"))
        days = (end - start).total_seconds() / 86400
        years = days / 365.25 if days > 0 else 0
        trades_per_year = bt.num_trades / years if years > 0 else 0
    except (ValueError, TypeError, AttributeError):
        trades_per_year = 0.0

    if constraints.max_trades_per_year is not None and trades_per_year > constraints.max_trades_per_year:
        return False
    if constraints.min_trades_per_year is not None and trades_per_year < constraints.min_trades_per_year:
        return False
    return True

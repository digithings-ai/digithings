"""Deterministic cumulative returns persisted for the Olympus Performance view."""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, field_validator


class PerformanceReturns(BaseModel):
    """Portfolio and benchmark returns over their stored observation window."""

    model_config = ConfigDict(frozen=True)

    net_return_pct: float | None
    benchmark_return_pct: float | None
    relative_return_pct: float | None
    benchmark_ticker: str = "SPY"

    @field_validator("benchmark_ticker")
    @classmethod
    def normalize_benchmark_ticker(cls, value: str) -> str:
        ticker = value.strip().upper()
        if not ticker:
            raise ValueError("benchmark_ticker must not be empty")
        return ticker


def _period_return_pct(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    first = float(values[0])
    last = float(values[-1])
    if first <= 0 or not math.isfinite(first) or not math.isfinite(last):
        return None
    return round((last / first - 1.0) * 100.0, 6)


def calculate_performance_returns(
    *,
    nav_values: Sequence[float],
    benchmark_closes: Sequence[float],
    benchmark_ticker: str = "SPY",
) -> PerformanceReturns:
    """Calculate cumulative simple returns from first and last stored observations."""
    net_return_pct = _period_return_pct(nav_values)
    benchmark_return_pct = _period_return_pct(benchmark_closes)
    relative_return_pct = (
        round(net_return_pct - benchmark_return_pct, 6)
        if net_return_pct is not None and benchmark_return_pct is not None
        else None
    )
    return PerformanceReturns(
        net_return_pct=net_return_pct,
        benchmark_return_pct=benchmark_return_pct,
        relative_return_pct=relative_return_pct,
        benchmark_ticker=benchmark_ticker,
    )

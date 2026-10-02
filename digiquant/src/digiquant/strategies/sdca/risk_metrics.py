"""Risk-adjusted metrics over an equity path (#4804, Plan 20).

Generic core for the period optimizer: everything here is a pure function over a
mark-to-market equity series, so any strategy family can be scored the same way.
There is no NautilusTrader import (SDCA core rule) and no asset knowledge.

**Conventions — pin these.** Every one is asserted by
``tests/dq/strategies/sdca/test_risk_metrics.py``, so a 100× or a 1/N error
turns that suite red:

- **Returns are simple per-period returns** of the equity series, in order:
  ``r[i] = values[i + 1] / values[i] - 1``. No log returns, no discounting.
- **Annualization is 252 periods per year** by default (``annualization=252``,
  the same 252 the tearsheet stats call out). The factor only scales
  Sharpe/Sortino (by ``sqrt(annualization)``); it never touches total return,
  CAGR or drawdown.
- **CAGR compounds over ``periods / annualization`` years**, where ``periods``
  is ``len(values) - 1`` — the number of returns actually observed, not the
  number of samples.
- **Risk-free rate is 0.** This module takes no cash-rate input by design: the
  score is a *relative* quality ranking between period sets on one asset over
  one history, where a constant drift is identical for every candidate.
- **Sharpe** = ``mean(r) / stdev(r, ddof=1) * sqrt(annualization)``.
- **Sortino** = ``mean(r) / downside_deviation * sqrt(annualization)``, with the
  minimum-acceptable-return set to 0 and downside deviation taken over **all**
  periods: ``sqrt(mean(min(r, 0) ** 2))``. Periods at or above the MAR
  contribute zero, which is the empyrical ``downside_risk`` convention — it is
  deliberately *not* the standard deviation of the losing subset, which would
  shrink as losses get rarer.
- **Calmar** = ``cagr_pct / max_drawdown_pct``. Both are ×100 percents, so the
  ratio is unit-free.
- **Drawdown is a positive ×100 percent magnitude** and is *reused*, never
  recomputed: ``max_drawdown_pct`` is
  ``walk_forward.max_drawdown_magnitude_pct(values)`` (#3174), so the package
  keeps exactly one drawdown definition.
- **Degenerate denominators report ``0.0``, never ``inf``/``nan``**: a flat
  series, a constant-returns series and a drawdown-free path all return finite
  numbers so downstream ranking (the period optimizer's objective) stays
  totally ordered and JSON-serializable.

The equity path must be strictly positive and finite: a zero or negative equity
is not representable here, and it raises rather than emitting a ``-inf`` CAGR.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.walk_forward import max_drawdown_magnitude_pct

# Trading days per year. The tearsheet stats label their Sharpe "Sharpe (252d)";
# this module uses the same factor so the two are comparable by eye.
TRADING_DAYS_PER_YEAR = 252


class RiskMetrics(BaseModel):
    """Risk-adjusted numbers for one equity path. ``*_pct`` are ×100 percents."""

    model_config = ConfigDict(frozen=True, strict=True)

    total_return_pct: float = Field(
        ...,
        description="First-to-last equity change as a ×100 percent (25.0 = +25%)",
    )
    cagr_pct: float = Field(
        ...,
        description=(
            "Geometric annual growth as a ×100 percent, compounded over "
            "(len(values) - 1) / annualization years"
        ),
    )
    sharpe: float = Field(
        ...,
        description=(
            "Mean per-period return / per-period stdev (ddof=1) × sqrt(annualization), "
            "risk-free rate 0"
        ),
    )
    sortino: float = Field(
        ...,
        description=(
            "Mean per-period return / downside deviation × sqrt(annualization), "
            "MAR 0; downside deviation is sqrt(mean(min(return, 0) ** 2)) over all periods"
        ),
    )
    calmar: float = Field(
        ...,
        description="cagr_pct / max_drawdown_pct; 0.0 when the path never draws down",
    )
    max_drawdown_pct: float = Field(
        ...,
        description=(
            "Peak-to-trough drawdown as a ×100 percent magnitude, reused from "
            "walk_forward.max_drawdown_magnitude_pct"
        ),
    )


def equity_metrics(
    values: Sequence[float],
    *,
    annualization: int = TRADING_DAYS_PER_YEAR,
) -> RiskMetrics:
    """Score one equity path. See the module docstring for every convention.

    ``values`` is the mark-to-market equity series in chronological order, one
    entry per period (daily for the SDCA calendars). Raises ``ValueError`` for an
    empty / single-value, non-finite, or non-positive path, or a non-positive
    ``annualization``.
    """
    if annualization < 1:
        raise ValueError(f"annualization must be >= 1, got {annualization}")
    series_values = [float(v) for v in values]
    if len(series_values) < 2:
        raise ValueError(f"equity_metrics requires at least two values, got {len(series_values)}")
    if any(not math.isfinite(v) for v in series_values):
        raise ValueError("equity_metrics requires finite equity values (no NaN or inf)")
    if any(v <= 0.0 for v in series_values):
        raise ValueError("equity_metrics requires strictly positive equity values")

    equity = pl.Series("equity", series_values, dtype=pl.Float64)
    first = series_values[0]
    last = series_values[-1]
    growth = last / first
    total_return_pct = (growth - 1.0) * 100.0
    years = (len(series_values) - 1) / annualization
    cagr_pct = (growth ** (1.0 / years) - 1.0) * 100.0

    returns = equity.slice(1) / equity.slice(0, len(series_values) - 1) - 1.0
    scale = math.sqrt(float(annualization))
    mean_return = float(returns.mean())
    stdev = returns.std(ddof=1)
    downside_dev = math.sqrt(float((returns.clip(upper_bound=0.0) ** 2).mean()))
    max_drawdown_pct = max_drawdown_magnitude_pct(series_values)

    return RiskMetrics(
        total_return_pct=total_return_pct,
        cagr_pct=cagr_pct,
        sharpe=0.0 if stdev is None or stdev <= 0.0 else mean_return / stdev * scale,
        sortino=0.0 if downside_dev <= 0.0 else mean_return / downside_dev * scale,
        calmar=cagr_pct / max_drawdown_pct if max_drawdown_pct > 0.0 else 0.0,
        max_drawdown_pct=max_drawdown_pct,
    )


__all__ = ["TRADING_DAYS_PER_YEAR", "RiskMetrics", "equity_metrics"]

"""Perfect-strategy oracle over buy/sell period sets (#4804, Plan 20).

The owner question was "if our buy and sell periods are well identified, our
returns should be higher" — so the only honest way to answer it is to score the
periods themselves. This module takes a price calendar plus two sets of period
dates and returns the *ceiling* an all-in / flat book would have earned on that
exact history, with the risk-adjusted metrics and time in market.

**The honesty frame is the point.** This is an in-sample ceiling on the same
history the periods were fit on: it measures period *quality*, never achievable
performance. Only a split-sample read (fit periods on one half, score on the
other) says anything out-of-sample, and both must be reported together.

Book rules (all deliberate, all pinned by tests):

- **Buy dates are all-in**: every unit of cash is spent at that day's close.
  **Sell dates are all-out**: every unit is liquidated at that day's close.
  Real DCA drips; the oracle does not, or it would not be a ceiling.
- **A date in neither set holds the previous position.** Neutrality is not a
  signal. The oracle never times an exit by omission — it only acts on a
  pinned period date.
- **Sell beats buy on the same date.** A date in both sets is treated as a sell,
  matching the "long sells override medium buys" precedence the period
  combination uses. Flat is the conservative read of an ambiguous pin.
- **A re-entry buys the whole (reinvested) book.** Cash is never split and never
  reserved, so a later buy date deploys whatever the flat period produced.
- **Exposure counts invested days**: a day is exposed when the book holds units
  at that day's close. A sell day is flat by construction, a buy day is exposed,
  and ``exposure_pct = exposed_days / total_days × 100``.
- **Parity pin**: with every date in the buy set the oracle *is* lump-sum
  buy-and-hold, and its path equals ``dca_metrics.lump_mark_to_market`` element
  for element (``test_all_buy_path_equals_lump_mark_to_market``). That is what
  keeps this module an oracle rather than a second, softer backtest.

Generic core: no NautilusTrader import, no asset knowledge, no engine call.
Metrics come from ``sdca.risk_metrics``, so the period optimizer and every
other consumer read one set of conventions.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.risk_metrics import (
    TRADING_DAYS_PER_YEAR,
    RiskMetrics,
    equity_metrics,
)


class PerfectStrategyMetrics(BaseModel):
    """One oracle run: risk-adjusted metrics plus time in market."""

    model_config = ConfigDict(frozen=True, strict=True)

    metrics: RiskMetrics = Field(
        ...,
        description="Risk-adjusted metrics of the oracle equity path (see sdca.risk_metrics)",
    )
    exposure_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Invested days / total days as a ×100 percent (70.0 = 70% time in market)",
    )


def perfect_strategy_path(
    dates: Sequence[date],
    prices: Sequence[float],
    buy_dates: Collection[date],
    sell_dates: Collection[date],
    initial_cash: float,
) -> tuple[list[float], list[bool]]:
    """All-in/all-out equity path for one period set.

    ``dates`` and ``prices`` are the price calendar (one close per date, in
    order). ``buy_dates`` / ``sell_dates`` are the pinned period dates; pins
    outside the calendar are ignored. Returns ``(equity_values, exposure_days)``
    — the mark-to-market value after each day's action, and whether the book
    held units at that close.

    Prices must be strictly positive and finite, ``initial_cash`` positive, and
    the two calendars the same length; anything else raises ``ValueError``.
    """
    if len(dates) != len(prices):
        raise ValueError("perfect_strategy_path requires dates and prices of the same length")
    if not prices:
        raise ValueError("perfect_strategy_path requires at least one day")
    if not math.isfinite(initial_cash) or initial_cash <= 0.0:
        raise ValueError(
            f"perfect_strategy_path requires positive initial_cash, got {initial_cash}"
        )

    buy_set = set(buy_dates)
    sell_set = set(sell_dates)
    cash = float(initial_cash)
    units = 0.0
    values: list[float] = []
    exposure: list[bool] = []
    for day, raw_price in zip(dates, prices, strict=True):
        price = float(raw_price)
        if not math.isfinite(price) or price <= 0.0:
            raise ValueError(
                f"perfect_strategy_path requires positive prices, got {price} on {day}"
            )
        if day in sell_set:
            cash += units * price
            units = 0.0
        elif day in buy_set:
            units += cash / price
            cash = 0.0
        values.append(cash + units * price)
        exposure.append(units > 0.0)
    return values, exposure


def perfect_strategy_metrics(
    dates: Sequence[date],
    prices: Sequence[float],
    buy_dates: Collection[date],
    sell_dates: Collection[date],
    initial_cash: float,
    *,
    annualization: int = TRADING_DAYS_PER_YEAR,
) -> PerfectStrategyMetrics:
    """Score one period set: oracle metrics plus ``exposure_pct`` (invested days).

    ``annualization`` is forwarded unchanged to ``risk_metrics.equity_metrics``
    (252 daily periods per year by default).

    Raises ``ValueError`` when the calendar holds fewer than two days — a risk
    adjustment needs at least one return, so the wrapper raises the same
    minimum-length guard ``risk_metrics.equity_metrics`` raises rather than
    surfacing it from two frames down (#4804 review). A longer calendar still
    fails on the same guard for non-finite / non-positive input.
    """
    if len(dates) < 2:
        raise ValueError(
            "perfect_strategy_metrics requires at least two days, got "
            f"{len(dates)} (a risk-adjusted metric needs at least one return)"
        )
    values, exposure = perfect_strategy_path(dates, prices, buy_dates, sell_dates, initial_cash)
    exposed_days = sum(1 for invested in exposure if invested)
    return PerfectStrategyMetrics(
        metrics=equity_metrics(values, annualization=annualization),
        exposure_pct=exposed_days / len(exposure) * 100.0,
    )


__all__ = ["PerfectStrategyMetrics", "perfect_strategy_metrics", "perfect_strategy_path"]

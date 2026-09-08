"""CI-only relative-strength rotation backtest (#1084 Phase 1).

Long-only top-N sleeves from ``RsRanker``, absolute-strength cash gate, optional
``risk_on`` overlay from the macro-liquidity regime (#1085). Reports vs
equal-weight and buy-&-hold — **not** a published ``BacktestResult``.
NautilusTrader remains the sole published engine; this harness pins allocation
math the same way ``strategies/sdca/backtest.py`` and
``indicators.macro_liquidity.backtest_regime_gate`` do.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Mapping, Sequence

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.indicators.rs_ranker import RsRanker, RsRankerConfig


class RsRotationReport(BaseModel):
    """Summary stats for one Phase-1 RS rotation CI harness run."""

    model_config = ConfigDict(strict=True)

    rotation_return_pct: float
    equal_weight_return_pct: float
    buy_hold_return_pct: float
    vs_equal_weight_pct: float = Field(
        description="rotation_return_pct − equal_weight_return_pct",
    )
    vs_buy_hold_pct: float = Field(
        description="rotation_return_pct − buy_hold_return_pct",
    )
    days_total: int
    days_invested: int
    days_cash: int
    rebalance_count: int
    final_rotation: float
    final_equal_weight: float
    final_buy_hold: float


def _align_close_panel(
    closes: Mapping[str, pl.DataFrame] | pl.DataFrame,
    *,
    symbols: Sequence[str] | None = None,
) -> tuple[list[date], dict[str, list[float]]]:
    """Inner-join calendar across symbols → date list + parallel close series."""
    ranker = RsRanker()
    long = ranker.to_long_panel(closes, symbols=symbols)
    if long.is_empty():
        raise ValueError("closes panel is empty")

    wide = (
        long.pivot(on="symbol", index="date", values="close", aggregate_function="first")
        .sort("date")
        .drop_nulls()
    )
    if wide.height < 2:
        raise ValueError("need at least 2 overlapping days across the pool")

    date_list = wide["date"].to_list()
    syms = [c for c in wide.columns if c != "date"]
    series = {s: [float(x) for x in wide[s].to_list()] for s in syms}
    return date_list, series


def backtest_rs_rotation(
    closes: Mapping[str, pl.DataFrame] | pl.DataFrame,
    *,
    config: RsRankerConfig | None = None,
    top_n: int = 1,
    rebalance_every: int = 7,
    initial_cash: float = 10_000.0,
    risk_on: Sequence[bool | None] | pl.Series | None = None,
    symbols: Sequence[str] | None = None,
) -> RsRotationReport:
    """Long-only RS rotation vs equal-weight and buy-&-hold.

    Absolute-strength gate: on rebalance days with no qualifying assets (or with
    ``risk_on`` false/null when provided), the book is 100% cash. Equal-weight
    always stays fully invested (rebalanced on the same cadence). Buy-&-hold
    splits cash equally at t0 and never rebalances.
    """
    if initial_cash <= 0 or not math.isfinite(initial_cash):
        raise ValueError(f"initial_cash must be finite and > 0, got {initial_cash}")
    if top_n < 1:
        raise ValueError(f"top_n must be >= 1, got {top_n}")
    if rebalance_every < 1:
        raise ValueError(f"rebalance_every must be >= 1, got {rebalance_every}")

    dates, price_map = _align_close_panel(closes, symbols=symbols)
    n = len(dates)
    syms = list(price_map.keys())
    if risk_on is not None:
        gate = list(risk_on) if not isinstance(risk_on, pl.Series) else risk_on.to_list()
        if len(gate) != n:
            raise ValueError("risk_on length must match aligned close calendar")
    else:
        gate = [True] * n

    ranker = RsRanker(config)
    # Rebuild mapping frames from aligned series for the ranker.
    close_frames = {s: pl.DataFrame({"date": dates, "close": price_map[s]}) for s in syms}
    ranked = ranker.rank(close_frames)
    picks = ranker.select_top_n(ranked, top_n=top_n, qualifying_only=True)
    picks_by_date: dict[date, list[tuple[str, float]]] = {}
    for row in picks.to_dicts():
        d = row["date"]
        key = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
        picks_by_date.setdefault(key, []).append((str(row["symbol"]), float(row["weight"])))

    # Buy-&-hold: equal units of cash at t0 prices.
    bh_cash_each = initial_cash / len(syms)
    bh_units = {s: bh_cash_each / price_map[s][0] for s in syms}

    # Equal-weight + rotation state.
    ew_units = {s: 0.0 for s in syms}
    rot_units = {s: 0.0 for s in syms}
    ew_cash = float(initial_cash)
    rot_cash = float(initial_cash)

    def _mtm(units: dict[str, float], cash: float, i: int) -> float:
        return cash + sum(units[s] * price_map[s][i] for s in syms)

    def _rebalance_ew(i: int) -> None:
        nonlocal ew_cash, ew_units
        total = _mtm(ew_units, ew_cash, i)
        target = total / len(syms)
        ew_units = {s: target / price_map[s][i] for s in syms}
        ew_cash = 0.0

    def _rebalance_rot(i: int) -> None:
        nonlocal rot_cash, rot_units
        total = _mtm(rot_units, rot_cash, i)
        want_risk = gate[i] is True
        sleeves = picks_by_date.get(dates[i], []) if want_risk else []
        # Absolute gate / empty top-N → cash.
        if not sleeves:
            rot_cash = total
            rot_units = {s: 0.0 for s in syms}
            return
        rot_units = {s: 0.0 for s in syms}
        for sym, weight in sleeves:
            if sym not in price_map:
                continue
            rot_units[sym] = (total * weight) / price_map[sym][i]
        rot_cash = 0.0

    # Day 0 allocate.
    _rebalance_ew(0)
    _rebalance_rot(0)
    rebalance_count = 1
    days_invested = 1 if any(u > 0 for u in rot_units.values()) else 0
    days_cash = 0 if days_invested else 1

    rot_equity = [_mtm(rot_units, rot_cash, 0)]
    ew_equity = [_mtm(ew_units, ew_cash, 0)]
    bh_equity = [_mtm(bh_units, 0.0, 0)]

    for i in range(1, n):
        if i % rebalance_every == 0:
            _rebalance_ew(i)
            _rebalance_rot(i)
            rebalance_count += 1

        rot_equity.append(_mtm(rot_units, rot_cash, i))
        ew_equity.append(_mtm(ew_units, ew_cash, i))
        bh_equity.append(_mtm(bh_units, 0.0, i))

        if any(u > 0 for u in rot_units.values()):
            days_invested += 1
        else:
            days_cash += 1

    rot_ret = (rot_equity[-1] / initial_cash - 1.0) * 100.0
    ew_ret = (ew_equity[-1] / initial_cash - 1.0) * 100.0
    bh_ret = (bh_equity[-1] / initial_cash - 1.0) * 100.0

    return RsRotationReport(
        rotation_return_pct=rot_ret,
        equal_weight_return_pct=ew_ret,
        buy_hold_return_pct=bh_ret,
        vs_equal_weight_pct=rot_ret - ew_ret,
        vs_buy_hold_pct=rot_ret - bh_ret,
        days_total=n,
        days_invested=days_invested,
        days_cash=days_cash,
        rebalance_count=rebalance_count,
        final_rotation=rot_equity[-1],
        final_equal_weight=ew_equity[-1],
        final_buy_hold=bh_equity[-1],
    )


def build_allocation_frame(
    ranked: pl.DataFrame,
    *,
    top_n: int = 1,
    risk_on_by_date: Mapping[date, bool | None] | None = None,
) -> pl.DataFrame:
    """Materialize ``date, symbol, weight`` for the Nautilus rotator.

    Dates with no qualifying top-N (or ``risk_on`` not True) emit no rows —
    the strategy interprets that as an all-cash target.
    """
    ranker = RsRanker()
    picks = ranker.select_top_n(ranked, top_n=top_n, qualifying_only=True)
    if picks.is_empty():
        return pl.DataFrame(schema={"date": pl.Date, "symbol": pl.Utf8, "weight": pl.Float64})
    if risk_on_by_date is None:
        return picks.select(["date", "symbol", "weight"])

    rows = []
    for row in picks.to_dicts():
        d = row["date"]
        key = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
        if risk_on_by_date.get(key) is not True:
            continue
        rows.append({"date": key, "symbol": row["symbol"], "weight": float(row["weight"])})
    if not rows:
        return pl.DataFrame(schema={"date": pl.Date, "symbol": pl.Utf8, "weight": pl.Float64})
    return pl.DataFrame(rows)


__all__ = [
    "RsRotationReport",
    "backtest_rs_rotation",
    "build_allocation_frame",
]

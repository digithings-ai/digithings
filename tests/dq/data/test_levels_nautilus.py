"""NautilusTrader harness for the causal levels engine (E6, #137).

Gated on the ``nautilus`` extra via ``importorskip`` so the plain digiquant lane
collects-and-skips it. The harness is deliberately engine-free: it uses the
indicator/object layer only, never a ``BacktestEngine``, so it cannot trip the
Linux SIGABRT from issue #42 (that crash needs a second in-process Rust
engine). Keep it that way — no ``BacktestEngine`` here.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import polars as pl
import pytest

pytest.importorskip("nautilus_trader")

from digiquant.data.prices._primitives import atr as atr_expr
from digiquant.data.prices.levels import (
    LevelsConfig,
    augment,
    compute_levels,
    trail_stop,
)
from nautilus_trader.indicators import AverageTrueRange, MovingAverageType
from nautilus_trader.model.objects import Price, Quantity

pytestmark = pytest.mark.unit


def _bars(n: int = 80) -> pl.DataFrame:
    closes: list[float] = []
    price = 100.0
    for i in range(n):
        price += 2.0 * math.sin(i / 5.0) + (i % 7 - 3) * 0.05
        closes.append(price)
    return pl.DataFrame(
        {
            "timestamp": [date(2024, 1, 1) + timedelta(days=i) for i in range(n)],
            "open": [c - 0.2 for c in closes],
            "high": [c + 1.0 for c in closes],
            "low": [c - 1.0 for c in closes],
            "close": closes,
            "volume": [1_000_000.0] * n,
        }
    )


def test_atr_parity_with_nautilus_wilder_online_series() -> None:
    """Our batch ATR must equal Nautilus' online Wilder ATR bar-for-bar.

    That equality is also the causality proof: the online indicator only ever
    sees past bars, so a batch value matching it cannot have looked ahead.
    """
    cfg = LevelsConfig(atr_len=14)
    df = _bars()
    ours = df.select(atr_expr(cfg.atr_len).alias("atr"))["atr"].to_list()
    naut = AverageTrueRange(cfg.atr_len, MovingAverageType.WILDER)
    for i, row in enumerate(df.iter_rows(named=True)):
        naut.update_raw(row["high"], row["low"], row["close"])
        if i < cfg.atr_len - 1:
            assert ours[i] is None
            continue
        assert ours[i] == pytest.approx(naut.value, abs=1e-9), i


def test_augment_matches_nautilus_streaming_prefixes() -> None:
    """Levels derivations at row i equal a recompute over df[:i+1] (no lookahead)."""
    cfg = LevelsConfig()
    df = _bars(120)
    full = augment(df, cfg)
    for i in (30, 60, 119):
        sliced = augment(df[: i + 1], cfg).tail(1).to_dicts()[0]
        row = full.row(i, named=True)
        for col in ("atr_14", "k_eff", "don_high_prev", "don_low_prev", "piv_low", "piv_high"):
            if row[col] is None:
                assert sliced[col] is None, (i, col)
            else:
                assert sliced[col] == pytest.approx(row[col], abs=1e-9), (i, col)


def test_bracket_geometry_is_nautilus_price_representable() -> None:
    result = compute_levels(_bars(), "long", LevelsConfig(), pair="EUR/USD")
    entry = Price.from_str(repr(result.entry_ref))
    stop = Price.from_str(repr(result.sl))
    assert stop.as_double() < entry.as_double()
    ladder = [Price.from_str(repr(rung.price)) for rung in result.tp_ladder]
    assert all(price.as_double() > entry.as_double() for price in ladder)
    assert [p.as_double() for p in ladder] == sorted(p.as_double() for p in ladder)
    assert Quantity.from_str("1").as_double() == 1.0

    short = compute_levels(_bars(), "short", LevelsConfig(), pair="EUR/USD")
    assert (
        Price.from_str(repr(short.sl)).as_double()
        > Price.from_str(repr(short.entry_ref)).as_double()
    )


def test_trail_stop_never_loosens_against_the_position() -> None:
    cfg = LevelsConfig(trail_atr=2.0)
    atr_value = 1.0
    high_water = 100.0
    stop = trail_stop(
        direction="long",
        high_water=high_water,
        low_water=100.0,
        entry_ref=100.0,
        atr_value=atr_value,
        cfg=cfg,
    )
    # Walk a path that makes a new high then pulls back; the stop must ratchet up only.
    for price in (103.0, 101.0, 106.0, 104.0, 110.0):
        high_water = max(high_water, price)
        new_stop = trail_stop(
            direction="long",
            high_water=high_water,
            low_water=100.0,
            entry_ref=100.0,
            atr_value=atr_value,
            cfg=cfg,
        )
        assert new_stop >= stop - 1e-12
        stop = new_stop
    assert stop == pytest.approx(high_water - 2.0 * atr_value)

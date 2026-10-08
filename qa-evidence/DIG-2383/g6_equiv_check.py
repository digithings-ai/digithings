#!/usr/bin/env python3
"""Independently test the G6 'equivalent mutant' claim.

The author says mutating EITHER side of _wilder_rsi's min_periods alone leaves
the emitted RSI Series byte-identical, so my survivor was an equivalent mutant
and not a test gap. Do not take that on trust: rebuild both variants of the
function inline and compare full Series across lengths and adversarial inputs.
"""
from __future__ import annotations

import itertools
import math
import sys

import polars as pl

RNG = __import__("random").Random(20261008)


def _rsi(close: pl.Series, length: int, *, min_gain: int, min_loss: int) -> pl.Series:
    frame = pl.DataFrame({"close": close})
    delta = pl.col("close").diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0.0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0.0)
    avg_gain = gain.ewm_mean(alpha=1.0 / length, adjust=False, min_periods=min_gain)
    avg_loss = loss.ewm_mean(alpha=1.0 / length, adjust=False, min_periods=min_loss)
    rsi = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return frame.select(rsi.alias("rsi"))["rsi"]


def same(a, b) -> bool:
    """NaN-aware element equality: nan == nan for our purposes."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


def cases():
    n = 400
    # 1. plain random walk
    walk, p = [], 100.0
    for _ in range(n):
        p *= math.exp(RNG.gauss(0, 0.02))
        walk.append(p)
    yield "random-walk", pl.Series("c", walk, dtype=pl.Float64)

    # 2. monotonically rising: avg_loss is identically zero -> division by zero
    yield "monotone-rising", pl.Series("c", [100.0 + i for i in range(n)], dtype=pl.Float64)

    # 3. monotonically falling: avg_gain is identically zero
    yield "monotone-falling", pl.Series("c", [100.0 - i for i in range(n)], dtype=pl.Float64)

    # 4. perfectly flat: both averages zero
    yield "flat", pl.Series("c", [100.0] * n, dtype=pl.Float64)

    # 5. regime flip: gains then losses
    up = [100.0 + i * 0.5 for i in range(200)]
    dn = [up[-1] - i * 0.5 for i in range(200)]
    yield "regime-flip", pl.Series("c", up + dn, dtype=pl.Float64)

    # 6. alternating up/down -> tiny alternating gains and losses
    alt, p = [], 100.0
    for i in range(n):
        p += 0.7 if i % 2 else -0.7
        alt.append(p)
    yield "alternating", pl.Series("c", alt, dtype=pl.Float64)

    # 7. short series, just long enough for length=30 warmup plus a little
    yield "short-40", pl.Series("c", [100.0 + (i % 7) for i in range(40)], dtype=pl.Float64)

    # 8. real-looking BTC scale with jumps
    btc, p = [], 30000.0
    for _ in range(n):
        p *= math.exp(RNG.gauss(0.001, 0.05))
        btc.append(p)
    yield "btc-like-jumpy", pl.Series("c", btc, dtype=pl.Float64)


VARIANTS = {
    "baseline (length,length)": (None, None),
    "avg_loss only -> 1": (None, 1),
    "avg_gain only -> 1": (1, None),
    "BOTH -> 1": (1, 1),
}

failures = 0
checked = 0
for length in (2, 3, 5, 14, 30, 50):
    for name, close in cases():
        out = {}
        for label, (mg, ml) in VARIANTS.items():
            out[label] = _rsi(close, length, min_gain=mg or length, min_loss=ml or length)
        base = out["baseline (length,length)"]

        # Claim A: each single-side mutant is byte-identical to baseline.
        for label in ("avg_loss only -> 1", "avg_gain only -> 1"):
            checked += 1
            m = out[label]
            same_values = all(same(x, y) for x, y in zip(base.to_list(), m.to_list()))
            same_nulls = m.null_count() == base.null_count()
            same_len = len(base) == len(m)
            if not (same_values and same_nulls and same_len):
                failures += 1
                print(f"  CLAIM-A VIOLATED length={length} case={name} mutant={label}")
                print(f"    base nulls={base.null_count()} head={base.head(8).to_list()}")
                print(f"    mut  nulls={m.null_count()} head={m.head(8).to_list()}")
                for i, (b, x) in enumerate(zip(base.to_list(), m.to_list())):
                    if not same(b, x):
                        print(f"    first diff at {i}: base={b!r} mut={x!r}")
                        break

        # Claim B: the joint mutant DOES differ, and differs only by emitting
        # values earlier (never by changing a value that baseline emits).
        checked += 1
        joint = out["BOTH -> 1"]
        jl, bl = joint.to_list(), base.to_list()
        differs = not all(same(x, y) for x, y in zip(bl, jl))
        mismatched_non_null = [
            (i, b, x) for i, (b, x) in enumerate(zip(bl, jl))
            if b is not None and not same(b, x)
        ]
        earlier = [
            i for i, (b, x) in enumerate(zip(bl, jl)) if b is None and x is not None
        ]
        if not differs or mismatched_non_null:
            failures += 1
            print(f"  CLAIM-B VIOLATED length={length} case={name} "
                  f"differs={differs} value_mismatches={mismatched_non_null[:3]}")
        if earlier and max(earlier) >= length - 1:
            failures += 1
            print(f"  CLAIM-B odd: joint emits before warmup ends? len={len(earlier)} "
                  f"max_idx={max(earlier)} length={length}")

print(f"\nchecked {checked} claims across 6 lengths x {len(list(cases()))} input cases")
print("G6 EQUIVALENT-MUTANT CLAIM: CONFIRMED" if failures == 0
      else f"G6 EQUIVALENT-MUTANT CLAIM: REFUTED ({failures} violations)")
sys.exit(0 if failures == 0 else 1)
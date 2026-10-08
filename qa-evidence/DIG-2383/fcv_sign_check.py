#!/usr/bin/env python3
"""Why did FCV1 (fast_crash_vol_z sign flip) survive?

The class TestFastCrashVol has test_vol_spike_is_sell_favourable which asserts
min(present) < 0.0 over z[60:100]. Flipping `(-z)` to `z` should break that.
It did not. This script recomputes both variants and prints exactly what each
assertion in TestFastCrashVol sees, so the reason is evidence and not a guess.
"""
from __future__ import annotations

import datetime as dt

import polars as pl

SIGMA_FLOOR = 1e-12
DEFAULT_ROLLING_WINDOW = 90
MIN_SAMPLES = 20


def causal_rolling_z(values, *, window=DEFAULT_ROLLING_WINDOW, min_samples=MIN_SAMPLES):
    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=SIGMA_FLOOR)).clip(-3.0, 3.0)


def core(dates, btc_price, *, window=14, min_samples=7, z_window=90, z_min_samples=20, flip=True):
    if len(dates) != len(btc_price):
        raise ValueError("dates and btc_price must be the same length")
    log_ret = btc_price.log() - btc_price.shift(1).log()
    realized_vol = log_ret.rolling_std(window_size=window, min_samples=min_samples)
    z = causal_rolling_z(realized_vol, window=z_window, min_samples=z_min_samples)
    return (-z if flip else z).alias("fast_crash_vol")


def dates(n: int) -> pl.Series:
    return pl.Series("date", [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(n)], dtype=pl.Date)


def calm_then_spike_then_calm() -> pl.Series:
    prices: list[float] = [50_000.0]
    steps = [1.001] * 60 + [1.08, 0.93, 1.07, 0.94, 1.06, 0.95, 1.05] * 5 + [1.001] * 130
    for step in steps:
        prices.append(prices[-1] * step)
    return pl.Series("value", prices, dtype=pl.Float64)


price = calm_then_spike_then_calm()
n = len(price)
d = dates(n)
orig = core(d, price, flip=True).to_list()
mut = core(d, price, flip=False).to_list()

print(f"series length = {n}")
print(f"original: nulls in z[60:100] = {sum(v is None for v in orig[60:100])}"
      f"   present = {sum(v is not None for v in orig[60:100])}")
print(f"mutant  : nulls in z[60:100] = {sum(v is None for v in mut[60:100])}"
      f"   present = {sum(v is not None for v in mut[60:100])}")

for label, z in (("ORIGINAL (-z)", orig), ("MUTANT (z)", mut)):
    spike = [v for v in z[60:100] if v is not None]
    allp = [v for v in z if v is not None]
    print(f"\n{label}")
    print(f"  z[60:100] present n={len(spike)}  min={min(spike) if spike else None}"
          f"  max={max(spike) if spike else None}")
    print(f"  whole series present n={len(allp)}  min={min(allp) if allp else None}"
          f"  max={max(allp) if allp else None}")
    print(f"  z[-1] = {z[-1]}")
    print(f"  first 6 present values: {[round(v,4) for v in allp[:6]]}")
    # what index range is actually non-null?
    nn = [i for i, v in enumerate(z) if v is not None]
    print(f"  non-null index range: {nn[0] if nn else None}..{nn[-1] if nn else None}"
          f"  (count {len(nn)})")

print("\n--- which TestFastCrashVol assertions change? ---")
spike_o = [v for v in orig[60:100] if v is not None]
spike_m = [v for v in mut[60:100] if v is not None]
print(f"test_vol_spike_is_sell_favourable : min(orig)={min(spike_o):.6f} < 0 -> {min(spike_o) < 0}"
      f" | min(mut)={min(spike_m):.6f} < 0 -> {min(spike_m) < 0}")
print(f"test_decays_back_to_zero           : |orig[-1]|={abs(orig[-1]):.2e} |mut[-1]|={abs(mut[-1]):.2e}"
      f"   (symmetric under a sign flip)")
print(f"test_bounded_to_three              : symmetric under a sign flip")
print(f"test_flat_price_is_flat_zero       : symmetric under a sign flip")
print(f"test_aliased_and_uses_default_windows: only checks null prefix + last non-null (symmetric)")
print(f"test_windows_are_tunable           : only checks null/non-null positions (symmetric)")
print(f"test_length_mismatch_rejected      : raises before any z (symmetric)")
print("\nConclusion: every assertion in TestFastCrashVol is invariant under z -> -z")
print("except test_vol_spike_is_sell_favourable, and that one only looks at z[60:100].")
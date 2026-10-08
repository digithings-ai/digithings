#!/usr/bin/env python3
"""Why does dropping .log() in _log_ratio_sign_flipped_z survive?

Hypothesis: the onchain family tests all run with a degenerate window (2), and a
geometric input makes the log and level paths produce the SAME rolling z. That
would mean no test in the class can see the log transform at all.
"""
from __future__ import annotations

import math

import polars as pl

SIGMA_FLOOR = 1e-12


def crz(values, *, window, min_samples):
    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=SIGMA_FLOOR)).clip(-3.0, 3.0)


def log_ratio_z(src, *, window, min_samples, do_log=True):
    frame = pl.DataFrame({"value": src})
    positive = frame.select(
        pl.when(pl.col("value") > 0).then(pl.col("value")).otherwise(None)
    )["value"]
    lv = positive.log() if do_log else positive
    return (-crz(lv, window=window, min_samples=min_samples)).alias("x")


def close(a, b, tol=1e-9):
    """NaN/None-aware approximate equality, like pytest.approx."""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b, strict=True):
        if x is None or y is None:
            if x is not y:
                return False
            continue
        if not math.isclose(x, y, rel_tol=tol, abs_tol=tol):
            return False
    return True


def geom(n, step, start):
    return pl.Series("v", [start * (step**i) for i in range(n)], dtype=pl.Float64)


print("=" * 78)
print("HYPOTHESIS: at window=2/min_samples=1 a geometric input makes log and level identical")
print("=" * 78)
for n, step in ((40, 1.01), (40, 0.99), (120, 1.001), (120, 1.05)):
    g = geom(n, step, 2.0)
    lg = log_ratio_z(g, window=2, min_samples=1, do_log=True).to_list()
    lv = log_ratio_z(g, window=2, min_samples=1, do_log=False).to_list()
    const_lg = {None if v is None else round(v, 10) for v in lg}
    print(f"  geom(n={n}, step={step}) @ window=2/min=1: log==level? {close(lg, lv)}"
          f"   log values seen: {sorted(x for x in const_lg if x is not None)}")

print()
print("=" * 78)
print("And at the production windows the two paths do differ on a geometric input")
print("=" * 78)
g = geom(200, 1.01, 4.0)
for window, ms in ((2, 1), (30, 15), (90, 20)):
    lg = log_ratio_z(g, window=window, min_samples=ms, do_log=True).to_list()
    lv = log_ratio_z(g, window=window, min_samples=ms, do_log=False).to_list()
    print(f"  window={window:>2}/min={ms:>2}: log==level? {close(lg, lv)}")

print()
print("=" * 78)
print("Scale invariance (the author's actual assertion in test_log_transformed_not_level)")
print("=" * 78)
n = 120
base = geom(n, 1.01, 4.0)
scaled = pl.Series("v", [v * 37.0 for v in base.to_list()], dtype=pl.Float64)
lg_b = log_ratio_z(base, window=2, min_samples=1, do_log=True).to_list()
lg_s = log_ratio_z(scaled, window=2, min_samples=1, do_log=True).to_list()
lv_b = log_ratio_z(base, window=2, min_samples=1, do_log=False).to_list()
lv_s = log_ratio_z(scaled, window=2, min_samples=1, do_log=False).to_list()
print(f"  log   path, x37 : equal? {close(lg_b, lg_s)}   -> asserted by the test, and TRUE")
print(f"  level path, x37 : equal? {close(lv_b, lv_s)}   -> ALSO true")
print("  -> scale invariance is a property of the rolling z (both numerator and")
print("     denominator scale linearly), NOT of the log transform. The test asserts")
print("     a real property, but it is the wrong property: it cannot fail for a")
print("     level-based implementation.")

print()
print("=" * 78)
print("What DOES distinguish log from level: a multiplicative jump, not a ramp")
print("=" * 78)
n = 200
raw = [100.0] * n
for k in (118, 119, 120, 121, 122):
    raw[k] = 900.0
spike = pl.Series("v", raw, dtype=pl.Float64)
for window, ms in ((2, 1), (30, 15), (90, 20)):
    lg = log_ratio_z(spike, window=window, min_samples=ms, do_log=True).to_list()
    lv = log_ratio_z(spike, window=window, min_samples=ms, do_log=False).to_list()
    peak_lg = max((v for v in lg[115:] if v is not None), default=None)
    peak_lv = max((v for v in lv[115:] if v is not None), default=None)
    same = close(lg, lv)
    print(f"  window={window:>2}/min={ms:>2}: equal? {same}"
          f"   peak sustained |z| log={peak_lg} level={peak_lv}")
print("  -> log path shows a ratio-move as ~log(9)=2.20 sigma; the level path divides a")
print("     4-day 900 spike against a 100 baseline and reports -3.0 (saturated), then")
print("     has to wash the raw level out of the rolling mean. The two disagree, so a")
print("     spike test pins the transform. A ramp/scale test cannot.")
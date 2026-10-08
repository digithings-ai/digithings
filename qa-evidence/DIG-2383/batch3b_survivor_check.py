#!/usr/bin/env python3
"""Chase the three batch3b survivors: real gaps or equivalent mutants?

ON2 : _log_ratio_sign_flipped_z drops .log()
FCV1: fast_crash_vol_z drops the (-) sign flip      (root cause already found)
FCV3: fast_crash_vol_z rolling_std min_samples -> 1

For each, find whether ANY observable input exists, and if so, what assertion
the author could have written that would have caught it.
"""
from __future__ import annotations

import datetime as dt

import polars as pl

SIGMA_FLOOR = 1e-12
DEFAULT_ROLLING_WINDOW = 90
MIN_SAMPLES = 20


def crz(values, *, window=DEFAULT_ROLLING_WINDOW, min_samples=MIN_SAMPLES):
    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=SIGMA_FLOOR)).clip(-3.0, 3.0)


def dates(n):
    return pl.Series("date", [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(n)], dtype=pl.Date)


def log_ratio_z(src, *, window=DEFAULT_ROLLING_WINDOW, min_samples=MIN_SAMPLES, do_log=True, name="x"):
    frame = pl.DataFrame({"value": src})
    positive = frame.select(
        pl.when(pl.col("value") > 0).then(pl.col("value")).otherwise(None)
    )["value"]
    log_values = positive.log() if do_log else positive
    return (-crz(log_values, window=window, min_samples=min_samples)).alias(name)


def fcv(prices, *, window=14, min_samples=7, z_window=90, z_min_samples=20, flip=True, vol_min=None):
    log_ret = prices.log() - prices.shift(1).log()
    realized_vol = log_ret.rolling_std(window_size=window, min_samples=vol_min or min_samples)
    z = crz(realized_vol, window=z_window, min_samples=z_min_samples)
    return (-z if flip else z).alias("fast_crash_vol")


def cmp(a, b, label):
    ok = (
        len(a) == len(b)
        and a.null_count() == b.null_count()
        and a.cast(pl.Float64).fill_nan(None).to_list() == b.cast(pl.Float64).fill_nan(None).to_list()
    )
    print(f"  {label}: {'IDENTICAL (equivalent mutant)' if ok else 'DIFFERENT (observable)'}")
    return not ok


print("=" * 78)
print("ON2 - is the log transform observable, and does the existing test miss it?")
print("=" * 78)
n = 120
geom_up = [4.0 * (1.01**i) for i in range(n)]
base_log = log_ratio_z(pl.Series("v", geom_up), do_log=True).to_list()
base_lvl = log_ratio_z(pl.Series("v", geom_up), do_log=False).to_list()
print(f"\nA) smooth geometric ramp, window=90/min=20: "
      f"{'IDENTICAL' if base_log == base_lvl else 'DIFFERENT'}  "
      "(this is why the mutation survives a normal case)")

# The author's test: scale invariance by 37.
scaled_log = log_ratio_z(pl.Series("v", [v * 37.0 for v in geom_up]), do_log=True).to_list()
scaled_lvl = log_ratio_z(pl.Series("v", [v * 37.0 for v in geom_up]), do_log=False).to_list()
print(f"B) scale invariance x37, LOG path: {'holds' if scaled_log == base_log else 'broken'}"
      f"   | LEVEL path: {'holds' if scaled_lvl == base_lvl else 'broken'}")
print("   -> scale invariance holds for BOTH, so test_log_transformed_not_level")
print("      cannot distinguish log from level. It asserts a property that does")
print("      not test the thing its name and docstring claim.")

# What DOES distinguish them: a multiplicative spike. Source docstring says the
# point is that 'a bull-market spike would otherwise dominate a level-based std'.
n = 200
spike = [100.0] * 120
for k in (118, 119, 120, 121, 122):
    spike[k] = 900.0
for i in range(123, n):
    spike[i] = 100.0
z_log = log_ratio_z(pl.Series("v", spike), do_log=True).to_list()
z_lvl = log_ratio_z(pl.Series("v", spike), do_log=False).to_list()
peak_log = max(v for v in z_log[115:] if v is not None)
peak_lvl = max(v for v in z_lvl[115:] if v is not None)
print(f"\nC) flat 100 with a 4-day 900x spike, sustained z after the spike:")
print(f"     log path   peak |z| after spike = {peak_log:.4f}")
print(f"     level path peak |z| after spike = {peak_lvl:.4f}")
print(f"     -> {'DISTINGUISHABLE' if abs(peak_log - peak_lvl) > 1e-6 else 'not distinguishable'}")
print(f"     (level path is {'worse' if peak_lvl > peak_log else 'better'}: the raw level"
      f" {peak_lvl:.2f} vs log {peak_log:.2f})")

print()
print("=" * 78)
print("FCV3 - is rolling_std min_samples=1 observable (or masked like CZ4/G6)?")
print("=" * 78)
steps = [1.001] * 60 + [1.08, 0.93, 1.07, 0.94, 1.06, 0.95, 1.05] * 5 + [1.001] * 130
prices = [50_000.0]
for s in steps:
    prices.append(prices[-1] * s)
p = pl.Series("value", prices, dtype=pl.Float64)
print(f"  default windows (14/7 vol, 90/20 z):")
cmp(fcv(p), fcv(p, vol_min=1), "full suite default windows")
diff = 0
for vol_win, vol_min in ((5, 3), (14, 7), (20, 20), (30, 2)):
    for z_win, z_min in ((20, 5), (90, 20), (60, 10)):
        for nlen in (60, 120, 226):
            pp = p[:nlen]
            try:
                a, b = fcv(pp, window=vol_win, min_samples=vol_min, z_window=z_win, z_min_samples=z_min), \
                       fcv(pp, window=vol_win, min_samples=vol_min, z_window=z_win, z_min_samples=z_min, vol_min=1)
            except Exception as exc:  # noqa: BLE001
                print(f"  vol({vol_win}/{vol_min}) z({z_win}/{z_min}) n={nlen}: raised {exc}")
                continue
            if cmp.__doc__ is None:
                pass
            ok = (
                a.null_count() == b.null_count()
                and a.cast(pl.Float64).fill_nan(None).to_list() == b.cast(pl.Float64).fill_nan(None).to_list()
            )
            if not ok:
                diff += 1
                print(f"    *** vol({vol_win}/{vol_min}) z({z_win}/{z_min}) n={nlen}: DIFFERENT")
print(f"  observable configurations found: {diff}")
print("  -> min_samples on the numerator-side vol series is masked whenever the")
print("     z window's own min_samples is larger; only reachable with a smaller")
print("     z_min_samples than the vol warmup.")

print()
print("=" * 78)
print("FCV1 - candidate assertions that WOULD pin the sign")
print("=" * 78)
price = pl.Series("value", prices, dtype=pl.Float64)
d = dates(len(price))
orig = fcv(price).to_list()
mut = fcv(price, flip=False).to_list()
cands = {
    "min(z[60:100]) < 0.0  [what the suite has]": lambda z: min(v for v in z[60:100] if v is not None) < 0.0,
    "max(z[60:100]) < -1.0": lambda z: max(v for v in z[60:100] if v is not None) < -1.0,
    "mean(z[60:95]) < -1.0": lambda z: (
        lambda vs: sum(vs) / len(vs) < -1.0)([v for v in z[60:95] if v is not None]),
    "min(z[60:95]) <= -2.0": lambda z: min(v for v in z[60:95] if v is not None) <= -2.0,
    "mean(burst) < mean(calm-before)": lambda z: (
        lambda b, c: sum(b) / len(b) < sum(c) / len(c))(
            [v for v in z[60:95] if v is not None],
            [v for v in z[20:60] if v is not None]),
}
for label, fn in cands.items():
    try:
        o = fn(orig)
    except Exception as exc:  # noqa: BLE001
        o = f"raised {exc}"
    try:
        m = fn(mut)
    except Exception as exc:  # noqa: BLE001
        m = f"raised {exc}"
    verdict = "PINS THE SIGN" if (o is True and m is False) else "still blind"
    print(f"  {verdict:14s} {label:42s} orig={o} mut={m}")
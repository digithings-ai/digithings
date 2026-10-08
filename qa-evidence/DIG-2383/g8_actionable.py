"""Make G8 actionable: find an assertion on the author's own fixture that is
discriminating between the original (-z) and the sign-flip mutant (z).

Fixture = TestFastCrashVol._calm_then_spike_then_calm: 60 geometric bars,
then 7 alternating steps repeated 5x (the burst), then 130 geometric bars.
Burst therefore occupies price indices 61..95.
"""

from __future__ import annotations

import math

import polars as pl

_SIGMA_FLOOR = 1e-12


def causal_rolling_z(values, *, window=90, min_samples=20):
    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=_SIGMA_FLOOR)).clip(-3.0, 3.0)


def fixture() -> pl.Series:
    prices = [50_000.0]
    steps = [1.001] * 60 + [1.08, 0.93, 1.07, 0.94, 1.06, 0.95, 1.05] * 5 + [1.001] * 130
    for step in steps:
        prices.append(prices[-1] * step)
    return pl.Series("value", prices, dtype=pl.Float64)


def vol(price, window=14, min_samples=7):
    log_ret = price.log() - price.shift(1).log()
    return log_ret.rolling_std(window_size=window, min_samples=min_samples)


def fcv(price, sign=-1.0, window=14, min_samples=7, z_window=90, z_min_samples=20):
    z = causal_rolling_z(vol(price, window, min_samples), window=z_window, min_samples=z_min_samples)
    return (sign * z).alias("fast_crash_vol")


def stats(series: pl.Series, lo: int, hi: int) -> tuple[float | None, float | None, int]:
    seg = series[lo:hi].to_list()
    present = [v for v in seg if v is not None]
    if not present:
        return None, None, 0
    return min(present), max(present), len(present)


def main() -> int:
    p = fixture()
    n = len(p)
    print(f"fixture length: {n} (burst = price indices 61..95)")
    vol_series = vol(p)
    vol_first = next(i for i, v in enumerate(vol_series.to_list()) if v is not None)
    peak_vol_i = max(range(n), key=lambda i: (vol_series[i] if vol_series[i] is not None else -1.0))
    print(f"realized vol first non-null index: {vol_first}")
    print(f"peak realized-vol index: {peak_vol_i}  value: {vol_series[peak_vol_i]:.6f}")

    orig = fcv(p, sign=-1.0)
    mut = fcv(p, sign=+1.0)

    orig_first = next(i for i, v in enumerate(orig.to_list()) if v is not None)
    mut_first = next(i for i, v in enumerate(mut.to_list()) if v is not None)
    print(f"\nfirst non-null z -- original: {orig_first}   mutant: {mut_first}")

    print("\n--- candidate windows (min, max, count_present) ---")
    for label, lo, hi in (
        ("author's z[60:100]", 60, 100),
        ("burst-only z[61:95]", 61, 95),
        ("z[55:101]", 55, 101),
        ("peak-vol +-4 z[%d:%d]" % (max(0, peak_vol_i - 4), min(n, peak_vol_i + 5)), None, None),
    ):
        if lo is None:
            lo, hi = max(0, peak_vol_i - 4), min(n, peak_vol_i + 5)
        o = stats(orig, lo, hi)
        m = stats(mut, lo, hi)
        print(f"{label:<30} orig min={o[0]:+.6f} max={o[1]:+.6f} n={o[2]}"
              f"   |  mut min={m[0]:+.6f} max={m[1]:+.6f} n={m[2]}")

    print("\n--- candidate assertions: does it pass ORIGINAL and reject MUTANT? ---")
    o_list = orig.to_list()
    m_list = mut.to_list()
    cands = [
        ("min(z[60:100]) < 0  (the author's current one)",
         lambda s: min(v for v in s[60:100] if v is not None) < 0.0),
        ("max(z[60:100]) < 0",
         lambda s: max(v for v in s[60:100] if v is not None) < 0.0),
        ("max(z[61:95]) < 0",
         lambda s: max(v for v in s[61:95] if v is not None) < 0.0),
        ("max(z[61:95]) < -1.0",
         lambda s: max(v for v in s[61:95] if v is not None) < -1.0),
        ("min(z[61:95]) <= -1.0",
         lambda s: min(v for v in s[61:95] if v is not None) <= -1.0),
        ("z[peak_vol_index] < -1.0",
         lambda s: s[peak_vol_i] < -1.0),
        ("z[peak_vol_index] < 0",
         lambda s: s[peak_vol_i] < 0.0),
        ("every burst bar negative: all(v<0 for v in z[61:95])",
         lambda s: all(v < 0.0 for v in s[61:95] if v is not None)),
        ("first non-null index == 26",
         lambda s: next(i for i, v in enumerate(s) if v is not None) == 26),
        ("first non-null index == orig first (26)",
         lambda s: next(i for i, v in enumerate(s) if v is not None) == orig_first),
    ]
    for label, fn in cands:
        try:
            o = fn(o_list)
        except Exception as exc:  # noqa: BLE001
            o = f"ERR {exc}"
        try:
            m = fn(m_list)
        except Exception as exc:  # noqa: BLE001
            m = f"ERR {exc}"
        good = "YES  <-- discriminating" if (o is True and m is False) else "no"
        print(f"  {label:<48} orig={o!s:<6} mut={m!s:<6} {good}")

    print("\n--- FCV3: the same fixture under realized-vol min_samples=7 vs 1 ---")
    a = fcv(p, window=14, min_samples=7)
    b = fcv(p, window=14, min_samples=1)
    af = next(i for i, v in enumerate(a.to_list()) if v is not None)
    bf = next(i for i, v in enumerate(b.to_list()) if v is not None)
    ndiff = sum(
        1
        for x, y in zip(a.to_list(), b.to_list())
        if not (
            (x is None and y is None)
            or (x is not None and y is not None and math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-15))
        )
    )
    last = max(
        (
            i
            for i, (x, y) in enumerate(zip(a.to_list(), b.to_list()))
            if not (
                (x is None and y is None)
                or (x is not None and y is not None and math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-15))
            )
        ),
        default=-1,
    )
    print(f"first non-null: min_samples=7 -> {af}   min_samples=1 -> {bf}")
    print(f"differing positions: {ndiff}   last differing index: {last} (len={n})")
    print(f"identical past index {last}: {last + 1 >= af + 90}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Where exactly does FCV3 differ? Split the difference into two kinds.

kind A -- the mutant emits a VALUE where the original emits NULL
          (warmup/pin difference: a different null prefix)
kind B -- both emit a value but the VALUES differ
          (a real numeric difference)

Prints, per case, the count of each kind and the last index of each kind,
plus the concrete pairs for the production default (vol 14/7, z 90/20).
"""

from __future__ import annotations

import math
import random

import polars as pl

_SIGMA_FLOOR = 1e-12


def causal_rolling_z(values, *, window=90, min_samples=20):
    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=_SIGMA_FLOOR)).clip(-3.0, 3.0)


def variant(btc_price, *, window, min_samples, z_window, z_min_samples, mutant):
    log_ret = btc_price.log() - btc_price.shift(1).log()
    vol_min = 1 if mutant else min_samples
    realized_vol = log_ret.rolling_std(window_size=window, min_samples=vol_min)
    z = causal_rolling_z(realized_vol, window=z_window, min_samples=z_min_samples)
    return (-z).alias("fast_crash_vol")


def classify(a: pl.Series, b: pl.Series) -> tuple[int, int, int, int, list]:
    null_but_value = 0  # original null, mutant value
    value_but_null = 0  # original value, mutant null
    both_value_diff = 0
    last_val_idx = -1
    last_any = -1
    pairs = []
    for i, (x, y) in enumerate(zip(a.to_list(), b.to_list())):
        if x is None and y is None:
            continue
        last_any = i
        if x is None:
            null_but_value += 1
            pairs.append((i, "A", None, y))
        elif y is None:
            value_but_null += 1
            pairs.append((i, "B", x, None))
        elif not math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-15):
            both_value_diff += 1
            last_val_idx = i
            pairs.append((i, "V", x, y))
    return null_but_value, value_but_null, both_value_diff, last_val_idx, (last_any, pairs)


def cases(rng, n):
    out = []
    out.append(("flat", pl.Series([100.0] * n)))
    out.append(("geom-up", pl.Series([100.0 * (1.01**i) for i in range(n)])))
    out.append(("random-walk", None))
    px = [100.0]
    for _ in range(n - 1):
        px.append(max(1.0, px[-1] * math.exp(rng.gauss(0.0004, 0.021))))
    out[-1] = ("random-walk", pl.Series(px))
    px = [100.0]
    for _ in range(n - 1):
        step = math.exp(rng.gauss(0.0, 0.004))
        if rng.random() < 0.04:
            step *= rng.choice((6.0, 9.0))
        px.append(max(1.0, px[-1] * step))
    out.append(("jumpy-spikes", pl.Series(px)))
    out.append(
        ("alternating-degenerate", pl.Series([100.0 * (1.03 if i % 2 else 0.97) for i in range(n)]))
    )
    return out


PROD = dict(window=14, min_samples=7, z_window=90, z_min_samples=20)


def main() -> int:
    rng = random.Random(20261008)
    print("=== FCV3 at PRODUCTION defaults: vol window=14 min_samples=7, z window=90 min_samples=20")
    print(f"{'n':>4} {'case':<22} {'origNull1st':>11} {'mutNull1st':>10} "
          f"{'A(null->val)':>12} {'B(val->null)':>12} {'V(both differ)':>14} {'lastV':>6}")
    for n in (60, 120, 226):
        for name, price in cases(rng, n):
            a = variant(price, mutant=False, **PROD)
            b = variant(price, mutant=True, **PROD)
            A, B, V, lastV, _ = classify(a, b)
            first_a = next((i for i, v in enumerate(a.to_list()) if v is not None), None)
            first_b = next((i for i, v in enumerate(b.to_list()) if v is not None), None)
            print(f"{n:>4} {name:<22} {str(first_a):>11} {str(first_b):>10} "
                  f"{A:>12} {B:>12} {V:>14} {lastV:>6}")

    print()
    print("=== the only kind-V cases, sample pairs ===")
    for n in (120, 226):
        for name, price in cases(rng, n):
            if name != "alternating-degenerate":
                continue
            a = variant(price, mutant=False, **PROD)
            b = variant(price, mutant=True, **PROD)
            A, B, V, lastV, (last_any, pairs) = classify(a, b)
            vs = [p for p in pairs if p[1] == "V"]
            print(f"n={n} {name}: A={A} B={B} V={V} last_diff_index={last_any}")
            for p in vs[:6]:
                print(f"    idx={p[0]:>4} orig={p[2]!r:>24} mutant={p[3]!r:>24}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

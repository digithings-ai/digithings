"""Adjudicate FCV3: realized_vol rolling_std(min_samples=min_samples) -> min_samples=1.

Equivalent-mutant test (same discipline as G6 / CZ4 / AD4):
rebuild BOTH variants of the fast_crash_vol_z pipeline inline and compare the
final Series element by element, NaN-aware.

A surviving mutant is only a test gap if some grid point shows an observable
difference. If every point is identical, the mutant is equivalent and there is
no gap -- exactly the G6 lesson.
"""

from __future__ import annotations

import math
import random

import polars as pl

_SIGMA_FLOOR = 1e-12


def causal_rolling_z(
    values: pl.Series, *, window: int = 90, min_samples: int = 20
) -> pl.Series:
    if window < 2:
        raise ValueError("window must be >= 2")
    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=_SIGMA_FLOOR)).clip(-3.0, 3.0)


def variant(btc_price: pl.Series, *, window, min_samples, z_window, z_min_samples, mutant):
    log_ret = btc_price.log() - btc_price.shift(1).log()
    vol_min = 1 if mutant else min_samples
    realized_vol = log_ret.rolling_std(window_size=window, min_samples=vol_min)
    z = causal_rolling_z(realized_vol, window=z_window, min_samples=z_min_samples)
    return (-z).alias("fast_crash_vol")


def same(a: pl.Series, b: pl.Series) -> bool:
    if a.len() != b.len():
        return False
    for x, y in zip(a.to_list(), b.to_list()):
        if x is None or y is None:
            if x is not y:
                return False
            continue
        if not math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-15):
            return False
    return True


def make_cases(rng: random.Random, n: int) -> list[tuple[str, pl.Series]]:
    cases: list[tuple[str, pl.Series]] = []
    cases.append(("flat", pl.Series([100.0] * n)))
    cases.append(("geom-up", pl.Series([100.0 * (1.01**i) for i in range(n)])))
    cases.append(("geom-down", pl.Series([100.0 * (0.99**i) for i in range(n)])))
    prices = [100.0]
    for _ in range(n - 1):
        prices.append(max(1.0, prices[-1] * math.exp(rng.gauss(0.0004, 0.021))))
    cases.append(("random-walk", pl.Series(prices)))
    prices = [100.0]
    for _ in range(n - 1):
        step = math.exp(rng.gauss(0.0, 0.004))
        if rng.random() < 0.04:
            step *= rng.choice((6.0, 9.0))
        prices.append(max(1.0, prices[-1] * step))
    cases.append(("jumpy-spikes", pl.Series(prices)))
    prices = [100.0]
    half = n // 2
    for i in range(n - 1):
        drift = 0.004 if i < half else -0.006
        prices.append(max(1.0, prices[-1] * math.exp(rng.gauss(drift, 0.012))))
    cases.append(("regime-flip", pl.Series(prices)))
    cases.append(
        (
            "alternating",
            pl.Series([100.0 * (1.03 if i % 2 else 0.97) for i in range(n)]),
        )
    )
    return cases


def main() -> int:
    rng = random.Random(20261008)
    vol_grid = [(5, 3), (14, 7), (20, 20), (30, 2), (14, 1), (5, 1)]
    z_grid = [(20, 5), (90, 20), (60, 10), (5, 2), (2, 1)]
    lengths = [60, 120, 226]

    checks = 0
    violations: list[str] = []
    for n in lengths:
        for name, price in make_cases(rng, n):
            for window, min_samples in vol_grid:
                for z_window, z_min_samples in z_grid:
                    checks += 1
                    a = variant(
                        price,
                        window=window,
                        min_samples=min_samples,
                        z_window=z_window,
                        z_min_samples=z_min_samples,
                        mutant=False,
                    )
                    b = variant(
                        price,
                        window=window,
                        min_samples=min_samples,
                        z_window=z_window,
                        z_min_samples=z_min_samples,
                        mutant=True,
                    )
                    if not same(a, b):
                        diff_idx = [
                            i
                            for i, (x, y) in enumerate(zip(a.to_list(), b.to_list()))
                            if not (
                                (x is None and y is None)
                                or (
                                    x is not None
                                    and y is not None
                                    and math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-15)
                                )
                            )
                        ]
                        # Steady state of the ORIGINAL: the first index at which the
                        # rolling z window is filled with non-null vol under the
                        # original warmup. Past that point both variants must agree.
                        a_list = a.to_list()
                        vol_first = None
                        for i in range(n):
                            probe = pl.Series(
                                pl.Series(price.to_list()).log().diff().to_list()
                            ).rolling_std(window_size=window, min_samples=min_samples)
                            if probe[i] is not None:
                                vol_first = i
                                break
                        steady = (vol_first + z_window - 1) if vol_first is not None else -1
                        after = [i for i in diff_idx if i >= steady]
                        violations.append(
                            {
                                "n": n,
                                "case": name,
                                "vol": f"{window}/{min_samples}",
                                "z": f"{z_window}/{z_min_samples}",
                                "n_diff": len(diff_idx),
                                "first": diff_idx[0],
                                "last": diff_idx[-1],
                                "steady": steady,
                                "n_after_steady": len(after),
                                "orig_null_prefix": next(
                                    (i for i, v in enumerate(a_list) if v is not None), None
                                ),
                            }
                        )

    print(f"FCV3 checks run: {checks}")
    print(f"FCV3 violations (observable differences): {len(violations)}")
    after_total = sum(v["n_after_steady"] for v in violations)
    print(f"FCV3 differing samples PAST the original's steady state: {after_total}")
    warmup_only = sum(1 for v in violations if v["n_after_steady"] == 0)
    print(f"FCV3 cases where the difference is warmup-only: {warmup_only}/{len(violations)}")
    print()
    hdr = (
        f"{'n':>4} {'case':<13} {'vol':>7} {'z':>7} {'#diff':>6} "
        f"{'first':>6} {'last':>6} {'steady':>7} {'after':>6} {'nullpfx':>8}"
    )
    print(hdr)
    for v in violations:
        print(
            f"{v['n']:>4} {v['case']:<13} {v['vol']:>7} {v['z']:>7} "
            f"{v['n_diff']:>6} {v['first']:>6} {v['last']:>6} "
            f"{v['steady']:>7} {v['n_after_steady']:>6} {str(v['orig_null_prefix']):>8}"
        )
    print(
        "FCV3 EQUIVALENT-MUTANT CLAIM: "
        + ("CONFIRMED" if not violations else "REFUTED -- real test gap")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

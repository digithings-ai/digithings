#!/usr/bin/env python3
"""Are the three batch3a survivors real gaps, or equivalent mutants?

CZ4 : causal_rolling_z mu honours min_samples  -> min_samples=1
AD1 : align_to_dates unique(keep="last")       -> keep="first"
AD4 : align_to_dates drops .sort("date")

A survivor is only a TEST GAP if some input exists where the mutation is
observable. So for each one, rebuild both variants inline and compare the full
output Series over a grid of adversarial inputs. A variant pair that agrees on
every input is an equivalent mutant (the author's G6 argument), not a gap.
"""
from __future__ import annotations

import datetime as dt

import polars as pl

WINDOW = 90
MIN_SAMPLES = 20
SIGMA_FLOOR = 1e-12


def crz(values: pl.Series, window: int, min_samples: int, mu_min: int) -> pl.Series:
    """causal_rolling_z with the mu min_samples injectable (CZ4)."""
    mu = values.rolling_mean(window_size=window, min_samples=mu_min)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=SIGMA_FLOOR)).clip(-3.0, 3.0)


def align(
    dates: pl.Series,
    src_dates: pl.Series,
    src_values: pl.Series,
    *,
    keep: str,
    do_sort: bool,
    forward_fill: bool = True,
) -> pl.Series:
    """align_to_dates with keep / sort injectable (AD1, AD4)."""
    src = pl.DataFrame({"date": src_dates, "value": src_values}).unique(
        subset=["date"], keep=keep
    )
    if do_sort:
        src = src.sort("date")
    joined = pl.DataFrame({"date": dates}).join(src, on="date", how="left")
    if forward_fill:
        joined = joined.with_columns(pl.col("value").forward_fill())
    return joined["value"]


def same(a: pl.Series, b: pl.Series) -> tuple[bool, str]:
    if len(a) != len(b):
        return False, f"len {len(a)} != {len(b)}"
    if a.null_count() != b.null_count():
        return False, f"null_count {a.null_count()} != {b.null_count()}"
    if a.cast(pl.Float64).fill_nan(None).to_list() != b.cast(pl.Float64).fill_nan(None).to_list():
        first = next(
            (
                i
                for i, (x, y) in enumerate(
                    zip(
                        a.cast(pl.Float64).fill_nan(None).to_list(),
                        b.cast(pl.Float64).fill_nan(None).to_list(),
                    )
                )
                if x != y
            ),
            None,
        )
        return False, f"values differ at index {first}"
    return True, "identical"


def day(i: int) -> dt.date:
    return dt.date(2024, 1, 1) + dt.timedelta(days=i)


violations: list[str] = []
checks = 0

# ---------------------------------------------------------------- CZ4
n_cases = 0
for length in (2, 3, 5, 20, 30, 90):
    for min_samples in (1, 2, min(20, length), length):
        for window in (max(2, min(length, WINDOW)),):
            cases = {
                "random-walk": [float((i * 37 % 17) - 8 + (i % 5) * 0.3) for i in range(length)],
                "flat": [3.5] * length,
                "monotone-rising": [1.0 + i * 0.7 for i in range(length)],
                "alternating": [1.0 if i % 2 else -1.0 for i in range(length)],
                "all-null": [None] * length,
                "nulls-then-values": [None] * (length // 2) + [float(i) for i in range(length - length // 2)],
                "one-spike": [1.0] * (length - 1) + [99.0],
                "zeros": [0.0] * length,
            }
            for cname, vals in cases.items():
                s = pl.Series("v", vals, dtype=pl.Float64)
                base = crz(s, window, min_samples, min_samples)
                mut = crz(s, window, min_samples, 1)
                ok, why = same(base, mut)
                checks += 1
                n_cases += 1
                if not ok:
                    violations.append(
                        f"CZ4 OBSERVABLE length={length} min_samples={min_samples} "
                        f"window={window} case={cname}: {why}"
                    )
print(f"CZ4: {checks} claim-checks, {len([v for v in violations if v.startswith('CZ4')])} observable")

# ---------------------------------------------------------------- AD1
d200 = pl.Series("date", [day(i) for i in range(200)], dtype=pl.Date)
dup_variants = {
    "no-duplicates": ([day(i) for i in range(0, 200, 7)], [10.0 + i for i in range(0, 200, 7)]),
    "duplicates-adjacent": (
        [day(i) for i in range(0, 200, 5)] + [day(i) for i in range(0, 200, 5)],
        [10.0 + i for i in range(0, 200, 5)] + [900.0 + i for i in range(0, 200, 5)],
    ),
    "duplicates-interleaved": (
        [day(i) for i in range(0, 200, 5)] + [day(i) for i in range(0, 200, 5)],
        [900.0 + i for i in range(0, 200, 5)] + [10.0 + i for i in range(0, 200, 5)],
    ),
    "all-same-date": ([day(0)] * 5, [1.0, 2.0, 3.0, 4.0, 5.0]),
}
ad1_viol = 0
ad1_total = 0
for ff in (True, False):
    for cname, (sd, sv) in dup_variants.items():
        sds = pl.Series("date", sd, dtype=pl.Date)
        svs = pl.Series("value", sv, dtype=pl.Float64)
        base = align(d200, sds, svs, keep="last", do_sort=True, forward_fill=ff)
        mut = align(d200, sds, svs, keep="first", do_sort=True, forward_fill=ff)
        ok, why = same(base, mut)
        ad1_total += 1
        if not ok:
            ad1_viol += 1
            violations.append(f"AD1 OBSERVABLE ff={ff} case={cname}: {why}")
print(f"AD1: {ad1_total} claim-checks, {ad1_viol} observable")

# ---------------------------------------------------------------- AD4
ad4_viol = 0
ad4_total = 0
for ff in (True, False):
    for cname, (sd, sv) in dup_variants.items():
        ordered = sorted(zip(sd, sv, strict=True), key=lambda t: t[0])
        shuffled = list(reversed(ordered))
        for label, rows in (("in-order", ordered), ("reversed", shuffled)):
            xs = [r[0] for r in rows]
            ys = [r[1] for r in rows]
            sds = pl.Series("date", xs, dtype=pl.Date)
            svs = pl.Series("value", ys, dtype=pl.Float64)
            with_sort = align(d200, sds, svs, keep="last", do_sort=True, forward_fill=ff)
            without = align(d200, sds, svs, keep="last", do_sort=False, forward_fill=ff)
            ok, why = same(with_sort, without)
            ad4_total += 1
            if not ok:
                ad4_viol += 1
                violations.append(f"AD4 OBSERVABLE ff={ff} case={cname} order={label}: {why}")
print(f"AD4: {ad4_total} claim-checks, {ad4_viol} observable")

print()
if violations:
    print("NOT EQUIVALENT - these survivors are observable, so they are real test gaps:")
    for v in violations:
        print("  " + v)
else:
    print("ALL THREE SURVIVORS ARE EQUIVALENT MUTANTS - no observable difference on any input tried.")
print(f"(total claim-checks: {checks + ad1_total + ad4_total})")
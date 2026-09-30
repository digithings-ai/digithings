"""Statistical honesty envelope for win-rate surfaces (#4828).

Ported from LuxAlgo edge-stats ``packages/core/src/stats/stats.ts``
(MIT, Copyright (c) 2026 LuxAlgo Global, LLC; upstream commit pinned on
#4828). Code only — upstream ``data/`` (CC BY) is not vendored, and this
module is not branded as edge-stats.

Every estimate emitted here carries its sample size: Wilson 95% score
intervals, minimum-N guards (warn 30 / refuse 10, identical to upstream),
and first-half/second-half stability via CI overlap. No bare percentages
leave this module.

Stdlib ``math`` only — no scipy.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

Z_95 = 1.959963984540054
WARN_FLOOR = 30
REFUSE_FLOOR = 10

DISCLAIMER = "Historical conditional frequencies with sample sizes. Not predictions, not advice."


class Wilson(BaseModel):
    """Wilson score interval for a binomial proportion (default 95%)."""

    estimate: float
    lo: float
    hi: float


class GuardResult(BaseModel):
    """Minimum-N guard outcome for a sample of size n."""

    low_sample: bool
    refused: bool
    warn_floor: int = WARN_FLOOR
    refuse_floor: int = REFUSE_FLOOR


class HalfStats(BaseModel):
    """One half of a stability split."""

    n: int
    k: int
    estimate: float | None = None
    ci95: tuple[float, float] | None = None


class StabilitySplit(BaseModel):
    """First-half/second-half stability; agree = Wilson CI overlap."""

    first_half: HalfStats
    second_half: HalfStats
    agree: bool | None = Field(
        default=None,
        description="CIs overlap → halves compatible; null when a half is empty",
    )


class HonestRate(BaseModel):
    """A win rate that cannot be rendered without its sample size."""

    k: int
    n: int
    estimate: float | None = None
    ci_lo: float | None = None
    ci_hi: float | None = None
    low_sample: bool = False
    refused: bool = False


def wilson(k: int, n: int, z: float = Z_95) -> Wilson | None:
    """Wilson score interval; None when n == 0. Raises on impossible counts."""
    if n <= 0:
        return None
    if k < 0 or k > n:
        raise ValueError(f"impossible counts: k={k} n={n}")
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return Wilson(estimate=p, lo=max(0.0, center - half), hi=min(1.0, center + half))


def apply_guards(n: int, *, warn: int = WARN_FLOOR, refuse: int = REFUSE_FLOOR) -> GuardResult:
    """Flag low samples (n < warn) and refuse tiny ones (n < refuse)."""
    return GuardResult(low_sample=n < warn, refused=n < refuse)


def _half(n: int, k: int) -> HalfStats:
    w = wilson(k, n)
    if w is None:
        return HalfStats(n=n, k=k)
    return HalfStats(n=n, k=k, estimate=w.estimate, ci95=(w.lo, w.hi))


def stability_split(n1: int, k1: int, n2: int, k2: int) -> StabilitySplit:
    """CI-overlap agreement between two halves; None when either is empty."""
    first = _half(n1, k1)
    second = _half(n2, k2)
    agree: bool | None = None
    if first.ci95 is not None and second.ci95 is not None:
        agree = first.ci95[0] <= second.ci95[1] and second.ci95[0] <= first.ci95[1]
    return StabilitySplit(first_half=first, second_half=second, agree=agree)


def honest_rate(
    k: int, n: int, *, warn: int = WARN_FLOOR, refuse: int = REFUSE_FLOOR
) -> HonestRate:
    """Build the render-ready HonestRate contract for k wins in n trades."""
    guards = apply_guards(n, warn=warn, refuse=refuse)
    w = wilson(k, n)
    if w is None:
        return HonestRate(k=k, n=n, low_sample=guards.low_sample, refused=guards.refused)
    return HonestRate(
        k=k,
        n=n,
        estimate=w.estimate,
        ci_lo=w.lo,
        ci_hi=w.hi,
        low_sample=guards.low_sample,
        refused=guards.refused,
    )


def format_honest_rate(
    k: int, n: int, *, warn: int = WARN_FLOOR, refuse: int = REFUSE_FLOOR
) -> str:
    """Render ``"{pct:.1f}% (k/n, n=N, 95% CI [lo, hi])"`` — never a bare %."""
    guards = apply_guards(n, warn=warn, refuse=refuse)
    if guards.refused:
        return f"REFUSED — n < {refuse} (n={n})"
    w = wilson(k, n)
    if w is None:  # pragma: no cover — n == 0 is always refused above
        return f"REFUSED — n < {refuse} (n={n})"
    assert w.estimate is not None
    s = f"{w.estimate * 100:.1f}% ({k}/{n}, n={n}, 95% CI [{w.lo * 100:.1f}%, {w.hi * 100:.1f}%])"
    if guards.low_sample:
        s += f" — LOW SAMPLE (n < {warn})"
    return s

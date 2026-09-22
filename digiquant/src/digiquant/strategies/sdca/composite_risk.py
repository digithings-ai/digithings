"""Composite-risk indicator vote — mirrors the M2 5-indicator weighted-blend pattern.

Blends N indicator z-scores (each in ``[-3, 3]``) into a single composite z-score,
then maps that composite to a ``[0, 100]`` risk score (0 = max buy signal, 100 =
max sell signal). Disabled indicators are excluded from the blend entirely. If
any *enabled* indicator is null on a given row, the composite (and therefore the
risk) is null that row too — there is no partial blend and no silent fallback.

``causal_rolling_z`` lives here (not ``indicator_catalog.py``, which imports it)
so both this module's own optional rolling-normalized composite and every
indicator built on top of it share one implementation.
"""

from __future__ import annotations

import math

import polars as pl
from pydantic import BaseModel, ConfigDict

_SIGMA_FLOOR = 1e-12
_ROLLING_MIN_SAMPLES_FLOOR = 20


class IndicatorWeight(BaseModel):
    """One indicator's z-score series plus its vote weight."""

    model_config = ConfigDict(strict=True, arbitrary_types_allowed=True)

    name: str
    z: pl.Series
    weight: float = 1.0
    enabled: bool = True


def causal_rolling_z(
    values: pl.Series,
    *,
    window: int,
    min_samples: int,
) -> pl.Series:
    """Rolling z in ``[-3, 3]``. Each day uses only that day and prior window."""
    if window < 2:
        raise ValueError(f"rolling window must be >= 2, got {window}")
    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=_SIGMA_FLOOR)).clip(-3.0, 3.0)


def compute_composite_risk(
    indicators: list[IndicatorWeight],
    *,
    rolling_window: int | None = None,
    rolling_min_samples: int | None = None,
    smoothing_window: int | None = None,
    smoothing_min_samples: int | None = None,
) -> pl.DataFrame:
    """Weighted blend of enabled indicators -> ``composite_z`` and ``risk`` columns.

    ``composite_z`` is the weight-normalized average z-score, clamped to
    ``[-3, 3]``. ``risk`` rescales that to ``[0, 100]`` (z=+3 -> risk=0,
    z=-3 -> risk=100). A row is null in both columns if any enabled indicator
    is null there.

    ``rolling_window`` (default ``None``, i.e. off — identical to the plain
    clip) re-normalizes the weighted blend with ``causal_rolling_z`` over the
    trailing ``rolling_window`` days *before* clamping, so the composite stays
    stationary as long-horizon legs like ``power_law`` drift with accumulating
    history instead of reading against the whole-history distribution. Since
    each per-indicator ``z`` is already in ``[-3, 3]`` and weights are the
    grid-searched nonnegative values used throughout Stage A, the pre-rolling
    weighted average is itself already bounded to ``[-3, 3]`` — rolling
    normalization re-centers/re-scales within that range, it does not need an
    extra pre-clip. ``rolling_min_samples`` defaults to half the window
    (floored at 20, mirroring ``indicator_catalog``'s single-window legs) so
    the rolling composite stays null until there is enough trailing history to
    trust its mean/std, the same warmup discipline as ``MIN_FIT_HISTORY_DAYS``
    for the power-law fit.

    ``smoothing_window`` (default ``None``, i.e. off) is a *separate* step
    applied last: a causal rolling mean over the final ``composite_z`` (after
    the optional rolling re-normalization above), for genuine day-to-day noise
    reduction. This is not the same knob as ``rolling_window`` — that
    re-centers/re-scales against a trailing distribution and can *amplify* a
    sudden move (a spike away from a quiet recent regime reads as an extreme
    z), it does not damp one. Averaging clipped ``[-3, 3]`` values keeps the
    result in range, so no re-clip is needed. ``smoothing_min_samples``
    defaults the same way as ``rolling_min_samples`` (half the window, floored
    at 20).
    """
    enabled = [ind for ind in indicators if ind.enabled]
    if not enabled:
        raise ValueError("compute_composite_risk requires at least one enabled indicator")

    names = [ind.name for ind in enabled]
    if len(set(names)) != len(names):
        raise ValueError(f"compute_composite_risk got duplicate enabled indicator names: {names}")

    total_weight = sum(ind.weight for ind in enabled)
    if not math.isfinite(total_weight) or total_weight == 0:
        raise ValueError(
            f"compute_composite_risk requires a finite, nonzero total weight, got {total_weight}"
        )

    df = pl.DataFrame({ind.name: ind.z for ind in enabled})

    weighted_sum = pl.sum_horizontal(
        [pl.col(ind.name) * ind.weight for ind in enabled], ignore_nulls=False
    )
    raw_z = df.select((weighted_sum / total_weight).alias("raw_z"))["raw_z"]

    if rolling_window is None:
        composite_z = raw_z.clip(-3.0, 3.0).alias("composite_z")
    else:
        if rolling_window < 2:
            raise ValueError(
                f"compute_composite_risk rolling_window must be >= 2, got {rolling_window}"
            )
        samples = (
            rolling_min_samples
            if rolling_min_samples is not None
            else max(_ROLLING_MIN_SAMPLES_FLOOR, rolling_window // 2)
        )
        composite_z = causal_rolling_z(raw_z, window=rolling_window, min_samples=samples).alias(
            "composite_z"
        )

    if smoothing_window is not None:
        if smoothing_window < 2:
            raise ValueError(
                f"compute_composite_risk smoothing_window must be >= 2, got {smoothing_window}"
            )
        smoothing_samples = (
            smoothing_min_samples
            if smoothing_min_samples is not None
            else max(_ROLLING_MIN_SAMPLES_FLOOR, smoothing_window // 2)
        )
        composite_z = composite_z.rolling_mean(
            window_size=smoothing_window, min_samples=smoothing_samples
        ).alias("composite_z")

    risk = (50.0 - composite_z * (50.0 / 3.0)).alias("risk")

    return pl.DataFrame({"composite_z": composite_z, "risk": risk})


Z_TO_RISK_SCALE = 50.0 / 3.0


def z_to_risk(z: float) -> float:
    """Map a clipped z in ``[-3, 3]`` onto the 0–100 composite-risk scale."""
    return 50.0 - float(z) * Z_TO_RISK_SCALE


__all__ = [
    "IndicatorWeight",
    "Z_TO_RISK_SCALE",
    "causal_rolling_z",
    "compute_composite_risk",
    "z_to_risk",
]

"""Composite-risk indicator vote — mirrors the M2 5-indicator weighted-blend pattern.

Blends N indicator z-scores (each in ``[-3, 3]``) into a single composite z-score,
then maps that composite to a ``[0, 100]`` risk score (0 = max buy signal, 100 =
max sell signal). Disabled indicators are excluded from the blend entirely. If
any *enabled* indicator is null on a given row, the composite (and therefore the
risk) is null that row too — there is no partial blend and no silent fallback.
"""

from __future__ import annotations

import math

import polars as pl
from pydantic import BaseModel, ConfigDict


class IndicatorWeight(BaseModel):
    """One indicator's z-score series plus its vote weight."""

    model_config = ConfigDict(strict=True, arbitrary_types_allowed=True)

    name: str
    z: pl.Series
    weight: float = 1.0
    enabled: bool = True


def compute_composite_risk(indicators: list[IndicatorWeight]) -> pl.DataFrame:
    """Weighted blend of enabled indicators -> ``composite_z`` and ``risk`` columns.

    ``composite_z`` is the weight-normalized average z-score, clamped to
    ``[-3, 3]``. ``risk`` rescales that to ``[0, 100]`` (z=+3 -> risk=0,
    z=-3 -> risk=100). A row is null in both columns if any enabled indicator
    is null there.
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
    composite_z = (weighted_sum / total_weight).clip(-3.0, 3.0).alias("composite_z")
    risk = (50.0 - composite_z * (50.0 / 3.0)).alias("risk")

    return df.select(composite_z, risk)


Z_TO_RISK_SCALE = 50.0 / 3.0


def z_to_risk(z: float) -> float:
    """Map a clipped z in ``[-3, 3]`` onto the 0–100 composite-risk scale."""
    return 50.0 - float(z) * Z_TO_RISK_SCALE


__all__ = ["IndicatorWeight", "Z_TO_RISK_SCALE", "compute_composite_risk", "z_to_risk"]

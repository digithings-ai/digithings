"""Per-indicator day-over-day roughness diagnostic (composite-index smoothing).

Measures each indicator's z-series the same way the round-8 post-mortem
measured the composite risk output (mean/p95/p99/max |delta|, spike counts
above fixed thresholds) so individual indicators can be compared on the
same risk-point scale the composite output is judged on, before deciding
which ones (per spec 2.1(b)) still need a smoothing pass.
"""

from __future__ import annotations

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.composite_risk import Z_TO_RISK_SCALE

_SPIKE_THRESHOLDS_RISK_PTS = (2.0, 5.0, 10.0)


class IndicatorRoughness(BaseModel):
    """Day-over-day roughness for one indicator's z-series, in risk-point units."""

    model_config = ConfigDict(frozen=True, strict=True)

    name: str
    n_days: int = Field(ge=0)
    mean_abs_delta_risk: float = Field(ge=0.0)
    p95_abs_delta_risk: float = Field(ge=0.0)
    p99_abs_delta_risk: float = Field(ge=0.0)
    max_abs_delta_risk: float = Field(ge=0.0)
    spike_days_gt_2: int = Field(ge=0)
    spike_days_gt_5: int = Field(ge=0)
    spike_days_gt_10: int = Field(ge=0)


def _percentile(sorted_values: list[float], p: float) -> float:
    idx = min(len(sorted_values) - 1, int(round(p * (len(sorted_values) - 1))))
    return sorted_values[idx]


def compute_indicator_roughness(name: str, z: pl.Series) -> IndicatorRoughness:
    """Day-over-day |delta z| * Z_TO_RISK_SCALE roughness for one indicator.

    Nulls are dropped before differencing so warm-up nulls (e.g. a rolling
    window's first `min_samples` days) never count as a delta.
    """
    values = [float(v) for v in z.to_list() if v is not None]
    n_days = len(values)
    deltas = [abs(values[i] - values[i - 1]) * Z_TO_RISK_SCALE for i in range(1, n_days)]
    if not deltas:
        return IndicatorRoughness(
            name=name,
            n_days=n_days,
            mean_abs_delta_risk=0.0,
            p95_abs_delta_risk=0.0,
            p99_abs_delta_risk=0.0,
            max_abs_delta_risk=0.0,
            spike_days_gt_2=0,
            spike_days_gt_5=0,
            spike_days_gt_10=0,
        )
    sorted_deltas = sorted(deltas)
    gt2, gt5, gt10 = _SPIKE_THRESHOLDS_RISK_PTS
    return IndicatorRoughness(
        name=name,
        n_days=n_days,
        mean_abs_delta_risk=sum(deltas) / len(deltas),
        p95_abs_delta_risk=_percentile(sorted_deltas, 0.95),
        p99_abs_delta_risk=_percentile(sorted_deltas, 0.99),
        max_abs_delta_risk=max(deltas),
        spike_days_gt_2=sum(1 for d in deltas if d > gt2),
        spike_days_gt_5=sum(1 for d in deltas if d > gt5),
        spike_days_gt_10=sum(1 for d in deltas if d > gt10),
    )


def compute_pool_roughness(indicators: dict[str, pl.Series]) -> list[IndicatorRoughness]:
    """One `IndicatorRoughness` per entry, in `indicators`' iteration order."""
    return [compute_indicator_roughness(name, z) for name, z in indicators.items()]

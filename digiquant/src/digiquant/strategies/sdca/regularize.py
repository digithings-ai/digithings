"""Shrink an aggressive two-stage fit so it is less likely to overfit."""

from __future__ import annotations

from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights

DEFAULT_WEIGHT_STEP = 0.1
DEFAULT_RATE_SCALE = 0.7


def _round_step(value: float, step: float) -> float:
    return round(value / step) * step


def regularize_weights(
    weights: SdcaCompositeWeights, *, step: float = DEFAULT_WEIGHT_STEP
) -> SdcaCompositeWeights:
    """Round each weight to ``step`` (tenths by default) and renormalize."""
    if step <= 0.0:
        raise ValueError(f"step must be positive, got {step}")
    rounded = {name: _round_step(value, step) for name, value in weights.model_dump().items()}
    total = sum(rounded.values())
    if total <= 0.0:
        raise ValueError("regularize_weights rounded every weight to 0")
    return SdcaCompositeWeights(**{name: value / total for name, value in rounded.items()})


def regularize_curve_shape(
    shape: SdcaCurveShape, *, rate_scale: float = DEFAULT_RATE_SCALE
) -> SdcaCurveShape:
    """Scale buy/sell max rates down; knees and curvature stay put."""
    if not (0.0 < rate_scale <= 1.0):
        raise ValueError(f"rate_scale must be in (0, 1], got {rate_scale}")
    return SdcaCurveShape(
        buy_max_rate=round(shape.buy_max_rate * rate_scale, 1),
        buy_knee_risk=shape.buy_knee_risk,
        sell_knee_risk=shape.sell_knee_risk,
        sell_max_rate=round(shape.sell_max_rate * rate_scale, 1),
        buy_curvature=shape.buy_curvature,
        sell_curvature=shape.sell_curvature,
    )


__all__ = [
    "DEFAULT_RATE_SCALE",
    "DEFAULT_WEIGHT_STEP",
    "regularize_curve_shape",
    "regularize_weights",
]

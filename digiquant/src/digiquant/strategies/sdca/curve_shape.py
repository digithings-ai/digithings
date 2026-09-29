"""Parametric SDCA curve shape — the authoring/optimization surface (#3169).

``AccumDistCurve`` remains the 21-node *runtime* representation. This module
generates those nodes from six bounded parameters that encode the owner's
required shape: a non-empty dead zone around fair value, progressive
accumulation below it, progressive distribution above it.

The generated path answers #2552 for this surface: ``buy_max_rate`` and
``sell_max_rate`` are capped at 100 (you cannot deploy more cash than you
hold, or sell more holdings than you have). The raw ``AccumDistCurve``
constructor is deliberately left unbounded — that question stays open for
hand-authored node lists; only the generated path is constrained.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from digiquant.strategies.sdca.curve import RISK_NODES

_RATE_EPS = 1e-12
_MID_TIER_RATE_FRAC = 0.5

# Optional second-knee fields shared by the tiered search (curve_optimize),
# the walk-forward gate (walk_forward.shape_from_params), and the periodic
# cycle driver. Defined here (next to SdcaCurveShape) so walk_forward can
# import it without creating a curve_optimize -> optimize -> walk_forward
# import cycle. curve_optimize re-exports it for its existing importers.
_MID_TIER_KEYS = (
    "buy_mid_knee_risk",
    "buy_mid_curvature",
    "sell_mid_knee_risk",
    "sell_mid_curvature",
)


class SdcaCurveShape(BaseModel):
    """Six-parameter generator for a 21-node accumulation/distribution curve.

    ``to_nodes()`` evaluates the shape at risk 0, 5, …, 100. Buy rates are
    daily % of *cash*; sell rates are daily % of *holdings* (returned as
    negative nodes, matching ``AccumDistCurve``).
    """

    model_config = ConfigDict(frozen=True, strict=True)

    buy_max_rate: float = Field(ge=0.0, le=100.0)
    buy_knee_risk: float = Field(gt=0.0, lt=100.0)
    sell_knee_risk: float = Field(gt=0.0, le=100.0)
    sell_max_rate: float = Field(ge=0.0, le=100.0)
    buy_curvature: float = Field(ge=1.0)
    sell_curvature: float = Field(ge=1.0)
    buy_mid_knee_risk: float | None = Field(default=None, gt=0.0, lt=100.0)
    buy_mid_curvature: float = Field(default=1.0, ge=1.0)
    sell_mid_knee_risk: float | None = Field(default=None, gt=0.0, lt=100.0)
    sell_mid_curvature: float = Field(default=1.0, ge=1.0)

    @model_validator(mode="after")
    def _enforce_shape_invariants(self) -> SdcaCurveShape:
        if not (self.buy_knee_risk < self.sell_knee_risk):
            raise ValueError(
                "dead zone must be non-empty: buy_knee_risk < sell_knee_risk, "
                f"got {self.buy_knee_risk} >= {self.sell_knee_risk}"
            )
        if self.sell_max_rate > 0.0 and self.sell_knee_risk >= 100.0:
            raise ValueError(
                "sell_knee_risk must be < 100 when sell_max_rate > 0 "
                f"(got sell_knee_risk={self.sell_knee_risk})"
            )
        if self.buy_mid_knee_risk is not None and not (
            0.0 < self.buy_mid_knee_risk < self.buy_knee_risk
        ):
            raise ValueError(
                f"buy_mid_knee_risk ({self.buy_mid_knee_risk}) must sit strictly between "
                f"0 and buy_knee_risk ({self.buy_knee_risk})"
            )
        if self.sell_mid_knee_risk is not None and not (
            self.sell_knee_risk < self.sell_mid_knee_risk < 100.0
        ):
            raise ValueError(
                f"sell_mid_knee_risk ({self.sell_mid_knee_risk}) must sit strictly between "
                f"sell_knee_risk ({self.sell_knee_risk}) and 100"
            )
        self._assert_generated_invariants(self.to_nodes())
        return self

    def rate_at(self, risk: float) -> float:
        """Daily trade rate (%) at ``risk`` in [0, 100]."""
        if risk < self.buy_knee_risk:
            return self._buy_rate(risk)
        if risk <= self.sell_knee_risk:
            return 0.0
        return self._sell_rate(risk)

    def _buy_rate(self, risk: float) -> float:
        if self.buy_mid_knee_risk is None:
            span = self.buy_knee_risk
            t = (self.buy_knee_risk - risk) / span
            return self.buy_max_rate * (t**self.buy_curvature)
        mid_rate = self.buy_max_rate * _MID_TIER_RATE_FRAC
        if risk >= self.buy_mid_knee_risk:
            span = self.buy_knee_risk - self.buy_mid_knee_risk
            t = (self.buy_knee_risk - risk) / span
            return mid_rate * (t**self.buy_curvature)
        span = self.buy_mid_knee_risk
        t = (self.buy_mid_knee_risk - risk) / span
        return mid_rate + (self.buy_max_rate - mid_rate) * (t**self.buy_mid_curvature)

    def _sell_rate(self, risk: float) -> float:
        if self.sell_mid_knee_risk is None:
            span = 100.0 - self.sell_knee_risk
            t = (risk - self.sell_knee_risk) / span
            return -self.sell_max_rate * (t**self.sell_curvature)
        mid_rate = self.sell_max_rate * _MID_TIER_RATE_FRAC
        if risk <= self.sell_mid_knee_risk:
            span = self.sell_mid_knee_risk - self.sell_knee_risk
            t = (risk - self.sell_knee_risk) / span
            return -(mid_rate * (t**self.sell_curvature))
        span = 100.0 - self.sell_mid_knee_risk
        t = (risk - self.sell_mid_knee_risk) / span
        return -(mid_rate + (self.sell_max_rate - mid_rate) * (t**self.sell_mid_curvature))

    def to_nodes(self) -> tuple[float, ...]:
        """21 nodes accepted by ``AccumDistCurve``."""
        return tuple(self.rate_at(r) for r in RISK_NODES)

    def _assert_generated_invariants(self, nodes: tuple[float, ...]) -> None:
        if len(nodes) != len(RISK_NODES):
            raise ValueError(f"generated curve must have {len(RISK_NODES)} nodes")
        for risk, node in zip(RISK_NODES, nodes, strict=True):
            if risk < self.buy_knee_risk:
                if self.buy_max_rate > 0.0 and node <= _RATE_EPS:
                    raise ValueError(
                        f"buy side must be > 0 strictly below buy_knee_risk, "
                        f"got node={node} at risk={risk}"
                    )
                if self.buy_max_rate == 0.0 and abs(node) > _RATE_EPS:
                    raise ValueError(f"zero buy_max_rate must produce 0, got {node}")
            elif risk <= self.sell_knee_risk:
                if abs(node) > _RATE_EPS:
                    raise ValueError(f"dead zone must be exactly 0, got node={node} at risk={risk}")
            else:
                if self.sell_max_rate > 0.0 and node >= -_RATE_EPS:
                    raise ValueError(
                        f"sell side must be < 0 strictly above sell_knee_risk, "
                        f"got node={node} at risk={risk}"
                    )
                if self.sell_max_rate == 0.0 and abs(node) > _RATE_EPS:
                    raise ValueError(f"zero sell_max_rate must produce 0, got {node}")
        for i in range(1, len(nodes)):
            if nodes[i] - nodes[i - 1] > _RATE_EPS:
                raise ValueError(
                    f"generated nodes must be monotonically non-increasing in risk, "
                    f"got {nodes[i - 1]} then {nodes[i]} at risks "
                    f"{RISK_NODES[i - 1]}, {RISK_NODES[i]}"
                )


def risk50_linear_reference_curve(max_rate: float, *, eps: float = 0.1) -> SdcaCurveShape:
    """Naive symmetric baseline: buy below risk 50, sell above 50, dead-simple linear.

    No curvature, no wide dead zone -- a straight linear ramp from
    ``max_rate`` at risk 0 down to 0 at risk 50, then from 0 down to
    ``-max_rate`` at risk 100. Used as the non-optimized comparator for
    baseline-relative evaluation, not as a candidate to be tuned itself.

    ``SdcaCurveShape`` forbids an exactly-zero-width dead zone
    (``buy_knee_risk < sell_knee_risk`` strict), so the knees sit at
    ``50 - eps``/``50 + eps``. On the 5-wide ``RISK_NODES`` grid (0, 5, ...,
    100) only the node at risk 50 falls inside that gap, so for any
    ``eps`` small enough not to reach the neighboring 45/55 nodes this is
    indistinguishable from a single knee at exactly 50.
    """
    if not (0.0 < eps < 5.0):
        raise ValueError(f"eps must be in (0, 5) to stay inside the 45..55 node gap, got {eps}")
    return SdcaCurveShape(
        buy_max_rate=max_rate,
        buy_knee_risk=50.0 - eps,
        sell_knee_risk=50.0 + eps,
        sell_max_rate=max_rate,
        buy_curvature=1.0,
        sell_curvature=1.0,
    )


__all__ = ["SdcaCurveShape", "risk50_linear_reference_curve"]

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
        self._assert_generated_invariants(self.to_nodes())
        return self

    def rate_at(self, risk: float) -> float:
        """Daily trade rate (%) at ``risk`` in [0, 100]."""
        if risk < self.buy_knee_risk:
            span = self.buy_knee_risk
            t = (self.buy_knee_risk - risk) / span
            return self.buy_max_rate * (t**self.buy_curvature)
        if risk <= self.sell_knee_risk:
            return 0.0
        span = 100.0 - self.sell_knee_risk
        t = (risk - self.sell_knee_risk) / span
        return -self.sell_max_rate * (t**self.sell_curvature)

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


__all__ = ["SdcaCurveShape"]

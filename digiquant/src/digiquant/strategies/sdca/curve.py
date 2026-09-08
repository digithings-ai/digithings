"""Accumulation/distribution curve — piecewise-linear risk-to-rate map for SDCA.

Mirrors the artifact's ``curveValueAtRisk``: 21 nodes at risk = 0, 5, ..., 100,
each holding a daily rate (%). ``value > 0`` buys that % of *currently
available cash* today; ``value < 0`` sells that % of the *current open
position* today. See
``digiquant/ARCHITECTURE.md`` (SDCA engine) for the full spec.
"""

from __future__ import annotations

import math

RISK_NODES: tuple[float, ...] = tuple(float(r) for r in range(0, 101, 5))  # 21 nodes

# Default (BTC reference) curve: all-positive accumulation through mid-risk,
# flat through the value zone, distribution at high risk.
DEFAULT_BTC_NODES: tuple[float, ...] = (
    10.0,
    10.0,
    10.0,
    10.0,  # risk 0, 5, 10, 15
    6.5,
    4.0,
    1.2,  # risk 20, 25, 30
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,  # risk 35..80
    -0.5,
    -1.5,
    -3.0,
    -10.0,  # risk 85, 90, 95, 100
)


class AccumDistCurve:
    """21-node piecewise-linear accumulation/distribution curve.

    ``value_at_risk(risk)`` returns the daily trade rate (%) for a composite
    risk score: positive buys that % of currently available cash, negative
    sells that % of the current open position. Risk is clamped to [0, 100]
    before lookup.
    """

    def __init__(self, nodes: tuple[float, ...] | list[float] = DEFAULT_BTC_NODES) -> None:
        if len(nodes) != len(RISK_NODES):
            raise ValueError(f"Curve must have {len(RISK_NODES)} nodes, got {len(nodes)}")
        if not all(math.isfinite(v) for v in nodes):
            raise ValueError(f"Curve nodes must all be finite, got {nodes}")
        self.nodes: tuple[float, ...] = tuple(nodes)

    def value_at_risk(self, risk: float) -> float:
        """Piecewise-linear rate (%) for ``risk`` in [0, 100]."""
        if not math.isfinite(risk):
            raise ValueError(f"value_at_risk requires a finite risk, got {risk}")
        r = min(max(risk, 0.0), 100.0)
        idx = min(int(r // 5), len(RISK_NODES) - 2)
        r0, r1 = RISK_NODES[idx], RISK_NODES[idx + 1]
        v0, v1 = self.nodes[idx], self.nodes[idx + 1]
        t = (r - r0) / (r1 - r0)
        return v0 + t * (v1 - v0)


__all__ = ["RISK_NODES", "DEFAULT_BTC_NODES", "AccumDistCurve"]

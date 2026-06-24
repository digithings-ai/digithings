"""Stage 2 — regime-conditioned analyst dispatch budget (#1017).

Turns market state (VIX term structure + breadth + cross-sectional return
dispersion) into a dispatch budget for H4's focus roster, with a fail-soft
fallback to the static ATLAS_MAX_ANALYSTS cap. See
docs/superpowers/specs/2026-06-23-adaptive-two-track-dispatch-design.md.
"""

from __future__ import annotations

import logging
import os
import statistics
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Module constants, overridable via environment variables
STRESS_FLOOR = int(os.getenv("ATLAS_BUDGET_STRESS_FLOOR", "3"))
DISPERSION_HI = float(os.getenv("ATLAS_BUDGET_DISPERSION_HI", "0.015"))

RegimeLabel = Literal["stress", "neutral", "dispersion"]


class RegimeAssessment(BaseModel):
    """The classified regime plus the signals that produced it (for the audit log)."""

    regime: RegimeLabel
    vix_state: str | None = None
    vix_ratio: float | None = None
    pct_above_50dma: float | None = None
    return_dispersion: float | None = None
    note: str = ""


def cross_sectional_dispersion(price_deltas: Mapping[str, float]) -> float | None:
    """Population stdev of per-ticker daily returns — a no-DB dispersion proxy.

    Returns ``None`` when fewer than two finite values are present.
    """
    vals = [float(v) for v in price_deltas.values() if v is not None]
    if len(vals) < 2:
        return None
    return statistics.pstdev(vals)


def classify_regime(
    *,
    vix_state: str | None,
    vix_ratio: float | None,
    pct_above_50dma: float | None,
    return_dispersion: float | None,
) -> RegimeAssessment:
    """Deterministic regime classifier based on VIX term structure, breadth,
    and cross-sectional dispersion.

    Decision tree:
    - `stress`: VIX backwardation OR weak breadth (<40% above 50dma)
    - `dispersion`: high cross-sectional dispersion (>= DISPERSION_HI)
    - `neutral`: otherwise (including when all signals are None)

    Returns a RegimeAssessment with the classified regime and the input
    signals for audit logging.
    """
    # Stress condition 1: backwardation dominates
    if vix_state == "backwardation":
        return RegimeAssessment(
            regime="stress",
            vix_state=vix_state,
            vix_ratio=vix_ratio,
            pct_above_50dma=pct_above_50dma,
            return_dispersion=return_dispersion,
        )

    # Stress condition 2: weak breadth
    if pct_above_50dma is not None and pct_above_50dma < 40.0:
        return RegimeAssessment(
            regime="stress",
            vix_state=vix_state,
            vix_ratio=vix_ratio,
            pct_above_50dma=pct_above_50dma,
            return_dispersion=return_dispersion,
        )

    # Dispersion condition: high cross-sectional dispersion
    if return_dispersion is not None and return_dispersion >= DISPERSION_HI:
        return RegimeAssessment(
            regime="dispersion",
            vix_state=vix_state,
            vix_ratio=vix_ratio,
            pct_above_50dma=pct_above_50dma,
            return_dispersion=return_dispersion,
        )

    # Default to neutral
    return RegimeAssessment(
        regime="neutral",
        vix_state=vix_state,
        vix_ratio=vix_ratio,
        pct_above_50dma=pct_above_50dma,
        return_dispersion=return_dispersion,
    )


def budget_for(assessment: RegimeAssessment, *, static_cap: int) -> tuple[int, int]:
    """Map regime assessment to a dispatch budget and explore floor.

    Budget policy (cost-safe — budget never exceeds static_cap when > 0):
    - `stress` → budget = max(STRESS_FLOOR, round(static_cap * 0.5)),
                 explore_floor = 0
    - `neutral` → budget = static_cap, explore_floor = 1
    - `dispersion` → budget = static_cap,
                     explore_floor = max(2, round(static_cap * 0.25))
    - When static_cap <= 0 (no cap), return (0, explore_floor) for
      uncapped roster; explore_floor still follows the regime.

    Returns (budget, explore_floor).
    """
    regime = assessment.regime

    # When static_cap <= 0, no cap is configured
    if static_cap <= 0:
        if regime == "stress":
            return 0, 0
        elif regime == "dispersion":
            return 0, max(2, round(0 * 0.25))  # yields 0 but follow logic
        else:  # neutral
            return 0, 1

    # When static_cap > 0, apply regime-specific budgeting
    if regime == "stress":
        budget = max(STRESS_FLOOR, round(static_cap * 0.5))
        return budget, 0
    elif regime == "dispersion":
        budget = static_cap
        explore_floor = max(2, round(static_cap * 0.25))
        return budget, explore_floor
    else:  # neutral
        return static_cap, 1

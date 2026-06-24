"""Stage 2 — regime-conditioned analyst dispatch budget (#1017).

Turns market state (VIX term structure + breadth + cross-sectional return
dispersion) into a dispatch budget for H4's focus roster, with a fail-soft
fallback to the static ATLAS_MAX_ANALYSTS cap. See
docs/superpowers/specs/2026-06-23-adaptive-two-track-dispatch-design.md.
"""

from __future__ import annotations

import logging
import statistics
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

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

"""portfolio sub-graph state (alias — see ADR-0015).

``PortfolioState`` re-exports :class:`digiquant.research.state.ResearchState`
until digest-only extraction lands (epic #471).

WP8.3/8.4: ``PhasePortfolioState.allocation_input_bundle`` holds the
:class:`~digiquant.portfolio.allocation_contracts.AllocationInputBundle`
assembled at sizing entry; WP8.4 feeds calibrated raw weights when coverage is usable.

WP9.3: ``PhasePortfolioState.pre_trade_risk_report`` holds the
:class:`~digiquant.portfolio.allocation_contracts.PreTradeRiskReport`
built after the final sizing control shell (carry/cadence/backstop/grid/final caps).

WP10.1: post-commit
:class:`~digiquant.portfolio.shadow_artifact.ShadowAllocationArtifact`
export is a one-way file boundary (not a state slot) — see ``shadow_artifact.py``.
"""

from __future__ import annotations

from digiquant.research.state import (
    Phase7DigestPayload,
    PhasePortfolioState,
    RebalancePayload,
    ResearchState,
    RiskDebatePayload,
)

# Alias — see module docstring. New code should import ``PortfolioState`` from
# here so the eventual split lands without churning every phase file.
PortfolioState = ResearchState

__all__ = [
    "ResearchState",
    "PortfolioState",
    "Phase7DigestPayload",
    "PhasePortfolioState",
    "RebalancePayload",
    "RiskDebatePayload",
]

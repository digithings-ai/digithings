"""Hermes sub-graph state (alias — see ADR-0015).

``HermesState`` re-exports :class:`digiquant.research.state.AtlasResearchState`
until digest-only extraction lands (epic #471).

WP8.3/8.4: ``PhaseHermesState.allocation_input_bundle`` holds the
:class:`~digiquant.portfolio.allocation_contracts.AllocationInputBundle`
assembled at H8 entry; WP8.4 feeds calibrated raw weights when coverage is usable.

WP9.3: ``PhaseHermesState.pre_trade_risk_report`` holds the
:class:`~digiquant.portfolio.allocation_contracts.PreTradeRiskReport`
built after the final H8 control shell (carry/cadence/backstop/grid/final caps).

WP10.1: post-H9
:class:`~digiquant.portfolio.shadow_artifact.ShadowAllocationArtifact`
export is a one-way file boundary (not a state slot) — see ``shadow_artifact.py``.
"""

from __future__ import annotations

from digiquant.research.state import (
    AtlasResearchState,
    Phase7DigestPayload,
    PhaseHermesState,
    RebalancePayload,
    RiskDebatePayload,
)

# Alias — see module docstring. New code should import ``HermesState`` from
# here so the eventual split lands without churning every phase file.
HermesState = AtlasResearchState

__all__ = [
    "AtlasResearchState",
    "HermesState",
    "Phase7DigestPayload",
    "PhaseHermesState",
    "RebalancePayload",
    "RiskDebatePayload",
]

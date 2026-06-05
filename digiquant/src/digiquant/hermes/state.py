"""Hermes sub-graph state (alias — see ADR-0015).

``HermesState`` re-exports :class:`digiquant.atlas.state.AtlasResearchState`
until digest-only extraction lands (epic #471).
"""

from __future__ import annotations

from digiquant.atlas.state import (
    AnalystRowPayload,
    AtlasResearchState,
    DebateTickerState,
    Phase7DigestPayload,
    RebalancePayload,
    RiskDebatePayload,
    SpecialistAxisPayload,
)

# Alias — see module docstring. New code should import ``HermesState`` from
# here so the eventual split lands without churning every phase file.
HermesState = AtlasResearchState

__all__ = [
    "AnalystRowPayload",
    "AtlasResearchState",
    "DebateTickerState",
    "HermesState",
    "Phase7DigestPayload",
    "RebalancePayload",
    "RiskDebatePayload",
    "SpecialistAxisPayload",
]

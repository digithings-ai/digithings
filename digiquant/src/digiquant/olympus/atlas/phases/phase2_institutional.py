"""Phase 2 — institutional intelligence (2 parallel segment nodes)."""

from __future__ import annotations

from typing import Literal

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant.olympus.atlas.phases._node_factory import (
    SegmentNodeSpec,
    build_segment_node,
)
from digiquant.olympus.atlas.segments import SegmentReport


class InstitutionalFlowsReport(SegmentReport):
    """Phase 2A — ETF inflows / outflows, dark-pool prints, 13D/13G/Form 4."""

    flow_direction: Literal["inflow", "outflow", "mixed"] | None = None
    largest_sector_inflow: str | None = Field(default=None)
    largest_sector_outflow: str | None = Field(default=None)
    notable_filings: list[str] = Field(
        default_factory=list,
        description="≤5 short filing labels (e.g., '13D by Elliott on XYZ').",
    )


class HedgeFundIntelReport(SegmentReport):
    """Phase 2B — tracked-fund signals (13F, X posts, conference calls)."""

    tracked_funds_count: int = Field(default=0, ge=0)
    top_signals: list[str] = Field(
        default_factory=list,
        description="≤8 short signal labels; ordered by conviction.",
    )


# ─── Phase assembly ─────────────────────────────────────────────────────────

_PHASE_FIELD = "phase2_outputs"

_SPECS = (
    SegmentNodeSpec(
        segment_slug="inst-institutional-flows",
        skill_slug="inst-institutional-flows",
        output_model=InstitutionalFlowsReport,
        phase_outputs_field=_PHASE_FIELD,
        live_search=True,  # 13F / flows color from web
    ),
    SegmentNodeSpec(
        segment_slug="inst-hedge-fund-intel",
        skill_slug="inst-hedge-fund-intel",
        output_model=HedgeFundIntelReport,
        phase_outputs_field=_PHASE_FIELD,
        live_search=True,
    ),
)


def build_phase2() -> PipelinePhase:
    """Return the Phase-2 fan-out (2 parallel nodes)."""
    return PipelinePhase(
        name="phase2_institutional",
        nodes=[NodeSpec(name=spec.segment_slug, run=build_segment_node(spec)) for spec in _SPECS],
    )


__all__ = [
    "HedgeFundIntelReport",
    "InstitutionalFlowsReport",
    "build_phase2",
]

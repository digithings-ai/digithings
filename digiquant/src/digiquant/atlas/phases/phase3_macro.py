"""Phase 3 — Macro regime classification (single node).

The analytical anchor for all downstream work. Output is a structured
4-factor regime label that phases 4, 5, 7 all reference.
"""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for dict shape typing below

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant.atlas.phases._node_factory import (
    SegmentNodeSpec,
    build_segment_node,
    scalar_slot_write_adapter,
)
from digiquant.atlas.segments import SegmentReport
from digiquant.atlas.state import AtlasResearchState


# Per ARCHITECTURE.md §Phase 3: 4-factor model.
GrowthFactor = Literal["expanding", "slowing", "contracting"]
InflationFactor = Literal["hot", "cooling", "cold"]
PolicyFactor = Literal["tightening", "neutral", "easing"]
RiskAppetiteFactor = Literal["risk_on", "mixed", "risk_off"]


class MacroRegimeReport(SegmentReport):
    """Phase 3 — 4-factor macro regime."""

    growth: GrowthFactor
    inflation: InflationFactor
    policy: PolicyFactor
    risk_appetite: RiskAppetiteFactor
    regime_label: str = Field(
        description="Short compound label, e.g. 'Slowing / Inflation Sticky / Policy Tightening / Risk-Off'",
        max_length=120,
    )
    portfolio_implications: str = Field(
        default="",
        description="1–3 sentence read on what the regime means for positioning.",
        max_length=800,
    )


_SPEC = SegmentNodeSpec(
    segment_slug="macro",
    skill_slug="macro",
    output_model=MacroRegimeReport,
    phase_outputs_field="phase3_output",  # single slot, not a dict
)


def _macro_inputs_builder(state: AtlasResearchState, spec: SegmentNodeSpec) -> dict[str, Any]:
    """Phase 3 reads Phase 1 alt-data signals so the regime classification
    is coloured by positioning (per ARCHITECTURE.md §Phase 3)."""
    return {
        "segment": spec.segment_slug,
        "phase1_outputs": {
            slug: slot.payload.model_dump(mode="json")
            for slug, slot in state.phase1_outputs.items()
        },
    }


def build_phase3() -> PipelinePhase:
    return PipelinePhase(
        name="phase3_macro",
        nodes=[
            NodeSpec(
                name=_SPEC.segment_slug,
                run=build_segment_node(
                    _SPEC,
                    inputs_builder=_macro_inputs_builder,
                    write_adapter=scalar_slot_write_adapter,
                ),
            )
        ],
    )


__all__ = ["MacroRegimeReport", "build_phase3"]

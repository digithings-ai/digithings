"""Phase 3 — 4-factor macro regime (single node; phases 4–7 consume output)."""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for dict shape typing below

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant.olympus.atlas.phases._node_factory import (
    SegmentNodeSpec,
    build_segment_node,
    scalar_slot_write_adapter,
)
from digiquant.olympus.atlas.segments import SegmentReport
from digiquant.olympus.atlas.state import AtlasResearchState


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
    )
    portfolio_implications: str = Field(
        default="",
        description="1–3 sentence read on what the regime means for positioning.",
    )


_SPEC = SegmentNodeSpec(
    segment_slug="macro",
    skill_slug="macro",
    output_model=MacroRegimeReport,
    phase_outputs_field="phase3_output",  # single slot, not a dict
    use_data_tools=True,  # FRED macro series via get_macro_series
    live_search=True,  # non-US M2 / policy freshness fallback
    extra_context_keys=("bonds", "commodities", "forex", "equity"),  # cross-asset priors (#696)
)


# Phase-1 segments the macro regime ignores. alt-ai-portfolios is a stock-pick proxy
# scoped to the equity/sector phases (#658), not a macro-regime signal.
_MACRO_EXCLUDED_PHASE1 = {"alt-ai-portfolios"}


def _macro_inputs_builder(state: AtlasResearchState, spec: SegmentNodeSpec) -> dict[str, Any]:
    """Phase 3 reads Phase 1 alt-data signals so the regime classification
    is coloured by positioning (per ARCHITECTURE.md §Phase 3)."""
    return {
        "segment": spec.segment_slug,
        "phase1_outputs": {
            slug: slot.payload.model_dump(mode="json")
            for slug, slot in state.phase1_outputs.items()
            if slug not in _MACRO_EXCLUDED_PHASE1
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

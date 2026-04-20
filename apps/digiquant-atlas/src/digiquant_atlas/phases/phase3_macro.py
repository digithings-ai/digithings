"""Phase 3 — Macro regime classification (single node).

The analytical anchor for all downstream work. Output is a structured
4-factor regime label that phases 4, 5, 7 all reference.
"""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for dict shape typing below

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant_atlas.phases._node_factory import SegmentNodeSpec, _shared_context
from digiquant_atlas.segments import SegmentReport
from digiquant_atlas.state import AtlasResearchState, SegmentPayload, SegmentSlot


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


def _macro_node(state: AtlasResearchState) -> dict[str, Any]:
    """Macro runs as a single SegmentSlot into phase3_output, not a dict.

    The generic build_segment_node targets a ``dict[slug]`` output field.
    Macro is a scalar slot on AtlasResearchState, so this node wraps the
    same underlying research-agent call and assigns directly to the slot.
    """
    from digigraph.graph.research_agent import run_research_agent

    from digiquant_atlas.skills import load_skill

    skill_text = load_skill(_SPEC.skill_slug)
    # Phase 3 reads Phase 1 alt-data signals per ARCHITECTURE.md — include
    # them as phase_inputs so the regime can reference sentiment/CTA signals.
    phase_inputs: dict[str, Any] = {
        "segment": _SPEC.segment_slug,
        "phase1_outputs": {
            slug: slot.payload.model_dump(mode="json")
            for slug, slot in state.phase1_outputs.items()
        },
    }
    shared = _shared_context(state)
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=shared,
        output_model=MacroRegimeReport,
    )
    payload = SegmentPayload(
        segment=_SPEC.segment_slug,
        body=result.model_dump(mode="json"),
        as_of=state.run_date,
    )
    return {"phase3_output": SegmentSlot(payload=payload)}


def build_phase3() -> PipelinePhase:
    return PipelinePhase(
        name="phase3_macro",
        nodes=[NodeSpec(name=_SPEC.segment_slug, run=_macro_node)],
    )


__all__ = ["MacroRegimeReport", "build_phase3"]

"""Phase 7 — Master digest synthesis.

One LLM call that reads every phase-1–6 output and emits the digest
snapshot JSON (matches ``templates/digest-snapshot-schema.json``). Unlike
the segment nodes, this is a single-node phase.

The ``DigestSnapshot`` model mirrors the required-narrative-coverage
sections listed in ARCHITECTURE.md §Phase 7. Adds a
``segment_freshness`` field per the plan (§6.2 risk #2) so the dashboard
can distinguish today-fresh vs. carried segments on delta days.
"""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field

from digiquant_atlas.phases._node_factory import _shared_context
from digiquant_atlas.segments import SegmentReport
from digiquant_atlas.state import AtlasResearchState


class SegmentFreshness(BaseModel):
    """Per-segment provenance marker used by the dashboard."""

    source: Literal["today", "baseline"]
    as_of: str = Field(description="ISO date")


class ActionableItem(BaseModel):
    priority: int = Field(ge=1, le=5)
    label: str = Field(max_length=120)
    rationale: str = Field(max_length=500)


class RiskItem(BaseModel):
    horizon_hours: int = Field(ge=1, le=168)
    label: str = Field(max_length=120)
    trigger: str = Field(max_length=400)


class DigestSnapshot(SegmentReport):
    """Phase 7 master synthesis payload."""

    market_regime_snapshot: str = Field(max_length=800)
    alt_data_dashboard: str = Field(max_length=800)
    institutional_summary: str = Field(max_length=800)
    asset_classes_summary: str = Field(max_length=1200)
    us_equities_summary: str = Field(max_length=1200)
    thesis_tracker: str = Field(default="", max_length=1200)
    portfolio_recommendations: str = Field(default="", max_length=1200)
    actionable_summary: list[ActionableItem] = Field(default_factory=list)
    risk_radar: list[RiskItem] = Field(default_factory=list)
    segment_freshness: dict[str, SegmentFreshness] = Field(
        default_factory=dict,
        description="Per-segment provenance (today vs. carried) — populated from state",
    )


def _segment_freshness(state: AtlasResearchState) -> dict[str, SegmentFreshness]:
    """Derive the freshness map from state — does not rely on the LLM."""
    out: dict[str, SegmentFreshness] = {}
    for bag in (
        state.phase1_outputs,
        state.phase2_outputs,
        state.phase4_outputs,
        state.phase5_outputs,
    ):
        for slug, slot in bag.items():
            source = "today" if slot.payload.source == "today" else "baseline"
            as_of_val = getattr(slot.payload, "as_of", None) or getattr(
                slot.payload, "baseline_date", None
            )
            as_of = as_of_val.isoformat() if as_of_val else ""
            out[slug] = SegmentFreshness(source=source, as_of=as_of)  # type: ignore[arg-type]
    if state.phase3_output is not None:
        source = "today" if state.phase3_output.payload.source == "today" else "baseline"
        as_of_val = getattr(state.phase3_output.payload, "as_of", None) or getattr(
            state.phase3_output.payload, "baseline_date", None
        )
        out["macro"] = SegmentFreshness(
            source=source,  # type: ignore[arg-type]
            as_of=as_of_val.isoformat() if as_of_val else "",
        )
    return out


def _synthesis_node(state: AtlasResearchState) -> dict[str, Any]:
    from digigraph.graph.research_agent import run_research_agent

    from digiquant_atlas.skills import load_skill

    skill_text = load_skill("digest")
    phase_inputs: dict[str, Any] = {
        "segment": "master-digest",
        "bias_row": state.phase6_bias_row or {},
        "phase1": _bodies(state.phase1_outputs),
        "phase2": _bodies(state.phase2_outputs),
        "phase3": _body(state.phase3_output),
        "phase4": _bodies(state.phase4_outputs),
        "phase5": _bodies(state.phase5_outputs),
    }
    # Custom research prompt threading (#313). Surfaced as an explicit
    # ``custom_prompt`` field rather than mixed into ``bias_row`` so the
    # digest skill can detect and prioritize it. Absent on routine runs.
    if state.custom_prompt:
        phase_inputs["custom_prompt"] = state.custom_prompt
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=_shared_context(state),
        output_model=DigestSnapshot,
        phase_slug="master-digest",
    )
    # Overwrite the LLM-proposed freshness map with the deterministic one.
    # The LLM is prone to inferring freshness incorrectly on delta runs;
    # state is authoritative.
    digest = result.model_copy(update={"segment_freshness": _segment_freshness(state)})
    return {"phase7_digest": digest.model_dump(mode="json")}


def _body(slot: Any) -> dict[str, Any]:
    if slot is None or slot.payload.source != "today":
        return {}
    return dict(slot.payload.body)


def _bodies(bag: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {slug: slot.payload.model_dump(mode="json") for slug, slot in bag.items()}


def build_phase7() -> PipelinePhase:
    return PipelinePhase(
        name="phase7_synthesis",
        nodes=[NodeSpec(name="master-digest", run=_synthesis_node)],
    )


__all__ = [
    "ActionableItem",
    "DigestSnapshot",
    "RiskItem",
    "SegmentFreshness",
    "build_phase7",
]

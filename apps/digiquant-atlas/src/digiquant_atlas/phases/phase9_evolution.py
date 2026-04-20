"""Phase 9 — Post-mortem and evolution JSON artifacts.

Per the plan (§3 "Skill collapses"), we drop 9D (document applied
proposals) and 9E (evolution branch + PR) — those don't fit deterministic
scheduling. Keep 9A (sources scorecard), 9B (quality post-mortem), and
9C (improvement proposals) as LLM-emitted JSON artifacts that land in
``state.phase9_evolution``.

Each artifact has a Pydantic model matching the legacy schema in
``templates/schemas/evolution-{sources,quality-log,proposals}.schema.json``
at the fields the legacy system enforces.
"""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field

from digiquant_atlas.phases._node_factory import _shared_context
from digiquant_atlas.state import AtlasResearchState


# ─── 9A Sources Scorecard ──────────────────────────────────────────────────


class SourceScore(BaseModel):
    source: str = Field(max_length=120)
    stars: int = Field(ge=1, le=5)
    failures_today: int = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=500)


class EvolutionSources(BaseModel):
    scored: list[SourceScore] = Field(default_factory=list)
    discoveries: list[str] = Field(default_factory=list)


# ─── 9B Quality Post-Mortem ─────────────────────────────────────────────────


class PredictionCheck(BaseModel):
    prediction: str = Field(max_length=400)
    outcome: Literal["confirmed", "failed", "pending"]


class QualityRubric(BaseModel):
    accuracy: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    actionability: int = Field(ge=1, le=5)
    conciseness: int = Field(ge=1, le=5)
    source_quality: int = Field(ge=1, le=5)


class EvolutionQualityLog(BaseModel):
    predictions_checked: list[PredictionCheck] = Field(default_factory=list)
    rubric: QualityRubric


# ─── 9C Improvement Proposals ──────────────────────────────────────────────


class ImprovementProposal(BaseModel):
    target_file: str = Field(max_length=300)
    change_summary: str = Field(max_length=800)
    rationale: str = Field(max_length=800)


class EvolutionProposals(BaseModel):
    # Legacy guardrail: max 2 proposals per session.
    proposals: list[ImprovementProposal] = Field(default_factory=list, max_length=2)


# ─── Combined emitter node ──────────────────────────────────────────────────


class Phase9Artifacts(BaseModel):
    """One Pydantic container so the node emits all three artifacts in one LLM call.

    Individual downstream consumers still get the structured sub-objects
    via dict access. Doing three separate LLM calls would be wasteful —
    the full context fits comfortably in one call.
    """

    sources: EvolutionSources
    quality: EvolutionQualityLog
    proposals: EvolutionProposals


def _phase9_node(state: AtlasResearchState) -> dict[str, Any]:
    from digigraph.graph.research_agent import run_research_agent

    from digiquant_atlas.skills import load_skill

    # Phase 9 is scheduled and deterministic — if pipeline-evolution is
    # missing that's a packaging regression, not a normal operating state.
    # Let SkillNotFoundError propagate; the graph run fails loud and the
    # operator sees the real cause instead of a "nothing to improve" row.
    skill_text = load_skill("pipeline-evolution")
    phase_inputs: dict[str, Any] = {
        "segment": "phase9-evolution",
        "today_digest": state.phase7_digest or {},
        "bias_row": state.phase6_bias_row or {},
        "prior_snapshots": list(state.prior_context.last_snapshots),
    }
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=_shared_context(state),
        output_model=Phase9Artifacts,
    )
    return {"phase9_evolution": result.model_dump(mode="json")}


def build_phase9() -> PipelinePhase:
    return PipelinePhase(
        name="phase9_evolution",
        nodes=[NodeSpec(name="evolution", run=_phase9_node)],
    )


__all__ = [
    "EvolutionProposals",
    "EvolutionQualityLog",
    "EvolutionSources",
    "Phase9Artifacts",
    "build_phase9",
]

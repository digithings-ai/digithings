"""Monthly synthesis — one LLM rollup at month-end (``run_type == 'monthly'``).

Reuses ``state.phase7_digest``; publish routes via ``doc_type == 'monthly_digest'``.
"""

from __future__ import annotations

from typing import Any  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant.atlas.phases._node_factory import _shared_context
from digiquant.atlas.phases.phase7_synthesis import DigestSnapshot
from digiquant.atlas.state import AtlasResearchState


class MonthlyDigest(DigestSnapshot):
    """Monthly digest extends the daily shape with a month-over-month field."""

    month_over_month_regime_delta: str = Field(
        default="",
        description="What changed in macro regime vs the prior month-end.",
    )


def _monthly_node(state: AtlasResearchState) -> dict[str, Any]:
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.atlas.skills import SkillNotFoundError, load_skill

    try:
        skill_text = load_skill("monthly-synthesis")
    except SkillNotFoundError:
        skill_text = load_skill("digest")

    phase_inputs: dict[str, Any] = {
        "segment": "monthly-digest",
        "run_type": "monthly",
        "prior_snapshots": list(state.prior_context.last_snapshots),
        "latest_segments": dict(state.prior_context.latest_segments),
    }
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=_shared_context(state),
        output_model=MonthlyDigest,
        phase_slug="monthly-digest",
    )
    return {"phase7_digest": result.model_dump(mode="json")}


def build_phase_monthly() -> PipelinePhase:
    return PipelinePhase(
        name="phase_monthly",
        nodes=[NodeSpec(name="monthly-digest", run=_monthly_node)],
    )


__all__ = ["MonthlyDigest", "build_phase_monthly"]

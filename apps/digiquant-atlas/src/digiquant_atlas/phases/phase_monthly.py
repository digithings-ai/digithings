"""Monthly synthesis phase — month-end rollup.

One LLM call per month-end invocation. Reads the week's baselines + daily
deltas (via prior_context) and emits a cross-month regime-shift digest.

Unlike Phase 7 (which runs every day), monthly synthesis is called from
a separate graph invocation with ``run_type == 'monthly'``. It writes
into ``state.phase7_digest`` (reusing the field — monthly and daily
digests share the same downstream consumer) but tags the payload with
``doc_type == 'monthly_digest'`` so the Supabase layer routes the row
to the monthly bucket.
"""

from __future__ import annotations

from typing import Any  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import Field

from digiquant_atlas.phases._node_factory import _shared_context
from digiquant_atlas.phases.phase7_synthesis import DigestSnapshot
from digiquant_atlas.state import AtlasResearchState


class MonthlyDigest(DigestSnapshot):
    """Monthly digest extends the daily shape with a month-over-month field."""

    month_over_month_regime_delta: str = Field(
        default="",
        description="What changed in macro regime vs the prior month-end.",
        max_length=1200,
    )


def _monthly_node(state: AtlasResearchState) -> dict[str, Any]:
    from digigraph.graph.research_agent import run_research_agent

    from digiquant_atlas.skills import load_skill

    # Prefer a dedicated monthly-synthesis skill if present; fall back to
    # the daily digest skill with an explicit "this is a monthly rollup"
    # marker in phase_inputs so the prompt can adjust tone.
    try:
        skill_text = load_skill("monthly-synthesis")
    except Exception:  # noqa: BLE001 — SkillNotFoundError on missing
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
    )
    return {"phase7_digest": result.model_dump(mode="json")}


def build_phase_monthly() -> PipelinePhase:
    return PipelinePhase(
        name="phase_monthly",
        nodes=[NodeSpec(name="monthly-digest", run=_monthly_node)],
    )


__all__ = ["MonthlyDigest", "build_phase_monthly"]

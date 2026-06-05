"""Phase 9 — Post-mortem, evolution artifacts, and decision-log persistence.

Three artifact families flow through this phase:

- **9A Sources scorecard** — LLM-emitted JSON.
- **9B Quality post-mortem** — LLM-emitted JSON.
- **9C Improvement proposals** — LLM-emitted JSON.
- **9D Decision log (Phase A of #432)** — non-LLM Supabase write. Persists
  one ``pending`` row per Phase 7C analyst output so the next run's reflector
  (Phase 0 / preflight_reflect) can resolve it against actual price action.

Per the plan (§3 "Skill collapses"), legacy 9D-applied-proposals and 9E
(evolution branch + PR) are dropped — those don't fit deterministic
scheduling. The decision-log step replaces the dropped 9D slot.

Each artifact has a Pydantic model matching the legacy schema in
``templates/schemas/evolution-{sources,quality-log,proposals}.schema.json``
at the fields the legacy system enforces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field, model_validator

from digiquant.atlas.decision_log import persist_pending
from digiquant.atlas.phases._node_factory import _shared_context
from digiquant.hermes.state import HermesState
from digiquant.atlas.supabase_io import SupabaseClient


# ─── 9A Sources Scorecard ──────────────────────────────────────────────────


class SourceScore(BaseModel):
    source: str = Field()
    stars: int = Field(ge=1, le=5)
    failures_today: int = Field(default=0, ge=0)
    notes: str = Field(default="")


class EvolutionSources(BaseModel):
    scored: list[SourceScore] = Field(default_factory=list)
    discoveries: list[str] = Field(default_factory=list)


# ─── 9B Quality Post-Mortem ─────────────────────────────────────────────────


class PredictionCheck(BaseModel):
    prediction: str = Field()
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
    target_file: str = Field()
    change_summary: str = Field()
    rationale: str = Field()
    confidence: int = Field(
        ge=1,
        le=5,
        description="Evidence strength: 1=speculative, 3=reasoned, 5=high-evidence.",
    )
    expected_impact: Literal["low", "medium", "high"]


class EvolutionProposals(BaseModel):
    # Count cap (not a string-length limit): hard ceiling to prevent runaway
    # self-modification. Low-confidence proposals (< 3) are stripped by the
    # model validator below so they never reach downstream consumers.
    proposals: list[ImprovementProposal] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _filter_low_confidence(self) -> "EvolutionProposals":
        self.proposals = [p for p in self.proposals if p.confidence >= 3]
        return self


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


@dataclass(frozen=True)
class Phase9Deps:
    """Optional wiring for Phase 9.

    Currently carries the Supabase client used to persist Phase A
    ``decision_log`` rows. Optional — when ``None``, the decision-log step
    is skipped (preserves the dry-run path that never builds a real client
    and keeps existing tests that exercise only the LLM artifact path
    untouched).

    Production CLI populates this with the same client used by preflight,
    publish, and the resolver — see :func:`digiquant.atlas.graph.cli_main`.
    """

    client: SupabaseClient


def _phase9_node_factory(
    deps: Phase9Deps | None,
) -> Callable[[HermesState], dict[str, Any]]:
    """Build the Phase 9 node bound to ``deps``.

    Returns a closure that:
    1. Persists the Phase A decision-log rows when a Supabase client is
       wired (no-op otherwise).
    2. Runs the existing LLM evolution-artifacts call and writes the
       result into ``state.phase9_evolution``.

    Step ordering matters: the persistence step must NOT block the LLM
    step. If the DB write throws, the LLM artifact still produces — Phase 9
    is best-effort on both sides and a partial output is more useful than
    a hard failure that loses the whole evolution snapshot.
    """

    def _node(state: HermesState) -> dict[str, Any]:
        # ── Phase A: decision-log persistence (non-LLM, Supabase write) ─
        if deps is not None:
            try:
                persist_pending(client=deps.client, state=state)
            except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
                # Surfaced via the standard logger so the operator sees it
                # in the audit log. Phase B still runs at start-of-next-run
                # against whatever rows did make it in.
                import logging

                logging.getLogger(__name__).warning(
                    "phase9 decision_log persist failed (run_id=%s): %s",
                    state.run_id,
                    exc,
                )

        # ── Phase 9A/B/C: LLM evolution artifacts ─────────────────────
        from digigraph.graph.research_agent import run_research_agent

        from digiquant.hermes.skills import load_skill

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
            phase_slug="phase9-evolution",
        )
        return {"phase9_evolution": result.model_dump(mode="json")}

    return _node


def build_phase9(deps: Phase9Deps | None = None) -> PipelinePhase:
    """Return the Phase 9 pipeline phase.

    ``deps=None`` preserves the legacy LLM-only behavior. Pass
    ``Phase9Deps(client=...)`` to enable the decision-log persistence step
    (Phase A of #432).
    """
    return PipelinePhase(
        name="phase9_evolution",
        nodes=[NodeSpec(name="evolution", run=_phase9_node_factory(deps))],
    )


__all__ = [
    "EvolutionProposals",
    "EvolutionQualityLog",
    "EvolutionSources",
    "Phase9Artifacts",
    "Phase9Deps",
    "build_phase9",
]

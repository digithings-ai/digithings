"""Phase-node factory.

Most phase nodes follow the same pattern:
1. Build shared_context from state (config, prior_context, data_layer).
2. Load the segment's skill text.
3. Call the generic research agent with the segment's output model.
4. Wrap the result in a ``SegmentSlot`` → stash under the phase's output dict.

Instead of repeating that skeleton 20+ times, this factory produces a
node callable from a small spec. Keeps phase modules short and makes the
pattern reviewable in one place.

Triage (delta-mode carry-forward) is wired in commit 8 — the factory takes
an optional ``triage_gate`` callable that, when supplied, decides whether
to regenerate or emit ``Carried`` for a given (state, segment_slug).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable  # noqa: F401 — used for heterogeneous node-update dict shape

from pydantic import BaseModel

from digigraph.graph.research_agent import run_research_agent

from digiquant_atlas.skills import load_skill
from digiquant_atlas.state import (
    AtlasResearchState,
    Carried,
    SegmentPayload,
    SegmentSlot,
)


@dataclass(frozen=True)
class SegmentNodeSpec:
    """Config for one segment-running node."""

    segment_slug: str
    """Stable slug written into SegmentPayload.segment and the output dict key."""

    skill_slug: str
    """Path in ``apps/digiquant-atlas/skills/<slug>/SKILL.md`` — the 'what to research'."""

    output_model: type[BaseModel]
    """Pydantic class the LLM output must validate against."""

    phase_outputs_field: str
    """AtlasResearchState attribute this node updates (e.g. 'phase1_outputs')."""


def _shared_context(state: AtlasResearchState) -> dict[str, Any]:
    """Assemble the stable, run-wide context block passed to every phase node.

    Serialized with sorted keys inside run_research_agent's formatter, so
    identical inputs produce identical cache keys across phase calls.
    """
    return {
        "run_type": state.run_type,
        "run_date": state.run_date.isoformat(),
        "baseline_date": state.baseline_date.isoformat() if state.baseline_date else None,
        "config": state.config.model_dump(mode="json"),
        "prior_context": state.prior_context.model_dump(mode="json"),
        "data_layer": state.data_layer.model_dump(mode="json"),
    }


def _phase_inputs(state: AtlasResearchState, spec: SegmentNodeSpec) -> dict[str, Any]:
    """Volatile per-segment inputs. Kept small so the cache wins on stable parts.

    For Phase 1–2 segments there is little per-segment volatile context
    today — each alt-data / institutional sub-agent reads the macro regime
    in their prompt only at Phase 3+. When a segment needs upstream phase
    outputs, extend ``_phase_inputs`` to look up the relevant keys from state.
    """
    inputs: dict[str, Any] = {"segment": spec.segment_slug}
    # If this is a Phase 3+ node, it can read earlier-phase outputs. Phases
    # 1 and 2 don't consume prior-phase work beyond shared_context, so the
    # baseline lookup is empty for them.
    return inputs


def build_segment_node(
    spec: SegmentNodeSpec,
    *,
    triage_gate: Callable[[AtlasResearchState, str], Carried | None] | None = None,
    model: str | None = None,
) -> Callable[[AtlasResearchState], dict[str, Any]]:
    """Return a LangGraph-shaped node function for one segment.

    Triage is consulted in this order:
    1. If ``triage_gate`` is passed, it takes precedence (used by tests that
       want to bypass state-based triage).
    2. Otherwise ``state.triage`` is read in-node: if it holds a decision
       for this segment and the decision is ``carry``, the node emits a
       Carried marker and returns. This is how the compiled Atlas graph
       wires delta-mode carry-forward without having to rebuild nodes.
    3. If neither path carries, the LLM runs.
    """

    def _node(state: AtlasResearchState) -> dict[str, Any]:
        carried: Carried | None = None
        if triage_gate is not None:
            carried = triage_gate(state, spec.segment_slug)
        elif state.triage is not None:
            decision = next(
                (d for d in state.triage.decisions if d.segment == spec.segment_slug),
                None,
            )
            if decision is not None and decision.decision == "carry":
                carried = Carried(
                    baseline_date=state.baseline_date or state.run_date,
                    reason=decision.reason,
                )
        if carried is not None:
            slot = SegmentSlot(payload=carried)
            return {spec.phase_outputs_field: {spec.segment_slug: slot}}

        skill_text = load_skill(spec.skill_slug)
        shared = _shared_context(state)
        inputs = _phase_inputs(state, spec)
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=inputs,
            shared_context=shared,
            output_model=spec.output_model,
            model=model,
        )
        payload = SegmentPayload(
            segment=spec.segment_slug,
            body=result.model_dump(mode="json"),
            as_of=state.run_date,
        )
        slot = SegmentSlot(payload=payload)
        return {spec.phase_outputs_field: {spec.segment_slug: slot}}

    return _node

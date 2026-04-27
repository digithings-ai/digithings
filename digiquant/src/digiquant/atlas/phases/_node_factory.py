"""Phase-node factory.

Most phase nodes follow the same pattern:
1. Build shared_context from state (config, prior_context, data_layer).
2. Assemble phase_inputs (volatile per-phase context — may include upstream
   phase outputs).
3. Load the segment's skill text.
4. Call the generic research agent with the segment's output model.
5. Wrap the result in a ``SegmentSlot`` → stash under the phase's output dict
   (or a scalar state field for single-slot phases like macro).

The factory exposes two seams so every Atlas phase can use it:
- ``inputs_builder`` — customizes step 2. Lets Phase 3+ nodes pull upstream
  phase outputs into phase_inputs; Phases 1/2 use the default.
- ``write_adapter`` — customizes step 5. Lets macro (single slot) and the
  dict-valued phases share one implementation.

Triage is consulted in three orders of precedence:
1. Explicit ``triage_gate`` kwarg (used by tests that want to bypass state).
2. ``state.triage`` decisions (how the compiled graph wires delta carry-forward).
3. Otherwise: run the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable  # noqa: F401 — used for heterogeneous node-update dict shape

from pydantic import BaseModel

from digigraph.graph.research_agent import run_research_agent

from digiquant.atlas.skills import load_skill
from digiquant.atlas.state import (
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


# Type aliases for the two factory seams.
InputsBuilder = Callable[[AtlasResearchState, SegmentNodeSpec], dict[str, Any]]
WriteAdapter = Callable[[SegmentNodeSpec, SegmentSlot], dict[str, Any]]


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


def default_inputs_builder(_state: AtlasResearchState, spec: SegmentNodeSpec) -> dict[str, Any]:
    """Volatile per-segment inputs — minimal default.

    Phase 1 and Phase 2 nodes use this as-is; later phases supply their own
    builder that pulls upstream phase outputs into phase_inputs (see
    ``phase4_assetclass.py``'s macro-regime injection).
    """
    return {"segment": spec.segment_slug}


def dict_slot_write_adapter(spec: SegmentNodeSpec, slot: SegmentSlot) -> dict[str, Any]:
    """Default write: update ``state.<phase_outputs_field>[segment_slug] = slot``."""
    return {spec.phase_outputs_field: {spec.segment_slug: slot}}


def scalar_slot_write_adapter(spec: SegmentNodeSpec, slot: SegmentSlot) -> dict[str, Any]:
    """Scalar write: ``state.<phase_outputs_field> = slot`` (used by single-slot
    phases like macro where ``phase_outputs_field`` names a scalar field, not a
    dict)."""
    return {spec.phase_outputs_field: slot}


def build_segment_node(
    spec: SegmentNodeSpec,
    *,
    inputs_builder: InputsBuilder = default_inputs_builder,
    write_adapter: WriteAdapter = dict_slot_write_adapter,
    triage_gate: Callable[[AtlasResearchState, str], Carried | None] | None = None,
    model: str | None = None,
) -> Callable[[AtlasResearchState], dict[str, Any]]:
    """Return a LangGraph-shaped node function for one segment.

    Parameters:
        spec: segment slug, skill slug, output model, output field name.
        inputs_builder: customizes the volatile per-call phase_inputs block.
            Default returns ``{"segment": spec.segment_slug}``. Phases 3+
            supply builders that pull upstream phase outputs.
        write_adapter: maps (spec, slot) → state-update dict. Default writes
            into the phase's output dict; ``scalar_slot_write_adapter``
            handles single-slot fields like ``phase3_output``.
        triage_gate: explicit gate callable (test-only). When None, the node
            reads ``state.triage`` in-node to pick carry vs. regen.
        model: LiteLLM model override; defaults to DIGI_LLM_MODE routing.
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
            return write_adapter(spec, SegmentSlot(payload=carried))

        skill_text = load_skill(spec.skill_slug)
        shared = _shared_context(state)
        inputs = inputs_builder(state, spec)
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=inputs,
            shared_context=shared,
            output_model=spec.output_model,
            model=model,
            phase_slug=spec.segment_slug,
        )
        payload = SegmentPayload(
            segment=spec.segment_slug,
            body=result.model_dump(mode="json"),
            as_of=state.run_date,
        )
        return write_adapter(spec, SegmentSlot(payload=payload))

    return _node


__all__ = [
    "InputsBuilder",
    "SegmentNodeSpec",
    "WriteAdapter",
    "build_segment_node",
    "default_inputs_builder",
    "dict_slot_write_adapter",
    "scalar_slot_write_adapter",
]

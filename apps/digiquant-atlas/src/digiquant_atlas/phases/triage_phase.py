"""Triage phase — computes state.triage on delta runs.

Runs between preflight and Phase 1. On baseline/monthly runs this phase
is a no-op (a triage computation would be wasted — all segments regen).
Downstream phase nodes read state.triage in ``_node_factory`` to decide
whether to carry or regenerate.
"""

from __future__ import annotations

from typing import Any  # noqa: F401 — used for LangGraph update dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant_atlas.state import AtlasResearchState
from digiquant_atlas.triage import evaluate


def _triage_node(state: AtlasResearchState) -> dict[str, Any]:
    if state.run_type != "delta":
        return {}
    result = evaluate(state)
    return {"triage": result}


def build_triage_phase() -> PipelinePhase:
    return PipelinePhase(
        name="triage",
        nodes=[NodeSpec(name="triage", run=_triage_node)],
    )


__all__ = ["build_triage_phase"]

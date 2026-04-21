"""Compiled Atlas sub-graph — public entry point.

DigiClaw (issue #219) invokes the Atlas pipeline through ``build_atlas_graph``
plus ``AtlasInput``. The contract is deliberately small and stable so the
scheduler never has to know about internal phase structure.

Three graph shapes based on ``run_type``:
- ``baseline`` — full 9-phase pipeline. Preflight → Phase 1 (parallel) →
  Phase 2 → Phase 3 → Phase 4 → Phase 5 (equity → sectors → scorecard) →
  Phase 6 → Phase 7 → Phase 7C (per-ticker) → Phase 7D → Phase 9.
- ``delta`` — same topology, with a triage phase inserted after preflight
  that populates ``state.triage``. Downstream nodes read triage
  in-node and short-circuit carry decisions.
- ``monthly`` — preflight → monthly-synthesis (bypasses the segment layer).

Phase 9 is only wired on baseline + monthly runs per the plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable  # noqa: F401 — used for LangGraph node shape
from uuid import UUID

from digigraph.graph.pipeline_builder import PipelinePhase, build_pipeline

from digiquant_atlas.phases.phase1_altdata import build_phase1
from digiquant_atlas.phases.phase2_institutional import build_phase2
from digiquant_atlas.phases.phase3_macro import build_phase3
from digiquant_atlas.phases.phase4_assetclass import build_phase4
from digiquant_atlas.phases.phase5_equities import build_phase5
from digiquant_atlas.phases.phase6_consolidate import build_phase6
from digiquant_atlas.phases.phase7_synthesis import build_phase7
from digiquant_atlas.phases.phase7c_analyst import build_phase7c
from digiquant_atlas.phases.phase7d_pm import build_phase7d
from digiquant_atlas.phases.phase9_evolution import build_phase9
from digiquant_atlas.phases.phase_monthly import build_phase_monthly
from digiquant_atlas.phases.preflight import PreflightDeps, build_preflight_node
from digiquant_atlas.phases.triage_phase import build_triage_phase
from digiquant_atlas.state import AtlasConfigBundle, AtlasResearchState, RunType


@dataclass(frozen=True)
class AtlasInput:
    """Contract between DigiClaw and the Atlas sub-graph.

    Kept small on purpose — one job's worth of invocation data. The
    watchlist is part of the input (not the state) because Phase 7C's
    fan-out width is determined at graph-compile time; changing the
    watchlist mid-run would require a recompile.
    """

    run_type: RunType
    run_date: date
    baseline_date: date | None = None
    watchlist: tuple[str, ...] = ()
    digi_bearer: str | None = None


@dataclass(frozen=True)
class AtlasGraphDeps:
    """Dependencies the sub-graph needs at invoke time.

    The caller injects a preflight deps object (Supabase client + config
    loader). This keeps the graph-construction pure — no env reads, no
    implicit globals.
    """

    preflight: PreflightDeps


def build_atlas_graph(
    run_type: RunType,
    *,
    deps: AtlasGraphDeps,
    watchlist: tuple[str, ...] = (),
):
    """Compile and return the StateGraph for ``run_type``.

    Callers:
        >>> graph = build_atlas_graph("baseline", deps=my_deps, watchlist=("AAPL",))
        >>> result = graph.invoke(AtlasResearchState(run_type="baseline", run_date=today))
    """
    preflight_phase = PipelinePhase(
        name="preflight",
        nodes=[_as_node("preflight", build_preflight_node(deps.preflight))],
    )

    if run_type == "monthly":
        phases = [preflight_phase, build_phase_monthly()]
        return build_pipeline(AtlasResearchState, phases)

    daily_phases: list[PipelinePhase] = [preflight_phase]
    if run_type == "delta":
        daily_phases.append(build_triage_phase())

    daily_phases.extend(
        [
            build_phase1(),
            build_phase2(),
            build_phase3(),
            build_phase4(),
            *build_phase5(),
            build_phase6(),
            build_phase7(),
            build_phase7c(list(watchlist)),
            build_phase7d(),
            build_phase9(),
        ]
    )
    return build_pipeline(AtlasResearchState, daily_phases)


def _as_node(name: str, run: Callable[..., dict[str, Any]]):
    """Wrap a plain callable into a NodeSpec without reaching into phase internals."""
    from digigraph.graph.pipeline_builder import NodeSpec

    return NodeSpec(name=name, run=run)


# ─── Initial-state helper ───────────────────────────────────────────────────


def initial_state(
    atlas_input: AtlasInput,
    config: AtlasConfigBundle | None = None,
    run_id: UUID | None = None,
) -> AtlasResearchState:
    """Build an ``AtlasResearchState`` from ``AtlasInput``.

    Separated from ``build_atlas_graph`` so tests and DigiClaw can
    construct states without touching the graph compiler.
    """
    extra: dict[str, Any] = {}
    if run_id is not None:
        extra["run_id"] = run_id
    return AtlasResearchState(
        run_type=atlas_input.run_type,
        run_date=atlas_input.run_date,
        baseline_date=atlas_input.baseline_date,
        config=config or AtlasConfigBundle(watchlist=list(atlas_input.watchlist)),
        **extra,
    )


__all__ = [
    "AtlasGraphDeps",
    "AtlasInput",
    "build_atlas_graph",
    "initial_state",
]

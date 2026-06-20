"""Compiled Hermes sub-graph — thesis-first H1–H9 (PR 4a–4d).

Per [ADR-0015](../../../../docs/adr/0015-atlas-vs-hermes.md), Hermes consumes
an Atlas digest and produces analyst, deliberation, PM, and reflection outputs
via ``state.phase_hermes`` slots.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any  # noqa  # scored-lint suppression: opaque LangGraph checkpointer handle

from digigraph.graph.pipeline_builder import NodeSpec
from digiquant.olympus.hermes.pipeline_builder import PipelinePhase, build_pipeline

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.phases.h1_thesis_review import build_h1_thesis_review
from digiquant.olympus.hermes.phases.h2_market_thesis_exploration import (
    build_h2_market_thesis_exploration,
)
from digiquant.olympus.hermes.phases.h3_thesis_vehicle_map import build_h3_thesis_vehicle_map
from digiquant.olympus.hermes.phases.h4_opportunity_screener import (
    build_h4_opportunity_screener,
    preview_focus_roster_tickers,
)
from digiquant.olympus.hermes.phases.h5_asset_analyst import build_h5_asset_analyst_phases
from digiquant.olympus.hermes.phases.h6_deliberation import build_h6_deliberation_phases
from digiquant.olympus.hermes.phases.h7_pm_direction import build_h7_pm_direction
from digiquant.olympus.hermes.phases.h9_commit_run import CommitRunDeps, build_h9_commit_run
from digiquant.olympus.hermes.phases.phase7e_risk_sizing import (
    RiskSizingDeps,
    build_risk_sizing_phase,
)
from digiquant.olympus.hermes.phases.phase9_evolution import Phase9Deps
from digiquant.olympus.hermes.state import HermesState

__all__ = [
    "CommitRunDeps",
    "HermesGraphDeps",
    "Phase9Deps",
    "ThesisGraphDeps",
    "build_hermes_graph",
    "build_hermes_phases",
    "build_hermes_phases_thesis",
]


@dataclass(frozen=True)
class ThesisGraphDeps:
    """Optional Supabase client for H1–H5 thesis/analyst row writers."""

    client: SupabaseClient | None = None


@dataclass(frozen=True)
class HermesGraphDeps:
    """Dependencies for the Hermes sub-graph."""

    phase9: Phase9Deps | None = None  # legacy evolution LLM — not on daily path; use beliefs on-demand
    thesis: ThesisGraphDeps | None = None
    risk_sizing: RiskSizingDeps | None = None
    commit_run: CommitRunDeps | None = None


def _resolve_risk_sizing_client(deps: HermesGraphDeps) -> SupabaseClient | None:
    if deps.risk_sizing is not None:
        return deps.risk_sizing.client
    if deps.thesis is not None:
        return deps.thesis.client
    return None


def _build_h8_risk_sizing(deps: HermesGraphDeps) -> PipelinePhase:
    client = _resolve_risk_sizing_client(deps)
    if client is None:

        def _noop(_state: HermesState) -> dict[str, Any]:
            return {}

        return PipelinePhase(
            name="hermes_h8_risk_sizing",
            nodes=[NodeSpec(name="hermes/portfolio/risk-sizing-noop", run=_noop)],
        )
    return build_risk_sizing_phase(RiskSizingDeps(client=client))


def build_hermes_phases_thesis(
    *,
    watchlist: list[str],
    deps: HermesGraphDeps | None = None,
    debate_rounds: int = 1,  # noqa: ARG001 — removed with 7CD; kept for CLI compat
    held: Collection[str] = (),
) -> list[PipelinePhase]:
    """Thesis-first Hermes phases H1–H9 (PR 4d)."""
    deps = deps or HermesGraphDeps()
    thesis_client = deps.thesis.client if deps.thesis else None
    phases: list[PipelinePhase] = []
    phases.append(build_h1_thesis_review(client=thesis_client))
    phases.append(build_h2_market_thesis_exploration(client=thesis_client))
    phases.append(build_h3_thesis_vehicle_map(client=thesis_client))
    phases.append(build_h4_opportunity_screener())
    roster_preview = preview_focus_roster_tickers(watchlist=watchlist, held=held)
    phases.extend(build_h5_asset_analyst_phases(roster_preview, held=held, client=thesis_client))
    phases.extend(build_h6_deliberation_phases(roster_preview, held=held))
    phases.append(build_h7_pm_direction())
    phases.append(_build_h8_risk_sizing(deps))
    phases.append(build_h9_commit_run(deps.commit_run))
    return phases


def build_hermes_phases(
    *,
    watchlist: list[str],
    deps: HermesGraphDeps | None = None,
    debate_rounds: int = 1,
    held: Collection[str] = (),
) -> list[PipelinePhase]:
    """Legacy alias — thesis-first graph is canonical."""
    return build_hermes_phases_thesis(
        watchlist=watchlist, deps=deps, debate_rounds=debate_rounds, held=held
    )


def build_hermes_graph(
    *,
    watchlist: list[str],
    deps: HermesGraphDeps | None = None,
    debate_rounds: int = 1,
    checkpointer: Any = None,
    held: Collection[str] = (),
):
    """Compile and return the Hermes StateGraph."""
    return build_pipeline(
        HermesState,
        build_hermes_phases_thesis(
            watchlist=watchlist, deps=deps, debate_rounds=debate_rounds, held=held
        ),
        checkpointer=checkpointer,
    )


def _build_cli_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m digiquant.olympus.hermes.graph",
        description="Run the Hermes analysis sub-graph against a saved Atlas digest.",
    )
    parser.add_argument("--from-digest", required=True)
    parser.add_argument("--watchlist", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _load_state(path: str) -> AtlasResearchState:
    import json
    from pathlib import Path

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return AtlasResearchState.model_validate(raw)


def cli_main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    import json
    import sys

    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    watchlist = [t.strip() for t in args.watchlist.split(",") if t.strip()]
    state = _load_state(args.from_digest)

    if args.dry_run:
        graph = build_hermes_graph(watchlist=watchlist)
        json.dump(
            {
                "dry_run": True,
                "compiled": graph is not None,
                "watchlist": watchlist,
                "loaded_run_id": str(state.run_id),
            },
            sys.stdout,
            default=str,
        )
        sys.stdout.write("\n")
        return 0

    graph = build_hermes_graph(watchlist=watchlist)
    final = graph.invoke(state)
    json.dump(
        {
            "ok": True,
            "run_id": str(state.run_id),
            "asset_analysts": list(final.phase_hermes.asset_analysts.keys()),
            "pm_direction_present": final.phase_hermes.pm_direction_memo is not None,
            "sized_book_present": final.phase_hermes.sized_book is not None,
        },
        sys.stdout,
        default=str,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_main())

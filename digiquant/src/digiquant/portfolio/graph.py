"""Compiled portfolio sub-graph — thesis-first H1–H9 (PR 4a–4d).

Per [ADR-0015](../../../../docs/adr/0015-research-vs-portfolio.md), portfolio consumes
an research digest and produces analyst, deliberation, PM, and reflection outputs
via ``state.phase_portfolio`` slots.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: opaque LangGraph checkpointer handle
)

from digigraph.graph.pipeline_builder import NodeSpec

from digiquant.dashboard.research_retrieval.store import EvidenceBundleStore, ResearchStateStore
from digiquant.portfolio.phases.h1_thesis_review import build_h1_thesis_review
from digiquant.portfolio.phases.h2_market_thesis_exploration import (
    build_h2_market_thesis_exploration,
)
from digiquant.portfolio.phases.h3_thesis_vehicle_map import build_h3_thesis_vehicle_map
from digiquant.portfolio.phases.h4_opportunity_screener import build_h4_opportunity_screener
from digiquant.portfolio.phases.h5_asset_analyst import build_h5_from_state
from digiquant.portfolio.phases.h6_deliberation import build_h6_from_state
from digiquant.portfolio.phases.h7_pm_direction import build_h7_pm_direction
from digiquant.portfolio.phases.h9_commit_run import CommitRunDeps, build_h9_commit_run
from digiquant.portfolio.phases.phase7e_risk_sizing import (
    RiskSizingDeps,
    build_risk_sizing_phase,
)
from digiquant.portfolio.phases.phase9_evolution import Phase9Deps
from digiquant.portfolio.pipeline_builder import PipelinePhase, build_pipeline
from digiquant.portfolio.state import PortfolioState
from digiquant.research.state import ResearchState
from digiquant.research.supabase_io import SupabaseClient

__all__ = [
    "CommitRunDeps",
    "PortfolioGraphDeps",
    "Phase9Deps",
    "ThesisGraphDeps",
    "build_portfolio_graph",
    "build_portfolio_phases",
    "build_portfolio_phases_thesis",
]


@dataclass(frozen=True)
class ThesisGraphDeps:
    """Optional Supabase client for H1–H5 thesis/analyst row writers."""

    client: SupabaseClient | None = None


@dataclass(frozen=True)
class PortfolioGraphDeps:
    """Dependencies for the portfolio sub-graph."""

    phase9: Phase9Deps | None = (
        None  # legacy evolution LLM — not on daily path; use beliefs on-demand
    )
    thesis: ThesisGraphDeps | None = None
    risk_sizing: RiskSizingDeps | None = None
    commit_run: CommitRunDeps | None = None
    evidence_bundle_store: EvidenceBundleStore | None = None
    research_state_store: ResearchStateStore | None = None


def _resolve_risk_sizing_client(deps: PortfolioGraphDeps) -> SupabaseClient | None:
    if deps.risk_sizing is not None:
        return deps.risk_sizing.client
    if deps.thesis is not None:
        return deps.thesis.client
    return None


def _resolve_shared_client(deps: PortfolioGraphDeps) -> SupabaseClient | None:
    """Prefer thesis, then risk sizing, then H9 commit client."""
    if deps.thesis is not None and deps.thesis.client is not None:
        return deps.thesis.client
    client = _resolve_risk_sizing_client(deps)
    if client is not None:
        return client
    if deps.commit_run is not None:
        return deps.commit_run.client
    return None


def _build_h8_risk_sizing(deps: PortfolioGraphDeps) -> PipelinePhase:
    client = _resolve_risk_sizing_client(deps)
    if client is None:

        def _noop(_state: PortfolioState) -> dict[str, Any]:
            return {}

        return PipelinePhase(
            name="portfolio_h8_risk_sizing",
            nodes=[NodeSpec(name="portfolio/risk-sizing-noop", run=_noop)],
        )
    return build_risk_sizing_phase(RiskSizingDeps(client=client))


def build_portfolio_phases_thesis(
    *,
    watchlist: list[str],
    deps: PortfolioGraphDeps | None = None,
    debate_rounds: int = 1,  # removed with 7CD; kept for CLI compat
    held: Collection[str] = (),
) -> list[PipelinePhase]:
    """Thesis-first portfolio phases H1–H9 (PR 4d)."""
    deps = deps or PortfolioGraphDeps()
    thesis_client = deps.thesis.client if deps.thesis else None
    shared_client = _resolve_shared_client(deps)
    bundle_store = deps.evidence_bundle_store
    state_store = deps.research_state_store
    phases: list[PipelinePhase] = []
    phases.append(build_h1_thesis_review(client=thesis_client))
    phases.append(build_h2_market_thesis_exploration(client=thesis_client))
    phases.append(build_h3_thesis_vehicle_map(client=thesis_client))
    phases.append(build_h4_opportunity_screener(client=thesis_client))
    phases.append(
        build_h5_from_state(
            client=thesis_client,
            evidence_bundle_store=bundle_store,
            research_state_store=state_store,
        )
    )
    phases.append(
        build_h6_from_state(
            evidence_bundle_store=bundle_store,
            research_state_store=state_store,
        )
    )
    phases.append(build_h7_pm_direction(client=shared_client, research_state_store=state_store))
    phases.append(_build_h8_risk_sizing(deps))
    phases.append(build_h9_commit_run(deps.commit_run))
    return phases


def build_portfolio_phases(
    *,
    watchlist: list[str],
    deps: PortfolioGraphDeps | None = None,
    debate_rounds: int = 1,
    held: Collection[str] = (),
) -> list[PipelinePhase]:
    """Legacy alias — thesis-first graph is canonical."""
    return build_portfolio_phases_thesis(
        watchlist=watchlist, deps=deps, debate_rounds=debate_rounds, held=held
    )


def build_portfolio_graph(
    *,
    watchlist: list[str],
    deps: PortfolioGraphDeps | None = None,
    debate_rounds: int = 1,
    checkpointer: Any = None,
    held: Collection[str] = (),
):
    """Compile and return the portfolio StateGraph."""
    return build_pipeline(
        PortfolioState,
        build_portfolio_phases_thesis(
            watchlist=watchlist, deps=deps, debate_rounds=debate_rounds, held=held
        ),
        checkpointer=checkpointer,
    )


def _build_cli_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m digiquant.portfolio.graph",
        description="Run the portfolio analysis sub-graph against a saved research digest.",
    )
    parser.add_argument("--from-digest", required=True)
    parser.add_argument("--watchlist", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _load_state(path: str) -> ResearchState:
    import json
    from pathlib import Path

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return ResearchState.model_validate(raw)


def cli_main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    import json
    import sys

    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    watchlist = [t.strip() for t in args.watchlist.split(",") if t.strip()]
    state = _load_state(args.from_digest)

    if args.dry_run:
        graph = build_portfolio_graph(watchlist=watchlist)
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

    graph = build_portfolio_graph(watchlist=watchlist)
    final = graph.invoke(state)
    json.dump(
        {
            "ok": True,
            "run_id": str(state.run_id),
            "asset_analysts": list(final.phase_portfolio.asset_analysts.keys()),
            "pm_direction_present": final.phase_portfolio.pm_direction_memo is not None,
            "sized_book_present": final.phase_portfolio.sized_book is not None,
        },
        sys.stdout,
        default=str,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_main())

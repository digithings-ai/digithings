"""Compiled Hermes sub-graph — analysis, debate, PM, reflection.

Per [ADR-0015](../../../../docs/adr/0015-atlas-vs-hermes.md), Hermes consumes
an Atlas digest (``state.phase7_digest`` populated; ``phase1..phase6_*``
slots populated for raw-input fan-in) and produces:

**Thesis-first entry (planned, not wired):** translate the digest into market
theses → map vehicles per thesis → fan out analysts on thesis-attributed tickers.
The live graph jumps straight to Phase 7C; the watchlist is chosen by
``chain.cli_main`` (``select_focus_tickers``: prior-book holdings + technical
scores). See ``hermes/docs/ARCHITECTURE.md``.

Outputs:

- ``state.phase7c_specialists`` / ``phase7c_analysts`` — 4-axis analyst
  outputs per ticker.
- ``state.phase7cd_debates`` — Bull/Bear adversarial debate summaries.
- ``state.phase7d_risk_debate`` / ``phase7d_rebalance`` — risk debate +
  PM allocation memo.
- ``state.phase9_evolution`` — closed-loop reflection / alpha scoring.

Hermes does **not** wire ``publish_phase`` — that runs at the end of the
:func:`digiquant.olympus.hermes.chain.run_atlas_then_hermes` orchestrator after both
engines have populated their state slots. Standalone Hermes invocation
(``python -m digiquant.olympus.hermes.graph --from-digest <path>``) returns the
final state without publishing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any  # noqa  # scored-lint suppression: opaque LangGraph checkpointer handle

from digiquant.olympus.hermes.pipeline_builder import PipelinePhase, build_pipeline

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.hermes.phases.phase7c_analyst import build_phase7c
from digiquant.olympus.hermes.phases.phase7cd_debate import build_phase7cd
from digiquant.olympus.hermes.phases.phase7d_pm import build_phase7d
from digiquant.olympus.hermes.phases.phase9_evolution import Phase9Deps, build_phase9
from digiquant.olympus.hermes.state import HermesState

__all__ = [
    "HermesGraphDeps",
    "Phase9Deps",
    "build_hermes_graph",
    "build_hermes_phases",
]


@dataclass(frozen=True)
class HermesGraphDeps:
    """Dependencies for the Hermes sub-graph.

    ``phase9`` is the closed-loop reflection write-side wiring (alpha-vs-SPY
    scoring + ``decision_log`` row insertion). ``None`` keeps the legacy
    LLM-only path that doesn't touch Supabase — used by the legacy test
    fixtures and the dry-run CLI.
    """

    phase9: Phase9Deps | None = None


def build_hermes_phases(
    *,
    watchlist: list[str],
    deps: HermesGraphDeps | None = None,
    debate_rounds: int = 1,
) -> list[PipelinePhase]:
    """Return the four Hermes phases as an ordered list.

    Wiring contract:
        phase7c (4-axis analyst, parallel fan-out) →
        phase7cd (Bull/Bear debate, per-ticker fan-out) →
        phase7d (risk debate + PM allocation memo) →
        phase9 (closed-loop reflection / alpha scoring).
    """
    deps = deps or HermesGraphDeps()
    phases: list[PipelinePhase] = []
    phases.extend(build_phase7c(watchlist))
    phases.extend(build_phase7cd(watchlist, rounds=debate_rounds))
    phases.extend(build_phase7d())
    phases.append(build_phase9(deps.phase9))
    return phases


def build_hermes_graph(
    *,
    watchlist: list[str],
    deps: HermesGraphDeps | None = None,
    debate_rounds: int = 1,
    checkpointer: Any = None,
):
    """Compile and return the Hermes StateGraph.

    Caller produces a populated :class:`AtlasResearchState` (research outputs
    + digest) and invokes the returned graph with it. Hermes mutates the
    state in place via LangGraph reducers, returning the final state with
    the analyst/debate/PM/reflection slots populated.

    ``checkpointer`` (optional) persists per-node state for resume (#665).
    """
    return build_pipeline(
        HermesState,
        build_hermes_phases(watchlist=watchlist, deps=deps, debate_rounds=debate_rounds),
        checkpointer=checkpointer,
    )


# ─── CLI entry point ────────────────────────────────────────────────────────
#
# Invoked as ``python -m digiquant.olympus.hermes.graph …`` for standalone Hermes
# runs over a saved Atlas digest. Production cron paths use
# ``digiquant.olympus.hermes.chain`` instead so Atlas + Hermes run end-to-end.


def _build_cli_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m digiquant.olympus.hermes.graph",
        description="Run the Hermes analysis sub-graph against a saved Atlas digest.",
    )
    parser.add_argument(
        "--from-digest",
        required=True,
        help=(
            "Path to a JSON file with the serialised AtlasResearchState "
            "(produced by ``python -m digiquant.olympus.atlas.graph``). Hermes reads "
            "the digest + raw segment slots and produces analyst/PM/reflection "
            "outputs."
        ),
    )
    parser.add_argument(
        "--watchlist",
        default="",
        help="Comma-separated ticker list. Empty means Phase 7C fan-out is skipped.",
    )
    parser.add_argument(
        "--debate-rounds",
        type=int,
        default=1,
        help="Compile-time upper bound on Bull/Bear debate rounds (1..5).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compile graph + load digest, print summary, exit 0 (no LLM calls).",
    )
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
        graph = build_hermes_graph(watchlist=watchlist, debate_rounds=args.debate_rounds)
        json.dump(
            {
                "dry_run": True,
                "compiled": graph is not None,
                "watchlist": watchlist,
                "loaded_run_id": str(state.run_id),
                "loaded_run_type": state.run_type,
            },
            sys.stdout,
            default=str,
        )
        sys.stdout.write("\n")
        return 0

    graph = build_hermes_graph(watchlist=watchlist, debate_rounds=args.debate_rounds)
    final = graph.invoke(state)
    json.dump(
        {
            "ok": True,
            "run_id": str(state.run_id),
            "phase7c_analysts": list(final.phase7c_analysts.keys()),
            "phase7d_rebalance_present": final.phase7d_rebalance is not None,
            "phase9_evolution_present": final.phase9_evolution is not None,
        },
        sys.stdout,
        default=str,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_main())

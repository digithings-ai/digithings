"""Atlas → Hermes chain orchestrator (ADR-0015).

Atlas research-only → Hermes analyst/debate/PM → ``publish_phase``.
Cron entry point: ``python -m digiquant.olympus.hermes.chain``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Any  # noqa  # scored-lint suppression: opaque LangGraph checkpointer/graph

from digiquant.olympus.atlas.graph import (
    AtlasGraphDeps,
    AtlasInput,
    build_atlas_graph,
    initial_state,
)

# DESLOP-034: import keeps phase_monthly in module graph for ADR-0015 doc linkage (no lazy split).
from digiquant.olympus.atlas.phases.phase_monthly import build_phase_monthly  # noqa: F401
from digiquant.olympus.atlas.phases.preflight import (
    PreflightDeps,
    PreflightReflectDeps,
)
from digiquant.olympus.atlas.phases.publish_phase import PublishDeps, build_publish_phase
from digiquant.olympus.hermes.phases.phase7e_risk_sizing import (
    RiskSizingDeps,
    build_risk_sizing_phase,
)
from digiquant.olympus.hermes.portfolio_materialize import (
    MaterializeDeps,
    build_materialize_phase,
)
from digiquant.olympus.atlas.phases.triage_phase import TriageDeps
from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.hermes.graph import HermesGraphDeps, Phase9Deps, build_hermes_graph

_logger = logging.getLogger(__name__)

__all__ = [
    "ChainDeps",
    "cli_main",
    "run_atlas_then_hermes",
]


@dataclass(frozen=True)
class ChainDeps:
    """Dependencies for the Atlas → Hermes chain.

    Atlas-side deps (preflight, triage, preflight-reflect) come from
    :class:`AtlasGraphDeps`. Hermes-side deps (phase9 reflection write)
    come from :class:`HermesGraphDeps`. The terminal ``publish``
    :class:`PublishDeps` is shared — one Supabase client writes
    everything at the end.
    """

    atlas: AtlasGraphDeps
    hermes: HermesGraphDeps
    publish: PublishDeps | None = None
    # Phase 7E deterministic risk-sizing enforcement (#726). None → no-op (legacy /
    # dry-run / monthly). Runs BEFORE publish + materialize so the published
    # pm-rebalance document and the booked positions share the same sized book.
    risk_sizing: RiskSizingDeps | None = None
    # Phase 9D paper-portfolio materialization (#700). None → no-op (legacy /
    # dry-run / monthly). Wired on by ``cli_main`` for non-monthly runs so the
    # pipeline owns the book (owner decision 2026-06-13).
    materialize: MaterializeDeps | None = None


def _acquire_checkpointer() -> Any:
    """Return a checkpointer when ``DIGI_CHECKPOINTER`` is set, else ``None``.

    Best-effort: checkpointing is an optimization, never a hard dependency. A missing
    package, bad ``DIGI_CHECKPOINTER_POSTGRES_URI``, or unreachable Postgres degrades to
    ``None`` (a normal, uncheckpointed run) with a warning — it must not crash the run.
    """
    if not os.environ.get("DIGI_CHECKPOINTER", "").strip():
        return None
    try:
        from digigraph.graph.graph import get_checkpointer

        return get_checkpointer()
    except Exception as exc:  # noqa: BLE001 — checkpointing is best-effort; never crash the run
        _logger.warning("checkpointer unavailable (%s); running without resume", exc)
        return None


def _invoke_resumable(
    graph: Any,
    state: Any,
    checkpointer: Any,
    thread_base: str | None,
    suffix: str,
) -> Any:
    """Invoke one chained graph, resuming its own thread when a checkpoint exists.

    Distinct thread per graph (``{thread_base}::{suffix}``) so Atlas/Hermes never
    share a thread (their state schemas differ). If the thread already has a
    checkpoint, invoke(None) to continue from where it died; otherwise invoke(state).
    """
    if checkpointer is None or not thread_base:
        return graph.invoke(state)
    cfg = {"configurable": {"thread_id": f"{thread_base}::{suffix}"}}
    resuming = False
    try:
        resuming = checkpointer.get_tuple(cfg) is not None
    except Exception as exc:  # noqa: BLE001 — treat checkpoint-lookup failure as fresh run
        _logger.warning("checkpoint lookup failed for %s (%s); running fresh", suffix, exc)
    if resuming:
        _logger.info(
            "resuming %s from checkpoint thread %s", suffix, cfg["configurable"]["thread_id"]
        )
    return graph.invoke(None if resuming else state, cfg)


def run_atlas_then_hermes(
    *,
    atlas_input: AtlasInput,
    deps: ChainDeps,
    debate_rounds: int = 1,
    checkpointer: Any = None,
    thread_base: str | None = None,
    hermes_watchlist: list[str] | None = None,
) -> AtlasResearchState:
    """Compose Atlas → Hermes → publish, return the final state.

    ``hermes_watchlist`` narrows the Phase 7C/7CD per-ticker fan-out to a
    focus list (#696 — holdings + top-scored candidates) without touching the
    Atlas research watchlist; ``None`` fans out over the full watchlist.

    ``deps.atlas.publish`` is overridden to ``None`` for the Atlas pass —
    publish runs once at the very end with the full populated state.

    When ``checkpointer`` + ``thread_base`` are set, Atlas and Hermes run under
    **distinct** thread ids (``{thread_base}::atlas`` / ``::hermes``) so each
    resumes from its own checkpoint (#665); publish is never checkpointed (cheap
    + idempotent upserts).
    """
    # Atlas: research only, no publish.
    atlas_deps = AtlasGraphDeps(
        preflight=deps.atlas.preflight,
        publish=None,  # chain handles publish at the end
        triage=deps.atlas.triage,
        preflight_reflect=deps.atlas.preflight_reflect,
    )
    atlas_graph = build_atlas_graph(
        atlas_input.run_type,
        deps=atlas_deps,
        watchlist=atlas_input.watchlist,
        checkpointer=checkpointer,
    )
    state = initial_state(atlas_input)
    state = _invoke_resumable(atlas_graph, state, checkpointer, thread_base, "atlas")

    # Monthly runs end at Atlas's phase_monthly. No Hermes, no terminal
    # publish (phase_monthly handles its own output shape).
    if atlas_input.run_type == "monthly":
        return state

    # Hermes: analysis, debate, PM, reflection.
    hermes_graph = build_hermes_graph(
        watchlist=list(hermes_watchlist if hermes_watchlist is not None else atlas_input.watchlist),
        deps=deps.hermes,
        debate_rounds=debate_rounds,
        checkpointer=checkpointer,
    )
    state = _invoke_resumable(hermes_graph, state, checkpointer, thread_base, "hermes")

    # Phase 7E — deterministic risk-sizing enforcement (#726). Overwrites the PM's
    # eyeballed candidate book with capped, vol-targeted, reduce-only weights. Runs
    # BEFORE publish + materialize so the published pm-rebalance document and the booked
    # positions reflect the SAME sized book. No-op when deps absent or the PM held cash.
    if deps.risk_sizing is not None:
        from digiquant.olympus.hermes.pipeline_builder import build_pipeline

        risk_only = [build_risk_sizing_phase(deps.risk_sizing)]
        state = build_pipeline(AtlasResearchState, risk_only).invoke(state)

    # Terminal publish — single pass over the fully populated state.
    if deps.publish is not None:
        from digiquant.olympus.hermes.pipeline_builder import build_pipeline

        publish_only = [build_publish_phase(deps.publish)]
        # Re-use the same state model + pipeline machinery for consistency.
        publish_graph = build_pipeline(AtlasResearchState, publish_only)
        state = publish_graph.invoke(state)

    # Phase 9D — materialize the PM decision into the paper book (#700). Runs
    # after publish so the documents exist alongside the positions/NAV. No-op
    # when deps absent (dry-run / legacy) or on monthly runs (no rebalance).
    if deps.materialize is not None:
        from digiquant.olympus.hermes.pipeline_builder import build_pipeline

        materialize_only = [build_materialize_phase(deps.materialize)]
        state = build_pipeline(AtlasResearchState, materialize_only).invoke(state)

    return state


# ─── CLI entry point ────────────────────────────────────────────────────────
#
# Invoked as ``python -m digiquant.olympus.hermes.chain --run-type baseline …`` by
# the cron workflows (atlas-baseline.yml / atlas-delta.yml /
# atlas-monthly.yml). Mirrors the old ``python -m digiquant.olympus.atlas.graph``
# CLI surface so the workflow YAML diff stays minimal.


def _parse_cli_date(value: str) -> date:
    from datetime import datetime as _dt

    return _dt.strptime(value, "%Y-%m-%d").date()


def _build_cli_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m digiquant.olympus.hermes.chain",
        description="Run Atlas → Hermes end-to-end (research + analysis + PM + reflection).",
    )
    parser.add_argument(
        "--run-type",
        required=True,
        choices=("baseline", "delta", "monthly"),
        help="Pipeline shape to compile and run.",
    )
    parser.add_argument(
        "--run-date",
        required=True,
        type=_parse_cli_date,
        help="YYYY-MM-DD — the logical date this run represents.",
    )
    parser.add_argument(
        "--baseline-date",
        type=_parse_cli_date,
        default=None,
        help="Explicit baseline date for delta runs. Ignored when --auto-baseline is set.",
    )
    parser.add_argument(
        "--resume-run-id",
        default=None,
        help=(
            "Resume a prior run's checkpoints (its GITHUB_RUN_ID). Requires "
            "DIGI_CHECKPOINTER=postgres + DIGI_CHECKPOINTER_POSTGRES_URI. Atlas/Hermes "
            "continue from the last completed node; completed work is not re-run."
        ),
    )
    parser.add_argument(
        "--auto-baseline",
        action="store_true",
        help="Resolve --baseline-date from Supabase (delta runs only).",
    )
    parser.add_argument(
        "--watchlist",
        default="",
        help=(
            "Comma-separated ticker list. Empty falls back to config/watchlist.md "
            "(#694); pass 'none' to skip the Phase 7C fan-out entirely."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve inputs + compile graphs, print summary, exit 0 (no LLM calls).",
    )
    parser.add_argument(
        "--custom-prompt",
        default="",
        help=(
            "Optional one-off research prompt (#313). When set, Phase 7 synthesis "
            "includes the prompt as additional context."
        ),
    )
    return parser


def cli_main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    import json
    import sys

    # Re-use Atlas's CLI helpers — they already handle --auto-baseline,
    # watchlist parsing, summary formatting.
    from digiquant.olympus.atlas.graph import _make_default_config_loader, resolve_cli_inputs

    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    kwargs = resolve_cli_inputs(args)
    atlas_input = AtlasInput(**kwargs)

    summary = {
        "run_type": atlas_input.run_type,
        "run_date": atlas_input.run_date.isoformat(),
        "baseline_date": (
            atlas_input.baseline_date.isoformat() if atlas_input.baseline_date else None
        ),
        "watchlist": list(atlas_input.watchlist),
    }

    if args.dry_run:
        # Compile both graphs cleanly, no invocation.
        compiled = {"atlas": False, "hermes": False}
        try:
            atlas_deps = AtlasGraphDeps(
                preflight=PreflightDeps(client=None, config_loader=None)  # type: ignore[arg-type]
            )
            build_atlas_graph(
                atlas_input.run_type, deps=atlas_deps, watchlist=atlas_input.watchlist
            )
            compiled["atlas"] = True
            if atlas_input.run_type != "monthly":
                build_hermes_graph(watchlist=list(atlas_input.watchlist))
                compiled["hermes"] = True
        except Exception as exc:  # pragma: no cover
            summary["compile_error"] = repr(exc)
        json.dump({**summary, "dry_run": True, "compiled": compiled}, sys.stdout, default=str)
        sys.stdout.write("\n")
        return 0

    from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client

    client = build_client(SupabaseConfig.from_env())
    atlas_deps = AtlasGraphDeps(
        preflight=PreflightDeps(
            client=client,
            config_loader=_make_default_config_loader(atlas_input.watchlist),
        ),
        publish=None,  # chain handles publish at the end
        triage=TriageDeps(client=client) if atlas_input.run_type == "delta" else None,
        preflight_reflect=(
            PreflightReflectDeps(client=client) if atlas_input.run_type != "monthly" else None
        ),
    )
    hermes_deps = HermesGraphDeps(
        phase9=(Phase9Deps(client=client) if atlas_input.run_type != "monthly" else None),
    )
    chain_deps = ChainDeps(
        atlas=atlas_deps,
        hermes=hermes_deps,
        publish=PublishDeps(client=client) if atlas_input.run_type != "monthly" else None,
        # Deterministic risk-sizing enforcement before publish/materialize (#726).
        risk_sizing=(RiskSizingDeps(client=client) if atlas_input.run_type != "monthly" else None),
        # Pipeline owns the paper book on non-monthly runs (#700).
        materialize=(MaterializeDeps(client=client) if atlas_input.run_type != "monthly" else None),
    )
    run_id = os.environ.get("GITHUB_RUN_ID") or (
        f"{atlas_input.run_type}-{atlas_input.run_date.isoformat()}-local"
    )
    # Checkpoint/resume (#665): durable per-graph threads when DIGI_CHECKPOINTER is set
    # (DIGI_CHECKPOINTER=postgres + DIGI_CHECKPOINTER_POSTGRES_URI in prod). thread_base is
    # the run to resume (--resume-run-id) or this run's id for a fresh start. Best-effort:
    # a bad URI / unreachable Postgres degrades to an uncheckpointed run (#667).
    _checkpointer = _acquire_checkpointer()
    _thread_base = getattr(args, "resume_run_id", None) or run_id
    # Focus the 7C/7CD per-ticker fan-out on holdings + top-scored candidates
    # (#696). An explicit --watchlist is the operator override and is honored
    # verbatim; the md-fallback path gets deterministic selection instead of
    # an arbitrary alphabetical slice. Atlas research scope is unchanged.
    _hermes_watchlist: list[str] | None = None
    if not args.watchlist.strip() and atlas_input.run_type != "monthly":
        from digiquant.olympus.hermes.candidates import select_focus_tickers

        _hermes_watchlist = select_focus_tickers(
            client=client,
            watchlist=list(atlas_input.watchlist),
            run_date=atlas_input.run_date,
        )
        summary["hermes_focus"] = list(_hermes_watchlist)

    run_atlas_then_hermes(
        atlas_input=atlas_input,
        deps=chain_deps,
        checkpointer=_checkpointer,
        thread_base=_thread_base,
        hermes_watchlist=_hermes_watchlist,
    )

    json.dump({"ok": True, "summary": summary}, sys.stdout, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_main())

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
from digiquant.olympus.atlas.state import AtlasResearchState, PhaseError
from digiquant.olympus.atlas import diagnostics as _diagnostics
from digiquant.olympus.hermes.graph import HermesGraphDeps, Phase9Deps, build_hermes_graph

from digigraph import usage as _usage

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
    # Per-run telemetry row (#726, 1B). None → skip the diagnostics write (dry-run /
    # legacy). Always wired by ``cli_main`` so every real run records its health.
    diagnostics: DiagnosticsDeps | None = None


@dataclass(frozen=True)
class DiagnosticsDeps:
    """Wiring for the ``atlas_run_diagnostics`` telemetry write (Pillar 1B)."""

    client: Any
    run_id: str
    model: str | None = None


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


def _degraded_run_pct() -> float:
    """``ATLAS_DEGRADED_RUN_PCT`` (failed-segment %% that marks a run degraded); default 50."""
    try:
        return float(os.environ.get("ATLAS_DEGRADED_RUN_PCT", "") or 50.0)
    except ValueError:
        return 50.0


def _record_chain_error(state: AtlasResearchState, label: str, exc: Exception) -> None:
    """Append a PhaseError marking a chain-level failure (``phase="chain"``, ``node=label``)
    so the diagnostics degraded gate sees it: ``summarize_run`` marks the run *failed* when a
    core engine (atlas/hermes) crashed and *degraded* on any other chain-level crash
    (publish/materialize/risk-sizing). The ``"chain"`` marker keeps these distinct from
    node-level errors (which are already reflected as failed segments). Best-effort —
    error-recording must never itself break the chain."""
    try:
        state.errors.append(
            PhaseError(phase="chain", node=label, message=str(exc)[:500], retryable=True)
        )
    except Exception:  # noqa: BLE001 — defensive; a bad append can't be allowed to abort the run
        _logger.debug("chain: could not record error for %s", label, exc_info=True)


def _safe_invoke_graph(
    graph: Any, state: AtlasResearchState, checkpointer: Any, thread_base: str | None, label: str
) -> AtlasResearchState:
    """Run a sub-graph; on a graph-level crash record the error and return the last-good
    state, so the terminal phases (publish/materialize) and the diagnostics row still run.
    Per-node failures are already handled fail-soft inside the graph (Pillar 1A); this is
    the belt-and-suspenders for a rare whole-graph raise (infra / checkpointer)."""
    try:
        return _invoke_resumable(graph, state, checkpointer, thread_base, label)
    except Exception as exc:  # noqa: BLE001 — a late crash must still reach publish/materialize
        _logger.exception("chain: %s graph failed; continuing with last-good state", label)
        _record_chain_error(state, label, exc)
        return state


def _run_terminal_phase(
    phase_deps: Any, build_phase: Any, state: AtlasResearchState, label: str
) -> AtlasResearchState:
    """Run one terminal single-node phase (risk-sizing / publish / materialize) when its
    deps are present; a failure in one is recorded and never blocks the others or the
    diagnostics write."""
    if phase_deps is None:
        return state
    from digiquant.olympus.hermes.pipeline_builder import build_pipeline

    try:
        return build_pipeline(AtlasResearchState, [build_phase(phase_deps)]).invoke(state)
    except Exception as exc:  # noqa: BLE001 — one terminal phase failing must not abort the rest
        _logger.exception("chain: terminal phase %s failed; continuing", label)
        _record_chain_error(state, label, exc)
        return state


def run_atlas_then_hermes(
    *,
    atlas_input: AtlasInput,
    deps: ChainDeps,
    debate_rounds: int | None = None,
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

    ``debate_rounds``: compile-time upper bound on Bull/Bear debate rounds.
    ``None`` (default) defers to ``atlas_input.config.preferences["debate_rounds"]``
    so the operator can configure multi-round debate via the investment profile
    without a code change (#814). Explicit non-None overrides preferences.
    """
    # Resolve the compile-time debate round count from preferences when no
    # explicit override was supplied.  Bounds clamped identically to
    # ``_round_count`` in phase7cd_debate.py (1..5).
    if debate_rounds is None:
        _pref_raw = atlas_input.config.preferences.get("debate_rounds", 1)
        try:
            debate_rounds = max(1, min(5, int(_pref_raw)))
        except (TypeError, ValueError):
            debate_rounds = 1

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
    # Capture LLM usage for the whole run and ALWAYS write the diagnostics row + reset on
    # the way out (telemetry is fail-soft inside write_row, so this never crashes the run).
    _usage.start()
    try:
        state = _safe_invoke_graph(atlas_graph, state, checkpointer, thread_base, "atlas")

        # Monthly runs end at Atlas's phase_monthly. No Hermes, no terminal phases
        # (phase_monthly handles its own output shape).
        if atlas_input.run_type != "monthly":
            # Hermes: analysis, debate, PM, reflection.
            hermes_graph = build_hermes_graph(
                watchlist=list(
                    hermes_watchlist if hermes_watchlist is not None else atlas_input.watchlist
                ),
                deps=deps.hermes,
                debate_rounds=debate_rounds,
                checkpointer=checkpointer,
            )
            state = _safe_invoke_graph(hermes_graph, state, checkpointer, thread_base, "hermes")

            # Terminal phases, each guarded so one failing never blocks the next or the
            # diagnostics write. Phase 7E risk-sizing runs BEFORE publish + materialize so
            # the published pm-rebalance document and the booked positions share the SAME
            # sized book; materialize then books the enforced weights.
            state = _run_terminal_phase(
                deps.risk_sizing, build_risk_sizing_phase, state, "risk-sizing"
            )
            state = _run_terminal_phase(deps.publish, build_publish_phase, state, "publish")
            state = _run_terminal_phase(
                deps.materialize, build_materialize_phase, state, "materialize"
            )
        return state
    finally:
        if deps.diagnostics is not None:
            _diagnostics.write_row(
                deps.diagnostics.client,
                state=state,
                run_id=deps.diagnostics.run_id,
                run_type=atlas_input.run_type,
                run_date=atlas_input.run_date,
                model=deps.diagnostics.model,
                usage_snapshot=_usage.snapshot(),
            )
        _usage.reset()


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
    run_id = os.environ.get("GITHUB_RUN_ID") or (
        f"{atlas_input.run_type}-{atlas_input.run_date.isoformat()}-local"
    )
    _non_monthly = atlas_input.run_type != "monthly"
    chain_deps = ChainDeps(
        atlas=atlas_deps,
        hermes=hermes_deps,
        publish=PublishDeps(client=client) if _non_monthly else None,
        # Deterministic risk-sizing enforcement before publish/materialize (#726).
        risk_sizing=(RiskSizingDeps(client=client) if _non_monthly else None),
        # Pipeline owns the paper book on non-monthly runs (#700).
        materialize=(MaterializeDeps(client=client) if _non_monthly else None),
        # Per-run telemetry row (#726, 1B) — segment-count based, so non-monthly only.
        diagnostics=(DiagnosticsDeps(client=client, run_id=run_id) if _non_monthly else None),
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

    final_state = run_atlas_then_hermes(
        atlas_input=atlas_input,
        deps=chain_deps,
        checkpointer=_checkpointer,
        thread_base=_thread_base,
        hermes_watchlist=_hermes_watchlist,
    )

    # Degraded-run gate (#726, 1B): a run that produced little/no fresh research is worth
    # retrying — exit non-zero so the CI outer-retry fires (one bad sector does NOT trip
    # it; the threshold is ATLAS_DEGRADED_RUN_PCT, default 50%). The diagnostics row, written
    # inside run_atlas_then_hermes, records the why. Monthly runs use a different output
    # shape (no research segments) so the gate doesn't apply.
    degraded = _non_monthly and _diagnostics.is_degraded(
        final_state, degraded_pct=_degraded_run_pct()
    )
    summary["degraded"] = degraded
    json.dump({"ok": not degraded, "summary": summary}, sys.stdout, default=str)
    sys.stdout.write("\n")
    return 1 if degraded else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_main())

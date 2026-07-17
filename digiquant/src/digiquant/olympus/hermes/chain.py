"""Atlas → Hermes chain orchestrator (ADR-0015).

Atlas research-only → Hermes analyst/debate/PM → ``publish_phase``.
Cron entry point: ``python -m digiquant.olympus.hermes.chain``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any  # noqa  # scored-lint suppression: opaque LangGraph checkpointer/graph

from digiquant.olympus.atlas.graph import (
    AtlasGraphDeps,
    AtlasInput,
    _legacy_run_type,
    build_atlas_graph,
    initial_state,
)
from digiquant.olympus.atlas.phases.preflight import (
    PreflightDeps,
    PreflightReflectDeps,
)
from digiquant.olympus.atlas.phases.publish_phase import PublishDeps, build_publish_phase
from digiquant.olympus.atlas.phases.triage_phase import TriageDeps
from digiquant.olympus.atlas.state import AtlasResearchState, PhaseError
from digiquant.olympus.atlas import diagnostics as _diagnostics
from digiquant.olympus.learning.beliefs_distillation import run_beliefs_distillation_if_triggered
from digiquant.olympus.hermes.graph import (
    HermesGraphDeps,
    ThesisGraphDeps,
    build_hermes_graph,
)
from digigraph import usage as _usage

_logger = logging.getLogger(__name__)

__all__ = [
    "ChainDeps",
    "cli_main",
    "run_atlas_then_hermes",
    "run_beliefs_distillation_if_triggered",
]


@dataclass(frozen=True)
class ChainDeps:
    """Dependencies for the Atlas → Hermes chain.

    Atlas-side deps (preflight, triage, preflight-reflect) come from
    :class:`AtlasGraphDeps`. Hermes-side deps (H1–H9 thesis path) come from
    :class:`HermesGraphDeps`. Phase 9 evolution LLM (9A–9C) is **not** on the
    daily graph — beliefs distillation is on-demand via
    :func:`run_beliefs_distillation_if_triggered` (spec §11.1). The terminal
    ``publish`` :class:`PublishDeps` is shared — one Supabase client writes
    everything at the end.
    """

    atlas: AtlasGraphDeps
    hermes: HermesGraphDeps
    publish: PublishDeps | None = None
    # Phase 7E / H8 risk-sizing runs inside the Hermes graph (PR 4c). ``risk_sizing`` is
    # wired via ``HermesGraphDeps`` for the H8 node — not as a chain terminal phase.
    risk_sizing: Any | None = None  # noqa: ANN401 — legacy ChainDeps field; use hermes.risk_sizing
    # Phase 9D paper-portfolio materialization folded into Hermes H9 (PR 4d).
    materialize: Any | None = None  # legacy ChainDeps field — use hermes.commit_run
    # Per-run telemetry row (#726, 1B). None → skip the diagnostics write (dry-run /
    # legacy). Always wired by ``cli_main`` so every real run records its health.
    diagnostics: DiagnosticsDeps | None = None


@dataclass(frozen=True)
class DiagnosticsDeps:
    """Wiring for the ``atlas_run_diagnostics`` telemetry write (Pillar 1B)."""

    client: Any
    run_id: str
    model: str | None = None


def _coerce_atlas_state(result: Any) -> AtlasResearchState:
    """LangGraph ``invoke`` may return a plain dict (notably on checkpoint resume)."""
    return AtlasResearchState.model_validate(result) if isinstance(result, dict) else result


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
        return _coerce_atlas_state(graph.invoke(state))
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
    return _coerce_atlas_state(graph.invoke(None if resuming else state, cfg))


def _degraded_run_pct() -> float:
    """``ATLAS_DEGRADED_RUN_PCT`` (failed-segment %% that marks a run degraded); default 50."""
    try:
        return float(os.environ.get("ATLAS_DEGRADED_RUN_PCT", "") or 50.0)
    except ValueError:
        return 50.0


def _retry_worthy(state: AtlasResearchState, *, degraded_pct: float) -> bool:
    """Whether the CI outer-retry should fire for this run.

    True only when the run is degraded AND its book did not actually **commit**. A run that
    committed a valid book (or idempotent-noop of an already-booked day) did real, durable
    work — re-running it just burns the outer loop's backoff sleeps on a good book (the
    inception baseline sat ~20 min in retry sleeps after a successful materialization; #809).

    #1555 generalizes the #809 guard from *materialized* to *committed*: a book that H8
    materialized but H9 never persisted (coherence fail-closed / idempotency conflict / silent
    skip) is NOT durable work — it must retry. A book-less degraded run (Atlas failed / Hermes
    skipped) still retries as before.
    """
    if not _diagnostics.is_degraded(state, degraded_pct=degraded_pct):
        return False
    return not _diagnostics.book_committed(state)


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
        return _coerce_atlas_state(
            build_pipeline(AtlasResearchState, [build_phase(phase_deps)]).invoke(state)
        )
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
    hermes_held: Collection[str] = (),
) -> AtlasResearchState:
    """Compose Atlas → Hermes → publish, return the final state.

    ``hermes_watchlist`` narrows the Phase 7C/7CD per-ticker fan-out to a
    focus list (#696 — holdings + top-scored candidates) without touching the
    Atlas research watchlist; ``None`` fans out over the full watchlist.

    ``hermes_held`` are the prior-book holdings; they are threaded to the
    7C/7CD cap so a holding is never dropped by ``ATLAS_MAX_ANALYSTS`` and
    auto-exited by the PM (the Jun-18 IJR regression, #936).

    ``deps.atlas.publish`` is overridden to ``None`` for the Atlas pass —
    publish runs once at the very end with the full populated state.

    When ``checkpointer`` + ``thread_base`` are set, Atlas and Hermes run under
    **distinct** thread ids (``{thread_base}::atlas`` / ``::hermes``) so each
    resumes from its own checkpoint (#665); publish is never checkpointed (cheap
    + idempotent upserts).

    ``debate_rounds``: compile-time upper bound on Bull/Bear debate rounds.
    ``None`` defers to ``state.config.preferences["debate_rounds"]`` after the Atlas
    pass (preflight loads config; clamped via ``clamp_debate_rounds``). Explicit
    non-None overrides preferences.
    """
    state = initial_state(atlas_input)
    # Capture LLM usage for the whole run and ALWAYS write the diagnostics row + reset on
    # the way out (telemetry is fail-soft inside write_row, so this never crashes the run).
    started_at = datetime.now(tz=timezone.utc)
    _usage.start()
    try:
        # Operator escape hatch: beliefs-only run (no Atlas/Hermes research).
        if atlas_input.refresh_scope == "beliefs":
            if deps.atlas.preflight.client is not None:
                run_beliefs_distillation_if_triggered(
                    client=deps.atlas.preflight.client,
                    atlas_input=atlas_input,
                    run_type=_legacy_run_type(atlas_input.refresh_scope),
                )
            return state

        # Atlas: research only, no publish.
        atlas_deps = AtlasGraphDeps(
            preflight=deps.atlas.preflight,
            publish=None,  # chain handles publish at the end
            triage=deps.atlas.triage,
            preflight_reflect=deps.atlas.preflight_reflect,
        )
        atlas_graph = build_atlas_graph(
            deps=atlas_deps,
            watchlist=atlas_input.watchlist,
            checkpointer=checkpointer,
        )
        state = _safe_invoke_graph(atlas_graph, state, checkpointer, thread_base, "atlas")

        # Research-sufficiency gate (#944): Hermes books a rebalance + decision_log rows
        # INSIDE its own graph (H9 commit-run), so it must NOT run when the Atlas pass
        # produced no fresh research — otherwise the PM commits decisions on stale prior
        # context. The Jun-20 incident: Atlas crashed on empty LLM responses, the chain
        # swallowed it (``_safe_invoke_graph``), and a pm-rebalance was written against
        # 2-day-stale prices. Skipping records a chain error so the run is gated degraded and
        # CI's outer retry fires; the terminal publish still flushes whatever Atlas produced.
        if _diagnostics.atlas_research_produced(state):
            hermes_graph = build_hermes_graph(
                watchlist=list(
                    hermes_watchlist if hermes_watchlist is not None else atlas_input.watchlist
                ),
                deps=deps.hermes,
                checkpointer=checkpointer,
                held=hermes_held,
            )
            state = _safe_invoke_graph(hermes_graph, state, checkpointer, thread_base, "hermes")
        else:
            _logger.error(
                "chain: Atlas produced no research for %s; skipping Hermes — no rebalance booked",
                atlas_input.run_date.isoformat(),
            )
            _record_chain_error(
                state,
                "hermes-skipped",
                RuntimeError(
                    "Atlas produced no fresh research; Hermes skipped to avoid booking a "
                    "rebalance on stale context"
                ),
            )

        # Terminal phase — Atlas research artifacts only; Hermes terminal is H9 in-graph.
        state = _run_terminal_phase(deps.publish, build_publish_phase, state, "publish")

        # Automatic beliefs backlog fold (on-demand — not a daily graph node).
        if deps.atlas.preflight.client is not None:
            run_beliefs_distillation_if_triggered(
                client=deps.atlas.preflight.client,
                atlas_input=atlas_input,
                run_type=_legacy_run_type(atlas_input.refresh_scope),
            )
        return state
    finally:
        if deps.diagnostics is not None:
            finished_at = datetime.now(tz=timezone.utc)
            _diagnostics.write_row(
                deps.diagnostics.client,
                state=state,
                run_id=deps.diagnostics.run_id,
                run_type=_legacy_run_type(atlas_input.refresh_scope),
                run_date=atlas_input.run_date,
                model=deps.diagnostics.model,
                usage_snapshot=_usage.snapshot(),
                started_at=started_at,
                finished_at=finished_at,
            )
        _usage.reset()


# ─── CLI entry point ────────────────────────────────────────────────────────
#
# Invoked as ``python -m digiquant.olympus.hermes.chain --cadence daily …`` by
# the unified cron workflow (.github/workflows/olympus.yml). Mirrors the Atlas
# CLI cadence surface so the workflow YAML stays thin.


def _parse_cli_date(value: str) -> date:
    from datetime import datetime as _dt

    return _dt.strptime(value, "%Y-%m-%d").date()


def _build_cli_parser():
    import argparse

    from digiquant.olympus.atlas.graph import _add_cadence_cli_args

    parser = argparse.ArgumentParser(
        prog="python -m digiquant.olympus.hermes.chain",
        description="Run Atlas → Hermes end-to-end (research + analysis + PM + reflection).",
    )
    _add_cadence_cli_args(parser)
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
        help="Explicit baseline date for delta runs. Deprecated — prefer --refresh-scope all.",
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
        help="Resolve --baseline-date from Supabase (deprecated shim for --run-type delta).",
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

    from digigraph.model_config import apply_olympus_openrouter_env

    apply_olympus_openrouter_env()

    # Re-use Atlas's CLI helpers — they already handle --auto-baseline,
    # watchlist parsing, summary formatting.
    from digiquant.olympus.atlas.graph import _make_default_config_loader, resolve_cli_inputs

    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    kwargs = resolve_cli_inputs(args)
    atlas_input = AtlasInput(**kwargs)

    summary = {
        "cadence": atlas_input.cadence,
        "refresh_scope": atlas_input.refresh_scope,
        "run_type": _legacy_run_type(atlas_input.refresh_scope),
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
            build_atlas_graph(deps=atlas_deps, watchlist=atlas_input.watchlist)
            compiled["atlas"] = True
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
        triage=TriageDeps(client=client),
        preflight_reflect=PreflightReflectDeps(client=client),
    )
    from digiquant.olympus.hermes.phases.h9_commit_run import CommitRunDeps
    from digiquant.olympus.hermes.phases.phase7e_risk_sizing import RiskSizingDeps

    hermes_deps = HermesGraphDeps(
        thesis=ThesisGraphDeps(client=client),
        risk_sizing=RiskSizingDeps(client=client),
        commit_run=CommitRunDeps(client=client),
    )
    run_id = os.environ.get("GITHUB_RUN_ID") or (
        f"{atlas_input.cadence}-{atlas_input.run_date.isoformat()}-local"
    )
    chain_deps = ChainDeps(
        atlas=atlas_deps,
        hermes=hermes_deps,
        publish=PublishDeps(client=client),
        diagnostics=DiagnosticsDeps(client=client, run_id=run_id),
    )
    # Checkpoint/resume (#665): durable per-graph threads when DIGI_CHECKPOINTER is set
    # (DIGI_CHECKPOINTER=postgres + DIGI_CHECKPOINTER_POSTGRES_URI in prod). thread_base is
    # the run to resume (--resume-run-id) or this run's id for a fresh start. Best-effort:
    # a bad URI / unreachable Postgres degrades to an uncheckpointed run (#667).
    _checkpointer = _acquire_checkpointer()
    _thread_base = getattr(args, "resume_run_id", None) or run_id
    # Hermes H4 builds ``phase_hermes.focus_roster`` in-graph; Atlas watchlist is
    # the research scope. Prior-book holdings still thread to the 7C/7CD cap (#936).
    _holdings: list[str] = []
    if not args.watchlist.strip():
        from digiquant.olympus.atlas.supabase_io import load_prior_book
        from digiquant.olympus.hermes.candidates import holdings_from_prior_book

        _prior_book = load_prior_book(client, atlas_input.run_date)
        _holdings = holdings_from_prior_book(_prior_book)

    final_state = run_atlas_then_hermes(
        atlas_input=atlas_input,
        deps=chain_deps,
        checkpointer=_checkpointer,
        thread_base=_thread_base,
        hermes_watchlist=None,
        # Prior-book holdings always survive the 7C/7CD cap (#936). Empty when the
        # operator overrides --watchlist or for monthly runs (no Hermes).
        hermes_held=set(_holdings or ()),
    )

    # Degraded-run gate (#726, 1B) + good-book guard (#809): a run that produced little/no
    # fresh research is worth retrying — exit non-zero so the CI outer-retry fires (one bad
    # sector does NOT trip it; the threshold is ATLAS_DEGRADED_RUN_PCT, default 50%). BUT a
    # run that already materialized a valid sized book must NOT retry — that wasted ~20 min of
    # backoff sleeps on a good book (#809). The diagnostics row, written inside
    # run_atlas_then_hermes, records the why. Monthly runs (no research segments) don't trip it.
    degraded = _diagnostics.is_degraded(final_state, degraded_pct=_degraded_run_pct())
    retry_worthy = _retry_worthy(final_state, degraded_pct=_degraded_run_pct())
    summary["degraded"] = degraded
    summary["book_materialized"] = final_state.phase_hermes.sized_book is not None
    # #1555: a green run must be *provably* a committed run. ``book_committed`` sits beside
    # ``book_materialized`` so an operator never again reads ``ok:true, book_materialized:true``
    # and assumes the book persisted — the silent H4→H9 freeze (2026-06-26) presented exactly
    # that shape while nothing committed for weeks.
    summary["book_committed"] = _diagnostics.book_committed(final_state)
    json.dump({"ok": not retry_worthy, "summary": summary}, sys.stdout, default=str)
    sys.stdout.write("\n")
    return 1 if retry_worthy else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_main())

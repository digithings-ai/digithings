"""research → portfolio chain orchestrator (ADR-0015).

research-only → portfolio analyst/debate/PM → ``publish_phase``.
Cron entry point: ``python -m digiquant.portfolio.chain``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: opaque LangGraph checkpointer/graph
)

from digigraph import usage as _usage

from digiquant.research import diagnostics as _diagnostics
from digiquant.research import provider_telemetry as _provider_telemetry
from digiquant.research.graph import (
    ResearchGraphDeps,
    ResearchInput,
    _legacy_run_type,
    build_research_graph,
    initial_state,
)
from digiquant.research.phases.preflight import (
    PreflightDeps,
    PreflightReflectDeps,
)
from digiquant.research.phases.publish_phase import PublishDeps, build_publish_phase
from digiquant.research.phases.triage_phase import TriageDeps
from digiquant.research.state import ResearchConfigBundle, ResearchState, PhaseError
from digiquant.dashboard.envcompat import ATTEMPT, DEGRADED_RUN_PCT, env_lookup
from digiquant.portfolio.graph import (
    PortfolioGraphDeps,
    ThesisGraphDeps,
    build_portfolio_graph,
)
from digiquant.dashboard.learning.beliefs_distillation import run_beliefs_distillation_if_triggered
from digiquant.dashboard.overlay.persist import OverlayLegacyBookBlocked, skip_overlay_shared_register

_logger = logging.getLogger(__name__)

__all__ = [
    "ChainDeps",
    "cli_main",
    "dispatch_house_notifications_after_chain",
    "run_research_then_portfolio",
    "run_beliefs_distillation_if_triggered",
]


@dataclass(frozen=True)
class ChainDeps:
    """Dependencies for the research → portfolio chain.

    research-side deps (preflight, triage, preflight-reflect) come from
    :class:`ResearchGraphDeps`. portfolio-side deps (H1–H9 thesis path) come from
    :class:`PortfolioGraphDeps`. Phase 9 evolution LLM (9A–9C) is **not** on the
    daily graph — beliefs distillation runs after publish via
    :func:`run_beliefs_distillation_if_triggered` (daily short fold; full
    rewrite on ``refresh_scope=beliefs`` or backlog). The terminal
    ``publish`` :class:`PublishDeps` is shared — one Supabase client writes
    everything at the end.
    """

    research: ResearchGraphDeps
    portfolio: PortfolioGraphDeps
    publish: PublishDeps | None = None
    # Phase 7E / H8 risk-sizing runs inside the portfolio graph (PR 4c). ``risk_sizing`` is
    # wired via ``PortfolioGraphDeps`` for the H8 node — not as a chain terminal phase.
    risk_sizing: Any | None = None  # legacy ChainDeps field; use portfolio.risk_sizing
    # Phase 9D paper-portfolio materialization folded into portfolio H9 (PR 4d).
    materialize: Any | None = None  # legacy ChainDeps field — use portfolio.commit_run
    # Per-run telemetry row (#726, 1B). None → skip the diagnostics write (dry-run /
    # legacy). Always wired by ``cli_main`` so every real run records its health.
    diagnostics: DiagnosticsDeps | None = None


@dataclass(frozen=True)
class DiagnosticsDeps:
    """Wiring for the ``atlas_run_diagnostics`` telemetry write (Pillar 1B)."""

    client: Any
    run_id: str
    model: str | None = None
    # Outer-retry attempt number (#1762). ``pipeline-digiquant.yml`` retries the chain up to 3
    # times inside ONE job, so ``GITHUB_RUN_ID`` — and therefore ``run_id`` — is identical
    # across attempts. Before this was part of the diagnostics key, the last attempt's upsert
    # replaced the previous attempt's tokens and cost, which is why 28 of 54 production rows
    # carry a ``created_at`` that predates their own ``started_at``. Defaults to 1 so a local
    # run without the env var is a plausible first attempt rather than the legacy 0 sentinel.
    attempt: int = 1


OUTER_ATTEMPT_ENV = "OLYMPUS_ATTEMPT"


def _outer_attempt() -> int:
    """The CI outer-retry attempt number, from ``DIGIQUANT_ATTEMPT``.

    ``pipeline-digiquant.yml``'s retry loop still exports ``OLYMPUS_ATTEMPT``
    per attempt (#1762). Readers accept both names. Falls back to 1 —
    a local or single-shot run genuinely is the first attempt, and 1 keeps it distinct from
    the ``0`` sentinel migration 065 stamped on rows written before per-attempt keying.

    Tolerant of a malformed value on purpose: this feeds telemetry, and a bad env var must
    never be the reason a research run dies. A non-numeric or non-positive value is logged
    and treated as attempt 1, which at worst re-collides two attempts the way the pre-#1762
    code always did.
    """
    raw = env_lookup(ATTEMPT)
    if not raw.strip():
        return 1
    try:
        attempt = int(raw)
    except ValueError:
        _logger.warning("%s=%r is not an integer; recording attempt 1", OUTER_ATTEMPT_ENV, raw)
        return 1
    if attempt < 1:
        _logger.warning("%s=%r is not >= 1; recording attempt 1", OUTER_ATTEMPT_ENV, raw)
        return 1
    return attempt


def _coerce_research_state(result: Any) -> ResearchState:
    """LangGraph ``invoke`` may return a plain dict (notably on checkpoint resume)."""
    return ResearchState.model_validate(result) if isinstance(result, dict) else result


def _maybe_export_shadow_allocation_artifact(state: Any) -> None:
    """WP10.1 fail-soft export — never imports challenger/replay/broker code."""
    try:
        from digiquant.portfolio.shadow_artifact import (
            maybe_export_shadow_allocation_artifact,
        )

        maybe_export_shadow_allocation_artifact(state)
    except Exception:  # export must not affect production booking
        _logger.exception("chain: shadow allocation artifact export failed; continuing")


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
    except Exception as exc:  # checkpointing is best-effort; never crash the run
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

    Distinct thread per graph (``{thread_base}::{suffix}``) so research/portfolio never
    share a thread (their state schemas differ). If the thread already has a
    checkpoint, invoke(None) to continue from where it died; otherwise invoke(state).

    On resume the checkpointed ``knowledge_cutoff_at`` (and WP12.3
    ``research_state_pin``) are authoritative — the freshly built *state*
    argument is discarded so the run does not re-pin wall-clock time or
    re-select research state mid-replay (#2628 / #2863).
    """
    if checkpointer is None or not thread_base:
        return _coerce_research_state(graph.invoke(state))
    cfg = {"configurable": {"thread_id": f"{thread_base}::{suffix}"}}
    resuming = False
    try:
        resuming = checkpointer.get_tuple(cfg) is not None
    except Exception as exc:  # treat checkpoint-lookup failure as fresh run
        _logger.warning("checkpoint lookup failed for %s (%s); running fresh", suffix, exc)
    if resuming:
        _logger.info(
            "resuming %s from checkpoint thread %s", suffix, cfg["configurable"]["thread_id"]
        )
    return _coerce_research_state(graph.invoke(None if resuming else state, cfg))


def _degraded_run_pct() -> float:
    """``ATLAS_DEGRADED_RUN_PCT`` (failed-segment %% that marks a run degraded); default 50."""
    try:
        return float(env_lookup(DEGRADED_RUN_PCT) or 50.0)
    except ValueError:
        return 50.0


def _retry_worthy_summary(summary: _diagnostics.RunSummary) -> bool:
    """:func:`_retry_worthy` for a :class:`RunSummary` already in hand (avoids re-deriving it).

    Keys on ``retry_signal``, **not** ``status``: since #1736 ``status`` also flips on damage
    that is honest to report but not worth re-running (a lost research segment on a day whose
    book committed). ``retry_signal`` is the frozen pre-#1736 gate, so CI's behaviour here is
    byte-for-byte what it was.
    """
    return summary.retry_signal and not summary.book_committed


def _retry_worthy(state: ResearchState, *, degraded_pct: float) -> bool:
    """Whether the CI outer-retry should fire for this run.

    True only when the run is degraded AND its book did not actually **commit**. A run that
    committed a valid book (or idempotent-noop of an already-booked day) did real, durable
    work — re-running it just burns the outer loop's backoff sleeps on a good book (the
    inception baseline sat ~20 min in retry sleeps after a successful materialization; #809).

    #1555 generalizes the #809 guard from *materialized* to *committed*: a book that H8
    materialized but H9 never persisted (coherence fail-closed / idempotency conflict / silent
    skip) is NOT durable work — it must retry. A book-less degraded run (research failed / portfolio
    skipped) still retries as before.
    """
    return _retry_worthy_summary(_diagnostics.summarize_run(state, degraded_pct=degraded_pct))


def _record_chain_error(state: ResearchState, label: str, exc: BaseException) -> None:
    """Append a PhaseError marking a chain-level failure (``phase="chain"``, ``node=label``)
    so the diagnostics degraded gate sees it: ``summarize_run`` marks the run *failed* when a
    core engine (research/portfolio) crashed and *degraded* on any other chain-level crash
    (publish/materialize/risk-sizing). The ``"chain"`` marker keeps these distinct from
    node-level errors (which are already reflected as failed segments). Best-effort —
    error-recording must never itself break the chain."""
    try:
        state.errors.append(
            PhaseError(phase="chain", node=label, message=str(exc)[:500], retryable=True)
        )
    except Exception:  # defensive; a bad append can't be allowed to abort the run
        _logger.debug("chain: could not record error for %s", label, exc_info=True)


def _preflight_config(deps: ChainDeps) -> ResearchConfigBundle | None:
    """Pin overlay workspace on initial state before fail-soft graph invoke.

    Overlay identity is loaded in research preflight. If research raises at graph
    level, ``_safe_invoke_graph`` returns the original state. Beliefs fold
    then ran with ``workspace_id=None`` (house path) and stamped house
    ``decision_log``. Call the preflight config loader once up front so a
    private workspace skip is already on the last-good state. House loaders
    that omit ``workspace_id`` still fold. Tests may pass ``research=None``.
    """
    research = getattr(deps, "research", None)
    if research is None:
        return None
    preflight = getattr(research, "preflight", None)
    if preflight is None:
        return None
    loader = getattr(preflight, "config_loader", None)
    if not callable(loader):
        return None
    loaded = loader()
    return loaded if isinstance(loaded, ResearchConfigBundle) else None


def _safe_invoke_graph(
    graph: Any, state: ResearchState, checkpointer: Any, thread_base: str | None, label: str
) -> ResearchState:
    """Run a sub-graph; on a graph-level crash record the error and return the last-good
    state, so the terminal phases (publish/materialize) and the diagnostics row still run.
    Per-node failures are already handled fail-soft inside the graph (Pillar 1A); this is
    the belt-and-suspenders for a rare whole-graph raise (infra / checkpointer)."""
    try:
        return _invoke_resumable(graph, state, checkpointer, thread_base, label)
    except OverlayLegacyBookBlocked:
        # Overlay leftover UNIQUE refuse must reach execute_overlay (FAILED +
        # legacy_book_unique). House never raises this.
        raise
    except Exception as exc:  # a late crash must still reach publish/materialize
        _logger.exception("chain: %s graph failed; continuing with last-good state", label)
        _record_chain_error(state, label, exc)
        return state


def _run_terminal_phase(
    phase_deps: Any, build_phase: Any, state: ResearchState, label: str
) -> ResearchState:
    """Run one terminal single-node phase (risk-sizing / publish / materialize) when its
    deps are present; a failure in one is recorded and never blocks the others or the
    diagnostics write."""
    if phase_deps is None:
        return state
    from digiquant.portfolio.pipeline_builder import build_pipeline

    try:
        return _coerce_research_state(
            build_pipeline(ResearchState, [build_phase(phase_deps)]).invoke(state)
        )
    except OverlayLegacyBookBlocked:
        raise
    except Exception as exc:  # one terminal phase failing must not abort the rest
        _logger.exception("chain: terminal phase %s failed; continuing", label)
        _record_chain_error(state, label, exc)
        return state


def resolve_run_id(research_input: ResearchInput) -> str:
    """CI run id when present, else a deterministic, self-labelled local id.

    ``-local`` is a suffix no GitHub run id can carry, so an off-CI run can never be mistaken
    for — or joined to — a CI run. Deliberately resolved once at the CLI boundary rather than
    recomputed deeper in the call stack: two unrelated in-process runs on the same cadence and
    date would otherwise share one identifier.
    """
    return os.environ.get("GITHUB_RUN_ID") or (
        f"{research_input.cadence}-{research_input.run_date.isoformat()}-local"
    )


def _run_beliefs_fold(state: ResearchState, deps: ChainDeps, research_input: ResearchInput) -> None:
    """Fold the beliefs backlog, fail-soft (#1737).

    Beliefs distillation is a daily short fold after publish (WP-I), not a graph node.
    LLM/Supabase errors must not kill a run that already committed a book. Record it as
    ``run_research_then_portfolio`` and killed a run that had already committed a book. Record it as
    a chain-level error (so the run reports ``degraded``, not ``ok``) and continue: the
    diagnostics row and the caller's exit code then describe what actually happened.
    """
    if deps.research.preflight.client is None:
        return
    if skip_overlay_shared_register(state.config.workspace_id):
        # Overlay persist-on still reaches this post-publish fold after a
        # fail-soft H9 ``legacy_book_unique``. Distillation reads every
        # unfolded house ``decision_log`` row and stamps ``beliefs_folded_at``
        # by id — a shared-register smash, same class as ``resolve_pending``.
        _logger.info("chain: overlay workspace skips beliefs fold (shared decision_log)")
        return
    try:
        run_beliefs_distillation_if_triggered(
            client=deps.research.preflight.client,
            research_input=research_input,
            run_type=_legacy_run_type(research_input.refresh_scope),
            workspace_id=state.config.workspace_id,
        )
    except Exception as exc:  # a daily fold must never kill a booked run
        _logger.exception("chain: beliefs distillation failed; continuing")
        _record_chain_error(state, "beliefs", exc)


def run_research_then_portfolio(
    *,
    research_input: ResearchInput,
    deps: ChainDeps,
    debate_rounds: int | None = None,
    checkpointer: Any = None,
    thread_base: str | None = None,
    portfolio_watchlist: list[str] | None = None,
    portfolio_held: Collection[str] = (),
    manage_usage: bool = True,
) -> ResearchState:
    """Compose research → portfolio → publish, return the final state.

    ``portfolio_watchlist`` narrows the Phase 7C/7CD per-ticker fan-out to a
    focus list (#696 — holdings + top-scored candidates) without touching the
    research watchlist; ``None`` fans out over the full watchlist.

    ``portfolio_held`` are the prior-book holdings; they are threaded to the
    7C/7CD cap so a holding is never dropped by ``ATLAS_MAX_ANALYSTS`` and
    auto-exited by the PM (the Jun-18 IJR regression, #936).

    ``deps.research.publish`` is overridden to ``None`` for the research pass —
    publish runs once at the very end with the full populated state.

    When ``checkpointer`` + ``thread_base`` are set, research and portfolio run under
    **distinct** thread ids (``{thread_base}::research`` / ``::portfolio``) so each
    resumes from its own checkpoint (#665); publish is never checkpointed (cheap
    + idempotent upserts).

    ``debate_rounds``: compile-time upper bound on Bull/Bear debate rounds.
    ``None`` defers to ``state.config.preferences["debate_rounds"]`` after the research
    pass (preflight loads config; clamped via ``clamp_debate_rounds``). Explicit
    non-None overrides preferences.

    ``initial_state`` pins one UTC ``knowledge_cutoff_at`` before graph invoke
    (#2628 / WP4.1) and, when the preflight ``config_loader`` is present, the
    overlay ``workspace_id`` so a fail-soft research crash cannot fold beliefs as
    house. research preflight then pins one ``research_state_pin``
    (#2863 / WP12.3). Checkpoint resume keeps both from the saved thread —
    it does not re-call ``now()`` or re-select state as ingestion continues.

    ``manage_usage``: house cron owns WP1 capture (default True). Overlay cron
    passes False so ``overlay_usage_scope`` is not wiped by a nested
    ``usage.start`` / ``usage.reset``.
    """
    state = initial_state(research_input)
    # Capture LLM usage for the whole run and ALWAYS write the diagnostics row + reset on
    # the way out (telemetry is fail-soft inside write_row, so this never crashes the run).
    started_at = datetime.now(tz=timezone.utc)
    # Detailed telemetry is keyed by the same run id the diagnostics row uses (GITHUB_RUN_ID
    # via DiagnosticsDeps, written with on_conflict="run_id,attempt"), so Task 1.5 can
    # reconcile the two against one value. With no diagnostics wiring there is no run to
    # attribute to: capture stays at today's no-identity behaviour rather than minting an
    # identifier that could silently join two unrelated in-process runs.
    if manage_usage:
        _usage.start(run_id=deps.diagnostics.run_id if deps.diagnostics is not None else None)
    try:
        pinned = _preflight_config(deps)
        if pinned is not None:
            # Preserve the already-pinned knowledge_cutoff_at. Overlay identity
            # must be on last-good state before fail-soft graph invoke; a raising
            # loader stays inside this envelope so diagnostics still flush.
            state = state.model_copy(update={"config": pinned})
        # Operator escape hatch: beliefs-only run (no research/portfolio research).
        if research_input.refresh_scope == "beliefs":
            _run_beliefs_fold(state, deps, research_input)
            return state

        # research: research only, no publish.
        research_deps = ResearchGraphDeps(
            preflight=deps.research.preflight,
            publish=None,  # chain handles publish at the end
            triage=deps.research.triage,
            preflight_reflect=deps.research.preflight_reflect,
        )
        research_graph = build_research_graph(
            deps=research_deps,
            watchlist=research_input.watchlist,
            checkpointer=checkpointer,
        )
        state = _safe_invoke_graph(research_graph, state, checkpointer, thread_base, "research")

        # Research-sufficiency gate (#944): portfolio books a rebalance + decision_log rows
        # INSIDE its own graph (H9 commit-run), so it must NOT run when the research pass
        # produced no fresh research — otherwise the PM commits decisions on stale prior
        # context. The Jun-20 incident: research crashed on empty LLM responses, the chain
        # swallowed it (``_safe_invoke_graph``), and a pm-rebalance was written against
        # 2-day-stale prices. Skipping records a chain error so the run is gated degraded and
        # CI's outer retry fires; the terminal publish still flushes whatever research produced.
        if _diagnostics.research_produced(state):
            portfolio_graph = build_portfolio_graph(
                watchlist=list(
                    portfolio_watchlist if portfolio_watchlist is not None else research_input.watchlist
                ),
                deps=deps.portfolio,
                checkpointer=checkpointer,
                held=portfolio_held,
            )
            state = _safe_invoke_graph(portfolio_graph, state, checkpointer, thread_base, "portfolio")
            # WP10.1: one-way shadow artifact after H9. Fail-soft — never reruns or
            # mutates the production booking path / graph.
            _maybe_export_shadow_allocation_artifact(state)
        else:
            _logger.error(
                "chain: research produced no research for %s; skipping portfolio — no rebalance booked",
                research_input.run_date.isoformat(),
            )
            _record_chain_error(
                state,
                "portfolio-skipped",
                RuntimeError(
                    "research produced no fresh research; portfolio skipped to avoid booking a "
                    "rebalance on stale context"
                ),
            )

        # Terminal phase — research artifacts only; portfolio terminal is H9 in-graph.
        state = _run_terminal_phase(deps.publish, build_publish_phase, state, "publish")

        # Daily short fold (WP-I) — always publishes a same-date beliefs document.
        _run_beliefs_fold(state, deps, research_input)
        return state
    except BaseException as exc:
        # Last-resort recorder (#1733/#1763). The diagnostics row is written by the ``finally``
        # below, but a *terminating* exception — SystemExit, KeyboardInterrupt, a job timeout's
        # SIGTERM, an unexpected raise from a helper outside the fail-soft wrappers — used to
        # reach that block with an error-free state, so the row said "ok" (or the process died
        # before the row said anything at all). Record the crash first, then re-raise
        # untouched: the caller's exit code and CI's view of the job are unchanged.
        _record_chain_error(state, "terminal", exc)
        raise
    finally:
        if manage_usage:
            if deps.diagnostics is not None:
                finished_at = datetime.now(tz=timezone.utc)
                # Detailed ledger (#1979) FIRST, and before `_usage.reset()` — which clears every
                # buffer both writes read, so anything ordered after it writes nothing while
                # reporting success.
                #
                # Ahead of `write_row` specifically so the two are independent in both directions
                # without touching the aggregate path. A detailed-flush failure cannot lose the
                # aggregate row because the `except` below contains it. An aggregate failure cannot
                # lose the detailed flush because the flush has already happened — which matters
                # because `write_row` is fail-soft for its *upsert* but calls `summarize_run`
                # outside that `try`, so a malformed state can still raise straight out of it. That
                # raise is pre-existing and left alone here; the ordering just stops it taking the
                # detailed records with it.
                try:
                    _provider_telemetry.flush_run_telemetry(
                        deps.diagnostics.client,
                        run_id=deps.diagnostics.run_id,
                        attempt=deps.diagnostics.attempt,
                        node_runs=_usage.node_runs_snapshot(),
                        provider_calls=_usage.provider_calls_snapshot(),
                        provider_attempts=_usage.provider_attempts_snapshot(),
                        aggregate_snapshot=_usage.snapshot(),
                        detailed_projection=_usage.detailed_usage_projection(),
                    )
                except Exception:  # a telemetry bug must not replace the run's real outcome
                    _logger.exception("chain: detailed provider telemetry flush failed; continuing")
                _diagnostics.write_row(
                    deps.diagnostics.client,
                    state=state,
                    run_id=deps.diagnostics.run_id,
                    attempt=deps.diagnostics.attempt,
                    run_type=_legacy_run_type(research_input.refresh_scope),
                    run_date=research_input.run_date,
                    model=deps.diagnostics.model,
                    usage_snapshot=_usage.snapshot(),
                    started_at=started_at,
                    finished_at=finished_at,
                )
            else:
                # Not a silent no-op. Without diagnostics wiring there is no run identifier, so
                # `node_run_scope` never opens and the run produces no node runs and no logical
                # calls *at the source* — only orphaned physical attempts, which have no
                # persistable parent. Nothing is lost by not flushing here, but the absence
                # must be visible.
                _logger.info(
                    "chain: no diagnostics wiring; %d physical attempt(s) captured in process "
                    "were not persisted and this run contributes no detailed telemetry",
                    len(_usage.provider_attempts_snapshot()),
                )
            _usage.reset()


# ─── CLI entry point ────────────────────────────────────────────────────────
#
# Invoked as ``python -m digiquant.portfolio.chain --cadence daily …`` by
# the unified cron workflow (.github/workflows/dashboard.yml). Mirrors the research
# CLI cadence surface so the workflow YAML stays thin.


def _parse_cli_date(value: str) -> date:
    from datetime import datetime as _dt

    # strptime, not date.fromisoformat: mirrors the research CLI, which must reject
    # non-ISO-extended input such as "20260420". The intermediate datetime is naive,
    # which is harmless — .date() discards the time immediately.
    return _dt.strptime(value, "%Y-%m-%d").date()  # noqa: DTZ007


def _build_cli_parser():
    import argparse

    from digiquant.research.graph import _add_cadence_cli_args

    parser = argparse.ArgumentParser(
        prog="python -m digiquant.portfolio.chain",
        description="Run research → portfolio end-to-end (research + analysis + PM + reflection).",
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
            "DIGI_CHECKPOINTER=postgres + DIGI_CHECKPOINTER_POSTGRES_URI. research/portfolio "
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


def dispatch_house_notifications_after_chain(
    run_date: date,
    *,
    dispatch: Callable[..., None] | None = None,
) -> None:
    """Fail-soft K5 close-out for the house CLI only.

    Overlay invokes :func:`run_research_then_portfolio` (not ``cli_main``), so nested
    overlay runs never send house digests. Notify is imported here rather than
    at module import so ``import chain`` on the overlay path does not load
    Mailgun. ``dispatch_notifications`` is itself fail-soft; this wrapper also
    swallows ImportError.
    """
    try:
        if dispatch is not None:
            dispatch(run_date=run_date, force_digest=True)
            return
        from digiquant.notify.dispatch import dispatch_notifications

        dispatch_notifications(run_date=run_date, force_digest=True)
    except Exception:
        _logger.warning("notify: house chain close-out failed", exc_info=True)


def cli_main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    import json
    import sys

    from digigraph.model_config import apply_digiquant_openrouter_env

    apply_digiquant_openrouter_env()

    # Re-use research's CLI helpers — they already handle --auto-baseline,
    # watchlist parsing, summary formatting.
    from digiquant.research.graph import _make_default_config_loader, resolve_cli_inputs

    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    kwargs = resolve_cli_inputs(args)
    research_input = ResearchInput(**kwargs)

    summary = {
        "cadence": research_input.cadence,
        "refresh_scope": research_input.refresh_scope,
        "run_type": _legacy_run_type(research_input.refresh_scope),
        "run_date": research_input.run_date.isoformat(),
        "baseline_date": (
            research_input.baseline_date.isoformat() if research_input.baseline_date else None
        ),
        "watchlist": list(research_input.watchlist),
    }

    if args.dry_run:
        # Compile both graphs cleanly, no invocation.
        compiled = {"research": False, "portfolio": False}
        try:
            research_deps = ResearchGraphDeps(
                preflight=PreflightDeps(client=None, config_loader=None)  # type: ignore[arg-type]
            )
            build_research_graph(deps=research_deps, watchlist=research_input.watchlist)
            compiled["research"] = True
            build_portfolio_graph(watchlist=list(research_input.watchlist))
            compiled["portfolio"] = True
        except Exception as exc:  # pragma: no cover
            summary["compile_error"] = repr(exc)
        json.dump({**summary, "dry_run": True, "compiled": compiled}, sys.stdout, default=str)
        sys.stdout.write("\n")
        return 0

    from digiquant.research.supabase_io import SupabaseConfig, build_client

    client = build_client(SupabaseConfig.from_env())
    research_deps = ResearchGraphDeps(
        preflight=PreflightDeps(
            client=client,
            config_loader=_make_default_config_loader(research_input.watchlist),
        ),
        publish=None,  # chain handles publish at the end
        triage=TriageDeps(client=client),
        preflight_reflect=PreflightReflectDeps(client=client),
    )
    from digiquant.portfolio.phases.h9_commit_run import CommitRunDeps
    from digiquant.portfolio.phases.phase7e_risk_sizing import RiskSizingDeps

    portfolio_deps = PortfolioGraphDeps(
        thesis=ThesisGraphDeps(client=client),
        risk_sizing=RiskSizingDeps(client=client),
        commit_run=CommitRunDeps(client=client),
    )
    run_id = resolve_run_id(research_input)
    chain_deps = ChainDeps(
        research=research_deps,
        portfolio=portfolio_deps,
        publish=PublishDeps(client=client),
        diagnostics=DiagnosticsDeps(client=client, run_id=run_id, attempt=_outer_attempt()),
    )
    # Checkpoint/resume (#665): durable per-graph threads when DIGI_CHECKPOINTER is set
    # (DIGI_CHECKPOINTER=postgres + DIGI_CHECKPOINTER_POSTGRES_URI in prod). thread_base is
    # the run to resume (--resume-run-id) or this run's id for a fresh start. Best-effort:
    # a bad URI / unreachable Postgres degrades to an uncheckpointed run (#667).
    _checkpointer = _acquire_checkpointer()
    _thread_base = getattr(args, "resume_run_id", None) or run_id
    # portfolio H4 builds ``phase_portfolio.focus_roster`` in-graph; research watchlist is
    # the research scope. Prior-book holdings still thread to the 7C/7CD cap (#936).
    _holdings: list[str] = []
    if not args.watchlist.strip():
        from digiquant.research.supabase_io import load_prior_book
        from digiquant.portfolio.candidates import holdings_from_prior_book

        _prior_book = load_prior_book(client, research_input.run_date)
        _holdings = holdings_from_prior_book(_prior_book)

    final_state = run_research_then_portfolio(
        research_input=research_input,
        deps=chain_deps,
        checkpointer=_checkpointer,
        thread_base=_thread_base,
        portfolio_watchlist=None,
        # Prior-book holdings always survive the 7C/7CD cap (#936). Empty when the
        # operator overrides --watchlist or for monthly runs (no portfolio).
        portfolio_held=set(_holdings or ()),
    )

    # Degraded-run gate (#726, 1B) + good-book guard (#809): a run that produced little/no
    # fresh research is worth retrying — exit non-zero so the CI outer-retry fires (one bad
    # sector does NOT trip it; the threshold is ATLAS_DEGRADED_RUN_PCT, default 50%). BUT a
    # run that already materialized a valid sized book must NOT retry — that wasted ~20 min of
    # backoff sleeps on a good book (#809). The diagnostics row, written inside
    # run_research_then_portfolio, records the why. Monthly runs (no research segments) don't trip it.
    run_summary = _diagnostics.summarize_run(final_state, degraded_pct=_degraded_run_pct())
    retry_worthy = _retry_worthy_summary(run_summary)
    # ``degraded`` keeps its pre-#1736 meaning (= the retry signal) so nothing parsing run.log
    # changes shape; ``status`` is the honest health verdict that lands in
    # ``atlas_run_diagnostics``. Both are printed because they legitimately disagree — a day
    # that lost segments but committed its book is ``status=degraded, degraded=false`` (#1736).
    summary["degraded"] = run_summary.retry_signal
    summary["status"] = run_summary.status
    summary["book_materialized"] = final_state.phase_portfolio.sized_book is not None
    # #1555: a green run must be *provably* a committed run. ``book_committed`` sits beside
    # ``book_materialized`` so an operator never again reads ``ok:true, book_materialized:true``
    # and assumes the book persisted — the silent H4→H9 freeze (2026-06-26) presented exactly
    # that shape while nothing committed for weeks.
    summary["book_committed"] = run_summary.book_committed
    json.dump({"ok": not retry_worthy, "summary": summary}, sys.stdout, default=str)
    sys.stdout.write("\n")
    # K5: production cron is this CLI, not run_db_first.py. Only on a
    # non-retry exit so a failed attempt that CI will redo does not email.
    if not retry_worthy:
        dispatch_house_notifications_after_chain(research_input.run_date)
    return 1 if retry_worthy else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_main())

"""Per-run telemetry → ``atlas_run_diagnostics`` (Pillar 1B).

Migration 032 created the ``atlas_run_diagnostics`` table and named this module as its
writer, but the module never existed — so the table stayed empty and a run's health was
invisible. This closes that gap: at the end of every chain run :func:`write_row` counts
fresh / carried / failed segments from state, folds in the LLM usage snapshot
(``digigraph.usage``), and upserts one row keyed by ``run_id``.

Everything here is fail-soft — telemetry must never crash a run. A write error is logged
and swallowed; :func:`is_degraded` lets the CLI decide whether a run was bad enough to
exit non-zero (so CI's outer retry fires) WITHOUT coupling that decision to the write
succeeding.

**Health and retry-worthiness are two questions** (#1736). :attr:`RunSummary.status` is the
health verdict — tightened so that nothing which goes wrong after the research segments can
hide behind a green row. :attr:`RunSummary.retry_signal` is the CI gate and is frozen at the
pre-#1736 rules, so making the report honest never costs a retry storm. New ``breakdown``
keys go through :func:`register_breakdown_contributor` rather than editing this module.

Segment accounting reads the discriminated ``SegmentSlot`` payloads: ``today`` = freshly
generated, ``carried`` = fell back to the baseline. A carry whose reason is
:data:`~digiquant.research.phases.fail_soft.NODE_FAILED_REASON` is a *node failure*
(counted as failed), distinct from a deliberate below-threshold carry.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any  # score:allow untyped any — scored-lint: duck-typed Supabase client + rows

from digiquant.research.phases.fail_soft import NODE_FAILED_REASON
from digiquant.research.state import ResearchState

logger = logging.getLogger(__name__)

# Phase output dicts that hold per-segment SegmentSlots (research segments). Phase 3
# (macro) is a *single* optional slot (``phase3_output``), counted separately below.
_SEGMENT_PHASES = ("phase1_outputs", "phase2_outputs", "phase4_outputs", "phase5_outputs")
_SINGLE_SEGMENT_PHASE = "phase3_output"

# ``phase`` marker stamped on chain-level errors by chain._record_chain_error (a whole
# sub-graph or terminal phase crashed), distinct from node-level PhaseErrors. A chain error
# gates the run; a crash in a core research engine (research/portfolio) marks it failed outright.
_CHAIN_ERROR_PHASE = "chain"
_CORE_ENGINES = ("research", "portfolio")

# ``phase`` stamped on a PhaseError raised by H9 commit-run (see
# ``portfolio.phases.h9_commit_run.PHASE_NAME``). It carries a node-level phase (not "chain"),
# so the chain-error gate never sees it — yet every one of its exits (coherence fail-closed,
# idempotency conflict, memo-present-but-no-book) is a non-commit that must gate the run (#1555).
_PORTFOLIO_COMMIT_PHASE = "portfolio_h9_commit_run"

# Master-digest synthesis is a first-class run artifact (#1559): when it fails and
# the run falls back to carrying the prior digest forward, the run must surface as
# degraded with the failure LEADING the error summary — not buried among per-segment
# noise, and not reported "ok" while the dashboard shows a silently stale headline.
# Matched by (phase, node) so ordinary node-level errors keep their non-gating
# behavior (see test_node_level_error_does_not_gate_via_chain_marker).
_MASTER_DIGEST_PHASE = "phase7_synthesis"
_MASTER_DIGEST_NODE = "master-digest"

# portfolio/thesis phases whose PhaseErrors mean "a piece of the book's reasoning
# died" (#1742). Deliberately an explicit allow-list of the five literals actually emitted
# (``h6_deliberation.PHASE_NAME``, ``h7_pm_direction.PHASE_NAME``, the ``phase_portfolio``
# marker shared by ``portfolio_common`` / ``thesis_common``, ``phase7d_pm``,
# ``phase9_evolution``) rather than a ``portfolio_*`` prefix match: a prefix would also swallow
# H1-H5 bookkeeping errors and ``portfolio_h9_commit_run``, which is already gated separately
# (#1555) and must NOT be double-counted here.
_PORTFOLIO_FAILURE_PHASES = frozenset(
    {
        "phase_portfolio",
        "portfolio_h6_deliberation",
        "portfolio_h7_pm_direction",
        "phase7d_pm",
        "phase9_evolution",
    }
)

# Default share of failed segments above which a run is "degraded" (CLI may exit non-zero).
_DEGRADED_PCT_DEFAULT = 50.0
# Default share of portfolio deliberations that may fail before the run is degraded (#1742).
# Calibrated against production: 2026-07-31 (31 of 39 deliberations dead → 79%) and 07-29
# (33 of 40 → 83%) must flip; the 07-26 baseline (1 of 50 → 2%) and 06-24 (9 of ~40 → 23%,
# mostly benign ``max_rounds`` caps) must not. H6 emits the *same* ``(phase, node)`` for an
# LLM crash and a benign cap, and discriminating them would mean parsing message text — so
# both are counted and the threshold is set wide enough that routine caps never trip it.
_PORTFOLIO_DEGRADED_PCT_DEFAULT = 50.0
_ERROR_SUMMARY_MAX = 2000

# ── breakdown extension seam (#1736) ────────────────────────────────────────────────────
#
# ``breakdown`` is the run's schema-free telemetry surface: adding a key needs no migration.
# Several packages contribute one key each (roster tallies, merge-fallback counters, spend,
# content-change signals). Registering a contributor here keeps those changes to *one new
# module plus one registration line* instead of seven concurrent edits to ``_segment_counts``.
#
# Contract for a contributor:
#   * pure — read ``state``, return ``{key: json_serialisable}``; never mutate state
#   * fail-soft — an exception is logged and swallowed (telemetry must never crash a run)
#   * it must not reuse a key another contributor or ``summarize_run`` already owns; a
#     collision is logged and the *existing* value wins
#   * it runs once per run, at ``summarize_run`` time — never mid-run (see ``_segment_counts``)
_BREAKDOWN_CONTRIBUTORS: list[Callable[[ResearchState], dict[str, Any]]] = []


def register_breakdown_contributor(
    fn: Callable[[ResearchState], dict[str, Any]],
) -> Callable[[ResearchState], dict[str, Any]]:
    """Register ``fn`` as a ``breakdown`` contributor. Returns ``fn`` (usable as a decorator)."""
    _BREAKDOWN_CONTRIBUTORS.append(fn)
    return fn


def _apply_breakdown_contributors(state: ResearchState, breakdown: dict[str, Any]) -> None:
    """Fold every registered contributor's keys into ``breakdown`` in place (fail-soft)."""
    for fn in _BREAKDOWN_CONTRIBUTORS:
        try:
            extra = fn(state) or {}
        except Exception as exc:  # a broken contributor must never gate a run
            logger.warning("diagnostics: breakdown contributor %r failed (%s)", fn, exc)
            continue
        for key, value in extra.items():
            if key in breakdown:
                logger.warning(
                    "diagnostics: contributor %r tried to overwrite breakdown[%r]; keeping "
                    "the existing value",
                    fn,
                    key,
                )
                continue
            breakdown[key] = value


@dataclass(frozen=True)
class RunSummary:
    """Counts + status derived from a finished run's state (the heart of a diagnostics row)."""

    segments_total: int
    segments_ok: int
    segments_carried: int
    segments_failed: int
    status: str  # "ok" | "degraded" | "failed" | "cancelled"
    error_summary: str
    breakdown: dict[str, Any]
    # portfolio H8/H9 terminal-book accounting (#1555). ``book_materialized`` = H8 produced a
    # sized book; ``book_committed`` = H9 persisted it (a commit manifest with status
    # committed/noop). A materialized-but-uncommitted book is a silent terminal failure —
    # it forces the run degraded (see :func:`summarize_run`) and is surfaced structurally in
    # the diagnostics breakdown so it survives the ``error_summary`` truncation cap.
    book_materialized: bool = False
    book_committed: bool = False
    # Whether CI's outer retry should fire (#1736). DELIBERATELY NOT ``status in
    # ("degraded", "failed")`` any more: ``status`` answers "was this run healthy?" and is
    # tightened by the rules below, while ``retry_signal`` answers "is re-running worth the
    # money?" and is frozen at the pre-#1736 gate. A day that lost 4 of 27 research segments
    # but committed a good book is honestly ``degraded`` — and re-running it would burn three
    # attempts plus ~20 min of backoff sleeps on work that already landed (#809).
    retry_signal: bool = False


def _tally_slot(slot: Any, counts: list[int]) -> None:
    """Increment ``counts`` = [ok, carried, failed] for one ``SegmentSlot``."""
    source = getattr(getattr(slot, "payload", None), "source", None)
    if source == "today":
        counts[0] += 1
    elif source == "carried":
        counts[1] += 1
        if getattr(slot.payload, "reason", None) == NODE_FAILED_REASON:
            counts[2] += 1


def _breaker_skips(slots: Mapping[str, Any]) -> dict[str, str]:
    """``{segment_slug: reason}`` for fresh stubs emitted by a circuit-breaker.

    Phase 2's institutional breaker (#928) writes a deterministic ``today`` stub
    carrying a ``circuit_breaker`` marker in its body when it skips the paid
    LLM/web-search nodes. Surfaced in the diagnostics breakdown so a cost audit
    can see *which* segments skipped paid grounding and *why*, without a new
    column or table.
    """
    skips: dict[str, str] = {}
    for slug, slot in slots.items():
        payload = getattr(slot, "payload", None)
        if getattr(payload, "source", None) != "today":
            continue
        body = getattr(payload, "body", None)
        reason = body.get("circuit_breaker") if isinstance(body, Mapping) else None
        if reason:
            skips[slug] = str(reason)
    return skips


def _segment_totals(state: ResearchState) -> tuple[int, int, int, int, dict[str, Any]]:
    """(total, ok, carried, failed, per-phase breakdown) over the research segment slots.

    Covers the four dict-backed phases AND the single macro slot (``phase3_output``).

    Pure counting only — no registered contributors. :func:`research_produced` calls
    this **mid-run** (``chain`` uses it to gate portfolio), and a contributor must never see a
    half-populated state. :func:`_segment_counts` is the end-of-run wrapper that adds them.
    """
    ok = carried = failed = 0
    breakdown: dict[str, Any] = {}
    for phase in _SEGMENT_PHASES:
        slots = getattr(state, phase, {}) or {}
        counts = [0, 0, 0]
        for slot in slots.values():
            _tally_slot(slot, counts)
        if slots:
            breakdown[phase] = {"ok": counts[0], "carried": counts[1], "failed": counts[2]}
            breaker_skips = _breaker_skips(slots)
            if breaker_skips:
                breakdown[phase]["circuit_breaker_skips"] = breaker_skips
        ok += counts[0]
        carried += counts[1]
        failed += counts[2]
    macro = getattr(state, _SINGLE_SEGMENT_PHASE, None)
    if macro is not None:
        counts = [0, 0, 0]
        _tally_slot(macro, counts)
        breakdown[_SINGLE_SEGMENT_PHASE] = {
            "ok": counts[0],
            "carried": counts[1],
            "failed": counts[2],
        }
        ok += counts[0]
        carried += counts[1]
        failed += counts[2]
    return ok + carried, ok, carried, failed, breakdown


def _segment_counts(state: ResearchState) -> tuple[int, int, int, int, dict[str, Any]]:
    """:func:`_segment_totals` plus every registered ``breakdown`` contributor.

    **This is the extension seam** (#1736). Call it once, at the end of a run
    (:func:`summarize_run`) — never on the mid-run gating path.
    """
    total, ok, carried, failed, breakdown = _segment_totals(state)
    _apply_breakdown_contributors(state, breakdown)
    return total, ok, carried, failed, breakdown


def _snapshot_published(state: ResearchState) -> bool:
    """Return True if the run published at least one daily_snapshots or documents row.

    Used to distinguish a *cancelled* run (ctrl-C mid-flight after the book was
    written) from a genuine *failed* run (nothing was produced). A published book
    is evidence the pipeline did useful work even if it never reached the finally
    block normally (#814).
    """
    for art in getattr(state, "published", []) or []:
        # ``state.published`` holds ``PublishedArtifact`` instances (table + row_id).
        table = getattr(art, "table", None) or ""
        if table in ("daily_snapshots", "documents"):
            return True
    return False


def _book_status(state: ResearchState) -> tuple[bool, bool]:
    """``(materialized, committed)`` for the portfolio H8/H9 terminal book (#1555).

    ``materialized`` — H8 produced ``phase_portfolio.sized_book``. ``committed`` — H9
    persisted it, evidenced by a ``commit_manifest`` whose status is ``committed`` or
    ``noop`` (an idempotent re-run of an already-booked day is committed, not a gap).
    Any other shape (no manifest, or a manifest without a terminal status) counts as
    *not* committed — the coherence fail-closed, the idempotency conflict, and the
    silent no-manifest skip all land here.
    """
    phase_portfolio = getattr(state, "phase_portfolio", None)
    materialized = getattr(phase_portfolio, "sized_book", None) is not None
    manifest = getattr(phase_portfolio, "commit_manifest", None)
    committed = isinstance(manifest, Mapping) and manifest.get("status") in ("committed", "noop")
    return materialized, committed


def book_committed(state: ResearchState) -> bool:
    """True when the portfolio terminal book was persisted (commit manifest present)."""
    return _book_status(state)[1]


def _portfolio_deliberation_health(state: ResearchState, errors: list[Any]) -> tuple[int, int]:
    """``(deliberations, portfolio_failures)`` — the density of dead portfolio reasoning (#1742).

    On 2026-07-31 the H6 deliberation LLM failed for 31 of 39 tickers and the run still
    reported ``ok``: each failure is a *node-level* PhaseError, so it never reached the
    chain-error gate, and it carries the analyst stance forward so no segment is marked
    failed either. The whole portfolio was then sized off carried stances.

    The denominator is ``phase_portfolio.deliberation_summaries`` — the number of tickers the
    portfolio path actually deliberated on, i.e. the best available measure of portfolio fan-out
    width (the roster width itself is not in state at this point). The numerator counts every
    :data:`_PORTFOLIO_FAILURE_PHASES` error, caps and crashes alike, because H6 emits an
    identical ``(phase, node)`` for both and telling them apart would mean parsing message
    text — brittle, and it would silently stop counting the moment a message is reworded.
    """
    phase_portfolio = getattr(state, "phase_portfolio", None)
    summaries = getattr(phase_portfolio, "deliberation_summaries", None) or {}
    failures = sum(1 for e in errors if getattr(e, "phase", None) in _PORTFOLIO_FAILURE_PHASES)
    return len(summaries), failures


def summarize_run(
    state: ResearchState,
    *,
    degraded_pct: float = _DEGRADED_PCT_DEFAULT,
    portfolio_degraded_pct: float = _PORTFOLIO_DEGRADED_PCT_DEFAULT,
) -> RunSummary:
    """Pure: derive segment counts, an error summary, a status and a retry signal from state.

    Two verdicts come out of the same facts and deliberately diverge (#1736). Everything that
    went wrong *after* the research segments used to be invisible: eight separate issues
    (#1736 #1732 #1735 #1738 #1737 #1733 #1763 #1742) are one defect wearing eight hats.

    ``status`` — the health verdict the dashboard and ``atlas_run_diagnostics`` read:

    - ``"failed"`` — nothing fresh was produced AND no snapshot was published; or a
      core research engine (research/portfolio) crashed at the chain level.
    - ``"cancelled"`` — a snapshot was published AND no core engine crashed. A cancelled
      run still published a useful book and must not be reported as failed. The snapshot
      check prevents a SIGINT-at-startup (no book produced) from being mislabelled as
      "cancelled" (#814).
    - ``"degraded"`` — any non-core chain-level crash (publish/materialize/risk-sizing/
      beliefs/terminal), a master-digest synthesis failure, **any** failed research segment,
      a majority of portfolio deliberations dead, an H9 non-commit (#1555), or research
      with no committed book at all.
    - ``"ok"`` — all other cases.

    ``retry_signal`` — whether CI's outer retry should fire. Frozen at the pre-#1736 gate
    (see :class:`RunSummary`): the new rules make the *report* honest without making CI
    re-run days whose book already committed.

    ``segments_failed`` counts node-failure carries (not deliberate carries); chain-level
    crashes are recorded by ``chain._record_chain_error`` with ``phase == "chain"`` so
    they gate the run distinctly from node-level errors.
    """
    total, ok, carried, failed, breakdown = _segment_counts(state)
    errors = list(getattr(state, "errors", []) or [])
    book_materialized, book_committed_ = _book_status(state)
    # Same predicate the chain uses to decide whether to run portfolio at all — reused here so
    # the no-book gate below cannot fire on a run where portfolio was legitimately never reached.
    research_produced = total > 0 and not _research_chain_crashed(errors)
    # Every H9 non-commit outcome, unified: (1) a book that materialized but never persisted
    # (coherence fail-closed / idempotency conflict / no-manifest skip), OR (2) any
    # ``portfolio_h9_commit_run`` PhaseError — which also covers the memo-present-but-no-book
    # fail-closed where nothing materialized (``book_materialized`` is False). H9 never both
    # commits and errors, so this can't fire on a healthy committed run (#1555).
    portfolio_commit_error = any(
        getattr(e, "phase", None) == _PORTFOLIO_COMMIT_PHASE for e in errors
    )
    commit_failed = (book_materialized and not book_committed_) or portfolio_commit_error
    error_parts = [
        f"{getattr(e, 'phase', '?')}/{getattr(e, 'node', '?')}: {getattr(e, 'message', '')}"
        for e in errors
    ]
    # An H9 non-commit is the highest-signal failure of a portfolio run; place it at the HEAD so
    # it survives the ``error_summary`` truncation cap even when research segment-validation
    # noise fills the tail (#1555). The structural ``breakdown["book_committed"]`` flag (see
    # ``_row``) is the truncation-proof source.
    if commit_failed:
        error_parts.insert(0, "portfolio_h9_commit_run/uncommitted: H9 produced no committed book")
    error_summary = "; ".join(error_parts)[:_ERROR_SUMMARY_MAX]
    if errors:
        breakdown["errors"] = [
            {
                "phase": getattr(e, "phase", None),
                "node": getattr(e, "node", None),
                "message": str(getattr(e, "message", ""))[:300],
            }
            for e in errors
        ]

    # Surface a master-digest synthesis failure as a first-class signal (#1559):
    # lead the summary so it survives truncation, and record a distinct breakdown
    # key. A carried-forward digest is only "ok"-looking noise otherwise.
    master_digest_error = next(
        (
            e
            for e in errors
            if getattr(e, "phase", None) == _MASTER_DIGEST_PHASE
            and getattr(e, "node", None) == _MASTER_DIGEST_NODE
        ),
        None,
    )
    if master_digest_error is not None:
        md_message = str(getattr(master_digest_error, "message", ""))
        breakdown["master_digest_failed"] = md_message[:300]
        lead = f"MASTER-DIGEST SYNTHESIS FAILED: {md_message}"
        error_summary = (f"{lead} || {error_summary}" if error_summary else lead)[
            :_ERROR_SUMMARY_MAX
        ]

    # portfolio reasoning density (#1742) — recorded unconditionally so the row is auditable
    # even on runs the gate does not trip, and so it survives the error_summary cap.
    portfolio_total, portfolio_failed = _portfolio_deliberation_health(state, errors)
    if portfolio_total or portfolio_failed:
        breakdown["portfolio_deliberation"] = {"total": portfolio_total, "failed": portfolio_failed}

    chain_errors = [e for e in errors if getattr(e, "phase", None) == _CHAIN_ERROR_PHASE]
    core_engine_down = any(getattr(e, "node", None) in _CORE_ENGINES for e in chain_errors)

    # ── legacy verdict → retry_signal ────────────────────────────────────────────────────
    # Deliberately unchanged from the pre-#1736 gate, because this is what decides whether
    # CI spends another two attempts plus ~20 min of backoff (#726/#809/#1555). The
    # ``degraded_pct`` share rule lives HERE and nowhere else now: with the STRICT rule below,
    # it no longer has any influence on ``status`` — ``ATLAS_DEGRADED_RUN_PCT`` has narrowed
    # from "how much damage is unhealthy" to "how much damage is worth re-running".
    #
    # A run that published a snapshot before SIGINT / ctrl-C did useful work — promote from
    # "failed" to "cancelled" so the dashboard reflects what happened. Requiring
    # _snapshot_published guards against a SIGINT-at-startup (no book produced) being
    # mislabelled as "cancelled" (#814).
    nothing_fresh = total == 0 or ok == 0
    if nothing_fresh or core_engine_down:
        if _snapshot_published(state) and not core_engine_down:
            status = "cancelled"
        else:
            status = "failed"
    elif chain_errors or master_digest_error is not None or (failed / total) * 100.0 > degraded_pct:
        status = "degraded"
    else:
        status = "ok"

    # H9 commit gate (#1555): an H9 non-commit is a silent terminal failure — the coherence
    # fail-closed, idempotency conflict, no-manifest skip, and memo-present-but-no-book exit
    # all present as ``ok`` today because an H9 PhaseError carries phase
    # ``portfolio_h9_commit_run`` (not ``chain``) and so never reaches the degraded gate above.
    # Force it degraded regardless of the research-segment verdict, and never let it be
    # reported "ok"/"cancelled". ``failed`` (a worse verdict) is left intact.
    if commit_failed and status in ("ok", "cancelled"):
        status = "degraded"

    retry_signal = status in ("degraded", "failed")

    # ── health verdict → status (#1736) ──────────────────────────────────────────────────
    # These rules only ever escalate "ok". "failed"/"cancelled" already say more than
    # "degraded" would, and escalating them would lose information.
    if status == "ok":
        for reason, tripped in (
            # STRICT (D1): one dead research segment is not a rounding error. Under the old
            # 50%-share rule 2026-07-29 lost 5 of 27 segments and still reported "ok".
            ("failed_segments", failed > 0),
            # A majority of the book's deliberations dead — see _portfolio_deliberation_health.
            (
                "portfolio_deliberations",
                portfolio_total > 0
                and (portfolio_failed / portfolio_total) * 100.0 > portfolio_degraded_pct,
            ),
            # No-book gate: research produced research, portfolio was therefore run by the chain,
            # and yet nothing committed. Closes the residual detection hole behind #1766 —
            # ``commit_failed`` above only fires when a book *materialized* first or H9 raised,
            # so a silent "H9 produced nothing at all" day still reported "ok".
            ("no_committed_book", research_produced and not book_committed_),
        ):
            if tripped:
                status = "degraded"
                breakdown.setdefault("degraded_reasons", []).append(reason)

    return RunSummary(
        segments_total=total,
        segments_ok=ok,
        segments_carried=carried,
        segments_failed=failed,
        status=status,
        error_summary=error_summary,
        breakdown=breakdown,
        book_materialized=book_materialized,
        book_committed=book_committed_,
        retry_signal=retry_signal,
    )


def is_degraded(state: ResearchState, *, degraded_pct: float = _DEGRADED_PCT_DEFAULT) -> bool:
    """True when the run is bad enough to warrant a non-zero CLI exit (CI retry).

    This is :attr:`RunSummary.retry_signal`, **not** ``status in ("degraded", "failed")``.
    Since #1736 the two differ: ``status`` was tightened (any failed segment, dead portfolio
    deliberations, no committed book) while the retry gate was deliberately left frozen, so
    an honest ``degraded`` on a day whose book committed does not cost three more CI attempts.
    Read ``summarize_run(state).status`` for health; call this only for the exit code.

    ``"cancelled"`` is excluded: a cancelled run that already published a book is
    not worth retrying — the book is on disk and the next scheduled run will pick
    up from there (#814).
    """
    return summarize_run(state, degraded_pct=degraded_pct).retry_signal


def _research_chain_crashed(errors: list[Any]) -> bool:
    """True when research crashed at the chain level (``phase="chain"``, ``node="research"``)."""
    return any(
        getattr(e, "phase", None) == _CHAIN_ERROR_PHASE and getattr(e, "node", None) == "research"
        for e in errors
    )


def research_produced(state: ResearchState) -> bool:
    """True when the research pass yielded usable research for portfolio to act on.

    False only when research crashed at the chain level (a core-engine ``research`` error) or
    produced zero research segments. The chain uses this to gate the portfolio commit so the
    PM never books a rebalance on stale prior context after an research failure — the Jun-2026
    incident where research returned empty LLM responses yet a pm-rebalance was still written
    on 2-day-stale prices (#944). A fully-carried quiet delta (segments carried from the
    baseline, none fresh) still counts as produced — the carried research is valid.

    Uses :func:`_segment_totals`, not :func:`_segment_counts`: the chain calls this mid-run,
    where registered ``breakdown`` contributors must not be invoked.
    """
    total, *_rest = _segment_totals(state)
    return total > 0 and not _research_chain_crashed(list(getattr(state, "errors", []) or []))


def _announce_spend_alert(row: Mapping[str, Any]) -> None:
    """Log + annotate the spend alert already recorded in *row*'s breakdown (#1764).

    Called from ``write_row`` AFTER the upsert succeeds, and outside its ``try``: ``_row`` runs
    inside that ``try``, so anything raised while announcing an alert would be swallowed by the
    fail-soft handler and the diagnostics row would never be written. An alert must never cost
    the row it annotates.

    Guarded end-to-end anyway — this is decoration, and no shape of ``row`` should reach the
    caller as an exception.
    """
    from digiquant.research import telemetry as _telemetry

    try:
        breakdown = row.get("breakdown") or {}
        alert = breakdown.get(_telemetry.SPEND_ALERT_KEY) if isinstance(breakdown, dict) else None
        if not isinstance(alert, dict):
            return
        logger.warning(
            "spend alert: this invocation cost $%.4f, above the $%.2f %s threshold "
            "(alert only — the run is unaffected)",
            alert["est_cost_usd"],
            alert["threshold_usd"],
            _telemetry.SPEND_ALERT_ENV,
        )
        _emit_ci_warning(
            f"dashboard spend alert: ${alert['est_cost_usd']:.4f} this invocation, "
            f"above the ${alert['threshold_usd']:.2f} threshold "
            f"({_telemetry.SPEND_ALERT_ENV}). Alert only; the run was not blocked."
        )
    except Exception as exc:  # announcing must never raise
        logger.debug("could not announce the spend alert (%s)", exc)


def _emit_ci_warning(message: str) -> None:
    """Raise a GitHub Actions warning annotation, when running under Actions.

    A ``breakdown`` key and a log line are both passive — someone has to go looking. An
    ``::warning::`` annotation appears on the run's summary page without anyone querying
    anything, which is what makes "alert only" (#1764) an actual alert rather than a record.

    Guarded on ``GITHUB_ACTIONS`` so a local run just gets the ordinary log line and no stray
    workflow-command text on stdout. Never raises: this is decoration on a fail-soft path.
    """
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    try:
        # Newlines would terminate the workflow command and leak the rest as plain output.
        print(f"::warning::{message}".replace("\n", " "), flush=True)
    except Exception as exc:  # pragma: no cover — stdout is closed/broken
        logger.debug("could not emit CI warning annotation (%s)", exc)


def _row(
    *,
    run_id: str,
    run_type: str,
    run_date: date,
    model: str | None,
    usage_snapshot: Mapping[str, Any] | None,
    summary: RunSummary,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
    usage = dict(usage_snapshot or {})
    breakdown = dict(summary.breakdown)
    # Structural (truncation-proof) commit signal (#1555): a green ``status`` must always be
    # readable alongside proof the book actually committed. ``book_committed`` is the single
    # field an operator/alert can key on without parsing ``error_summary`` text.
    breakdown["book_materialized"] = summary.book_materialized
    breakdown["book_committed"] = summary.book_committed
    models = usage.get("models")
    if models:
        breakdown["models"] = models
    # Surface the per-kind token/cost detail (incl. cached_tokens) in the breakdown JSONB so
    # cost attribution is visible without a new column (no migration). cached_tokens is the
    # prompt-cache-hit portion billed at the cheaper rate.
    if usage.get("by_kind"):
        breakdown["by_kind"] = usage["by_kind"]
    if usage.get("cached_tokens") is not None:  # include an explicit 0 (distinct from absent)
        breakdown["cached_tokens"] = usage["cached_tokens"]
    # Empty-completion self-heal retries (#1639): rising counts on an ``ok`` run are the earliest
    # provider-degradation signal — always present so operators need not parse logs.
    breakdown["empty_retries"] = usage.get("empty_retries") or {"total": 0, "by_model": {}}
    # Spend alert (#1764). Computed HERE rather than through the ``register_breakdown_contributor``
    # seam because that seam is ``state -> dict`` and spend does not live in state — it comes
    # from the ``digigraph.usage`` snapshot, which is only in scope at this call site. ``models``,
    # ``by_kind`` and ``cached_tokens`` above set the precedent for a usage-derived breakdown key.
    # Alert only, per the owner's decision: nothing below this line touches ``status``,
    # ``retry_signal``, or the exit code.
    #
    # Deferred import, not module-level: ``telemetry`` imports ``register_breakdown_contributor``
    # from THIS module, so a top-level import here is a cycle. ``_row`` runs once per run, so the
    # cached-module lookup costs nothing measurable.
    from digiquant.research import telemetry as _telemetry

    # Only the breakdown key is written here. The log line and the CI annotation are side effects
    # and fire from ``write_row`` AFTER the upsert succeeds — ``_row`` runs inside ``write_row``'s
    # fail-soft ``try``, so an exception raised while announcing an alert would be swallowed by
    # that handler and the diagnostics row would never be written. An alert must never cost the
    # row it annotates. See :func:`_announce_spend_alert`.
    alert = _telemetry.spend_alert(usage.get("cost_usd"))
    if alert is not None:
        breakdown[_telemetry.SPEND_ALERT_KEY] = alert
    # Keep the `model` column a single stable slug for GROUP BY (the full per-run set lives in
    # breakdown["models"]). When the router serves several models we record the first; callers
    # wanting the complete list read the breakdown.
    resolved_model = model or (models[0] if models else None)
    return {
        "run_id": run_id,
        # Part of the primary key since migration 065 (#1762). ``created_at`` is deliberately
        # still omitted from this payload — that is what makes an overwrite detectable after
        # the fact (ON CONFLICT DO UPDATE preserves the first insert's ``created_at`` while
        # replacing everything else), and it is how the 28 corrupted rows were found.
        "attempt": attempt,
        "run_type": run_type,
        "run_date": run_date.isoformat(),
        "model": resolved_model,
        "status": summary.status,
        "started_at": started_at.isoformat() if started_at is not None else None,
        "finished_at": finished_at.isoformat() if finished_at is not None else None,
        "duration_s": (
            round((finished_at - started_at).total_seconds(), 3)
            if started_at is not None and finished_at is not None
            else None
        ),
        "llm_calls": usage.get("llm_calls"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "est_cost_usd": usage.get("cost_usd"),
        "search_calls": usage.get("search_calls"),
        "sources_used": usage.get("sources_used"),
        "grounding_ok": usage.get("grounding_ok"),
        "grounding_failed": usage.get("grounding_failed"),
        "segments_total": summary.segments_total,
        "segments_ok": summary.segments_ok,
        "segments_carried": summary.segments_carried,
        "segments_failed": summary.segments_failed,
        "error_summary": summary.error_summary or None,
        "breakdown": breakdown or None,
    }


def write_row(
    client: Any,
    *,
    state: ResearchState,
    run_id: str,
    run_type: str,
    run_date: date,
    model: str | None = None,
    usage_snapshot: Mapping[str, Any] | None = None,
    degraded_pct: float = _DEGRADED_PCT_DEFAULT,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    attempt: int = 1,
) -> RunSummary | None:
    """Upsert one ``atlas_run_diagnostics`` row (on ``run_id, attempt``). Fail-soft → ``None``
    on any error (telemetry never breaks a run). Returns the :class:`RunSummary` on success.

    The conflict key is per-ATTEMPT since #1762. ``pipeline-digiquant.yml`` retries the chain up
    to 3 times inside one job, so ``run_id`` alone made the last attempt's row overwrite the
    expensive attempt's tokens and cost — 28 of 54 production rows, and it also collapsed
    ``run-episodes.ts``'s ``attempts`` count to 1 and made its ``recovered`` outcome
    unreachable. Requires migration 065; before it is applied the composite ``on_conflict``
    raises, which the fail-soft below turns into one lost telemetry row rather than a dead run.
    """
    summary = summarize_run(state, degraded_pct=degraded_pct)
    try:
        row = _row(
            run_id=run_id,
            run_type=run_type,
            run_date=run_date,
            model=model,
            usage_snapshot=usage_snapshot,
            summary=summary,
            started_at=started_at,
            finished_at=finished_at,
            attempt=attempt,
        )
        client.table("atlas_run_diagnostics").upsert(row, on_conflict="run_id,attempt").execute()
    except Exception as exc:  # telemetry write must never crash the run
        logger.warning("diagnostics: write_row failed (%s); run continues", exc)
        return None
    events_captured = usage_snapshot is not None and "events" in usage_snapshot
    events = list((usage_snapshot or {}).get("events") or [])
    event_rows = [
        {
            "run_id": run_id,
            "attempt": attempt,
            "run_date": run_date.isoformat(),
            "run_type": run_type,
            "sequence": event.get("sequence"),
            "event_kind": event.get("kind"),
            "phase": event.get("phase"),
            "operation": event.get("operation"),
            "document_key": event.get("document_key"),
            "name": event.get("name"),
            "status": event.get("status"),
            "duration_ms": event.get("duration_ms"),
            "retry_count": event.get("retry_count"),
            "prompt_tokens": event.get("prompt_tokens"),
            "completion_tokens": event.get("completion_tokens"),
            "cached_tokens": event.get("cached_tokens"),
            "cost_usd": event.get("cost_usd"),
            "sources": event.get("sources"),
            "input_summary": event.get("input_summary"),
            "output_summary": event.get("output_summary"),
            "call_id": event.get("call_id"),
            "attempt_id": event.get("attempt_id"),
            "node_run_id": event.get("node_run_id"),
        }
        for event in events
        if (
            isinstance(event, Mapping)
            and isinstance(event.get("sequence"), int)
            and event["sequence"] > 0
            and event.get("kind") in {"model_call", "search_call", "tool_call"}
            and event.get("status") in {"ok", "error"}
            and isinstance(event.get("name"), str)
            and isinstance(event.get("input_summary"), str)
            and isinstance(event.get("output_summary"), str)
        )
    ]
    if events_captured:
        try:
            stale_events = (
                client.table("olympus_run_events")
                .delete()
                .eq("run_id", run_id)
                .eq("attempt", attempt)
            )
            if event_rows:
                stale_events = stale_events.gte(
                    "sequence", max(row["sequence"] for row in event_rows) + 1
                )
            stale_events.execute()
        except Exception as exc:  # event telemetry is independently fail-soft
            logger.warning("diagnostics: stale run-event cleanup failed (%s); run continues", exc)
    if event_rows:
        try:
            client.table("olympus_run_events").upsert(
                event_rows,
                on_conflict="run_id,attempt,sequence",
            ).execute()
        except Exception as exc:  # event telemetry is independently fail-soft
            logger.warning("diagnostics: run-event write failed (%s); run continues", exc)
    logger.info(
        "diagnostics[%s attempt=%d]: status=%s segments ok=%d carried=%d failed=%d",
        run_id,
        attempt,
        summary.status,
        summary.segments_ok,
        summary.segments_carried,
        summary.segments_failed,
    )
    _announce_spend_alert(row)
    return summary


__all__ = [
    "RunSummary",
    "research_produced",
    "book_committed",
    "is_degraded",
    "register_breakdown_contributor",
    "summarize_run",
    "write_row",
]

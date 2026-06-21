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

Segment accounting reads the discriminated ``SegmentSlot`` payloads: ``today`` = freshly
generated, ``carried`` = fell back to the baseline. A carry whose reason is
:data:`~digiquant.olympus.atlas.phases.fail_soft.NODE_FAILED_REASON` is a *node failure*
(counted as failed), distinct from a deliberate below-threshold carry.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any  # noqa  # scored-lint: duck-typed Supabase client + rows

from digiquant.olympus.atlas.phases.fail_soft import NODE_FAILED_REASON
from digiquant.olympus.atlas.state import AtlasResearchState

logger = logging.getLogger(__name__)

# Phase output dicts that hold per-segment SegmentSlots (research segments). Phase 3
# (macro) is a *single* optional slot (``phase3_output``), counted separately below.
_SEGMENT_PHASES = ("phase1_outputs", "phase2_outputs", "phase4_outputs", "phase5_outputs")
_SINGLE_SEGMENT_PHASE = "phase3_output"

# ``phase`` marker stamped on chain-level errors by chain._record_chain_error (a whole
# sub-graph or terminal phase crashed), distinct from node-level PhaseErrors. A chain error
# gates the run; a crash in a core research engine (atlas/hermes) marks it failed outright.
_CHAIN_ERROR_PHASE = "chain"
_CORE_ENGINES = ("atlas", "hermes")

# Default share of failed segments above which a run is "degraded" (CLI may exit non-zero).
_DEGRADED_PCT_DEFAULT = 50.0
_ERROR_SUMMARY_MAX = 2000


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


def _segment_counts(state: AtlasResearchState) -> tuple[int, int, int, int, dict[str, Any]]:
    """(total, ok, carried, failed, per-phase breakdown) over the research segment slots.

    Covers the four dict-backed phases AND the single macro slot (``phase3_output``).
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


def _snapshot_published(state: AtlasResearchState) -> bool:
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


def summarize_run(
    state: AtlasResearchState,
    *,
    degraded_pct: float = _DEGRADED_PCT_DEFAULT,
) -> RunSummary:
    """Pure: derive segment counts, an error summary, and an overall status from state.

    Status values (in precedence order):

    - ``"failed"`` — nothing fresh was produced AND no snapshot was published; or a
      core research engine (atlas/hermes) crashed at the chain level.
    - ``"cancelled"`` — a snapshot was published AND no core engine crashed. A cancelled
      run still published a useful book and must not be reported as failed. The snapshot
      check prevents a SIGINT-at-startup (no book produced) from being mislabelled as
      "cancelled" (#814).
    - ``"degraded"`` — failed-segment share exceeds ``degraded_pct`` OR any non-core
      chain-level phase crashed (publish/materialize/risk-sizing).
    - ``"ok"`` — all other cases.

    ``segments_failed`` counts node-failure carries (not deliberate carries); chain-level
    crashes are recorded by ``chain._record_chain_error`` with ``phase == "chain"`` so
    they gate the run distinctly from node-level errors.
    """
    total, ok, carried, failed, breakdown = _segment_counts(state)
    errors = list(getattr(state, "errors", []) or [])
    error_summary = "; ".join(
        f"{getattr(e, 'phase', '?')}/{getattr(e, 'node', '?')}: {getattr(e, 'message', '')}"
        for e in errors
    )[:_ERROR_SUMMARY_MAX]
    if errors:
        breakdown["errors"] = [
            {
                "phase": getattr(e, "phase", None),
                "node": getattr(e, "node", None),
                "message": str(getattr(e, "message", ""))[:300],
            }
            for e in errors
        ]

    chain_errors = [e for e in errors if getattr(e, "phase", None) == _CHAIN_ERROR_PHASE]
    core_engine_down = any(getattr(e, "node", None) in _CORE_ENGINES for e in chain_errors)

    # A run that published a snapshot before SIGINT / ctrl-C did useful work —
    # promote from "failed" to "cancelled" so the dashboard reflects what happened.
    # Requiring _snapshot_published guards against a SIGINT-at-startup (no book
    # produced) being mislabelled as "cancelled" (#814).
    nothing_fresh = total == 0 or ok == 0
    if nothing_fresh or core_engine_down:
        if _snapshot_published(state) and not core_engine_down:
            status = "cancelled"
        else:
            status = "failed"
    elif chain_errors or (failed / total) * 100.0 > degraded_pct:
        status = "degraded"
    else:
        status = "ok"

    return RunSummary(
        segments_total=total,
        segments_ok=ok,
        segments_carried=carried,
        segments_failed=failed,
        status=status,
        error_summary=error_summary,
        breakdown=breakdown,
    )


def is_degraded(state: AtlasResearchState, *, degraded_pct: float = _DEGRADED_PCT_DEFAULT) -> bool:
    """True when the run is degraded/failed enough to warrant a non-zero CLI exit (CI retry).

    ``"cancelled"`` is excluded: a cancelled run that already published a book is
    not worth retrying — the book is on disk and the next scheduled run will pick
    up from there (#814).
    """
    return summarize_run(state, degraded_pct=degraded_pct).status in ("degraded", "failed")


def atlas_research_produced(state: AtlasResearchState) -> bool:
    """True when the Atlas pass yielded usable research for Hermes to act on.

    False only when Atlas crashed at the chain level (a core-engine ``atlas`` error) or
    produced zero research segments. The chain uses this to gate the Hermes commit so the
    PM never books a rebalance on stale prior context after an Atlas failure — the Jun-2026
    incident where Atlas returned empty LLM responses yet a pm-rebalance was still written
    on 2-day-stale prices (#944). A fully-carried quiet delta (segments carried from the
    baseline, none fresh) still counts as produced — the carried research is valid.
    """
    errors = list(getattr(state, "errors", []) or [])
    atlas_crashed = any(
        getattr(e, "phase", None) == _CHAIN_ERROR_PHASE and getattr(e, "node", None) == "atlas"
        for e in errors
    )
    total, *_rest = _segment_counts(state)
    return not atlas_crashed and total > 0


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
) -> dict[str, Any]:
    usage = dict(usage_snapshot or {})
    breakdown = dict(summary.breakdown)
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
    # Keep the `model` column a single stable slug for GROUP BY (the full per-run set lives in
    # breakdown["models"]). When the router serves several models we record the first; callers
    # wanting the complete list read the breakdown.
    resolved_model = model or (models[0] if models else None)
    return {
        "run_id": run_id,
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
    state: AtlasResearchState,
    run_id: str,
    run_type: str,
    run_date: date,
    model: str | None = None,
    usage_snapshot: Mapping[str, Any] | None = None,
    degraded_pct: float = _DEGRADED_PCT_DEFAULT,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> RunSummary | None:
    """Upsert one ``atlas_run_diagnostics`` row (on ``run_id``). Fail-soft → ``None`` on any
    error (telemetry never breaks a run). Returns the :class:`RunSummary` on success.
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
        )
        client.table("atlas_run_diagnostics").upsert(row, on_conflict="run_id").execute()
    except Exception as exc:  # noqa: BLE001 — telemetry write must never crash the run
        logger.warning("diagnostics: write_row failed (%s); run continues", exc)
        return None
    logger.info(
        "diagnostics[%s]: status=%s segments ok=%d carried=%d failed=%d",
        run_id,
        summary.status,
        summary.segments_ok,
        summary.segments_carried,
        summary.segments_failed,
    )
    return summary


__all__ = [
    "RunSummary",
    "atlas_research_produced",
    "is_degraded",
    "summarize_run",
    "write_row",
]

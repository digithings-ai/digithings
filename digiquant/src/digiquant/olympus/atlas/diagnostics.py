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
from datetime import date
from typing import Any  # noqa  # scored-lint: duck-typed Supabase client + rows

from digiquant.olympus.atlas.phases.fail_soft import NODE_FAILED_REASON
from digiquant.olympus.atlas.state import AtlasResearchState

logger = logging.getLogger(__name__)

# Phase output dicts that hold per-segment SegmentSlots (research segments).
_SEGMENT_PHASES = ("phase1_outputs", "phase2_outputs", "phase4_outputs", "phase5_outputs")

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
    status: str  # "ok" | "degraded" | "failed"
    error_summary: str
    breakdown: dict[str, Any]


def _segment_counts(state: AtlasResearchState) -> tuple[int, int, int, int, dict[str, Any]]:
    """(total, ok, carried, failed, per-phase breakdown) over the research segment slots."""
    ok = carried = failed = 0
    breakdown: dict[str, Any] = {}
    for phase in _SEGMENT_PHASES:
        slots = getattr(state, phase, {}) or {}
        p_ok = p_carried = p_failed = 0
        for slot in slots.values():
            payload = getattr(slot, "payload", None)
            source = getattr(payload, "source", None)
            if source == "today":
                p_ok += 1
            elif source == "carried":
                p_carried += 1
                if getattr(payload, "reason", None) == NODE_FAILED_REASON:
                    p_failed += 1
        if slots:
            breakdown[phase] = {"ok": p_ok, "carried": p_carried, "failed": p_failed}
        ok += p_ok
        carried += p_carried
        failed += p_failed
    return ok + carried, ok, carried, failed, breakdown


def summarize_run(
    state: AtlasResearchState, *, degraded_pct: float = _DEGRADED_PCT_DEFAULT
) -> RunSummary:
    """Pure: derive segment counts, an error summary, and an overall status from state.

    ``status`` is ``failed`` when nothing fresh was produced (a starved/aborted run worth
    retrying), ``degraded`` when the failed-segment share exceeds ``degraded_pct``, else
    ``ok``. ``segments_failed`` counts node-failure carries (not deliberate carries).
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

    if total == 0 or ok == 0:
        status = "failed"
    elif (failed / total) * 100.0 > degraded_pct:
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
    """True when the run is degraded/failed enough to warrant a non-zero CLI exit (CI retry)."""
    return summarize_run(state, degraded_pct=degraded_pct).status in ("degraded", "failed")


def _row(
    *,
    run_id: str,
    run_type: str,
    run_date: date,
    model: str | None,
    usage_snapshot: Mapping[str, Any] | None,
    summary: RunSummary,
) -> dict[str, Any]:
    usage = dict(usage_snapshot or {})
    breakdown = dict(summary.breakdown)
    models = usage.get("models")
    if models:
        breakdown["models"] = models
    # Fall back to the model(s) the usage observer actually saw when none was passed in.
    resolved_model = model or (",".join(map(str, models)) if models else None)
    return {
        "run_id": run_id,
        "run_type": run_type,
        "run_date": run_date.isoformat(),
        "model": resolved_model,
        "status": summary.status,
        "llm_calls": usage.get("llm_calls"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
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
) -> RunSummary | None:
    """Upsert one ``atlas_run_diagnostics`` row (on ``run_id``). Fail-soft → ``None`` on any
    error (telemetry never breaks a run). Returns the :class:`RunSummary` on success."""
    summary = summarize_run(state, degraded_pct=degraded_pct)
    try:
        row = _row(
            run_id=run_id,
            run_type=run_type,
            run_date=run_date,
            model=model,
            usage_snapshot=usage_snapshot,
            summary=summary,
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


__all__ = ["RunSummary", "is_degraded", "summarize_run", "write_row"]

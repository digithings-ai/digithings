"""Fail-soft execution wrapper for Atlas research nodes (Pillar 1A).

A single research node that gets an empty/invalid LLM body (or a transient
provider error) must not abort the whole run. Before this, an empty OpenRouter
response made ``run_research_agent`` raise ``JSONDecodeError`` after its retries,
the exception propagated through LangGraph, and the entire Atlas→Hermes chain
died **before publish + materialize** — so 19 healthy phases' work and the paper
book were lost to one bad sector call.

``run_segment_fail_soft`` runs the node's research call and, on any recoverable
failure, degrades the segment to an explicit ``Carried`` slot (read the prior
baseline payload for this segment) plus a ``PhaseError`` the caller merges into
``state.errors`` for the diagnostics audit row — instead of raising. A data gap
thus yields a *more conservative* book (one stale segment), never a crashed run.

This is a **deliberate, observable** degrade boundary, not a silent swallow: every
failure is logged at WARNING with the exception type and recorded as a structured
``PhaseError`` that surfaces in ``atlas_run_diagnostics``. ``KeyboardInterrupt`` /
``SystemExit`` (``BaseException``) still propagate.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

from pydantic import BaseModel

from digiquant.olympus.atlas.state import (
    Carried,
    PhaseError,
    SegmentPayload,
    SegmentSlot,
)

logger = logging.getLogger(__name__)

NODE_FAILED_REASON = "node_failed_no_data"
"""``Carried.reason`` marker distinguishing a node FAILURE carry from a triage carry."""


def run_segment_fail_soft(
    *,
    run_fn: Callable[[], BaseModel],
    segment_slug: str,
    phase: str,
    run_date: date,
    baseline_date: date | None,
) -> tuple[SegmentSlot, list[PhaseError]]:
    """Run one research node's LLM call, degrading any failure to a Carried slot.

    Args:
        run_fn: Thunk that performs ONLY the ``run_research_agent(...)`` call and
            returns its validated model. Input preparation (skill load, grounding,
            inputs_builder) must happen *outside* the thunk so genuine wiring bugs
            still fail loud — only the LLM call + validation is made fail-soft.
        segment_slug: The segment this node owns (becomes ``PhaseError.node`` and
            the fresh payload's ``segment``).
        phase: The owning phase label (e.g. ``"phase5_outputs"``) for ``PhaseError.phase``.
        run_date: Run date for the fresh payload's ``as_of`` and the carry fallback.
        baseline_date: Baseline the carry points at (falls back to ``run_date``).

    Returns:
        ``(slot, errors)`` — on success a fresh ``SegmentPayload`` slot and ``[]``;
        on a recoverable failure a ``Carried`` slot and a single-element error list
        the caller merges into ``state.errors``.
    """
    try:
        result = run_fn()
        slot = SegmentSlot(
            payload=SegmentPayload(
                segment=segment_slug,
                body=result.model_dump(mode="json"),
                as_of=run_date,
            )
        )
        return slot, []
    except Exception as exc:  # noqa: BLE001 — deliberate fail-soft boundary; see module docstring
        logger.warning(
            "atlas node %r (phase %s) failed (%s: %s); carrying baseline forward",
            segment_slug,
            phase,
            type(exc).__name__,
            exc,
        )
        slot = SegmentSlot(
            payload=Carried(baseline_date=baseline_date or run_date, reason=NODE_FAILED_REASON)
        )
        error = PhaseError(
            phase=phase,
            node=segment_slug,
            message=f"{type(exc).__name__}: {exc}"[:500],
            retryable=True,
        )
        return slot, [error]


__all__ = ["NODE_FAILED_REASON", "run_segment_fail_soft"]

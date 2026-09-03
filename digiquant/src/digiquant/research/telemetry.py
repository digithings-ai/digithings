"""Non-gating diagnostics-``breakdown`` contributors.

``breakdown`` is the run's schema-free telemetry surface: adding a key needs no migration.
Some events are worth an operator's attention without being worth degrading a run over —
``breakdown[phase]["circuit_breaker_skips"]`` and ``breakdown["master_digest_failed"]`` are
the existing precedents. This module holds that kind of contributor for edit-mode merge
fallbacks (#1741): a pure ``state -> dict`` function with no side effects, wired through
the ``register_breakdown_contributor`` seam (#1736) rather than by editing
``diagnostics._segment_counts``.

Registration is an import-time side effect, so something on the run path has to import
this module. ``phases/_node_factory.py`` does — it is the module that *writes*
``state.merge_fallbacks``, and every phase module imports it, so any compiled graph has
the contributor wired well before ``summarize_run`` is called.
"""

from __future__ import annotations

import logging
import math
import os
from typing import (
    Any,  # score:allow untyped any — jsonb breakdown fragment shape
)

from digiquant.research.diagnostics import register_breakdown_contributor
from digiquant.research.state import ResearchState

logger = logging.getLogger(__name__)

MERGE_FALLBACK_KEY = "merge_fallback"
CONTENT_FREEZE_KEY = "content_freeze"
SPEND_ALERT_KEY = "spend_alert"

# ── spend alert (#1764) ──────────────────────────────────────────────────────────────────
#
# Before this, the only bound on a day's LLM spend was the job's 240-minute
# ``timeout-minutes``. The owner's decision (2026-08-04) is **alert only, never block**: record
# the breach and surface it, but never abort a run and never refuse a segment. A mid-run abort
# would leave a partially-published run, and #1749/#1751 established that partial states are
# exactly where the silent-staleness defects live.
#
# So this is a WARNING threshold, not a ceiling. Nothing here can change ``status``,
# ``retry_signal``, or the process exit code.
SPEND_ALERT_ENV = "RESEARCH_SPEND_ALERT_USD"

# Calibrated against observed production runs: 2026-07-31 $4.00 / 292 calls, 07-26 $4.70 / 349
# calls, and a ~$1.55 mean across the 22 rows whose telemetry was never overwritten. The known
# outlier is the Jun 19 delta run at $11.95 / 147 calls (RUNBOOK's own cost-governance example).
# 10.0 sits above every normal day and below that outlier, so it fires on the anomaly rather
# than on Tuesday.
SPEND_ALERT_DEFAULT_USD = 10.0

__all__ = [
    "CONTENT_FREEZE_KEY",
    "MERGE_FALLBACK_KEY",
    "SPEND_ALERT_DEFAULT_USD",
    "SPEND_ALERT_ENV",
    "SPEND_ALERT_KEY",
    "content_freeze_breakdown",
    "merge_fallback_breakdown",
    "spend_alert",
    "spend_alert_threshold_usd",
]


@register_breakdown_contributor
def merge_fallback_breakdown(state: ResearchState) -> dict[str, Any]:
    """Count the segments whose edit patch failed to merge and were regenerated full.

    #1641 replaced the ``edit merge failed`` ``PhaseError`` with a silent fallback to
    full-mode regeneration. That was the right health call — a successful full run is not
    a degraded run — but the ``PhaseError`` had been the *only* thing that ever put the
    event into ``breakdown['errors']``, so the fallbacks became invisible: production run
    30636503352 (2026-07-31) logged three of them and recorded ``status='ok'`` with none of
    the three in ``err_nodes``. Each one is a segment that paid for a patch call *and* a
    full regeneration.

    Returns ``{}`` when nothing fell back, so no key is written rather than a zero in every
    row (matching ``circuit_breaker_skips``). Never gates: cost audits read this, not
    ``status`` or ``retry_signal``.
    """
    fallbacks = getattr(state, "merge_fallbacks", None) or {}
    if not fallbacks:
        return {}
    return {
        MERGE_FALLBACK_KEY: {
            "count": len(fallbacks),
            "segments": {slug: str(reason) for slug, reason in sorted(fallbacks.items())},
        }
    }


@register_breakdown_contributor
def content_freeze_breakdown(state: ResearchState) -> dict[str, Any]:
    """Count the segments whose edit merge produced a content-identical body (#1749/#1751).

    A no-op merge still publishes a ``documents`` row under the run date marked
    ``source="today"``, so it is counted in ``segments_ok`` and rendered in the dashboard's
    "18/27 segments" banner. Before this key the freeze left no telemetry trace at all: it was
    discoverable only by hashing ``documents.payload`` in SQL after the fact, which is how the
    #1559 digest freeze and the #1555 commit freeze both went unnoticed while runs reported
    ``ok``. Production 2026-07-31 recorded ``status='ok'``, ``segments_ok=18``, with
    ``sector-healthcare`` byte-identical to 07-28 inside the 18.

    ``segments_ok`` is deliberately NOT adjusted. It counts the segments that produced a row
    today, which stays true of a frozen one, and it is read by ``atlas_run_health`` (migration
    041), ``run-episodes.ts`` and three frontend components — redefining it is a separate
    change with its own consumers to migrate. The honest fix for the *public* surface is the
    freshness marker on the segment itself (``phase7_synthesis._segment_freshness``), which
    rides in ``daily_snapshots.snapshot`` and needs no migration. This key is the operator
    half: ``breakdown`` is omitted from the anon-readable 041 view.

    Each value is the segment's ``unchanged_since`` date, so the row shows *how long* each
    segment has been frozen rather than merely that it is. Returns ``{}`` when nothing froze,
    matching ``merge_fallback`` and ``circuit_breaker_skips`` — no zero in every row. Never
    gates: a frozen segment is a content-quality signal, not a run failure.
    """
    freezes = getattr(state, "content_freezes", None) or {}
    if not freezes:
        return {}
    return {
        CONTENT_FREEZE_KEY: {
            "count": len(freezes),
            "segments": {slug: str(since) for slug, since in sorted(freezes.items())},
        }
    }


def spend_alert_threshold_usd() -> float | None:
    """The per-invocation USD alert threshold, or ``None`` when alerting is off.

    ``RESEARCH_SPEND_ALERT_USD`` overrides :data:`SPEND_ALERT_DEFAULT_USD`. A value of ``0`` or
    below **disables** the alert — an explicit off switch matters because this fires on a
    heuristic, and an operator running a deliberately expensive backfill should be able to
    silence it without editing code.

    A malformed value falls back to the default rather than disabling: failing open on a typo
    would silently remove the alert, which is the failure mode the alert exists to prevent.
    """
    raw = os.environ.get(SPEND_ALERT_ENV)
    if raw is None or not raw.strip():
        return SPEND_ALERT_DEFAULT_USD
    try:
        threshold = float(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not a number; using the default $%.2f",
            SPEND_ALERT_ENV,
            raw,
            SPEND_ALERT_DEFAULT_USD,
        )
        return SPEND_ALERT_DEFAULT_USD
    return threshold if threshold > 0 else None


def spend_alert(cost_usd: object) -> dict[str, Any] | None:
    """The ``breakdown[spend_alert]`` fragment when *cost_usd* breached the threshold, else None.

    Pure — the caller does the logging and the GitHub annotation, so this stays trivially
    testable. Returns ``None`` rather than a zero/false record, matching ``merge_fallback``,
    ``content_freeze`` and ``circuit_breaker_skips``: the key's presence IS the signal, so a
    row without it is unambiguous.

    **Scope, stated plainly: this is per chain INVOCATION, not per day.**
    ``digigraph.usage`` accumulates in process-global state and ``chain`` calls ``start()`` once
    per process, so on a day that takes three outer-retry attempts each attempt measures only
    its own spend. Three attempts at $6 each would not trip a $10 threshold even though the day
    cost $18. Since #1762 the day's true total IS recoverable —
    ``SELECT sum(est_cost_usd) … GROUP BY run_date`` now sums across attempts instead of reading
    one surviving row — but that needs a query, not in-process state, so a daily aggregate
    belongs in a separate check rather than here.
    """
    threshold = spend_alert_threshold_usd()
    if threshold is None:
        return None
    if not isinstance(cost_usd, (int, float)) or isinstance(cost_usd, bool):
        return None
    if not math.isfinite(cost_usd) or cost_usd <= threshold:
        return None
    return {
        "threshold_usd": threshold,
        "est_cost_usd": round(float(cost_usd), 6),
        "scope": "invocation",
    }

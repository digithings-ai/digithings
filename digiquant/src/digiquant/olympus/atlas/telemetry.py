"""Non-gating diagnostics-breakdown contributors.

``diagnostics.py`` derives ``atlas_run_diagnostics.breakdown`` from the run state. Some
events are worth an operator's attention without being worth degrading a run over —
``breakdown[phase]["circuit_breaker_skips"]`` and ``breakdown["master_digest_failed"]``
are the existing precedents. This module holds the same kind of contributor for
edit-mode merge fallbacks (#1741): pure ``state -> dict`` functions with no side
effects, so they can be unit-tested and registered independently of the gate rules.

**Not yet registered, deliberately.** ``diagnostics.py`` is owned by an open PR that
adds the ``_BREAKDOWN_CONTRIBUTORS`` registration seam, so this branch does not touch
it. Once that seam lands, wiring is one line::

    from digiquant.olympus.atlas.telemetry import merge_fallback_breakdown

    _BREAKDOWN_CONTRIBUTORS = (
        ...,
        ("merge_fallback", merge_fallback_breakdown),
    )

Until then ``state.merge_fallbacks`` is populated on every run and is readable from the
checkpointer and the node logs; only the jsonb projection is pending.
"""

from __future__ import annotations

from typing import (
    Any,  # score:allow untyped any — jsonb breakdown fragment shape
)

from digiquant.olympus.atlas.state import AtlasResearchState

__all__ = ["merge_fallback_breakdown"]


def merge_fallback_breakdown(state: AtlasResearchState) -> dict[str, Any]:
    """Count the segments whose edit patch failed to merge and were regenerated full.

    #1641 replaced the ``edit merge failed`` ``PhaseError`` with a silent fallback to
    full-mode regeneration. That was the right health call — a successful full run is not
    a degraded run — but the ``PhaseError`` had been the *only* thing that ever put the
    event into ``breakdown['errors']``, so the fallbacks became invisible: production run
    30636503352 (2026-07-31) logged three of them and recorded ``status='ok'`` with none
    of the three in ``err_nodes``. Each one is a segment that paid for a patch call *and*
    a full regeneration.

    Returns ``{}`` when nothing fell back, so the caller can skip the key entirely rather
    than write a zero into every row (matching ``circuit_breaker_skips``).
    """
    fallbacks = getattr(state, "merge_fallbacks", None) or {}
    if not fallbacks:
        return {}
    return {
        "count": len(fallbacks),
        "segments": {slug: str(reason) for slug, reason in sorted(fallbacks.items())},
    }

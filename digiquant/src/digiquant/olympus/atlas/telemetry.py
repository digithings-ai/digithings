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

from typing import (
    Any,  # score:allow untyped any — jsonb breakdown fragment shape
)

from digiquant.olympus.atlas.diagnostics import register_breakdown_contributor
from digiquant.olympus.atlas.state import AtlasResearchState

MERGE_FALLBACK_KEY = "merge_fallback"

__all__ = ["MERGE_FALLBACK_KEY", "merge_fallback_breakdown"]


@register_breakdown_contributor
def merge_fallback_breakdown(state: AtlasResearchState) -> dict[str, Any]:
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

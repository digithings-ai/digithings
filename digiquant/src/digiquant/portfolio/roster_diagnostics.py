"""Roster-width contributor for the ``atlas_run_diagnostics.breakdown`` jsonb (#1767).

``ATLAS_MAX_ANALYSTS`` was bypassed for the entire observed lifetime of the pipeline and
**no column recorded roster width**, so a 1.6× cap breach (39 dispatched analysts against
a configured cap of 25 on 2026-07-31) was invisible in the database and the 4.9× cost
swing it produced got attributed to prompt growth. Width therefore has to be recorded,
not just fixed — otherwise the next regression is equally undetectable.

Width folds into the existing ``breakdown`` jsonb rather than a new column, following the
``_row`` precedent: **no migration**.

This module is a *pure* ``Callable[[AtlasResearchState], dict[str, Any]]`` matching the
``_BREAKDOWN_CONTRIBUTORS`` seam that PR #1774 lands in
``atlas/diagnostics.py::_segment_counts``. It deliberately imports **nothing** from
``diagnostics.py``: the seam is not on ``develop`` yet, and #1774 owns that file. Once
#1774 has landed, wiring this up is a single line there —

    _BREAKDOWN_CONTRIBUTORS.append(roster_breakdown)

— and until that line exists nothing calls this in production, so the width is only in
H4's log line. That is stated plainly in the #1767 PR body rather than hidden here.
"""

from __future__ import annotations

from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: jsonb breakdown payload
)

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.hermes.roster_cap import configured_max_analysts

BREAKDOWN_KEY = "roster"


def roster_breakdown(state: AtlasResearchState) -> dict[str, Any]:
    """``{"roster": {...}}`` — H4 focus-roster width by reason, plus the cap in force.

    ``over_cap`` compares width against the **static** ``ATLAS_MAX_ANALYSTS``, not the
    regime-adaptive budget: a stress-regime budget below the static cap is a deliberate
    tightening, whereas exceeding the static cap is the #1767 breach. ``0`` means no cap
    is configured, in which case no width can be a breach.

    Defensive by construction (``getattr`` chains, no raise, no I/O) — this runs on the
    run-summary path, and a contributor must never be the reason a diagnostics row goes
    unwritten. Mirrors the ``getattr`` idiom ``diagnostics._book_status`` already uses.
    """
    phase_hermes = getattr(state, "phase_hermes", None)
    roster = list(getattr(phase_hermes, "focus_roster", None) or [])
    excluded = list(getattr(phase_hermes, "focus_roster_excluded", None) or [])
    by_reason: dict[str, int] = {}
    theses: set[str] = set()
    for entry in roster:
        reason = str(getattr(entry, "roster_reason", "") or "other")
        by_reason[reason] = by_reason.get(reason, 0) + 1
        thesis_id = getattr(entry, "linked_market_thesis_id", None)
        if thesis_id:
            theses.add(str(thesis_id))
    cap = configured_max_analysts()
    return {
        BREAKDOWN_KEY: {
            "width": len(roster),
            "by_reason": dict(sorted(by_reason.items())),
            "theses_covered": len(theses),
            "excluded": len(excluded),
            "max_analysts": cap,
            "over_cap": bool(cap > 0 and len(roster) > cap),
        }
    }

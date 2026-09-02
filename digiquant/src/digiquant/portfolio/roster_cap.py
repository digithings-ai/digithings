"""Focus-roster cap helpers shared by H4–H6 fan-out (#936, #950, #1767)."""

from __future__ import annotations

import logging
from collections.abc import Collection, Sequence

from digiquant.dashboard.envcompat import MAX_ANALYSTS, env_lookup

logger = logging.getLogger(__name__)

_DEFAULT_MIN_NEW = 1


def configured_max_analysts() -> int:
    """``ATLAS_MAX_ANALYSTS`` as an int; ``0`` (or unset/malformed) means *no cap*.

    Single reader for the env var so the cap in force, the roster telemetry, and the
    H4 node's static baseline can never disagree — before #1767 three call sites
    parsed it independently.
    """
    raw = env_lookup(MAX_ANALYSTS, default="0") or "0"
    try:
        return int(raw)
    except ValueError:
        logger.warning("roster_cap: ignoring malformed ATLAS_MAX_ANALYSTS=%r; treating as 0", raw)
        return 0


def _ranked_candidates(candidates: list[str], candidate_priority: Sequence[str]) -> list[str]:
    """*candidates* reordered so ``candidate_priority`` names come first, in that order.

    Names absent from *candidate_priority* keep their original relative order behind
    them. With an empty *candidate_priority* this is the identity — which is what
    every caller other than H4 relies on for byte-identical selection.
    """
    if not candidate_priority:
        return candidates
    rank = {ticker: i for i, ticker in enumerate(candidate_priority)}
    unranked = len(rank)
    ordered = sorted(
        (rank.get(ticker, unranked), position, ticker) for position, ticker in enumerate(candidates)
    )
    return [ticker for _, _, ticker in ordered]


def capped_tickers(
    tickers: list[str],
    held: Collection[str] = (),
    *,
    min_new: int = _DEFAULT_MIN_NEW,
    adaptive_max_analysts: int | None = None,
    candidate_priority: Sequence[str] = (),
) -> list[str]:
    """Apply ``ATLAS_MAX_ANALYSTS`` while preserving the held-ticker invariant (#936).

    **Cap invariant (#1767):** ``len(result) <= max(max_analysts, len(held_in_order))``.
    The prior book is the *only* sanctioned overshoot — #936 forbids dropping a holding,
    so a book wider than the cap wins and the operator must raise the cap. Nothing else
    may widen the roster: the cap is a cost ceiling, and a ceiling that other rules can
    lift is not a ceiling.

    ``min_new`` (#950) is a *floor* on non-held survivors, clamped to the remaining
    budget. The whole post-held budget already goes to non-held candidates, so the floor
    is met implicitly whenever ``min_new <= max_analysts - len(held)``; a larger value is
    clamped and logged rather than honoured, because honouring it would breach the cap.
    Before #1767 it *expanded* the cap instead — which, together with H4 passing the
    whole H3 thesis-vehicle map as ``held``, is why the cap never capped anything.

    ``adaptive_max_analysts`` (optional): when not None, overrides the
    ATLAS_MAX_ANALYSTS environment variable as the analyst cap. When None,
    falls back to the env var.

    ``candidate_priority`` (optional, #1767): preferred order for *non-held* candidates
    when the budget cannot fit them all. H4 passes its thesis-vehicle round-robin here,
    so thesis coverage is prioritised **within** the cap instead of being exempt from
    it. Output order always follows *tickers*, never this list.
    """
    max_analysts = (
        adaptive_max_analysts if adaptive_max_analysts is not None else configured_max_analysts()
    )
    if max_analysts <= 0 or len(tickers) <= max_analysts:
        return list(tickers)

    held_set = set(held)
    held_in_order = [t for t in tickers if t in held_set]
    candidates = [t for t in tickers if t not in held_set]

    if len(held_in_order) >= max_analysts:
        # #936 wins over the cap, but only by exactly the width of the book. Reserving
        # new-candidate slots on top (the pre-#1767 behaviour) compounds a breach that
        # is already forced — raising ATLAS_MAX_ANALYSTS is the operator's lever.
        logger.warning(
            "Hermes roster cap: %d held tickers meet or exceed ATLAS_MAX_ANALYSTS=%d; "
            "keeping ALL held (over budget) so no prior-book holding is dropped (#936), "
            "and reserving NO new-candidate slots — the cap is never widened beyond the "
            "book (#1767). Raise ATLAS_MAX_ANALYSTS to restore exploration: %s",
            len(held_in_order),
            max_analysts,
            ", ".join(held_in_order),
        )
        return held_in_order

    budget = max_analysts - len(held_in_order)
    kept_candidates = _ranked_candidates(candidates, candidate_priority)[:budget]
    if min_new > budget:
        logger.info(
            "Hermes roster cap: explore floor min_new=%d exceeds the %d candidate slots "
            "left under ATLAS_MAX_ANALYSTS=%d; clamped to %d (#1767 — the floor never "
            "widens the cap).",
            min_new,
            budget,
            max_analysts,
            len(kept_candidates),
        )
    kept = set(held_in_order) | set(kept_candidates)
    prioritised = len(kept_candidates) - len(set(kept_candidates) - set(candidate_priority))
    logger.info(
        "Hermes roster capped to %d/%d tickers (ATLAS_MAX_ANALYSTS=%d): %d held + "
        "%d candidates (%d of them prioritised)",
        len(kept),
        len(tickers),
        max_analysts,
        len(held_in_order),
        len(kept_candidates),
        prioritised,
    )
    return [t for t in tickers if t in kept]

"""Focus-roster cap helpers shared by H4–H6 fan-out (#936)."""

from __future__ import annotations

import logging
import os
from collections.abc import Collection

logger = logging.getLogger(__name__)


def capped_tickers(tickers: list[str], held: Collection[str] = ()) -> list[str]:
    """Apply ``ATLAS_MAX_ANALYSTS`` while preserving the held-ticker invariant (#936)."""
    max_analysts = int(os.environ.get("ATLAS_MAX_ANALYSTS", "0") or "0")
    if max_analysts <= 0 or len(tickers) <= max_analysts:
        return list(tickers)

    held_set = set(held)
    held_in_order = [t for t in tickers if t in held_set]
    candidates = [t for t in tickers if t not in held_set]

    if len(held_in_order) >= max_analysts:
        logger.warning(
            "Hermes roster cap: %d held tickers exceed ATLAS_MAX_ANALYSTS=%d; keeping ALL held "
            "(over budget) so no prior-book holding is dropped (#936): %s",
            len(held_in_order),
            max_analysts,
            ", ".join(held_in_order),
        )
        return held_in_order

    budget = max_analysts - len(held_in_order)
    kept_candidates = candidates[:budget]
    logger.info(
        "Hermes roster capped to %d/%d tickers (ATLAS_MAX_ANALYSTS=%d): %d held + %d candidates",
        max_analysts,
        len(tickers),
        max_analysts,
        len(held_in_order),
        len(kept_candidates),
    )
    kept = set(held_in_order) | set(kept_candidates)
    return [t for t in tickers if t in kept]

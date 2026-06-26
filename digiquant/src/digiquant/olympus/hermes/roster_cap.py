"""Focus-roster cap helpers shared by H4–H6 fan-out (#936, #950)."""

from __future__ import annotations

import logging
import os
from collections.abc import Collection

logger = logging.getLogger(__name__)

_DEFAULT_MIN_NEW = 1


def capped_tickers(
    tickers: list[str],
    held: Collection[str] = (),
    *,
    min_new: int = _DEFAULT_MIN_NEW,
    adaptive_max_analysts: int | None = None,
) -> list[str]:
    """Apply ``ATLAS_MAX_ANALYSTS`` while preserving the held-ticker invariant (#936).

    ``min_new`` (#950): when non-held candidates exist, the cap expands (if
    necessary) so that at least *min_new* non-held tickers survive. This
    prevents the roster from freezing on prior-book holdings and never
    surfacing new opportunities.

    ``adaptive_max_analysts`` (optional): when not None, overrides the
    ATLAS_MAX_ANALYSTS environment variable as the analyst cap. When None,
    falls back to the env var.
    """
    max_analysts = (
        adaptive_max_analysts
        if adaptive_max_analysts is not None
        else int(os.environ.get("ATLAS_MAX_ANALYSTS", "0") or "0")
    )
    if max_analysts <= 0 or len(tickers) <= max_analysts:
        return list(tickers)

    held_set = set(held)
    held_in_order = [t for t in tickers if t in held_set]
    candidates = [t for t in tickers if t not in held_set]

    # How many new slots we *must* reserve (clamped to available candidates).
    effective_min = min(min_new, len(candidates))

    if len(held_in_order) >= max_analysts:
        if effective_min > 0:
            # Expand the cap to fit both all held AND the minimum new slots (#950).
            kept_candidates = candidates[:effective_min]
            logger.info(
                "Hermes roster cap: %d held tickers fill ATLAS_MAX_ANALYSTS=%d; "
                "expanding by %d to reserve new-candidate slots (#950): %s",
                len(held_in_order),
                max_analysts,
                len(kept_candidates),
                ", ".join(kept_candidates),
            )
            kept = set(held_in_order) | set(kept_candidates)
            return [t for t in tickers if t in kept]

        logger.warning(
            "Hermes roster cap: %d held tickers exceed ATLAS_MAX_ANALYSTS=%d; "
            "keeping ALL held (over budget) so no prior-book holding is "
            "dropped (#936): %s",
            len(held_in_order),
            max_analysts,
            ", ".join(held_in_order),
        )
        return held_in_order

    budget = max(max_analysts - len(held_in_order), effective_min)
    kept_candidates = candidates[:budget]
    logger.info(
        "Hermes roster capped to %d/%d tickers (ATLAS_MAX_ANALYSTS=%d): %d held + %d candidates",
        len(held_in_order) + len(kept_candidates),
        len(tickers),
        max_analysts,
        len(held_in_order),
        len(kept_candidates),
    )
    kept = set(held_in_order) | set(kept_candidates)
    return [t for t in tickers if t in kept]

"""Triage helpers — segment ↔ ticker mapping + price-delta aggregation.

Used by ``digiquant_atlas.triage`` to convert raw per-ticker percentage
moves (computed in :func:`digiquant_atlas.supabase_io.query_price_deltas`)
into per-segment signals the rule evaluators consume.

The mapping below is the **load-bearing source of truth** for ticker→segment
attribution in triage. It is deliberately encoded in code (not YAML) for
two reasons:

1. The high-tier asset-class segments (bonds / commodities / forex) are not
   driven by ``config/sectors.yaml`` (that file covers the 11 GICS sectors
   only).
2. The watchlist file uses free-form category strings ("fixed_income",
   "commodity_gold", …) — fine for documentation, but parsing those into
   triage segments would silently swallow typos in the markdown table.
   A code constant fails loudly if a referenced ticker is renamed.

Sector ETFs come straight from ``config/sectors.yaml`` (loaded via
``sectors_config.load_sectors``) — re-encoding them here would drift.

Judgment calls (called out for the PR reviewer):
- **forex**: Atlas's watchlist tracks DXY/UUP as macro indicators rather
  than a dedicated forex segment; UUP is the only tradeable proxy with
  consistent ``price_history`` coverage. Map ``forex`` → ``("UUP",)``.
  DXY is omitted because not every ingest source delivers DXY rows
  reliably; the high-tier rule still fires when UUP moves enough.
- **international / crypto**: not wired here — ``crypto`` is mandatory
  (always regen) and ``international`` is a standard-tier bias-driven
  rule. Adding price deltas there is a future enhancement.
"""

from __future__ import annotations

from functools import lru_cache

from digiquant_atlas.sectors_config import load_sectors


# ─── High-tier asset-class tickers ──────────────────────────────────────────

_BOND_TICKERS: tuple[str, ...] = ("TLT", "IEF", "SHY", "AGG", "LQD", "HYG", "TIP", "EMB")
"""Bonds segment representative ETFs. TLT/IEF/SHY span the curve; AGG is the
broad index; LQD/HYG/TIP/EMB cover credit, inflation-linked, and EM. Any one
moving > threshold should regen the segment."""

_COMMODITY_TICKERS: tuple[str, ...] = (
    "GLD",
    "SLV",
    "GDX",
    "USO",
    "DBO",
    "BNO",
    "PDBC",
    "DJP",
    "CPER",
)
"""Commodities segment ETFs. Gold/silver/oil/copper plus broad baskets."""

_FOREX_TICKERS: tuple[str, ...] = ("UUP",)
"""Forex segment. Watchlist treats DXY/UUP as macro indicators; UUP is the
only consistently-loaded tradeable proxy. See module docstring."""


# ─── Public mapping ──────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def segment_tickers() -> dict[str, tuple[str, ...]]:
    """Return ``{segment_slug: tuple_of_tickers}`` for every triage segment
    that has price-delta-driven rules.

    Includes:
    - High-tier asset classes: ``bonds``, ``commodities``, ``forex``.
    - Low-tier sectors: each ``sector-*`` slug from ``config/sectors.yaml``,
      mapped to its primary ETFs. Per-segment top-tickers are intentionally
      excluded — sector ETFs already track those names, and adding them would
      double-count idiosyncratic moves into the segment-level signal.

    The returned dict is fresh per call (so mutation by a caller cannot leak
    back into the cache); the underlying tuple data is process-static.
    """
    out: dict[str, tuple[str, ...]] = {
        "bonds": _BOND_TICKERS,
        "commodities": _COMMODITY_TICKERS,
        "forex": _FOREX_TICKERS,
    }
    for sector in load_sectors():
        # Primary ETF first (already the convention in sectors.yaml).
        out[sector.slug] = tuple(sector.etfs)
    return dict(out)


def all_tracked_tickers() -> tuple[str, ...]:
    """Return the deduped union of every ticker referenced by ``segment_tickers()``.

    Used by the price-delta query path to bound the Supabase read to tickers
    that actually feed a triage rule. Order is not guaranteed — callers
    should treat the result as a set.
    """
    seen: dict[str, None] = {}
    for tickers in segment_tickers().values():
        for t in tickers:
            seen.setdefault(t, None)
    return tuple(seen.keys())


def max_abs_move_for_segment(
    segment: str,
    deltas: dict[str, float],
) -> float | None:
    """Return the largest absolute ``pct_change`` observed across the segment's
    tickers, or ``None`` if no ticker has a delta.

    ``deltas`` is the keyed-by-ticker output of
    :func:`digiquant_atlas.supabase_io.query_price_deltas` — values are
    fractional pct changes (``0.0123`` means +1.23%). A ticker missing from
    the dict is treated as "no signal," not "zero move" — caller decides
    what to do (the high-tier rule defaults to regenerate).
    """
    tickers = segment_tickers().get(segment)
    if not tickers:
        return None
    observed: list[float] = []
    for t in tickers:
        val = deltas.get(t)
        if val is None:
            continue
        try:
            observed.append(abs(float(val)))
        except (TypeError, ValueError):
            continue
    if not observed:
        return None
    return max(observed)


__all__ = [
    "all_tracked_tickers",
    "max_abs_move_for_segment",
    "segment_tickers",
]

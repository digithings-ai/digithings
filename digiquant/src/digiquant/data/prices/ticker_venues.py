"""Ticker → trading-calendar venue mapping for the core watchlist (issue #337).

ADR-0013 establishes four venues — ``NYSE``, ``NASDAQ``, ``CRYPTO``, ``FX`` —
and assigns every core-universe ticker to one of them.  The mapping lives here
(rather than in a Postgres table) per ADR-0013: it is a small static constant
that changes rarely; a code-resident dict avoids an extra round-trip per query
and keeps the list reviewable in PRs.

Conventions (from ADR-0013):

* All US equity ETFs in the watchlist are assigned ``NYSE`` regardless of their
  primary listing exchange.  NYSE serves as the canonical US equity calendar.
* Crypto spot tickers (``*-USD``) and US-listed crypto ETFs (IBIT, FBTC, etc.)
  are assigned ``CRYPTO`` even though the ETFs trade on NYSE Arca during NYSE
  hours.  Per the ADR this is intentional: downstream consumers join the crypto
  calendar to model continuous-market behaviour for these series.
* FX majors are assigned ``FX``.  Daily resolution treats Sat+Sun as
  non-trading; the Sun-evening reopen is below the granularity we backfill at.
* ``NASDAQ`` is reserved for future per-equity coverage and is currently empty
  for the watchlist (the schema column accepts it; no rows yet).

The :data:`CORE_TICKER_VENUES` mapping is the single source of truth for the
backfill job and for the technicals/frontend join sites.
"""

from __future__ import annotations

from typing import Final

# US equity ETFs (market-cap, sector, international, EM, commodity, fixed-income).
_NYSE_TICKERS: Final[tuple[str, ...]] = (
    # Market cap
    "SPY",
    "QQQ",
    "DIA",
    "IWB",
    "VTI",
    "MDY",
    "IJH",
    "IWM",
    "IJR",
    # Sector
    "XLK",
    "XLF",
    "XLE",
    "XLV",
    "XLI",
    "XLRE",
    "XLU",
    "XLY",
    "XLP",
    "XLB",
    "XLC",
    # International developed
    "EFA",
    "VEA",
    "VGK",
    "EWJ",
    "EWG",
    "EWU",
    "EWA",
    # Emerging markets
    "EEM",
    "VWO",
    "FXI",
    "ASHR",
    "EWZ",
    "EWT",
    "EWY",
    "INDA",
    # Commodities
    "GLD",
    "IAU",
    "SLV",
    "DBO",
    "USO",
    "BNO",
    "PDBC",
    "DJP",
    "CPER",
    # Fixed income / cash
    "BIL",
    "SHV",
    "SHY",
    "IEF",
    "TLT",
    "AGG",
    "HYG",
    "LQD",
    "TIP",
    "EMB",
    # Macro indicator (USD bull) — tradeable equity-like ticker on NYSE Arca.
    "UUP",
)

# Crypto spot pairs (yfinance ``*-USD`` suffix) and US-listed crypto ETFs.
# ADR-0013: all assigned ``CRYPTO`` venue regardless of where the ETF lists.
_CRYPTO_TICKERS: Final[tuple[str, ...]] = (
    # Spot pairs
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "XRP-USD",
    "BNB-USD",
    "TRX-USD",
    "DOGE-USD",
    "ADA-USD",
    "AVAX-USD",
    "LINK-USD",
    "DOT-USD",
    "BCH-USD",
    "LTC-USD",
    "NEAR-USD",
    "ATOM-USD",
    "XMR-USD",
    "SUI20947-USD",
    # ETFs (futures-based + spot)
    "BITO",
    "IBIT",
    "FBTC",
    "ETHA",
    "FETH",
    "GBTC",
)

# FX majors (yfinance ``X=F`` form is intraday; daily backfill uses pair codes
# from the FX adapter).  Venue mapping is authoritative regardless of source.
_FX_TICKERS: Final[tuple[str, ...]] = (
    "EURUSD",
    "GBPUSD",
    "JPYUSD",
    "CADUSD",
    # Yahoo-style alternates that the FX fetcher may emit (#328).
    "EURUSD=X",
    "GBPUSD=X",
    "JPYUSD=X",
    "CADUSD=X",
)


def _build_mapping() -> dict[str, str]:
    """Materialise the ticker → venue dict from the per-venue tuples."""
    mapping: dict[str, str] = {}
    for ticker in _NYSE_TICKERS:
        mapping[ticker] = "NYSE"
    for ticker in _CRYPTO_TICKERS:
        mapping[ticker] = "CRYPTO"
    for ticker in _FX_TICKERS:
        mapping[ticker] = "FX"
    return mapping


CORE_TICKER_VENUES: Final[dict[str, str]] = _build_mapping()
"""Mapping from ticker → venue for the core backfill universe.

Use :func:`venue_for` for case-insensitive lookups.  Read this dict directly
when iterating the universe (e.g., to backfill calendar rows for every venue
that has at least one ticker assigned).
"""

ALLOWED_VENUES: Final[frozenset[str]] = frozenset({"NYSE", "NASDAQ", "CRYPTO", "FX"})
"""Venue values that the schema (migration 025) accepts."""


def venue_for(ticker: str) -> str | None:
    """Return the venue for ``ticker`` or ``None`` if not mapped.

    Lookup is case-insensitive on the ticker; the stored mapping uses the
    upper-case form that yfinance / the watchlist emit.
    """
    if not ticker:
        return None
    return CORE_TICKER_VENUES.get(ticker.upper())


__all__ = [
    "ALLOWED_VENUES",
    "CORE_TICKER_VENUES",
    "venue_for",
]

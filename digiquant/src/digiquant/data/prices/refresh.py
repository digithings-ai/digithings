"""On-demand technicals refresh (Pillar 1F).

When ``price_technicals`` is stale at run time (e.g. a Saturday baseline whose Friday
intraday prices cron didn't run), recompute the indicators from the raw OHLCV **already in
``price_history``** and upsert them — *network-free* (no yfinance fetch), so it is safe to
call from inside the pipeline. This brings the technicals table current to the freshest
prices already ingested, rather than silently reading days-old indicators.

This is distinct from the prices cron's ``fetch-quotes`` (which pulls *new* OHLCV from the
network). The CI pre-baseline step still does a real fetch; this recompute is the in-graph
fallback (opt-in via ``ATLAS_REFRESH_ON_DEMAND``) and the reusable core both can share.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any  # noqa  # scored-lint: duck-typed Supabase client + rows

import polars as pl

from digiquant.data.prices import TECHNICAL_COLUMNS
from digiquant.data.prices.supabase_writer import technicals_to_rows, upsert_price_technicals
from digiquant.data.prices.technicals import MIN_BARS, compute_indicators

logger = logging.getLogger(__name__)

# Calendar window of OHLCV to pull per ticker — wide enough for the 200-day SMA (~270
# trading days) plus slack for weekends/holidays.
_DEFAULT_LOOKBACK_DAYS = 400
_OHLCV_COLUMNS = ("date", "ticker", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of a technicals recompute."""

    tickers_processed: int
    rows_upserted: int


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _read_history(client: Any, tickers: list[str], as_of: date, lookback_days: int) -> list[dict]:
    """Raw OHLCV rows for ``tickers`` in ``(as_of − lookback, as_of]``, oldest first.

    Look-ahead-guarded (``.lte(as_of)``) so a recompute is reproducible for a back-dated run.
    """
    since = (as_of - timedelta(days=max(1, lookback_days))).isoformat()
    resp = (
        client.table("price_history")
        .select(",".join(_OHLCV_COLUMNS))
        .in_("ticker", list(tickers))
        .lte("date", as_of.isoformat())
        .gte("date", since)
        .order("date", desc=False)
        .execute()
    )
    return list(getattr(resp, "data", None) or [])


def _frame_for_ticker(rows: list[dict]) -> pl.DataFrame:
    """Build the OHLCV frame ``compute_indicators`` expects (``timestamp`` + OHLCV)."""
    return pl.DataFrame(
        {
            "timestamp": [str(r.get("date"))[:10] for r in rows],
            "open": [_to_float(r.get("open")) for r in rows],
            "high": [_to_float(r.get("high")) for r in rows],
            "low": [_to_float(r.get("low")) for r in rows],
            "close": [_to_float(r.get("close")) for r in rows],
            "volume": [_to_float(r.get("volume")) for r in rows],
        }
    ).with_columns(pl.col("timestamp").str.to_date(strict=False))


def recompute_technicals_from_history(
    *,
    client: Any,
    tickers: list[str] | tuple[str, ...],
    as_of: date,
    lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
) -> RefreshResult:
    """Recompute + upsert ``price_technicals`` from ``price_history`` (≤ ``as_of``).

    Network-free and idempotent (upserts on ``(date, ticker)``). A ticker with fewer than
    :data:`~digiquant.data.prices.technicals.MIN_BARS` bars is skipped. The caller decides
    whether to run this (it does I/O); errors propagate so the caller can fail-soft.
    """
    tickers = [t for t in dict.fromkeys(tickers) if t]  # dedupe, drop empties
    if not tickers:
        return RefreshResult(0, 0)

    rows = _read_history(client, tickers, as_of, lookback_days)
    by_ticker: dict[str, list[dict]] = {}
    for row in rows:
        ticker = row.get("ticker")
        if isinstance(ticker, str):
            by_ticker.setdefault(ticker, []).append(row)

    out_rows: list[dict] = []
    processed = 0
    for ticker, t_rows in by_ticker.items():
        if len(t_rows) < MIN_BARS:
            continue
        frame = _frame_for_ticker(t_rows)
        indicators = compute_indicators(frame)
        keep = [c for c in TECHNICAL_COLUMNS if c in indicators.columns]
        out_rows.extend(technicals_to_rows(indicators.select(keep), ticker, frame["timestamp"]))
        processed += 1

    result = upsert_price_technicals(client, out_rows)
    logger.info(
        "refresh: recomputed technicals for %d/%d tickers (%d rows) as_of %s",
        processed,
        len(tickers),
        result.rows,
        as_of.isoformat(),
    )
    return RefreshResult(tickers_processed=processed, rows_upserted=result.rows)


__all__ = ["RefreshResult", "recompute_technicals_from_history"]

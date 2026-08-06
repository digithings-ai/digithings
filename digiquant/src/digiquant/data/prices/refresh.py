"""On-demand technicals refresh (Pillar 1F).

When ``price_technicals`` is stale at run time (e.g. a Saturday baseline whose Friday
intraday prices cron didn't run), recompute the indicators from the raw OHLCV **already in
``price_history``** and upsert them — *network-free* (no yfinance fetch), so it is safe to
call from inside the pipeline. This brings the technicals table current to the freshest
prices already ingested, rather than silently reading days-old indicators.

This is distinct from the prices cron's ``fetch-quotes`` (which pulls *new* OHLCV from the
network). The CI pre-baseline step still does a real fetch; this recompute is the in-graph
fallback (opt-in via ``ATLAS_REFRESH_ON_DEMAND``) and the reusable core both can share.

Read window vs write window (#1752)
-----------------------------------

The two are deliberately **separate**. Every rolling indicator has a warm-up prefix —
``sma_200`` / ``zscore_200`` need 200 prior bars — and during that prefix the indicator is
genuinely ``NULL``. ``upsert_price_technicals`` issues a PostgREST bulk upsert with no
per-column coalesce, so writing a warm-up row *overwrites* a previously-valid value with
``NULL``. That is the #1752 clobber.

So this module reads ``[write_start − warmup_days, as_of]`` but only upserts rows on or
after ``write_start``. Every written row therefore carries a full warm-up behind it and no
long-window value is ever replaced by ``NULL``.

*Known limitation:* a ticker whose actual inception falls inside the warm-up read window has
no 200 bars to compute from, so its leading rows legitimately carry ``NULL`` long-window
indicators. Those are first writes, not clobbers.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any  # score:allow untyped any — scored-lint: duck-typed Supabase client + rows

import polars as pl

from digiquant.data.prices import TECHNICAL_COLUMNS
from digiquant.data.prices._utils import fetch_trading_days, filter_rows_by_trading_days
from digiquant.data.prices.supabase_writer import technicals_to_rows, upsert_price_technicals
from digiquant.data.prices.technicals import MIN_BARS, compute_indicators
from digiquant.data.prices.ticker_venues import venue_for

logger = logging.getLogger(__name__)

# Calendar days of extra OHLCV read *before* the write window, wide enough for the longest
# indicator warm-up (200 trading bars ≈ 280 calendar days) plus slack for holidays.
WARMUP_CALENDAR_DAYS = 320
# Calendar days written by default. The preflight caller only needs the freshest rows to
# clear a staleness signal; a wider default would rewrite settled history for no gain.
DEFAULT_WRITE_WINDOW_DAYS = 30

# PostgREST's hard `max-rows` cap. A `page_size` above this silently returns only the first
# 1 000 rows, which makes `len(batch) < page_size` true on page 1 and stops paging after one
# page — the same trap documented on `_utils.fetch_trading_days`.
_POSTGREST_MAX_ROWS = 1000

_OHLCV_COLUMNS = ("date", "ticker", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of a technicals recompute.

    ``rows_upserted`` is the number of rows actually written (0 on a dry run) — callers
    such as ``preflight._refresh_stale_technicals`` gate on it, so it must never count
    rows that were only computed. ``rows_computed`` carries that figure instead.
    """

    tickers_processed: int
    rows_upserted: int
    rows_computed: int = 0
    history_rows_read: int = 0
    non_trading_rows_dropped: int = 0


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _read_history(
    client: Any,
    tickers: list[str],
    *,
    start: date,
    end: date,
    page_size: int = _POSTGREST_MAX_ROWS,
) -> list[dict]:
    """Raw OHLCV rows for ``tickers`` in ``[start, end]`` (both bounds inclusive), paginated.

    Look-ahead-guarded (``.lte(end)``) so a recompute is reproducible for a back-dated run.

    **Paginated** because PostgREST caps a rangeless response at 1 000 rows. A single
    request over ~250 tickers × ~400 days returned the *oldest* 1 000 rows — roughly four
    bars per ticker, every one below :data:`MIN_BARS` — so the recompute silently processed
    nothing. ``.order("ticker").order("date")`` makes paging deterministic (a single-column
    date order leaves same-date rows free to shuffle between pages).
    """
    page_size = max(1, min(page_size, _POSTGREST_MAX_ROWS))
    # Safety valve: the window can hold at most one row per ticker per calendar day, so an
    # over-long loop means the client is not honouring `.range()` — stop rather than spin.
    span_days = (end - start).days + 1
    max_pages = math.ceil(max(1, len(tickers) * span_days) / page_size) + 2

    out: list[dict] = []
    offset = 0
    for _ in range(max_pages):
        resp = (
            client.table("price_history")
            .select(",".join(_OHLCV_COLUMNS))
            .in_("ticker", list(tickers))
            .lte("date", end.isoformat())
            .gte("date", start.isoformat())
            .order("ticker")
            .order("date")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = list(getattr(resp, "data", None) or [])
        out.extend(batch)
        if len(batch) < page_size:
            return out
        offset += page_size
    logger.warning(
        "refresh: price_history read hit the %d-page safety valve (%d rows) — window %s..%s",
        max_pages,
        len(out),
        start.isoformat(),
        end.isoformat(),
    )
    return out


def _frame_for_ticker(rows: list[dict]) -> pl.DataFrame:
    """Build the OHLCV frame ``compute_indicators`` expects (``timestamp`` + OHLCV).

    Sorted ascending on ``timestamp``: every rolling indicator assumes that order, and the
    paginated read must not be trusted to preserve it.
    """
    return (
        pl.DataFrame(
            {
                "timestamp": [str(r.get("date"))[:10] for r in rows],
                "open": [_to_float(r.get("open")) for r in rows],
                "high": [_to_float(r.get("high")) for r in rows],
                "low": [_to_float(r.get("low")) for r in rows],
                "close": [_to_float(r.get("close")) for r in rows],
                "volume": [_to_float(r.get("volume")) for r in rows],
            }
        )
        .with_columns(pl.col("timestamp").str.to_date(strict=False))
        .drop_nulls("timestamp")
        .sort("timestamp")
    )


def _resolve_trading_days(client: Any, tickers: list[str]) -> dict[str, pl.Series | None]:
    """Trading-day Series per ticker, fetched once per venue. Fail-soft → ``None``.

    ``price_history`` carries weekend/holiday bars for some tickers (crypto is genuinely
    24×7; several equity feeds carry stray non-session rows), and computing indicators over
    them fabricates sessions that never traded. ``cli/prices.py compute-technicals`` already
    applies this filter — a recompute that skipped it would write technicals the cron path
    would never produce.
    """
    by_venue: dict[str, pl.Series | None] = {}
    out: dict[str, pl.Series | None] = {}
    for ticker in tickers:
        venue = venue_for(ticker)
        if venue is None:
            logger.warning(
                "refresh: no venue mapping for %s — computing technicals on all rows", ticker
            )
            out[ticker] = None
            continue
        if venue not in by_venue:
            days = fetch_trading_days(client, venue)
            if days is None:
                logger.warning(
                    "refresh: no trading_calendar rows for venue %s — "
                    "computing technicals on all rows for its tickers",
                    venue,
                )
            elif days.dtype != pl.Date:
                days = days.cast(pl.Date)
            by_venue[venue] = days
        out[ticker] = by_venue[venue]
    return out


def recompute_technicals_from_history(
    *,
    client: Any,
    tickers: list[str] | tuple[str, ...],
    as_of: date,
    since: date | None = None,
    write_window_days: int = DEFAULT_WRITE_WINDOW_DAYS,
    warmup_days: int = WARMUP_CALENDAR_DAYS,
    dry_run: bool = False,
) -> RefreshResult:
    """Recompute + upsert ``price_technicals`` from ``price_history`` (≤ ``as_of``).

    Network-free and idempotent (upserts on ``(date, ticker)``). Non-session rows are
    dropped first, then a ticker with fewer than
    :data:`~digiquant.data.prices.technicals.MIN_BARS` bars is skipped. The caller decides
    whether to run this (it does I/O); errors propagate so the caller can fail-soft.

    Parameters
    ----------
    since:
        Earliest date to **write**. ``None`` → ``as_of − write_window_days``. Rows before it
        are still read, as warm-up context, but never upserted (see the module docstring).
    warmup_days:
        Calendar days of extra history read before the write floor.
    dry_run:
        Compute and report without writing. ``rows_upserted`` stays 0.
    """
    tickers = [t for t in dict.fromkeys(tickers) if t]  # dedupe, drop empties
    if not tickers:
        return RefreshResult(0, 0)

    write_start = since if since is not None else as_of - timedelta(days=max(0, write_window_days))
    read_start = write_start - timedelta(days=max(0, warmup_days))

    rows = _read_history(client, tickers, start=read_start, end=as_of)
    by_ticker: dict[str, list[dict]] = {}
    for row in rows:
        ticker = row.get("ticker")
        if isinstance(ticker, str):
            by_ticker.setdefault(ticker, []).append(row)

    trading_days = _resolve_trading_days(client, list(by_ticker))

    out_rows: list[dict] = []
    processed = 0
    dropped = 0
    for ticker, t_rows in by_ticker.items():
        frame = _frame_for_ticker(t_rows)
        venue_days = trading_days.get(ticker)
        if venue_days is not None and len(venue_days) > 0:
            before = frame.height
            frame = filter_rows_by_trading_days(frame, venue_days)
            dropped += before - frame.height
        if frame.height < MIN_BARS:
            continue
        indicators = compute_indicators(frame)
        keep = [c for c in TECHNICAL_COLUMNS if c in indicators.columns]
        # Write window only — warm-up rows would clobber good values with NULL (#1752).
        in_window = frame["timestamp"] >= write_start
        out_rows.extend(
            technicals_to_rows(
                indicators.select(keep).filter(in_window),
                ticker,
                frame["timestamp"].filter(in_window),
            )
        )
        processed += 1

    written = 0
    if not dry_run:
        written = upsert_price_technicals(client, out_rows).rows
    logger.info(
        "refresh: recomputed technicals for %d/%d tickers — %d rows in [%s..%s] "
        "(read %d bars from %s, dropped %d non-session, dry_run=%s)",
        processed,
        len(tickers),
        len(out_rows),
        write_start.isoformat(),
        as_of.isoformat(),
        len(rows),
        read_start.isoformat(),
        dropped,
        dry_run,
    )
    return RefreshResult(
        tickers_processed=processed,
        rows_upserted=written,
        rows_computed=len(out_rows),
        history_rows_read=len(rows),
        non_trading_rows_dropped=dropped,
    )


__all__ = [
    "DEFAULT_WRITE_WINDOW_DAYS",
    "WARMUP_CALENDAR_DAYS",
    "RefreshResult",
    "recompute_technicals_from_history",
]

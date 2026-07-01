"""`digiquant prices ...` subcommands.

Wraps :mod:`digiquant.data.prices` for the scheduled GitHub Action and for
local dev (``python -m digiquant prices …``).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import click
import polars as pl

_logger = logging.getLogger(__name__)

# Yahoo FX backfill origin — the ECB daily-rate series start. Previously sourced from the
# Frankfurter manifest field (removed with the Frankfurter source, #328); it was always this
# constant, so it's inlined here rather than re-introducing the dropped manifest field.
_YAHOO_FX_BACKFILL_START = "1999-01-04"


@click.group()
def prices() -> None:
    """Price / technicals / macro pipeline (migrated from Atlas scripts)."""


# ─── Trading-calendar helpers ─────────────────────────────────────────────


def _fetch_trading_days(client: Any, venue: str, *, page_size: int = 1000) -> pl.Series | None:
    """Fetch all trading days for ``venue`` from the ``trading_calendar`` table.

    Returns a :class:`polars.Series` of :class:`datetime.date` values for rows
    where ``is_trading_day=True``, or ``None`` on error.  Paginates automatically
    so callers are not limited by Supabase's default 1 000-row cap.

    ``page_size`` must be <= PostgREST's max-rows cap (1 000). A larger value
    silently returns only the first 1 000 rows, so ``len(batch) < page_size``
    is true on page 1 and pagination stops after one page — which previously
    yielded only the *oldest* 1 000 days and dropped every recent session from
    the technicals trading-day filter. ``.order("date")`` makes paging
    deterministic.
    """
    all_dates: list[date] = []
    offset = 0
    try:
        while True:
            resp = (
                client.table("trading_calendar")
                .select("date")
                .eq("venue", venue)
                .eq("is_trading_day", True)
                .order("date")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = resp.data or []
            for row in batch:
                raw = row.get("date")
                if raw:
                    all_dates.append(date.fromisoformat(str(raw)[:10]))
            if len(batch) < page_size:
                break
            offset += page_size
    except Exception as exc:  # noqa: BLE001
        _logger.warning("trading_calendar query failed for venue %s: %s", venue, exc)
        return None
    if not all_dates:
        return None
    return pl.Series("trading_days", all_dates)


# ─── fetch-quotes ────────────────────────────────────────────────────────


@prices.command("fetch-quotes")
@click.option(
    "--watchlist",
    type=click.Path(path_type=Path, exists=True),
    required=False,
    help="Path to watchlist.md (ETF rotation universe).",
)
@click.option(
    "--tickers", type=str, default="", help="Comma-separated tickers (overrides --watchlist)."
)
@click.option("--cache-dir", type=click.Path(path_type=Path), default=Path("data/price-history"))
@click.option("--period", type=str, default="3mo", help="yfinance period for uncached tickers.")
@click.option("--dry-run", is_flag=True, help="Synthesize fixture data; no network calls.")
@click.option("--supabase", is_flag=True, help="Upsert OHLCV to price_history.")
@click.option(
    "--include-sectors",
    is_flag=True,
    help=(
        "Union the sector config's ETFs + sub-segment + top single-name tickers into the "
        "universe, so sector research gets single-name technicals (price_technicals was "
        "ETF-only; #946). Use on a daily refresh, not the 15-min intraday job."
    ),
)
def fetch_quotes_cmd(
    watchlist: Path | None,
    tickers: str,
    cache_dir: Path,
    period: str,
    dry_run: bool,
    supabase: bool,
    include_sectors: bool,
) -> None:
    """Fetch latest OHLCV for watchlist tickers, update cache, optionally upsert."""
    from digiquant.data.prices.fetchers import parse_watchlist
    from digiquant.data.prices.history_cache import incremental_update
    from digiquant.data.prices.supabase_writer import (
        build_supabase_client,
        ohlcv_to_price_history_rows,
        upsert_price_history,
    )

    if tickers:
        universe = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    elif watchlist:
        universe = parse_watchlist(watchlist)
    else:
        raise click.UsageError("Provide --watchlist or --tickers.")

    if include_sectors:
        from digiquant.olympus.atlas.sectors_config import sector_universe

        present = {t.upper() for t in universe}
        for ticker in sector_universe():
            if ticker not in present:
                present.add(ticker)
                universe.append(ticker)

    click.echo(f"fetch-quotes: {len(universe)} tickers | dry_run={dry_run}")
    frames = incremental_update(universe, cache_dir=cache_dir, bulk_period=period, dry_run=dry_run)
    click.echo(f"  fetched: {len(frames)}")
    if dry_run and frames:
        first = next(iter(frames.values()))
        click.echo(f"  schema : {dict(first.schema)}")

    if supabase and not dry_run:
        client = build_supabase_client(
            os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL")),
            os.environ.get(
                "CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            ),
        )
        if client is None:
            raise click.ClickException("Supabase credentials not set.")
        # Accumulate all tickers' rows and upsert once — cuts per-ticker HTTP
        # overhead from O(N) round-trips to 1 (chunked internally by DEFAULT_CHUNK).
        all_rows: list[dict] = []
        for ticker, df in frames.items():
            all_rows.extend(ohlcv_to_price_history_rows(df, ticker))
        total = 0
        if all_rows:
            try:
                res = upsert_price_history(client, all_rows)
                total = res.rows
            except Exception as exc:  # noqa: BLE001
                _logger.warning("price_history upsert failed (non-fatal): %s", exc, exc_info=True)
                click.echo(f"  warning: upsert skipped — {exc}", err=True)
        click.echo(f"  upserted {total} rows into price_history")


# ─── compute-technicals ──────────────────────────────────────────────────


@prices.command("compute-technicals")
@click.option(
    "--tickers", type=str, default="", help="Comma-separated tickers. Empty = use all cached."
)
@click.option("--cache-dir", type=click.Path(path_type=Path), default=Path("data/price-history"))
@click.option(
    "--date",
    "target_date",
    type=str,
    default=None,
    help="Slice output to <= YYYY-MM-DD (default: full cache).",
)
@click.option(
    "--days", type=int, default=365, help="Keep only the last N indicator rows per ticker."
)
@click.option("--dry-run", is_flag=True, help="Compute but skip upsert.")
@click.option("--supabase", is_flag=True, help="Upsert to price_technicals.")
def compute_technicals_cmd(
    tickers: str, cache_dir: Path, target_date: str | None, days: int, dry_run: bool, supabase: bool
) -> None:
    """Compute 35+ indicators from cached OHLCV and optionally upsert."""
    from digiquant.data.prices.history_cache import load_cached
    from digiquant.data.prices.supabase_writer import (
        build_supabase_client,
        technicals_to_rows,
        upsert_price_technicals,
    )
    from digiquant.data.prices._utils import filter_rows_by_trading_days
    from digiquant.data.prices.technicals import MIN_BARS, compute_indicators
    from digiquant.data.prices.ticker_venues import venue_for

    if tickers:
        universe = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        # Scan cache_dir for <TICKER>.csv files.
        d = Path(cache_dir)
        if not d.exists():
            raise click.ClickException(f"Cache dir {d} does not exist — run fetch-quotes first.")
        universe = sorted({p.stem for p in d.glob("*.csv")})

    client = None
    if supabase and not dry_run:
        client = build_supabase_client(
            os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL")),
            os.environ.get(
                "CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            ),
        )
        if client is None:
            raise click.ClickException("Supabase credentials not set.")

    # Pre-fetch trading days per venue (once per venue, not once per ticker).
    # Only fetched when --supabase is active so local/dry-run paths stay fast.
    # Build ticker→venue map up front so the per-ticker loop avoids double lookup.
    venue_trading_days: dict[str, pl.Series | None] = {}
    ticker_venue: dict[str, str | None] = {}
    if client is not None:
        for t in universe:
            ticker_venue[t] = venue_for(t)
        for v in {v for v in ticker_venue.values() if v is not None}:
            days_series = _fetch_trading_days(client, v)
            if days_series is None:
                _logger.warning(
                    "No trading_calendar rows found for venue %s — "
                    "technicals will be computed on all rows for tickers in this venue",
                    v,
                )
            venue_trading_days[v] = days_series

    # Accumulate all tickers' indicator rows, then upsert once at the end —
    # cuts per-ticker HTTP round-trips to 1 (chunked by DEFAULT_CHUNK).
    all_rows: list[dict] = []
    for ticker in universe:
        df = load_cached(ticker, cache_dir)
        if df is None or df.height < MIN_BARS:
            click.echo(f"  skip {ticker:6s} (insufficient cache)")
            continue
        if target_date:
            # ``timestamp`` is often Datetime('μs') from the CSV cache; Polars no
            # longer coerces Datetime vs a python ``date``, so cast to Date for the
            # boundary comparison (sibling of the #608 is_in dtype fix).
            df = df.filter(df["timestamp"].cast(pl.Date) <= date.fromisoformat(target_date))

        # Resolve trading-days filter. Filter df *before* compute_indicators so
        # ind.height == df.height holds after the call (see assertion below).
        trading_days: pl.Series | None = None
        if venue_trading_days:
            venue = ticker_venue.get(ticker)
            if venue is not None:
                trading_days = venue_trading_days.get(venue)
            else:
                _logger.warning(
                    "No venue mapping for ticker %s — computing technicals on all rows",
                    ticker,
                )
        if trading_days is not None and "timestamp" in df.columns:
            if trading_days.dtype != pl.Date:
                trading_days = trading_days.cast(pl.Date)
            df = filter_rows_by_trading_days(df, trading_days)

        ind = compute_indicators(df)
        if days and ind.height > days:
            ind = ind.tail(days)
            ts_series = df["timestamp"].tail(days)
        else:
            if ind.height != df.height:
                # Defensive guard: compute_indicators preserves input length (NaN for
                # warm-up windows), but an upstream filter or future implementation change
                # could produce a different row count — align both sides to avoid a mismatch.
                n = min(ind.height, df.height)
                _logger.warning(
                    "compute_indicators(%s) row count mismatch: ind=%d df=%d — trimming to %d",
                    ticker,
                    ind.height,
                    df.height,
                    n,
                )
                ind = ind.tail(n)
                ts_series = df["timestamp"].tail(n)
            else:
                ts_series = df["timestamp"]
        rows = technicals_to_rows(ind, ticker, ts_series)
        all_rows.extend(rows)
        click.echo(f"  {ticker:6s} {len(rows):4d} indicator rows")

    total = 0
    if client is not None and all_rows:
        try:
            res = upsert_price_technicals(client, all_rows)
            total = res.rows
        except Exception as exc:  # noqa: BLE001
            _logger.warning("price_technicals upsert failed (non-fatal): %s", exc, exc_info=True)
            click.echo(f"  warning: upsert skipped — {exc}", err=True)
    if supabase and not dry_run:
        click.echo(f"  upserted {total} rows into price_technicals")


# ─── fetch-macro ─────────────────────────────────────────────────────────


@prices.command("fetch-macro")
@click.option(
    "--sources",
    type=str,
    default="fred,yahoo",
    help=(
        "Comma-separated subset of {fred,yahoo,fedprob}. "
        "Default = fred,yahoo. fedprob ingests free prediction-market "
        "Fed rate-decision odds (Kalshi + Polymarket)."
    ),
)
@click.option(
    "--manifest",
    type=click.Path(path_type=Path, exists=True),
    required=True,
    help="Path to macro_series.yaml.",
)
@click.option("--backfill", is_flag=True, help="Full historical backfill (slow).")
@click.option("--dry-run", is_flag=True)
@click.option("--supabase", is_flag=True)
def fetch_macro_cmd(
    sources: str, manifest: Path, backfill: bool, dry_run: bool, supabase: bool
) -> None:
    """Ingest macro series (FRED + Yahoo FX) into macro_series_observations."""
    from digiquant.data.prices.macro_ingest import (
        MacroManifest,
        dedupe_observation_rows,
        fetch_fred,
        fetch_fx_yahoo,
    )
    from digiquant.data.prices.supabase_writer import (
        build_supabase_client,
        upsert_macro_observations,
    )

    import concurrent.futures

    sources_set = {s.strip() for s in sources.split(",") if s.strip()}
    mani = MacroManifest.from_yaml(manifest)

    # Validate FRED creds up-front so --dry-run'd FRED fails fast before the
    # ThreadPoolExecutor spins up.
    fred_api_key: str | None = None
    if "fred" in sources_set:
        fred_api_key = os.environ.get("FRED_API_KEY", "").strip() or None
        if fred_api_key is None and not dry_run:
            raise click.ClickException("FRED_API_KEY required unless --dry-run")

    # Run the independent upstream fetchers in parallel. Each call is a
    # network-bound HTTP loop, so threads (not processes) are the right tool.
    from collections.abc import Callable

    tasks: dict[str, Callable[[], list[dict]]] = {}
    if "fred" in sources_set and fred_api_key is not None:
        fred_start = mani.fred_backfill_start if backfill else None
        key = fred_api_key  # bind for closure
        tasks["fred"] = lambda: fetch_fred(mani, key, start=fred_start)
    if "yahoo" in sources_set:
        # Yahoo FX backfill starts at the ECB series origin (1999-01-04). This was
        # previously read from the Frankfurter manifest field; Frankfurter was removed
        # as a source (#328) so the start date is inlined as the constant it always was.
        yh_start = _YAHOO_FX_BACKFILL_START if backfill else None
        tasks["yahoo"] = lambda: fetch_fx_yahoo(start=yh_start)
    if "fedprob" in sources_set:
        # Free prediction-market Fed rate-decision odds (Kalshi + Polymarket); daily snapshot,
        # fail-soft per source. No backfill (point-in-time odds). See fed_probabilities.py.
        from digiquant.data.prices.fed_probabilities import (
            fetch_fed_prob_kalshi,
            fetch_fed_prob_polymarket,
        )

        tasks["fedprob"] = lambda: [*fetch_fed_prob_kalshi(), *fetch_fed_prob_polymarket()]

    all_rows: list[dict] = []
    if tasks:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(tasks), 1)) as pool:
            futures = {pool.submit(fn): name for name, fn in tasks.items()}
            for fut in concurrent.futures.as_completed(futures):
                all_rows.extend(fut.result())

    all_rows = dedupe_observation_rows(all_rows)
    click.echo(f"macro ingest: {len(all_rows)} rows (sources={sorted(sources_set)})")

    if dry_run or not supabase:
        # Dry-run: print a compact summary by series
        summary: dict[str, int] = {}
        for r in all_rows:
            summary[r["series_id"]] = summary.get(r["series_id"], 0) + 1
        click.echo(json.dumps(summary, indent=2))
        return

    client = build_supabase_client(
        os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL")),
        os.environ.get("CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
    )
    if client is None:
        raise click.ClickException("Supabase credentials not set.")
    res = upsert_macro_observations(client, all_rows)
    click.echo(f"  upserted {res.rows} rows into macro_series_observations")


# ─── sync-calendar ───────────────────────────────────────────────────────


@prices.command("sync-calendar")
@click.option(
    "--venues",
    type=str,
    default="NYSE,NASDAQ,CRYPTO,FX",
    help="Comma-separated subset of {NYSE,NASDAQ,CRYPTO,FX}.",
)
@click.option(
    "--start",
    type=str,
    default="1950-01-01",
    help="ISO date — earliest day to populate (default 1950-01-01 per ADR-0013).",
)
@click.option(
    "--end",
    type=str,
    default="+5y",
    help="ISO date or relative offset (+5y, -30d, +18m, +12w).  Default +5y.",
)
@click.option("--dry-run", is_flag=True, help="Build rows but skip upsert; print summary.")
@click.option("--supabase", is_flag=True, help="Upsert to trading_calendar.")
def sync_calendar_cmd(venues: str, start: str, end: str, dry_run: bool, supabase: bool) -> None:
    """Backfill / refresh the trading_calendar table for one or more venues.

    Idempotent on ``(date, venue)`` — running twice produces zero net change.
    The first run after migration 025 populates the table for the full
    ``[start, end]`` range; subsequent daily runs are essentially no-ops aside
    from extending the future tail by one day.
    """
    from datetime import date as _date

    from digiquant.data.prices.calendar_sync import (
        ALL_VENUES,
        build_rows,
        parse_end_spec,
        upsert_trading_calendar,
    )
    from digiquant.data.prices.supabase_writer import build_supabase_client

    venue_list = [v.strip().upper() for v in venues.split(",") if v.strip()]
    if not venue_list:
        raise click.UsageError("--venues must list at least one venue")
    unknown = [v for v in venue_list if v not in ALL_VENUES]
    if unknown:
        raise click.UsageError(f"unknown venues: {unknown} (allowed: {list(ALL_VENUES)})")

    try:
        start_d = _date.fromisoformat(start)
    except ValueError as exc:
        raise click.UsageError(f"--start must be ISO YYYY-MM-DD ({exc})") from exc
    try:
        end_d = parse_end_spec(end)
    except ValueError as exc:
        raise click.UsageError(f"invalid --end: {exc}") from exc
    if end_d < start_d:
        raise click.UsageError(f"--end ({end_d}) must be on or after --start ({start_d})")

    click.echo(f"sync-calendar: venues={venue_list} {start_d} -> {end_d}")
    rows = build_rows(venue_list, start_d, end_d)
    summary: dict[str, int] = {}
    for r in rows:
        summary[r["venue"]] = summary.get(r["venue"], 0) + 1
    for v, n in sorted(summary.items()):
        click.echo(f"  {v:7s} {n:>7d} rows")

    if dry_run or not supabase:
        return

    client = build_supabase_client(
        os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL")),
        os.environ.get("CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
    )
    if client is None:
        raise click.ClickException("Supabase credentials not set.")
    written = upsert_trading_calendar(client, rows)
    click.echo(f"  upserted {written} rows into trading_calendar")


# ─── preload-history ─────────────────────────────────────────────────────


@prices.command("preload-history")
@click.option("--tickers", type=str, required=True, help="Comma-separated tickers.")
@click.option("--years", type=int, default=2, help="History span in years.")
@click.option("--cache-dir", type=click.Path(path_type=Path), default=Path("data/price-history"))
@click.option("--dry-run", is_flag=True)
def preload_history_cmd(tickers: str, years: int, cache_dir: Path, dry_run: bool) -> None:
    """Bulk-download history to the local CSV cache."""
    from digiquant.data.prices.history_cache import preload_history

    universe = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not universe:
        raise click.UsageError("--tickers must be non-empty")
    frames = preload_history(universe, cache_dir=cache_dir, period=f"{years}y", dry_run=dry_run)
    click.echo(f"preloaded {len(frames)} tickers into {cache_dir}")


__all__ = ["prices"]

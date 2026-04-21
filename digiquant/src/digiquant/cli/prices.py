"""`digiquant prices ...` subcommands.

Wraps :mod:`digiquant.data.prices` for the scheduled GitHub Action and for
local dev (``python -m digiquant prices …``).
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import click


@click.group()
def prices() -> None:
    """Price / technicals / macro pipeline (migrated from Atlas scripts)."""


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
def fetch_quotes_cmd(
    watchlist: Path | None,
    tickers: str,
    cache_dir: Path,
    period: str,
    dry_run: bool,
    supabase: bool,
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

    click.echo(f"fetch-quotes: {len(universe)} tickers | dry_run={dry_run}")
    frames = incremental_update(universe, cache_dir=cache_dir, bulk_period=period, dry_run=dry_run)
    click.echo(f"  fetched: {len(frames)}")
    if dry_run and frames:
        first = next(iter(frames.values()))
        click.echo(f"  schema : {dict(first.schema)}")

    if supabase and not dry_run:
        client = build_supabase_client(
            os.environ.get("SUPABASE_URL"),
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY"),
        )
        if client is None:
            raise click.ClickException("Supabase credentials not set.")
        total = 0
        for ticker, df in frames.items():
            rows = ohlcv_to_price_history_rows(df, ticker)
            if rows:
                res = upsert_price_history(client, rows)
                total += res.rows
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
    from digiquant.data.prices.technicals import MIN_BARS, compute_indicators

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
            os.environ.get("SUPABASE_URL"),
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY"),
        )
        if client is None:
            raise click.ClickException("Supabase credentials not set.")

    total = 0
    for ticker in universe:
        df = load_cached(ticker, cache_dir)
        if df is None or df.height < MIN_BARS:
            click.echo(f"  skip {ticker:6s} (insufficient cache)")
            continue
        if target_date:
            df = df.filter(df["timestamp"] <= date.fromisoformat(target_date))
        ind = compute_indicators(df)
        if days and ind.height > days:
            ind = ind.tail(days)
            ts_series = df["timestamp"].tail(days)
        else:
            ts_series = (
                df["timestamp"].tail(ind.height) if ind.height != df.height else df["timestamp"]
            )
        rows = technicals_to_rows(ind, ticker, ts_series)
        if client is not None and rows:
            res = upsert_price_technicals(client, rows)
            total += res.rows
        click.echo(f"  {ticker:6s} {len(rows):4d} indicator rows")

    if supabase and not dry_run:
        click.echo(f"  upserted {total} rows into price_technicals")


# ─── fetch-macro ─────────────────────────────────────────────────────────


@prices.command("fetch-macro")
@click.option(
    "--sources",
    type=str,
    default="fred,frankfurter,fng",
    help="Comma-separated subset of {fred,frankfurter,fng}.",
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
    """Ingest macro series (FRED, Frankfurter FX, Crypto FNG) into macro_series_observations."""
    from digiquant.data.prices.macro_ingest import (
        MacroManifest,
        dedupe_observation_rows,
        fetch_crypto_fng,
        fetch_frankfurter,
        fetch_fred,
    )
    from digiquant.data.prices.supabase_writer import (
        build_supabase_client,
        upsert_macro_observations,
    )

    sources_set = {s.strip() for s in sources.split(",") if s.strip()}
    mani = MacroManifest.from_yaml(manifest)
    all_rows: list[dict] = []

    if "fred" in sources_set:
        api_key = os.environ.get("FRED_API_KEY", "").strip()
        if not api_key and not dry_run:
            raise click.ClickException("FRED_API_KEY required unless --dry-run")
        if api_key:
            start = mani.fred_backfill_start if backfill else None
            all_rows.extend(fetch_fred(mani, api_key, start=start))
    if "frankfurter" in sources_set:
        start = mani.frankfurter_backfill_start if backfill else None
        all_rows.extend(fetch_frankfurter(mani, start=start))
    if "fng" in sources_set:
        all_rows.extend(fetch_crypto_fng(mani, backfill=backfill))

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
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY"),
    )
    if client is None:
        raise click.ClickException("Supabase credentials not set.")
    res = upsert_macro_observations(client, all_rows)
    click.echo(f"  upserted {res.rows} rows into macro_series_observations")


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

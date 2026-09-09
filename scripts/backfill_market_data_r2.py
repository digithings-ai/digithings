"""One-time backfill: Supabase market tables -> versioned R2 generations (#3780).

Reads via direct-PG ONLY (never PostgREST: every statement runs under the
authenticator role's 8s ``statement_timeout``), paginated by (ticker, date).
Resume-safe: generations already recorded in the manifest are skipped; every
object put goes through R2HistoryStore
(put -> get -> SHA compare -> registry -> pointer swap).

Key shapes are the REAL R2HistoryStore layouts (NOT a ``BACKFILL.parquet``
sentinel): ``market-data/price/{TICKER}/{as_of}.parquet`` via
:func:`generation_key` and ``market-data/macro/{SOURCE}__{SERIES}/{as_of}.parquet``
via :func:`macro_key`. Manifest dataset ids are normalized tickers for prices
(``datasets["SPY"]`` — the Task 4 read path looks up ``ticker`` verbatim first)
and ``{SOURCE}__{SERIES}`` for macro (the Task 4 macro path matches the
``latest`` pointer target against dataset ``object`` values, so the id is free).

Row counts are exact copies of the Supabase source: calendar-day gaps in a
generation are non-trading days (weekends/holidays), NOT missing data. The
parity gate (``scripts/check_r2_parity.py``) compares Supabase-vs-R2 row
counts, where the source is identical by construction.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.data.prices.r2_history import (  # noqa: E402
    MANIFEST_KEY,
    SOURCE_TABLE_MACRO,
    SOURCE_TABLE_PRICE,
    ArchiveVerifyError,
    R2HistoryStore,
    build_manifest,
    generation_key,
    latest_pointer_key,
    macro_key,
    macro_latest_pointer_key,
    normalize_ticker,
)
from digiquant.ops.checkpoint_archive import (  # noqa: E402
    R2_ACCESS_KEY_ENV,
    R2_ACCOUNT_ENV,
    R2_BUCKET_ENV,
    R2_SECRET_KEY_ENV,
    R2Backend,
)

PAGE_SIZE = 500
POSTGRES_URI_ENV = "MARKET_DATA_POSTGRES_URI"

FetchPage = Callable[[str, int, int], list[dict[str, Any]]]

PRICE_COLUMNS = ("date", "ticker", "open", "high", "low", "close", "volume")


def to_parquet_bytes(rows: list[dict[str, Any]], date_col: str = "date") -> bytes:
    """Encode row dicts as Snappy parquet bytes (Polars-only, never pandas).

    OHLCV numerics are normalized to Float64 (direct-PG yields ``Decimal`` for
    ``numeric`` columns, which the Task 4 indicator path cannot consume) and
    ``volume`` to Int64; the date column is cast to ``Date`` and sorted.
    """
    frame = pl.DataFrame(rows)
    for col in ("open", "high", "low", "close", "value"):
        if col in frame.columns:
            frame = frame.with_columns(pl.col(col).cast(pl.Float64, strict=False))
    if "volume" in frame.columns:
        frame = frame.with_columns(pl.col("volume").cast(pl.Int64, strict=False))
    frame = frame.with_columns(pl.col(date_col).cast(pl.Date)).sort(date_col)
    buf = io.BytesIO()
    frame.write_parquet(buf, compression="snappy")
    return buf.getvalue()


def backfill_ticker(
    ticker: str,
    fetch_page: FetchPage,
    store: Any,
    page_size: int = PAGE_SIZE,
    progress: Callable[[str], None] = print,
) -> int:
    """Copy one ticker's full history into a new sealed generation.

    Returns 1 when a generation was written, 0 when the generation for the
    fetched ``as_of`` was already in the manifest (resume-skip) or there were
    no rows. The ``latest`` pointer is swapped only after a verified put.
    """
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = fetch_page(ticker, offset, page_size)
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    if not rows:
        progress(f"skip: no rows for {ticker}")
        return 0
    as_of = max(str(r["date"]) for r in rows)
    key = generation_key(ticker, as_of)
    prefix = f"market-data/price/{normalize_ticker(ticker)}/"
    known = store.existing_generations(prefix)
    if key in known:
        progress(f"resume: {key} already present")
        return 0
    if known:
        progress(f"resume: {len(known)} generation(s) already present; writing {key}")
    payload = to_parquet_bytes(rows, date_col="date")
    store.put_generation(
        key,
        payload,
        SOURCE_TABLE_PRICE,
        {"ticker": normalize_ticker(ticker), "as_of": as_of},
        rows=len(rows),
    )
    store.swap_latest_pointer(latest_pointer_key(ticker), key)
    progress(f"wrote: {key} ({len(rows)} rows)")
    return 1


def backfill_macro(
    source: str,
    series: str,
    fetch_page: Callable[[int, int], list[dict[str, Any]]],
    store: Any,
    page_size: int = PAGE_SIZE,
    progress: Callable[[str], None] = print,
) -> int:
    """Copy one macro series' observations into a new sealed generation."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = fetch_page(offset, page_size)
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    if not rows:
        progress(f"skip: no observations for {source}/{series}")
        return 0
    as_of = max(str(r["obs_date"]) for r in rows)
    key = macro_key(source, series, as_of)
    prefix = f"market-data/macro/{source}__{series}/"
    known = store.existing_generations(prefix)
    if key in known:
        progress(f"resume: {key} already present")
        return 0
    if known:
        progress(f"resume: {len(known)} generation(s) already present; writing {key}")
    payload = to_parquet_bytes(rows, date_col="obs_date")
    store.put_generation(
        key,
        payload,
        SOURCE_TABLE_MACRO,
        {"source": source, "series": series, "as_of": as_of},
        rows=len(rows),
    )
    store.swap_latest_pointer(macro_latest_pointer_key(source, series), key)
    progress(f"wrote: {key} ({len(rows)} rows)")
    return 1


class R2StoreAdapter:
    """Production store seam: R2HistoryStore + a mutable manifest dict.

    ``existing_generations`` reads the manifest's dataset ``object`` values so
    resume decisions never list R2; ``put_generation`` registers the new
    dataset entry (price id = normalized ticker, macro id = ``SRC__SERIES``)
    after the verified put, before the caller swaps the pointer.
    """

    def __init__(self, store: R2HistoryStore, manifest: dict[str, Any]) -> None:
        self._store = store
        self._manifest = manifest

    def existing_generations(self, prefix: str) -> list[str]:
        datasets = self._manifest.get("datasets") or {}
        return sorted(
            str(entry["object"])
            for entry in datasets.values()
            if isinstance(entry, dict) and str(entry.get("object", "")).startswith(prefix)
        )

    def put_generation(
        self,
        key: str,
        payload: bytes,
        source_table: str,
        source_key: dict[str, Any] | None = None,
        rows: int = -1,
    ) -> Any:
        gen = self._store.put_generation(key, payload, source_table, source_key, rows=rows)
        datasets = self._manifest.setdefault("datasets", {})
        info = dict(source_key or {})
        if source_table == SOURCE_TABLE_MACRO:
            dataset_id = f"{info.get('source')}__{info.get('series')}"
        else:
            dataset_id = str(info.get("ticker", key))
        datasets[dataset_id] = {
            "object": gen.key,
            "sha256": gen.sha256,
            "rows": rows,
            "as_of": info.get("as_of", ""),
        }
        return gen

    def swap_latest_pointer(self, pointer_key: str, generation_key_: str) -> None:
        self._store.swap_latest_pointer(pointer_key, generation_key_)


def _pg_connect(uri: str) -> Any:
    """Open a direct Postgres connection; deferred import keeps unit installs lean."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "psycopg is required for direct Postgres reads (install the digiquant research extra)"
        ) from exc
    return psycopg.connect(uri)


def _dict_rows(conn: Any, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    try:
        from psycopg.rows import dict_row as _dict_row
    except ImportError:
        _dict_row = None  # type: ignore[assignment]
    kwargs = {"row_factory": _dict_row} if _dict_row is not None else {}
    cur = conn.cursor(**kwargs)
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        for col in ("date", "obs_date"):
            if col in row and row[col] is not None and not isinstance(row[col], str):
                row[col] = row[col].isoformat()
    return rows


def make_price_fetcher(uri: str, connect: Any = None) -> FetchPage:
    """``fetch_page(ticker, offset, limit)`` over direct-PG ``price_history``."""

    holder: dict[str, Any] = {}
    connector = connect or _pg_connect

    def fetch_page(ticker: str, offset: int, limit: int) -> list[dict[str, Any]]:
        if holder.get("conn") is None:
            holder["conn"] = connector(uri)
        return _dict_rows(
            holder["conn"],
            "SELECT date,ticker,open,high,low,close,volume FROM price_history "
            "WHERE ticker = %s ORDER BY date LIMIT %s OFFSET %s",
            (ticker, limit, offset),
        )

    return fetch_page


def make_macro_fetcher(uri: str, source: str, series: str, connect: Any = None) -> Any:
    """``fetch_page(offset, limit)`` over direct-PG ``macro_series_observations``."""

    holder: dict[str, Any] = {}
    connector = connect or _pg_connect

    def fetch_page(offset: int, limit: int) -> list[dict[str, Any]]:
        if holder.get("conn") is None:
            holder["conn"] = connector(uri)
        return _dict_rows(
            holder["conn"],
            "SELECT source,series_id,obs_date,value,unit FROM macro_series_observations "
            "WHERE source = %s AND series_id = %s ORDER BY obs_date LIMIT %s OFFSET %s",
            (source, series, limit, offset),
        )

    return fetch_page


def _pg_registry_insert(uri: str, connect: Any = None) -> Any:
    """Idempotent ``archive_objects`` insert over direct-PG (same-sha skip)."""
    connector = connect or _pg_connect
    holder: dict[str, Any] = {}

    def insert(
        source_table: str, source_key: dict[str, Any], r2_key: str, sha256: str, size: int
    ) -> None:
        if holder.get("conn") is None:
            holder["conn"] = connector(uri)
        conn = holder["conn"]
        cur = conn.cursor()
        cur.execute("SELECT sha256 FROM archive_objects WHERE r2_key = %s", (r2_key,))
        found = cur.fetchall()
        for (existing_sha,) in found:
            if existing_sha == sha256:
                return
            raise ArchiveVerifyError(f"archive pointer conflict for {r2_key}: existing row kept")
        cur.execute(
            "INSERT INTO archive_objects (source_table, source_key, r2_key, sha256, size)"
            " VALUES (%s, %s::jsonb, %s, %s, %s)",
            (source_table, json.dumps(source_key), r2_key, sha256, size),
        )
        conn.commit()

    return insert


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="config/watchlist.md")
    parser.add_argument("--tickers", default="", help="Comma-separated override.")
    parser.add_argument("--macro-series", action="append", default=[])
    parser.add_argument("--postgres-uri", default=os.environ.get(POSTGRES_URI_ENV, ""))
    parser.add_argument("--manifest-out", default="/tmp/market-data-manifest.json")
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from digiquant.data.prices.fetchers import parse_watchlist

    if args.tickers.strip():
        universe = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        universe = parse_watchlist(args.universe)
    print(f"universe: {len(universe)} tickers from {args.universe}")

    if args.dry_run:
        for ticker in universe:
            print(f"plan: {generation_key(ticker, '<max-date>')}")
        return 0
    if not args.postgres_uri:
        raise SystemExit(f"set --postgres-uri or ${POSTGRES_URI_ENV} (direct-PG only)")

    account = os.environ.get(R2_ACCOUNT_ENV, "").strip()
    bucket = os.environ.get(R2_BUCKET_ENV, "").strip()
    access = os.environ.get(R2_ACCESS_KEY_ENV, "").strip()
    secret = os.environ.get(R2_SECRET_KEY_ENV, "").strip()
    if not (account and bucket and access and secret):
        raise SystemExit("missing R2 credentials (R2_ACCOUNT_ID/R2_BUCKET/...)")
    backend = R2Backend(
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        bucket=bucket,
        access_key=access,
        secret_key=secret,
    )
    store = R2HistoryStore(backend, _pg_registry_insert(args.postgres_uri))
    try:
        manifest = store.read_manifest()
        print(f"loaded manifest {MANIFEST_KEY} as_of={manifest.get('as_of')}")
    except Exception as exc:
        print(f"no readable manifest ({type(exc).__name__}); starting fresh")
        manifest = build_manifest("1970-01-01", {})
    adapter = R2StoreAdapter(store, manifest)

    fetch_price = make_price_fetcher(args.postgres_uri)
    written = sum(
        backfill_ticker(t, fetch_price, adapter, page_size=args.page_size) for t in universe
    )
    for spec in args.macro_series:
        source, _, series = spec.partition(":")
        if not source or not series:
            raise SystemExit(f"--macro-series expects SOURCE:SERIES, got {spec!r}")
        written += backfill_macro(
            source, series, make_macro_fetcher(args.postgres_uri, source, series), adapter
        )
    datasets = manifest.get("datasets") or {}
    as_of = max((str(e.get("as_of", "")) for e in datasets.values()), default="1970-01-01")
    manifest.update(build_manifest(as_of, datasets))
    digest = store.write_manifest(manifest)
    Path(args.manifest_out).write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"wrote {written} generation(s); manifest sha={digest} -> {args.manifest_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

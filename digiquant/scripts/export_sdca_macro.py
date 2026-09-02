#!/usr/bin/env python3
"""Stage M2 / DXY CSVs next to the Coinbase OHLCV cache for published btc_sdca.

``generate_tearsheets.py`` loads extras via ``load_sdca_extra_sources(cache_dir)``.
Missing ``M2SL.csv`` / ``DTWEXBGS.csv`` silently zeros those weights, so the
nightly job would publish a different composite than ``settings.json``.

Sources (first hit wins per series):

1. Supabase ``macro_series_observations`` (service role) — already populated
   for DTWEXBGS by the prices pipeline
2. FRED observations API when ``FRED_API_KEY`` is set (same secret as the
   prices job)
3. FRED ``fredgraph.csv`` (no key) as a last resort

Usage:
    python digiquant/scripts/export_sdca_macro.py
    python digiquant/scripts/export_sdca_macro.py --cache-dir digiquant/data/price-history
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

import polars as pl

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = ROOT / "data" / "price-history"
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from _env import load_repo_env  # noqa: E402

# Filename ``load_sdca_extra_sources`` looks for next to BTC-USD.csv.
SERIES_FILES: dict[str, str] = {
    "M2SL": "M2SL.csv",
    "DTWEXBGS": "DTWEXBGS.csv",
}

FRED_GRAPH_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def write_observation_csv(rows: list[tuple[str, float]], dest: Path) -> Path:
    """Write FRED-shaped ``observation_date,SERIES`` CSV ``load_date_value_frame`` accepts."""
    if not rows:
        raise ValueError(f"refusing to write empty macro series to {dest}")
    series_col = dest.stem
    frame = pl.DataFrame(
        {
            "observation_date": [d for d, _ in rows],
            series_col: [v for _, v in rows],
        }
    ).sort("observation_date")
    dest.parent.mkdir(parents=True, exist_ok=True)
    frame.write_csv(dest)
    return dest


def rows_from_supabase(series_id: str) -> list[tuple[str, float]]:
    """Read ``macro_series_observations`` for ``series_id``. Empty if unset/unavailable."""
    url = (os.environ.get("CORE_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "").strip()
    key = (
        os.environ.get("CORE_SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
        or ""
    ).strip()
    if not url or not key:
        return []
    try:
        from supabase import create_client
    except ImportError:
        logger.warning("supabase package missing — skip DB source for %s", series_id)
        return []

    client = create_client(url, key)
    page_size = 1000
    start = 0
    out: list[tuple[str, float]] = []
    while True:
        resp = (
            client.table("macro_series_observations")
            .select("obs_date,value")
            .eq("series_id", series_id)
            .order("obs_date")
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = resp.data or []
        for row in batch:
            raw = row.get("value")
            day = row.get("obs_date")
            if day is None or raw is None:
                continue
            try:
                out.append((str(day)[:10], float(raw)))
            except (TypeError, ValueError):
                continue
        if len(batch) < page_size:
            break
        start += page_size
    return out


def rows_from_fred_api(series_id: str, api_key: str) -> list[tuple[str, float]]:
    from digiquant.data.prices.macro_ingest import fetch_fred_series

    observations = fetch_fred_series(api_key, series_id, observation_start="1959-01-01")
    rows: list[tuple[str, float]] = []
    for obs in observations:
        day = obs.get("date")
        raw = obs.get("value")
        if not day or raw in (None, ".", ""):
            continue
        try:
            rows.append((str(day)[:10], float(raw)))
        except (TypeError, ValueError):
            continue
    return rows


def rows_from_fredgraph(series_id: str, *, opener: Any | None = None) -> list[tuple[str, float]]:
    """Keyless FRED CSV export. ``opener`` is ``urlopen``-compatible for tests."""
    from urllib.parse import urlencode
    from urllib.request import urlopen

    fetch = opener or urlopen
    query = urlencode({"id": series_id})
    with fetch(f"{FRED_GRAPH_CSV}?{query}") as resp:
        body = resp.read()
    text = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)
    frame = pl.read_csv(text.encode("utf-8") if isinstance(text, str) else body)
    date_col = next(
        (c for c in ("observation_date", "DATE", "date") if c in frame.columns),
        None,
    )
    if date_col is None:
        raise ValueError(f"fredgraph.csv for {series_id} has no date column: {frame.columns}")
    value_col = next((c for c in (series_id, "value") if c in frame.columns), None)
    if value_col is None:
        numeric = [c for c in frame.columns if c != date_col]
        if len(numeric) != 1:
            raise ValueError(f"fredgraph.csv for {series_id} has no value column: {frame.columns}")
        value_col = numeric[0]
    rows: list[tuple[str, float]] = []
    for day, raw in zip(frame[date_col].to_list(), frame[value_col].to_list(), strict=True):
        if raw in (None, ".", "") or day is None:
            continue
        try:
            rows.append((str(day)[:10], float(raw)))
        except (TypeError, ValueError):
            continue
    return rows


def export_series(series_id: str, cache_dir: Path) -> tuple[Path, str, int]:
    """Write one series. Returns ``(path, source, row_count)``."""
    dest = cache_dir / SERIES_FILES[series_id]
    rows = rows_from_supabase(series_id)
    source = "supabase"
    if not rows:
        api_key = (os.environ.get("FRED_API_KEY") or "").strip()
        if api_key:
            rows = rows_from_fred_api(series_id, api_key)
            source = "fred_api"
    if not rows:
        rows = rows_from_fredgraph(series_id)
        source = "fredgraph"
    if not rows:
        raise RuntimeError(f"no observations for {series_id} from supabase, FRED API, or fredgraph")
    write_observation_csv(rows, dest)
    return dest, source, len(rows)


def main() -> None:
    load_repo_env()
    parser = argparse.ArgumentParser(description="Stage SDCA M2/DXY CSVs for tearsheet generate")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--series",
        default=",".join(SERIES_FILES),
        help="Comma-separated FRED series ids (default: M2SL,DTWEXBGS)",
    )
    args = parser.parse_args()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    wanted = [s.strip() for s in args.series.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in SERIES_FILES]
    if unknown:
        parser.error(f"unknown series {unknown}; known: {sorted(SERIES_FILES)}")
    for series_id in wanted:
        dest, source, n = export_series(series_id, args.cache_dir)
        logger.info("  %s: %d rows via %s → %s", series_id, n, source, dest)


if __name__ == "__main__":
    main()

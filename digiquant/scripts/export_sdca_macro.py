#!/usr/bin/env python3
"""Stage the M2SL CSV next to the Coinbase OHLCV cache for published btc_sdca.

``generate_tearsheets.py`` loads extras via ``load_sdca_extra_sources(cache_dir)``.
A missing ``M2SL.csv`` silently zeros that weight, so the nightly job would
publish a different composite than ``settings.json``.

Sources for M2SL (first hit wins):

1. Supabase ``macro_series_observations`` (service role) — existing rows
2. Sealed R2 ``fred__M2SL`` generation (no key; same bytes the panel refresh seals)

``DTWEXBGS`` is not on the gloomberb panel (dropped 2026-09-29, #4794 PR3), so
this script no longer touches the FRED observations API or fredgraph.csv. A
missing ``DTWEXBGS.csv`` makes the existing SDCA loader zero ``dxy_weight``
loudly via ``drop_extras_missing_sources``.

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
}

#: Legacy dollar sibling: not on the gloomberb panel, never fetched here.
DTWEXBGS_SKIP_MESSAGE = "DTWEXBGS is not on the gloomberb panel; dxy sibling CSV skipped"


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


def rows_from_r2(series_id: str) -> list[tuple[str, float]]:
    """Read the sealed R2 ``fred__{series_id}`` generation. Empty if unavailable."""
    from digiquant.data.prices.r2_history import MANIFEST_KEY
    from digiquant.ops.checkpoint_archive import (
        R2_ACCESS_KEY_ENV,
        R2_ACCOUNT_ENV,
        R2_BUCKET_ENV,
        R2_SECRET_KEY_ENV,
        R2Backend,
    )

    account = os.environ.get(R2_ACCOUNT_ENV, "").strip()
    bucket = os.environ.get(R2_BUCKET_ENV, "").strip()
    access = os.environ.get(R2_ACCESS_KEY_ENV, "").strip()
    secret = os.environ.get(R2_SECRET_KEY_ENV, "").strip()
    if not (account and bucket and access and secret):
        return []
    try:
        import hashlib
        import io
        import json

        backend = R2Backend(
            endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
            bucket=bucket,
            access_key=access,
            secret_key=secret,
        )
        manifest = json.loads(backend.get(MANIFEST_KEY).decode("utf-8"))
        entry = (manifest.get("datasets") or {}).get(f"fred__{series_id}")
        if not isinstance(entry, dict):
            return []
        raw = backend.get(str(entry["object"]))
        if hashlib.sha256(raw).hexdigest() != str(entry.get("sha256")):
            logger.warning("SHA mismatch reading R2 fred__%s — skip R2 source", series_id)
            return []
        frame = pl.read_parquet(io.BytesIO(raw))
        if "obs_date" not in frame.columns or "value" not in frame.columns:
            return []
        rows: list[tuple[str, float]] = []
        for day, value in zip(frame["obs_date"].to_list(), frame["value"].to_list(), strict=True):
            if day is None or value is None:
                continue
            try:
                rows.append((str(day)[:10], float(value)))
            except (TypeError, ValueError):
                continue
        return sorted(rows)
    except Exception:
        logger.warning("R2 read failed for fred__%s — skip R2 source", series_id, exc_info=True)
        return []


def export_series(series_id: str, cache_dir: Path) -> tuple[Path | None, str, int]:
    """Write one series. Returns ``(path, source, row_count)``.

    ``DTWEXBGS`` is not staged: one warning, zero rows, no file.
    """
    if series_id == "DTWEXBGS":
        logger.warning(DTWEXBGS_SKIP_MESSAGE)
        return None, "skipped", 0
    dest = cache_dir / SERIES_FILES[series_id]
    rows = rows_from_supabase(series_id)
    source = "supabase"
    if not rows:
        rows = rows_from_r2(series_id)
        source = "r2"
    if not rows:
        raise RuntimeError(f"no observations for {series_id} from supabase or sealed R2")
    write_observation_csv(rows, dest)
    return dest, source, len(rows)


def main() -> None:
    load_repo_env()
    parser = argparse.ArgumentParser(description="Stage SDCA M2 CSV for tearsheet generate")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--series",
        default=",".join(SERIES_FILES),
        help="Comma-separated series ids (default: M2SL). DTWEXBGS is skipped with a warning.",
    )
    args = parser.parse_args()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    wanted = [s.strip() for s in args.series.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in SERIES_FILES and s != "DTWEXBGS"]
    if unknown:
        parser.error(f"unknown series {unknown}; known: {sorted(SERIES_FILES)}")
    for series_id in wanted:
        dest, source, n = export_series(series_id, args.cache_dir)
        if dest is None:
            continue
        logger.info("  %s: %d rows via %s → %s", series_id, n, source, dest)


if __name__ == "__main__":
    main()

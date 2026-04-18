#!/usr/bin/env python3
"""
ingest_crypto_fng.py — Crypto Fear & Greed (Alternative.me) into macro_series_observations.

Usage:
  python3 scripts/ingest_crypto_fng.py --dry-run
  python3 scripts/ingest_crypto_fng.py --supabase
  python3 scripts/ingest_crypto_fng.py --supabase --backfill
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lib.macro_ingest import (  # noqa: E402
    connect_supabase,
    load_manifest,
    upsert_observations,
)

SOURCE = "crypto_fear_greed"
FNG_URL = "https://api.alternative.me/fng/"


def fetch_fng(limit: int) -> list[dict]:
    r = requests.get(FNG_URL, params={"limit": limit}, timeout=60)
    r.raise_for_status()
    body = r.json()
    data = body.get("data")
    return data if isinstance(data, list) else []


def rows_from_fng(entries: list[dict], series_value_id: str) -> list[dict]:
    rows: list[dict] = []
    for item in entries:
        try:
            ts = int(item.get("timestamp", 0))
        except (TypeError, ValueError):
            continue
        if ts <= 0:
            continue
        obs_date = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        raw_v = item.get("value")
        try:
            val = float(raw_v)
        except (TypeError, ValueError):
            continue
        cls = item.get("value_classification")
        meta: dict = {}
        if isinstance(cls, str) and cls:
            meta["classification"] = cls
        row: dict = {
            "source": SOURCE,
            "series_id": series_value_id,
            "obs_date": obs_date,
            "value": val,
            "unit": "index",
        }
        if meta:
            row["meta"] = meta
        rows.append(row)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest crypto Fear & Greed into Supabase")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--supabase", action="store_true")
    p.add_argument(
        "--backfill",
        action="store_true",
        help="Use manifest crypto_fear_greed.backfill_limit (default large history)",
    )
    args = p.parse_args()

    manifest = load_manifest()
    cfg = manifest.get("crypto_fear_greed") or {}
    series_value_id = str(cfg.get("series_value_id") or "FNG/value")
    backfill_limit = int(cfg.get("backfill_limit") or 3650)
    incremental_limit = 30

    limit = backfill_limit if args.backfill else incremental_limit

    sb = connect_supabase() if args.supabase else None
    if args.supabase and not sb:
        print("Supabase not configured", file=sys.stderr)
        return 1

    entries = fetch_fng(limit)
    rows = rows_from_fng(entries, series_value_id)
    if not rows:
        print("No FNG rows parsed")
        return 0

    rows.sort(key=lambda r: r["obs_date"])

    if args.dry_run:
        ds = [r["obs_date"] for r in rows]
        print(f"Total rows: {len(rows)} limit={limit} min={min(ds)} max={max(ds)}")
        return 0

    if not args.supabase or not sb:
        print("Use --supabase to upsert (or --dry-run to preview)", file=sys.stderr)
        return 1

    n = upsert_observations(sb, rows)
    print(f"Upserted {n} rows ({SOURCE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

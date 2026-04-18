#!/usr/bin/env python3
"""
ingest_fred.py — Fetch FRED series observations into macro_series_observations.

Requires: FRED_API_KEY (free from https://fred.stlouisfed.org/docs/api/api_key.html), or set in config/mcp.secrets.env
Env: SUPABASE_URL, SUPABASE_SERVICE_KEY for --supabase

Usage:
  python3 scripts/ingest_fred.py --dry-run
  python3 scripts/ingest_fred.py --supabase --incremental
  python3 scripts/ingest_fred.py --supabase --backfill
  python3 scripts/ingest_fred.py --dry-run --series DGS10
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lib.macro_ingest import (  # noqa: E402
    connect_supabase,
    iso_today,
    latest_obs_date,
    load_config_env,
    load_manifest,
    upsert_observations,
)

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"
SOURCE = "fred"
OVERLAP_DAYS = 14


def fetch_fred_series(
    api_key: str,
    series_id: str,
    observation_start: str,
    observation_end: str | None = None,
) -> list[dict]:
    params: dict = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start,
    }
    if observation_end:
        params["observation_end"] = observation_end
    r = requests.get(FRED_OBS_URL, params=params, timeout=120)
    r.raise_for_status()
    payload = r.json()
    return payload.get("observations") or []


def observations_to_rows(
    series_id: str,
    unit: str | None,
    title: str | None,
    observations: list[dict],
) -> list[dict]:
    rows: list[dict] = []
    for obs in observations:
        d = obs.get("date")
        raw = obs.get("value")
        if not d or raw in (None, ".", ""):
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        meta = {}
        if title:
            meta["title"] = title
        rs = obs.get("realtime_start")
        if rs:
            meta["realtime_start"] = rs
        row: dict = {
            "source": SOURCE,
            "series_id": series_id,
            "obs_date": d,
            "value": val,
            "unit": unit,
        }
        if meta:
            row["meta"] = meta
        rows.append(row)
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest FRED observations into Supabase")
    p.add_argument("--dry-run", action="store_true", help="Fetch and print stats only")
    p.add_argument("--supabase", action="store_true", help="Upsert to macro_series_observations")
    p.add_argument(
        "--incremental",
        action="store_true",
        help="From max(obs_date) per series minus overlap (default when --supabase without --backfill)",
    )
    p.add_argument(
        "--backfill",
        action="store_true",
        help="From manifest fred.backfill_start through today",
    )
    p.add_argument("--series", type=str, default="", help="Only this FRED series id")
    args = p.parse_args()

    load_config_env()

    if args.incremental and args.backfill:
        print("Use only one of --incremental or --backfill", file=sys.stderr)
        return 1

    use_incremental = args.incremental or (args.supabase and not args.backfill)

    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        print("FRED_API_KEY is required unless --dry-run", file=sys.stderr)
        return 1

    manifest = load_manifest()
    fred_cfg = manifest.get("fred") or {}
    series_list = fred_cfg.get("series") or []
    backfill_start = str(fred_cfg.get("backfill_start") or "1990-01-01")
    end = iso_today()

    entries: list[dict] = []
    for item in series_list:
        if not isinstance(item, dict):
            continue
        sid = item.get("id")
        if not sid:
            continue
        if args.series and sid != args.series:
            continue
        entries.append(item)

    if not entries:
        print("No FRED series to ingest (check manifest or --series)", file=sys.stderr)
        return 1

    sb = connect_supabase() if args.supabase else None
    if args.supabase and not sb:
        print("Supabase not configured (SUPABASE_URL + SUPABASE_SERVICE_KEY)", file=sys.stderr)
        return 1

    all_rows: list[dict] = []
    for item in entries:
        sid = item["id"]
        title = item.get("title")
        unit = item.get("unit")

        if args.backfill:
            start = backfill_start
        elif use_incremental and sb:
            last = latest_obs_date(sb, SOURCE, sid)
            if last:
                start = (datetime.strptime(last, "%Y-%m-%d").date() - timedelta(days=OVERLAP_DAYS)).isoformat()
            else:
                start = backfill_start
        else:
            start = backfill_start

        if args.dry_run and not api_key:
            print(f"  [dry-run, no key] would fetch {sid} from {start} to {end}")
            continue

        try:
            obs = fetch_fred_series(api_key, sid, start, end)
        except Exception as e:
            print(f"  ⚠️  {sid}: FRED request failed — {e}", file=sys.stderr)
            continue
        rows = observations_to_rows(sid, unit, title, obs)
        all_rows.extend(rows)
        print(f"  {sid}: {len(rows)} observations ({start} .. {end})")

    if args.dry_run and not api_key:
        print(f"Total rows (not fetched): manifest covers {len(entries)} series")
        return 0

    if not all_rows:
        print("No rows to upsert")
        return 0

    all_rows.sort(key=lambda r: (r["series_id"], r["obs_date"]))
    if args.dry_run:
        by_s: dict[str, list] = {}
        for r in all_rows:
            by_s.setdefault(r["series_id"], []).append(r["obs_date"])
        print(f"Total rows: {len(all_rows)}")
        for sid, dates in sorted(by_s.items()):
            print(f"  {sid}: min={min(dates)} max={max(dates)} n={len(dates)}")
        return 0

    if not args.supabase or not sb:
        print("Use --supabase to upsert (or --dry-run to preview)", file=sys.stderr)
        return 1

    n = upsert_observations(sb, all_rows)
    print(f"Upserted {n} rows into macro_series_observations ({SOURCE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

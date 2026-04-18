#!/usr/bin/env python3
"""
ingest_fx_frankfurter.py — Frankfurter (ECB) FX into macro_series_observations.

No API key. https://www.frankfurter.app/docs/

Usage:
  python3 scripts/ingest_fx_frankfurter.py --dry-run
  python3 scripts/ingest_fx_frankfurter.py --supabase
  python3 scripts/ingest_fx_frankfurter.py --supabase --backfill
"""

from __future__ import annotations

import argparse
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
    latest_obs_date_for_source,
    load_manifest,
    upsert_observations,
)

SOURCE = "frankfurter"
FRANKFURTER_BASE = "https://api.frankfurter.app"
OVERLAP_DAYS = 7


def fetch_range(start: str, end: str, base: str, symbols: list[str]) -> dict:
    url = f"{FRANKFURTER_BASE}/{start}..{end}"
    to_param = ",".join(symbols)
    r = requests.get(
        url,
        params={"from": base, "to": to_param},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def payload_to_rows(
    payload: dict,
    base: str,
    symbols: list[str],
    date_min: str,
    date_max: str,
) -> list[dict]:
    """Frankfurter often returns one extra day outside the requested range at year boundaries."""
    rates = payload.get("rates") or {}
    rows: list[dict] = []
    for obs_date, day_rates in sorted(rates.items()):
        if obs_date < date_min or obs_date > date_max:
            continue
        if not isinstance(day_rates, dict):
            continue
        for sym in symbols:
            raw = day_rates.get(sym)
            if raw is None:
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "source": SOURCE,
                    "series_id": f"FX/{sym}",
                    "obs_date": obs_date,
                    "value": val,
                    "unit": "fx",
                    "meta": {"base": base, "quote": sym},
                }
            )
    return rows


def iter_year_chunks(start_d: date, end_d: date):
    y = start_d.year
    while True:
        chunk_start = max(start_d, date(y, 1, 1))
        chunk_end = min(end_d, date(y, 12, 31))
        if chunk_start <= chunk_end:
            yield chunk_start.isoformat(), chunk_end.isoformat()
        if chunk_end >= end_d:
            break
        y += 1


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest Frankfurter FX into Supabase")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--supabase", action="store_true")
    p.add_argument("--backfill", action="store_true", help="Year-chunk history from manifest backfill_start")
    args = p.parse_args()

    use_incremental = args.supabase and not args.backfill

    manifest = load_manifest()
    ff = manifest.get("frankfurter") or {}
    base = str(ff.get("base") or "USD")
    symbols = ff.get("symbols") or ["EUR", "GBP", "JPY", "CAD"]
    if not isinstance(symbols, list):
        symbols = ["EUR", "GBP", "JPY", "CAD"]
    backfill_start = str(ff.get("backfill_start") or "1999-01-04")

    sb = connect_supabase() if args.supabase else None
    if args.supabase and not sb:
        print("Supabase not configured", file=sys.stderr)
        return 1

    end_d = date.fromisoformat(iso_today())
    if args.backfill:
        start_d = date.fromisoformat(backfill_start[:10])
    elif use_incremental and sb:
        last = latest_obs_date_for_source(sb, SOURCE)
        if last:
            start_d = date.fromisoformat(last) - timedelta(days=OVERLAP_DAYS)
        else:
            start_d = date.fromisoformat(backfill_start[:10])
    else:
        start_d = date.fromisoformat(backfill_start[:10])

    if start_d > end_d:
        print("Nothing to fetch (start after end)")
        return 0

    # Fast local preview: avoid multi-year Frankfurter calls unless backfill or DB incremental.
    if args.dry_run and not args.backfill and not use_incremental:
        start_d = max(start_d, end_d - timedelta(days=120))

    all_rows: list[dict] = []
    for s, e in iter_year_chunks(start_d, end_d):
        print(f"  Fetch {s} .. {e} base={base} …")
        payload = fetch_range(s, e, base, symbols)
        rows = payload_to_rows(payload, base, symbols, s, e)
        all_rows.extend(rows)
        print(f"    -> {len(rows)} row fragments")

    if not all_rows:
        print("No FX rows parsed")
        return 0

    all_rows.sort(key=lambda r: (r["series_id"], r["obs_date"]))

    if args.dry_run:
        by_s: dict[str, list] = {}
        for r in all_rows:
            by_s.setdefault(r["series_id"], []).append(r["obs_date"])
        print(f"Total rows: {len(all_rows)}")
        for sid in sorted(by_s):
            ds = by_s[sid]
            print(f"  {sid}: min={min(ds)} max={max(ds)} n={len(ds)}")
        return 0

    if not args.supabase or not sb:
        print("Use --supabase to upsert (or --dry-run to preview)", file=sys.stderr)
        return 1

    n = upsert_observations(sb, all_rows)
    print(f"Upserted {n} rows ({SOURCE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

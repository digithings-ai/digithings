#!/usr/bin/env python3
"""Standalone per-position attribution refresh (Pillar 3B, #726).

Computes the single-benchmark attribution decomposition for one date and upserts it to
``position_attribution``: reads the booked ``positions`` weights, each holding's trailing-
window return + the benchmark's return from ``price_history``, runs the pure
:func:`digiquant.olympus.atlas.attribution.compute_position_attribution`, and writes the
rows. Decoupled from the research pipeline so it can run on its own daily cron after EOD
prices land. Idempotent (upsert on ``(date, ticker)``).

A dedicated script (vs. wedging into ``refresh_performance_metrics.py``) keeps the
attribution path importable + unit-testable and gives it a clean cron entry, mirroring
``resolve_decisions.py``.

Usage::

    python digiquant/scripts/atlas/refresh_attribution.py [--date YYYY-MM-DD] [--window-days N]

Env: ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY``. Reads positions + price_history,
writes position_attribution (migration 040 must be applied). Exit 0 = clean (no positions
for the date is success); 1 = hard failure; 2 = bad ``--date``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any  # noqa  # scored-lint: duck-typed Supabase client + rows

# repo root: .../digiquant/scripts/atlas/refresh_attribution.py → up 4 (atlas → scripts →
# digiquant → repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_DEFAULT_WINDOW_DAYS = 21
_BENCHMARK = "SPY"


def _ensure_importable() -> None:
    for rel in ("digiquant/src", "digigraph/src", "digibase/src", "digismith/src"):
        path = str(_REPO_ROOT / rel)
        if path not in sys.path:
            sys.path.insert(0, path)


def _parse_date(value: str | None) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.now(timezone.utc).date()


def _opt_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _window_return(client: Any, ticker: str, start_iso: str, end_iso: str) -> float | None:
    """Return over ``[start_iso, end_iso]`` from price_history (latest/earliest − 1).

    Look-ahead-guarded (``.lte(end)``). ``None`` when fewer than two closes are available.
    """
    resp = (
        client.table("price_history")
        .select("date,close")
        .eq("ticker", ticker)
        .gte("date", start_iso)
        .lte("date", end_iso)
        .order("date", desc=False)
        .limit(400)
        .execute()
    )
    closes = [
        c for c in (_opt_float(r.get("close")) for r in (getattr(resp, "data", None) or [])) if c
    ]
    if len(closes) < 2 or closes[0] <= 0:
        return None
    return closes[-1] / closes[0] - 1.0


def refresh_attribution(
    *,
    client: Any,
    as_of: date,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    benchmark: str = _BENCHMARK,
) -> tuple[int, bool]:
    """Compute + upsert attribution rows for ``as_of``. Returns (rows_written, reconciles)."""
    from digiquant.olympus.atlas.attribution import (
        Holding,
        attribution_rows_to_records,
        compute_position_attribution,
    )

    date_str = as_of.isoformat()
    start_iso = (as_of - timedelta(days=window_days)).isoformat()

    pos_resp = (
        client.table("positions")
        .select("ticker,weight_pct,sector_bucket")
        .eq("date", date_str)
        .execute()
    )
    holdings_raw = [
        row
        for row in (getattr(pos_resp, "data", None) or [])
        if isinstance(row.get("ticker"), str) and row["ticker"].strip().upper() != "CASH"
    ]
    if not holdings_raw:
        return 0, True  # no holdings (all-cash / no book) → nothing to attribute

    benchmark_return = _window_return(client, benchmark, start_iso, date_str)
    if benchmark_return is None:
        return 0, False  # no benchmark window yet → skip; the next run retries

    holdings = [
        Holding(
            ticker=row["ticker"],
            weight_frac=(_opt_float(row.get("weight_pct")) or 0.0) / 100.0,
            return_frac=_window_return(client, row["ticker"], start_iso, date_str),
            sector_bucket=row.get("sector_bucket"),
        )
        for row in holdings_raw
    ]
    result = compute_position_attribution(holdings=holdings, benchmark_return_frac=benchmark_return)
    records = attribution_rows_to_records(result, date_str=date_str)
    for record in records:
        client.table("position_attribution").upsert(record, on_conflict="date,ticker").execute()
    return len(records), result.reconciles


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh per-position attribution for a date.")
    parser.add_argument(
        "--date", default=None, help="Attribution date YYYY-MM-DD (default: today UTC)."
    )
    parser.add_argument(
        "--window-days", type=int, default=_DEFAULT_WINDOW_DAYS, help="Trailing return window."
    )
    args = parser.parse_args(argv)

    try:
        as_of = _parse_date(args.date)
    except ValueError:
        print(f"error: bad --date {args.date!r} (expected YYYY-MM-DD)", file=sys.stderr)
        return 2

    _ensure_importable()
    from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client

    try:
        client = build_client(SupabaseConfig.from_env())
    except Exception as exc:  # noqa: BLE001 — a config/connectivity failure is a hard error
        print(f"error: Supabase client unavailable: {exc}", file=sys.stderr)
        return 1

    try:
        written, reconciles = refresh_attribution(
            client=client, as_of=as_of, window_days=max(1, args.window_days)
        )
    except Exception as exc:  # noqa: BLE001 — surface a hard failure as a non-zero exit
        print(f"error: refresh_attribution failed: {exc}", file=sys.stderr)
        return 1

    flag = "reconciles" if reconciles else "PARTIAL (some holding unpriced)"
    print(f"refresh_attribution: wrote {written} row(s) for {as_of.isoformat()} — {flag}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

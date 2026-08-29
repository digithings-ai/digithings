#!/usr/bin/env python3
"""Standalone current-book lookback refresh (Pillar 3B, #726 / #2598).

Computes the single-benchmark trailing-window diagnostic for one date and upserts it to
``current_book_lookback``: reads the booked ``positions`` weights, each holding's trailing-
window return + the benchmark's return from ``price_history``, runs the pure
:func:`digiquant.olympus.atlas.attribution.compute_current_book_lookback`, and writes the
rows. Decoupled from the research pipeline so it can run on its own daily cron after EOD
prices land. Idempotent (upsert on ``(date, ticker)``).

**Contract (#2598 / OLY-REV-007):** this job is diagnostic-only. It must never populate
daily realized contribution / ``pnl_pct`` fields. Realized period contribution comes from
finalized accounting (``daily_realized_attribution``). Metrics/lookback job order is
irrelevant for daily semantics.

Usage::

    python digiquant/scripts/atlas/refresh_attribution.py [--date YYYY-MM-DD] [--window-days N]

Env: ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY``. Reads positions + price_history,
writes current_book_lookback (migrations 040 + 073 must be applied). Exit 0 = clean (no
positions for the date is success); 1 = hard failure; 2 = bad ``--date``.
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any  # score:allow untyped any — scored-lint: duck-typed Supabase client + rows

# repo root: .../digiquant/scripts/atlas/refresh_attribution.py → up 4 (atlas → scripts →
# digiquant → repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_DEFAULT_WINDOW_DAYS = 21
_BENCHMARK = "SPY"
_LOOKBACK_TABLE = "current_book_lookback"


def _ensure_importable() -> None:
    for rel in ("digiquant/src", "digigraph/src", "digibase/src", "digismith/src"):
        path = str(_REPO_ROOT / rel)
        if path not in sys.path:
            sys.path.insert(0, path)


def _parse_date(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return datetime.now(timezone.utc).date()


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None  # reject NaN/inf (e.g. Postgres numeric 'NaN')


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
    # Keep 0.0 (only drop None) so a bad non-positive close at either end trips the guard
    # below rather than being silently skipped (which would compute a return off wrong rows).
    closes = [
        c
        for c in (_opt_float(r.get("close")) for r in (getattr(resp, "data", None) or []))
        if c is not None
    ]
    if len(closes) < 2 or closes[0] <= 0 or closes[-1] <= 0:
        return None
    return closes[-1] / closes[0] - 1.0


def refresh_attribution(
    *,
    client: Any,
    as_of: date,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    benchmark: str = _BENCHMARK,
) -> tuple[int, bool]:
    """Compute + upsert lookback rows for ``as_of``. Returns (rows_written, reconciles).

    Writes only to ``current_book_lookback``. Never writes daily realized contribution.
    """
    from digiquant.olympus.atlas.attribution import (
        Holding,
        compute_current_book_lookback,
        lookback_rows_to_records,
    )

    date_str = as_of.isoformat()
    lookback_days = max(1, window_days)
    start_iso = (as_of - timedelta(days=lookback_days)).isoformat()

    pos_resp = (
        client.table("positions")
        .select("ticker,weight_pct,sector_bucket")
        .eq("date", date_str)
        .execute()
    )
    pos_rows = getattr(pos_resp, "data", None) or []
    if not pos_rows:
        return 0, True  # the date was never materialized → genuine no-op
    # An all-cash day (only a CASH row) still gets a CASH lookback row: drop CASH here and
    # let the core emit it from the cash residual (holdings=[]).
    holdings_raw = [
        row
        for row in pos_rows
        if isinstance(row.get("ticker"), str) and row["ticker"].strip().upper() != "CASH"
    ]

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
    result = compute_current_book_lookback(
        holdings=holdings, benchmark_return_frac=benchmark_return
    )
    records = lookback_rows_to_records(
        result,
        date_str=date_str,
        window_start_date=start_iso,
        window_end_date=date_str,
        lookback_days=lookback_days,
    )
    _upsert_lookback(client, records)
    return len(records), result.reconciles


def _upsert_lookback(client: Any, records: list[dict[str, Any]]) -> None:
    """Bulk-upsert lookback rows; fall back to per-row for clients whose upsert is singular."""
    if not records:
        return
    try:
        client.table(_LOOKBACK_TABLE).upsert(records, on_conflict="date,ticker").execute()
    except (TypeError, ValueError, AttributeError):
        for record in records:
            client.table(_LOOKBACK_TABLE).upsert(record, on_conflict="date,ticker").execute()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh current-book lookback diagnostic for a date (not realized period attribution)."
        )
    )
    parser.add_argument(
        "--date", default=None, help="Lookback as-of date YYYY-MM-DD (default: today UTC)."
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=_DEFAULT_WINDOW_DAYS,
        help="Trailing return window in calendar days (diagnostic only).",
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
    except Exception as exc:
        print(f"error: Supabase client unavailable: {exc}", file=sys.stderr)
        return 1

    try:
        written, reconciles = refresh_attribution(
            client=client, as_of=as_of, window_days=max(1, args.window_days)
        )
    except Exception as exc:
        print(f"error: refresh_attribution failed: {exc}", file=sys.stderr)
        return 1

    flag = "reconciles" if reconciles else "PARTIAL (some holding unpriced)"
    print(
        f"refresh_attribution: wrote {written} current_book_lookback row(s) "
        f"for {as_of.isoformat()} — {flag}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

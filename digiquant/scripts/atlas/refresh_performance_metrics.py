#!/usr/bin/env python3
"""
refresh_performance_metrics.py

Run after price_history (and optionally price_technicals) are updated for the day.
Uses Supabase price_history closes + positions snapshot rows to populate:

  - positions: unrealized_pnl_pct, day_change_pct, since_entry_return_pct,
    contribution_pct, metrics_as_of
  - position_events: cumulative_return_since_event_pct (where price exists)
  - nav_history: one indexed NAV point per calendar day (uses forward-filled prices)
  - portfolio_metrics: one row per calendar day for continuity (computed_from=refresh_script).
    Rows from update_tearsheet.py (computed_from=tearsheet) are never overwritten.

Daily pipeline policy (--fill-calendar-through):
  Refreshes the latest existing positions date, then for each calendar day until the
  target date: clones the prior day's positions if missing (carry-forward), recomputes
  per-position metrics, NAV, and a portfolio_metrics row so timelines stay dense even
  when no digest ran.

Does not replace update_tearsheet.py NAV simulation history; it aligns end-of-day
metrics with stored closes so the dashboard matches market data.

Usage:
  python3 scripts/refresh_performance_metrics.py --supabase
  python3 scripts/refresh_performance_metrics.py --supabase --date YYYY-MM-DD
  python3 scripts/refresh_performance_metrics.py --supabase --fill-calendar-through YYYY-MM-DD
Environment: SUPABASE_URL, SUPABASE_SERVICE_KEY (see config/supabase.env)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

_POSITION_INSERT_SKIP = frozenset({"id", "created_at", "updated_at"})
_METRIC_CLEAR = (
    "unrealized_pnl_pct",
    "day_change_pct",
    "since_entry_return_pct",
    "contribution_pct",
    "metrics_as_of",
)

try:
    from supabase import create_client  # type: ignore

    _HAS_SB = True
except ImportError:
    _HAS_SB = False

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

from position_entry_from_events import patch_positions_entries_for_date


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def _fetch_closes(sb, ticker: str, dates: List[str]) -> Dict[str, float]:
    """date -> close for ticker for given ISO dates (best effort)."""
    if not dates:
        return {}
    res = (
        sb.table("price_history")
        .select("date, close")
        .eq("ticker", ticker)
        .in_("date", dates)
        .execute()
    )
    out: Dict[str, float] = {}
    for row in getattr(res, "data", None) or []:
        d = row.get("date")
        c = row.get("close")
        if d and c is not None:
            out[str(d)[:10]] = float(c)
    return out


def _max_positions_date(sb) -> Optional[date]:
    r = sb.table("positions").select("date").order("date", desc=True).limit(1).execute()
    data = getattr(r, "data", None) or []
    if not data:
        return None
    return datetime.strptime(str(data[0]["date"])[:10], "%Y-%m-%d").date()


def carry_forward_positions(sb, as_of: str) -> int:
    """If no rows exist for ``as_of``, clone the latest prior day's positions.

    Weights and static fields carry forward; performance fields are cleared and
    filled by ``refresh_positions_metrics``. Returns rows inserted (0 if skipped).
    """
    probe = sb.table("positions").select("ticker").eq("date", as_of).limit(1).execute()
    if getattr(probe, "data", None):
        return 0
    snap = (
        sb.table("positions")
        .select("date")
        .lt("date", as_of)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    snap_data = getattr(snap, "data", None) or []
    if not snap_data:
        print(f"⚠️  carry_forward {as_of}: no prior positions snapshot")
        return 0
    prev = str(snap_data[0]["date"])[:10]
    res = sb.table("positions").select("*").eq("date", prev).execute()
    rows: List[Dict[str, Any]] = getattr(res, "data", None) or []
    if not rows:
        return 0
    inserts: List[Dict[str, Any]] = []
    for r in rows:
        row = {k: v for k, v in r.items() if k not in _POSITION_INSERT_SKIP}
        row["date"] = as_of
        for k in _METRIC_CLEAR:
            row[k] = None
        inserts.append(row)
    CHUNK = 500
    for i in range(0, len(inserts), CHUNK):
        sb.table("positions").upsert(inserts[i : i + CHUNK], on_conflict="date,ticker").execute()
    print(f"✅ positions {as_of}: carried forward {len(inserts)} row(s) from {prev}")
    return len(inserts)


def upsert_portfolio_metrics_daily(sb, as_of: str) -> None:
    """Ensure one ``portfolio_metrics`` row per calendar day (dashboard continuity).

    Skips if a ``tearsheet`` row already exists for ``as_of``. Otherwise upserts
    with ``computed_from='refresh_script'``: ``pnl_pct`` from ``nav_history``,
    cash / invested from positions, and sharpe/vol/max_dd/alpha copied from the
    previous metrics row until update_tearsheet recomputes them.
    """
    ex = sb.table("portfolio_metrics").select("computed_from").eq("date", as_of).limit(1).execute()
    if getattr(ex, "data", None) and ex.data[0].get("computed_from") == "tearsheet":
        print(f"   portfolio_metrics {as_of}: skip (tearsheet row)")
        return
    nav_res = sb.table("nav_history").select("nav").eq("date", as_of).limit(1).execute()
    nav_data = getattr(nav_res, "data", None) or []
    nav = float(nav_data[0]["nav"]) if nav_data else None

    pos_res = sb.table("positions").select("ticker", "weight_pct").eq("date", as_of).execute()
    prow = getattr(pos_res, "data", None) or []
    cash_pct: Optional[float] = None
    total_invested = 0.0
    for p in prow:
        t = p.get("ticker")
        w = float(p.get("weight_pct") or 0)
        if t == "CASH":
            cash_pct = w
        elif t:
            total_invested += w
    if cash_pct is None and prow:
        cash_pct = max(0.0, 100.0 - total_invested)

    prev_m = (
        sb.table("portfolio_metrics")
        .select("sharpe", "volatility", "max_drawdown", "alpha")
        .lt("date", as_of)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    pmd = getattr(prev_m, "data", None) or []
    prev = pmd[0] if pmd else {}

    ts = datetime.utcnow().isoformat() + "Z"
    row = {
        "date": as_of,
        "pnl_pct": round(nav - 100.0, 4) if nav is not None else None,
        "sharpe": prev.get("sharpe"),
        "volatility": prev.get("volatility"),
        "max_drawdown": prev.get("max_drawdown"),
        "alpha": prev.get("alpha"),
        "cash_pct": round(cash_pct, 4) if cash_pct is not None else None,
        "total_invested": round(total_invested, 4) if prow else None,
        "computed_from": "refresh_script",
        "as_of_date": as_of,
        "generated_at": ts,
    }
    sb.table("portfolio_metrics").upsert(row, on_conflict="date").execute()
    print(f"✅ portfolio_metrics {as_of}: upserted (refresh_script)")


def _prev_trading_date(sb, ref_ticker: str, as_of: str) -> Optional[str]:
    """Latest price_history date strictly before as_of for ref_ticker."""
    res = (
        sb.table("price_history")
        .select("date")
        .eq("ticker", ref_ticker)
        .lt("date", as_of)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    data = getattr(res, "data", None) or []
    if not data:
        return None
    return str(data[0]["date"])[:10]


def refresh_positions_metrics(sb, metrics_date: str) -> int:
    """Update positions for date == metrics_date. Returns rows updated."""
    patched = patch_positions_entries_for_date(sb, metrics_date)
    if patched:
        print(f"   entry_price filled from position_events: {patched} row(s)")
    res = (
        sb.table("positions")
        .select("*")
        .eq("date", metrics_date)
        .execute()
    )
    rows: List[Dict[str, Any]] = getattr(res, "data", None) or []
    prev_d = _prev_trading_date(sb, "SPY", metrics_date)
    if not prev_d:
        print("⚠️  No prior trading day in price_history — skip day_change_pct")
    updated = 0
    for r in rows:
        t = r.get("ticker")
        if not t or t == "CASH":
            continue
        entry = r.get("entry_price")
        entry_dt = r.get("entry_date")
        w = float(r.get("weight_pct") or 0)
        dates_needed = [metrics_date]
        if prev_d:
            dates_needed.append(prev_d)
        if entry_dt:
            dates_needed.append(str(entry_dt)[:10])
        closes = _fetch_closes(sb, t, list(set(dates_needed)))
        c_now = closes.get(metrics_date)
        c_prev = closes.get(prev_d) if prev_d else None
        day_ch = None
        if c_now is not None and c_prev is not None and c_prev > 0:
            day_ch = (c_now - c_prev) / c_prev * 100.0
        unreal = None
        since = None
        if entry and c_now and float(entry) > 0:
            unreal = (c_now - float(entry)) / float(entry) * 100.0
        if entry_dt and c_now:
            ed = str(entry_dt)[:10]
            c_entry = closes.get(ed)
            if c_entry is None:
                c_entry_map = _fetch_closes(sb, t, [ed])
                c_entry = c_entry_map.get(ed)
            if c_entry and c_entry > 0:
                since = (c_now - c_entry) / c_entry * 100.0
        contrib = None
        if since is not None:
            contrib = w * (since / 100.0)
        patch = {
            "unrealized_pnl_pct": unreal,
            "day_change_pct": day_ch,
            "since_entry_return_pct": since,
            "contribution_pct": contrib,
            "metrics_as_of": metrics_date,
            "current_price": c_now if c_now is not None else r.get("current_price"),
        }
        sb.table("positions").update(patch).eq("date", metrics_date).eq("ticker", t).execute()
        updated += 1
    return updated


def refresh_event_cumulative(sb, as_of: str) -> int:
    """Fill cumulative_return_since_event_pct for recent events with prices."""
    cut = (datetime.strptime(as_of, "%Y-%m-%d").date() - timedelta(days=120)).isoformat()
    res = sb.table("position_events").select("*").gte("date", cut).lte("date", as_of).execute()
    events = getattr(res, "data", None) or []
    n = 0
    for ev in events:
        t = ev.get("ticker")
        if not t or t == "CASH":
            continue
        evd = str(ev.get("date"))[:10]
        cmap = _fetch_closes(sb, t, [evd, as_of])
        c0 = cmap.get(evd)
        c1 = cmap.get(as_of)
        if c0 and c1 and c0 > 0:
            pct = (c1 - c0) / c0 * 100.0
            sb.table("position_events").update({"cumulative_return_since_event_pct": pct}).eq("id", ev["id"]).execute()
            n += 1
    return n


def refresh_nav_point(sb, as_of: str) -> None:
    """Append/update indexed NAV for `as_of`.

    On non-trading days (weekends / holidays) price_history carries forward the
    prior close, so every position's return is 0 and NAV stays flat — giving the
    portfolio page a continuous daily series with no gaps.

    If there is no positions snapshot for `as_of` (common on non-trading days),
    the most recent prior snapshot is used for weights.
    """
    # Fetch the most recent NAV before as_of (needed whether trading day or not)
    nav_res = (
        sb.table("nav_history")
        .select("date, nav")
        .lt("date", as_of)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    nav_data = getattr(nav_res, "data", None) or []
    prev_nav = float(nav_data[0]["nav"]) if nav_data else 100.0

    # Try exact-date positions snapshot first; fall back to most recent prior snapshot.
    pos_res = sb.table("positions").select("*").eq("date", as_of).execute()
    pos_rows = getattr(pos_res, "data", None) or []
    if not pos_rows:
        # No snapshot for as_of — find the most recent one
        snap_res = (
            sb.table("positions")
            .select("date")
            .lt("date", as_of)
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        snap_data = getattr(snap_res, "data", None) or []
        if snap_data:
            snap_date = str(snap_data[0]["date"])[:10]
            all_res = sb.table("positions").select("*").eq("date", snap_date).execute()
            pos_rows = getattr(all_res, "data", None) or []

    # Get previous day's price date (will be yesterday for every calendar day now
    # that price_history is forward-filled; on non-trading days p0 == p1 → dr=0)
    prev_d = _prev_trading_date(sb, "SPY", as_of)

    if not prev_d or not pos_rows:
        # No price history at all or no positions anywhere — just carry forward
        ts = datetime.utcnow().isoformat() + "Z"
        sb.table("nav_history").upsert(
            {"date": as_of, "nav": round(prev_nav, 6), "updated_at": ts},
            on_conflict="date",
        ).execute()
        print(f"✅ nav_history {as_of}: nav={prev_nav:.4f} (carried forward — no data)")
        return

    dr = 0.0
    for r in pos_rows:
        t = r.get("ticker")
        if not t or t == "CASH":
            continue
        w = float(r.get("weight_pct") or 0) / 100.0
        c_prev_map = _fetch_closes(sb, t, [prev_d])
        c_now_map = _fetch_closes(sb, t, [as_of])
        p0 = c_prev_map.get(prev_d)
        p1 = c_now_map.get(as_of)
        # On non-trading days price_history ffill means p0 == p1, so dr stays 0
        if p0 and p1 and p0 > 0:
            dr += w * (p1 - p0) / p0
    new_nav = prev_nav * (1.0 + dr)
    ts = datetime.utcnow().isoformat() + "Z"
    sb.table("nav_history").upsert(
        {"date": as_of, "nav": round(new_nav, 6), "updated_at": ts},
        on_conflict="date",
    ).execute()
    print(f"✅ nav_history {as_of}: nav={new_nav:.4f} (prev={prev_nav:.4f})")


def run_one_day(sb, metrics_date: str) -> None:
    """Carry-forward snapshot (if needed), refresh position metrics, NAV, portfolio_metrics."""
    print(f"\n📊 {metrics_date}")
    carry_forward_positions(sb, metrics_date)
    u = refresh_positions_metrics(sb, metrics_date)
    print(f"   positions performance columns updated: {u}")
    e = refresh_event_cumulative(sb, metrics_date)
    print(f"   position_events cumulative filled: {e}")
    refresh_nav_point(sb, metrics_date)
    upsert_portfolio_metrics_daily(sb, metrics_date)


def fill_calendar_through(sb, end: date) -> None:
    """Refresh latest snapshot date, then fill each calendar day through ``end`` inclusive."""
    latest = _max_positions_date(sb)
    if not latest:
        print("No positions rows — nothing to do")
        return
    if end < latest:
        print(
            f"⚠️  --fill-calendar-through {end} is before latest snapshot {latest}; "
            f"running a single refresh for {end}"
        )
        run_one_day(sb, end.isoformat())
        return
    print(f"📆 Calendar fill: refresh {latest}, then {latest + timedelta(days=1)} → {end}")
    run_one_day(sb, latest.isoformat())
    d = latest + timedelta(days=1)
    while d <= end:
        run_one_day(sb, d.isoformat())
        d += timedelta(days=1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    mx = ap.add_mutually_exclusive_group()
    mx.add_argument("--date", help="Single metrics date (YYYY-MM-DD)")
    mx.add_argument(
        "--fill-calendar-through",
        metavar="YYYY-MM-DD",
        dest="fill_through",
        help="Refresh latest snapshot, then carry-forward + metrics for each day through this date (inclusive)",
    )
    ap.add_argument("--supabase", action="store_true", help="Required flag for clarity")
    args = ap.parse_args()
    if not args.supabase:
        ap.error("Pass --supabase to run against Supabase")

    sb = _sb()
    if args.fill_through:
        fill_calendar_through(sb, datetime.strptime(args.fill_through, "%Y-%m-%d").date())
    elif args.date:
        run_one_day(sb, args.date)
    else:
        latest = _max_positions_date(sb)
        if not latest:
            print("No positions rows — nothing to do")
            sys.exit(0)
        run_one_day(sb, latest.isoformat())


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"❌ {ex}", file=sys.stderr)
        sys.exit(1)

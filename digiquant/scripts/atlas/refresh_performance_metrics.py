#!/usr/bin/env python3
"""
refresh_performance_metrics.py

Run after price_history (and optionally price_technicals) are updated for the day.
Uses Supabase price_history closes + positions snapshot rows to populate:

  - positions: unrealized_pnl_pct, day_change_pct, since_entry_return_pct, metrics_as_of
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
Environment: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (see config/supabase.env)
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_POSITION_INSERT_SKIP = frozenset({"id", "created_at", "updated_at"})
_METRIC_CLEAR = (
    "unrealized_pnl_pct",
    "day_change_pct",
    "since_entry_return_pct",
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
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
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


_MIN_HISTORY_ROWS = 20  # fewer rows → Sharpe / vol / max_dd / alpha are unreliable; write NULL


def _sum_attribution_pnl(sb, as_of: str) -> Optional[float]:
    """SUM of non-CASH position_attribution.contribution_pct for ``as_of``.

    Returns None when no attribution rows exist for the date (e.g. first run,
    or the attribution script has not yet been run). Falls back to None rather
    than silently returning 0 so callers can distinguish "no data" from "0% day".
    """
    res = (
        sb.table("position_attribution")
        .select("ticker,contribution_pct")
        .eq("date", as_of)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    non_cash = [
        float(r["contribution_pct"])
        for r in rows
        if r.get("ticker") != "CASH" and r.get("contribution_pct") is not None
    ]
    if not non_cash:
        return None
    return round(sum(non_cash), 6)


def _nav_history_count(sb, as_of: str) -> int:
    """Count of nav_history rows up to and including ``as_of`` (for history-length gate)."""
    res = sb.table("nav_history").select("date").lte("date", as_of).execute()
    return len(getattr(res, "data", None) or [])


def _risk_metrics_from_nav_history(sb, as_of: str) -> dict[str, float] | None:
    """Compute Sharpe, annualized vol %, and max drawdown % from nav_history through ``as_of``."""
    res = (
        sb.table("nav_history")
        .select("date,nav")
        .lte("date", as_of)
        .order("date")
        .execute()
    )
    rows = getattr(res, "data", None) or []
    navs = [float(r["nav"]) for r in rows if r.get("nav") is not None]
    if len(navs) < _MIN_HISTORY_ROWS:
        return None

    returns = [
        (navs[i] - navs[i - 1]) / navs[i - 1]
        for i in range(1, len(navs))
        if navs[i - 1] > 0
    ]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    std = math.sqrt(variance)
    sharpe = (mean / std) * math.sqrt(252) if std > 0 else 0.0
    volatility = std * math.sqrt(252) * 100.0

    peak = navs[0]
    max_drawdown = 0.0
    for nav in navs:
        if nav > peak:
            peak = nav
        if peak > 0:
            dd = (nav - peak) / peak
            if dd < max_drawdown:
                max_drawdown = dd

    return {
        "sharpe": round(sharpe, 6),
        "volatility": round(volatility, 6),
        "max_drawdown": round(max_drawdown * 100.0, 6),
    }


def upsert_portfolio_metrics_daily(sb, as_of: str) -> None:
    """Ensure one ``portfolio_metrics`` row per calendar day (dashboard continuity).

    Skips if a ``tearsheet`` row already exists for ``as_of``. Otherwise upserts
    with ``computed_from='refresh_script'`` (or ``'refresh_script_insufficient_history'``
    when nav_history has < 20 rows):
    - ``pnl_pct`` derived from SUM(position_attribution.contribution_pct) for
      non-CASH positions on ``as_of``; falls back to nav-based day return when no
      attribution rows exist yet (#814).  The nav fallback computes
      ``(nav - nav_prev) / nav_prev * 100`` using the most recent prior nav_history
      row — NOT ``nav - 100`` (which would be total-return-since-inception and wrong
      on any day past inception).  When no prior nav row exists the fallback yields
      None rather than a misleading value.
    - ``sharpe`` / ``volatility`` / ``max_drawdown`` computed from nav_history when
      there are >= 20 rows; otherwise NULL.  ``alpha`` is carried from the prior row
      when history is sufficient.  ``computed_from`` is
      ``'refresh_script_insufficient_history'`` when the history gate fails.
    """
    ex = sb.table("portfolio_metrics").select("computed_from").eq("date", as_of).limit(1).execute()
    if getattr(ex, "data", None) and ex.data[0].get("computed_from") == "tearsheet":
        print(f"   portfolio_metrics {as_of}: skip (tearsheet row)")
        return

    # pnl_pct: prefer attribution-derived sum (the real per-position return #814);
    # fall back to day-over-day nav return when attribution is missing.
    pnl_pct = _sum_attribution_pnl(sb, as_of)
    if pnl_pct is None:
        nav_res = sb.table("nav_history").select("nav").eq("date", as_of).limit(1).execute()
        nav_data = getattr(nav_res, "data", None) or []
        nav = float(nav_data[0]["nav"]) if nav_data else None
        # Fetch the most recent nav_history row strictly before as_of to derive a
        # day return.  Using (nav - 100) would be total-return-since-inception and
        # is wrong on any day past the first (#814).
        nav_prev: Optional[float] = None
        if nav is not None:
            prev_nav_res = (
                sb.table("nav_history")
                .select("nav")
                .lt("date", as_of)
                .order("date", desc=True)
                .limit(1)
                .execute()
            )
            prev_nav_data = getattr(prev_nav_res, "data", None) or []
            if prev_nav_data and prev_nav_data[0].get("nav") is not None:
                nav_prev = float(prev_nav_data[0]["nav"])
        if nav is not None and nav_prev is not None and nav_prev > 0:
            pnl_pct = round((nav - nav_prev) / nav_prev * 100.0, 4)
            print(f"   portfolio_metrics {as_of}: pnl_pct from nav fallback (no attribution rows)")
        else:
            pnl_pct = None

    pos_res = sb.table("positions").select("ticker,weight_pct").eq("date", as_of).execute()
    prow = getattr(pos_res, "data", None) or []
    total_invested = 0.0
    for p in prow:
        t = p.get("ticker")
        if t and t != "CASH":
            total_invested += float(p.get("weight_pct") or 0)

    # Risk metrics (sharpe/vol/max_dd): compute from NAV history once the existing
    # 20-row gate is met. With less history, write NULL so the dashboard doesn't
    # display misleading zeros.
    risk_metrics = _risk_metrics_from_nav_history(sb, as_of)
    has_sufficient_history = risk_metrics is not None
    sharpe = volatility = max_drawdown = None
    alpha = None
    if risk_metrics is not None:
        sharpe = risk_metrics["sharpe"]
        volatility = risk_metrics["volatility"]
        max_drawdown = risk_metrics["max_drawdown"]
        prev_m = (
            sb.table("portfolio_metrics")
            .select("alpha")
            .lt("date", as_of)
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        pmd = getattr(prev_m, "data", None) or []
        prev = pmd[0] if pmd else {}
        alpha = prev.get("alpha")

    ts = datetime.now(tz=timezone.utc).isoformat()
    computed_from = (
        "refresh_script" if has_sufficient_history else "refresh_script_insufficient_history"
    )
    row = {
        "date": as_of,
        "pnl_pct": pnl_pct,
        "sharpe": sharpe,
        "volatility": volatility,
        "max_drawdown": max_drawdown,
        "alpha": alpha,
        "invested_pct": round(total_invested, 4) if prow else None,
        "computed_from": computed_from,
        "as_of_date": as_of,
        "generated_at": ts,
    }
    sb.table("portfolio_metrics").upsert(row, on_conflict="date").execute()
    suffix = "" if has_sufficient_history else " [insufficient_history — risk metrics NULL]"
    print(f"✅ portfolio_metrics {as_of}: upserted ({computed_from}){suffix}")


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


_ENTRY_PRICE_SANITY_THRESHOLD = 0.10  # warn when |entry/close - 1| > 10%


def refresh_positions_metrics(sb, metrics_date: str) -> int:
    """Update positions for date == metrics_date. Returns rows updated.

    current_price is always written from the latest price_history close for the
    date — it is never left NULL when price data exists (#814). An entry_price
    sanity check warns to stderr when the stored entry_price deviates from the
    current close by more than 10% (catches data-entry errors like SPY@750 #814).
    """
    patched = patch_positions_entries_for_date(sb, metrics_date)
    if patched:
        print(f"   entry_price filled from position_events: {patched} row(s)")
    res = sb.table("positions").select("*").eq("date", metrics_date).execute()
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
        dates_needed = [metrics_date]
        if prev_d:
            dates_needed.append(prev_d)
        if entry_dt:
            dates_needed.append(str(entry_dt)[:10])
        closes = _fetch_closes(sb, t, list(set(dates_needed)))
        # Always populate current_price from the freshest available close (#814).
        # Try the exact metrics_date first; fall back to the most recent prior close
        # so weekends / holidays still produce a non-NULL price.
        c_now = closes.get(metrics_date)
        if c_now is None and prev_d:
            c_now = closes.get(prev_d)
        c_prev = closes.get(prev_d) if prev_d else None
        day_ch = None
        if c_now is not None and c_prev is not None and c_prev > 0:
            day_ch = (c_now - c_prev) / c_prev * 100.0
        # Sanity-check entry_price vs current close — flag implausible entries like SPY@750 (#814).
        if entry is not None and c_now is not None and c_now > 0:
            ratio = abs(float(entry) / c_now - 1.0)
            if ratio > _ENTRY_PRICE_SANITY_THRESHOLD:
                print(
                    f"⚠️  entry_price sanity: {t} entry={entry} vs close={c_now:.4f} "
                    f"({ratio * 100:.1f}% deviation — possible data error)",
                    file=sys.stderr,
                )
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
        patch = {
            "unrealized_pnl_pct": unreal,
            "day_change_pct": day_ch,
            "since_entry_return_pct": since,
            "metrics_as_of": metrics_date,
            # current_price: always set from the latest close available (today or prev trading day).
            # This replaces any stale/NULL value stored from a prior run or initial materialization.
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
            sb.table("position_events").update({"cumulative_return_since_event_pct": pct}).eq(
                "id", ev["id"]
            ).execute()
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

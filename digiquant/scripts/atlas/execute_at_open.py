#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as dt_date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def _trading_day_only(d: str) -> bool:
    try:
        wd = datetime.fromisoformat(d).isoweekday()
        return 1 <= wd <= 5
    except Exception:
        return False


def _prior_trading_date(execution_date: str) -> Optional[str]:
    """Previous calendar date that falls on Mon–Fri (US equity session proxy)."""
    try:
        cur = datetime.fromisoformat(execution_date).date()
    except Exception:
        return None
    for _ in range(12):
        cur = cur - timedelta(days=1)
        if cur.weekday() < 5:
            return cur.isoformat()
    return None


def _parse_pct(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_open(sb, ticker: str, d: str) -> Optional[float]:
    res = (
        sb.table("price_history")
        .select("open")
        .eq("ticker", ticker)
        .eq("date", d)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    o = rows[0].get("open")
    return float(o) if o is not None else None


def _rebalance_payload_for_date(sb, rebalance_date: str) -> Optional[Dict[str, Any]]:
    """Load rebalance_decision for a given documents.date (fast path + fallback scan)."""
    res = (
        sb.table("documents")
        .select("payload")
        .eq("date", rebalance_date)
        .eq("document_key", "rebalance-decision.json")
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if rows:
        p = rows[0].get("payload")
        if isinstance(p, dict) and p.get("doc_type") == "rebalance_decision":
            return p

    res2 = (
        sb.table("documents")
        .select("payload")
        .eq("date", rebalance_date)
        .order("document_key", desc=True)
        .execute()
    )
    for r in getattr(res2, "data", None) or []:
        p = r.get("payload")
        if isinstance(p, dict) and p.get("doc_type") == "rebalance_decision":
            return p
    return None


def _rebalance_table_nonempty(payload: Dict[str, Any]) -> bool:
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    table = body.get("rebalance_table") if isinstance(body, dict) else None
    return isinstance(table, list) and len(table) > 0


def resolve_rebalance_payload_fallback(sb, execution_d: str) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    When no rebalance_decision row exists for documents.date == execution day, find the PM
    artifact used for that session: walk backward along prior trading days (Fri decision → Mon
    open), then search calendar neighbors (+/- days) like backfill_position_event_reasons.
    """
    d = execution_d
    for _ in range(25):
        p = _rebalance_payload_for_date(sb, d)
        if isinstance(p, dict) and p.get("doc_type") == "rebalance_decision" and _rebalance_table_nonempty(p):
            return d, p
        pd = _prior_trading_date(d)
        if not pd or pd == d:
            break
        d = pd

    try:
        anchor = dt_date.fromisoformat(execution_d)
    except ValueError:
        return None, None
    order: List[dt_date] = [anchor]
    for i in range(1, 12):
        order.append(anchor + timedelta(days=i))
    for i in range(1, 16):
        order.append(anchor - timedelta(days=i))
    seen: Set[dt_date] = set()
    for ad in order:
        if ad in seen:
            continue
        seen.add(ad)
        ds = ad.isoformat()
        p = _rebalance_payload_for_date(sb, ds)
        if isinstance(p, dict) and p.get("doc_type") == "rebalance_decision" and _rebalance_table_nonempty(p):
            return ds, p
    return None, None


def _event_tickers_for_date(sb, execution_date: str) -> Set[str]:
    res = sb.table("position_events").select("ticker").eq("date", execution_date).execute()
    out: Set[str] = set()
    for r in getattr(res, "data", None) or []:
        if isinstance(r, dict) and r.get("ticker"):
            out.add(str(r["ticker"]))
    return out


def _prior_position_weight(sb, prior_date: Optional[str], ticker: str) -> Optional[float]:
    if not prior_date:
        return None
    res = (
        sb.table("positions")
        .select("weight_pct")
        .eq("date", prior_date)
        .eq("ticker", ticker)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    return _parse_pct(rows[0].get("weight_pct"))


def _hold_events_for_positions_not_in_rebalance(
    sb, execution_date: str, skip_tickers: Set[str]
) -> List[Dict[str, Any]]:
    """
    For every held line in `positions` on execution_date whose ticker is not in skip_tickers,
    emit a HOLD ledger row so Activity shows the full book.
    skip_tickers should include rebalance_table tickers and any tickers already present in
    position_events for this date (so we do not overwrite OPEN/TRIM/etc.).
    """
    res = (
        sb.table("positions")
        .select("ticker,weight_pct,thesis_id,rationale")
        .eq("date", execution_date)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    prior_d = _prior_trading_date(execution_date)
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = row.get("ticker")
        if not ticker or not isinstance(ticker, str):
            continue
        if str(ticker).upper() == "CASH":
            continue
        if ticker in skip_tickers:
            continue
        w = _parse_pct(row.get("weight_pct"))
        if w is None or w <= 0:
            continue
        prev_w = _prior_position_weight(sb, prior_d, ticker)
        wch = (w - prev_w) if prev_w is not None and w is not None else None
        price = _fetch_open(sb, ticker, execution_date)
        reason = row.get("rationale")
        if isinstance(reason, str) and reason.strip():
            reason_s = reason.strip()
        else:
            reason_s = (
                "Held — position on book; not listed in rebalance_table for this session "
                "(synced via positions snapshot)."
            )
        out.append(
            {
                "date": execution_date,
                "ticker": ticker,
                "event": "HOLD",
                "weight_pct": w,
                "prev_weight_pct": prev_w,
                "weight_change_pct": wch,
                "price": price,
                "reason": reason_s,
                "thesis_id": row.get("thesis_id"),
            }
        )
    return out


def build_events_from_digest_snapshot(sb, execution_d: str) -> Optional[List[Dict[str, Any]]]:
    """
    When `rebalance-decision.json` is not published for this date, derive OPEN/TRIM/ADD/HOLD/EXIT
    from `daily_snapshots.snapshot.portfolio.proposed_positions` (post-trade targets) vs prior
    session `positions` weights (prior trading day), using market-open prices for execution_d.
    """
    res = sb.table("daily_snapshots").select("snapshot").eq("date", execution_d).limit(1).execute()
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    raw = rows[0].get("snapshot")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    port = raw.get("portfolio")
    if not isinstance(port, dict):
        return None
    pp = port.get("proposed_positions")
    if not isinstance(pp, list) or not pp:
        return None
    targets: Dict[str, float] = {}
    for row in pp:
        if not isinstance(row, dict):
            continue
        t = row.get("ticker")
        if not t or t == "CASH":
            continue
        try:
            targets[str(t).upper()] = float(row.get("weight_pct") or 0)
        except (TypeError, ValueError):
            continue
    prior_d = _prior_trading_date(execution_d)
    if not prior_d:
        return None
    pw_res = sb.table("positions").select("ticker,weight_pct").eq("date", prior_d).execute()
    prior_w: Dict[str, float] = {}
    for row in getattr(pw_res, "data", None) or []:
        if not isinstance(row, dict):
            continue
        tk = row.get("ticker")
        if not tk or tk == "CASH":
            continue
        try:
            prior_w[str(tk).upper()] = float(row.get("weight_pct") or 0)
        except (TypeError, ValueError):
            continue
    all_tickers = set(prior_w) | set(targets)
    out: List[Dict[str, Any]] = []
    eps = 0.0001
    for t in sorted(all_tickers):
        prev = prior_w.get(t, 0.0)
        rec = targets.get(t, 0.0)
        chg = rec - prev
        if prev <= eps and rec > eps:
            ev = "OPEN"
        elif prev > eps and rec <= eps:
            ev = "EXIT"
        elif chg < -eps:
            ev = "TRIM"
        elif chg > eps:
            ev = "ADD"
        else:
            ev = "HOLD"
        price = _fetch_open(sb, t, execution_d)
        out.append(
            {
                "date": execution_d,
                "ticker": t,
                "event": ev,
                "weight_pct": rec,
                "prev_weight_pct": prev if prev > eps else None,
                "weight_change_pct": chg if abs(chg) > eps else None,
                "price": price,
                "reason": (
                    "Derived from digest snapshot proposed_positions vs prior session positions "
                    "(no rebalance_decision.json for this date)."
                ),
                "thesis_id": None,
            }
        )
    return out if out else None


def build_events_from_positions_book(sb, execution_d: str) -> Optional[List[Dict[str, Any]]]:
    """
    When digest `proposed_positions` is absent, infer OPEN/TRIM/ADD/HOLD/EXIT from the book
    recorded in `positions` on execution_d vs the prior trading day's `positions`.
    """
    res = sb.table("positions").select("ticker,weight_pct,thesis_id").eq("date", execution_d).execute()
    rows = getattr(res, "data", None) or []
    targets: Dict[str, float] = {}
    thesis: Dict[str, Optional[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        t = row.get("ticker")
        if not t or t == "CASH":
            continue
        try:
            targets[str(t).upper()] = float(row.get("weight_pct") or 0)
        except (TypeError, ValueError):
            continue
        tid = row.get("thesis_id")
        thesis[str(t).upper()] = str(tid) if tid else None
    if not targets:
        return None
    prior_d = _prior_trading_date(execution_d)
    if not prior_d:
        return None
    pw_res = sb.table("positions").select("ticker,weight_pct").eq("date", prior_d).execute()
    prior_w: Dict[str, float] = {}
    for row in getattr(pw_res, "data", None) or []:
        if not isinstance(row, dict):
            continue
        tk = row.get("ticker")
        if not tk or tk == "CASH":
            continue
        try:
            prior_w[str(tk).upper()] = float(row.get("weight_pct") or 0)
        except (TypeError, ValueError):
            continue
    all_tickers = set(prior_w) | set(targets)
    out: List[Dict[str, Any]] = []
    eps = 0.0001
    for t in sorted(all_tickers):
        prev = prior_w.get(t, 0.0)
        rec = targets.get(t, 0.0)
        chg = rec - prev
        if prev <= eps and rec > eps:
            ev = "OPEN"
        elif prev > eps and rec <= eps:
            ev = "EXIT"
        elif chg < -eps:
            ev = "TRIM"
        elif chg > eps:
            ev = "ADD"
        else:
            ev = "HOLD"
        price = _fetch_open(sb, t, execution_d)
        out.append(
            {
                "date": execution_d,
                "ticker": t,
                "event": ev,
                "weight_pct": rec,
                "prev_weight_pct": prev if prev > eps else None,
                "weight_change_pct": chg if abs(chg) > eps else None,
                "price": price,
                "reason": (
                    "Derived from positions book vs prior session positions "
                    "(digest proposed_positions unavailable; no rebalance_decision.json for this date)."
                ),
                "thesis_id": thesis.get(t),
            }
        )
    return out if out else None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Record market-open execution events into position_events (OPEN/EXIT/TRIM/ADD/HOLD). "
        "Execution prices use price_history.open for --date (execution day). "
        "HOLD rows keep the ledger continuous on no-trade days."
    )
    ap.add_argument("--date", default=dt_date.today().isoformat(), help="Execution session date YYYY-MM-DD (opens from this day)")
    ap.add_argument(
        "--rebalance-date",
        default=None,
        help="documents.date for rebalance_decision (default: same as --date, or prior weekday with --prior-trading-day-rebalance)",
    )
    ap.add_argument(
        "--prior-trading-day-rebalance",
        action="store_true",
        help="Use rebalance_decision from the previous Mon–Fri, execute at opens on --date (e.g. Fri decision → Mon open).",
    )
    ap.add_argument(
        "--no-rebalance-fallback",
        action="store_true",
        help="Do not search nearby documents.dates when same-day rebalance_decision is missing (strict).",
    )
    ap.add_argument(
        "--no-digest-events",
        action="store_true",
        help="Do not derive events from daily_snapshots when rebalance_decision is missing.",
    )
    args = ap.parse_args()
    d = args.date

    if not _trading_day_only(d):
        print("Skipping execution: non-trading day (weekend).")
        return 0

    if args.prior_trading_day_rebalance and args.rebalance_date:
        print("error: use only one of --prior-trading-day-rebalance or --rebalance-date", file=sys.stderr)
        return 2

    rebalance_d = args.rebalance_date
    if args.prior_trading_day_rebalance:
        rebalance_d = _prior_trading_date(d)
        if not rebalance_d:
            print("Could not resolve prior trading date for rebalance source.", file=sys.stderr)
            return 2
    elif not rebalance_d:
        rebalance_d = d

    sb = _sb()
    payload = _rebalance_payload_for_date(sb, rebalance_d)
    if (
        not payload
        and not args.rebalance_date
        and not args.prior_trading_day_rebalance
        and not args.no_rebalance_fallback
    ):
        rd_fb, p_fb = resolve_rebalance_payload_fallback(sb, d)
        if p_fb:
            rebalance_d = rd_fb
            payload = p_fb
            print(
                f"Resolved rebalance_decision from documents.date={rebalance_d} "
                f"(no same-day row for {d}; using PM artifact search)."
            )
    if not payload:
        if not args.no_digest_events:
            digest_events = build_events_from_digest_snapshot(sb, d)
            if not digest_events:
                digest_events = build_events_from_positions_book(sb, d)
            if digest_events:
                for e in digest_events:
                    sb.table("position_events").upsert(e, on_conflict="date,ticker").execute()
                null_px = sum(1 for e in digest_events if e.get("price") is None)
                if null_px:
                    print(
                        f"⚠️  {null_px} event(s) have null price (no price_history.open for {d} yet). "
                        f"After opens sync: python3 scripts/backfill_execution_prices.py --date {d}"
                    )
                trade_n = sum(1 for e in digest_events if e.get("event") != "HOLD")
                hold_n = len(digest_events) - trade_n
                print(
                    f"✅ recorded {len(digest_events)} event(s) from digest snapshot vs prior positions for {d} "
                    f"({trade_n} trade-related, {hold_n} HOLD) — no rebalance_decision.json for this date."
                )
                return 0
        print(f"No rebalance_decision payload for documents.date={rebalance_d}; filling from positions only.")
        extra = _hold_events_for_positions_not_in_rebalance(sb, d, _event_tickers_for_date(sb, d))
        if not extra:
            print("No positions rows for this date — nothing to record.")
            return 0
        for e in extra:
            sb.table("position_events").upsert(e, on_conflict="date,ticker").execute()
        null_px = sum(1 for e in extra if e.get("price") is None)
        if null_px:
            print(
                f"⚠️  {null_px} event(s) have null price (no price_history.open for {d} yet). "
                f"After opens sync: python3 scripts/backfill_execution_prices.py --date {d}"
            )
        print(f"✅ recorded {len(extra)} HOLD event(s) from positions snapshot only for {d}")
        return 0

    if rebalance_d != d:
        print(f"Using rebalance_decision from {rebalance_d} for execution on {d} (opens).")

    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    table = body.get("rebalance_table") if isinstance(body, dict) else None
    if not isinstance(table, list) or not table:
        print("rebalance_decision has no rebalance_table; filling from positions only.")
        extra = _hold_events_for_positions_not_in_rebalance(sb, d, _event_tickers_for_date(sb, d))
        if not extra:
            print("No positions rows for this date — nothing to record.")
            return 0
        for e in extra:
            sb.table("position_events").upsert(e, on_conflict="date,ticker").execute()
        null_px = sum(1 for e in extra if e.get("price") is None)
        if null_px:
            print(
                f"⚠️  {null_px} event(s) have null price (no price_history.open for {d} yet). "
                f"After opens sync: python3 scripts/backfill_execution_prices.py --date {d}"
            )
        print(f"✅ recorded {len(extra)} HOLD event(s) from positions snapshot only for {d}")
        return 0

    # Build events for every rebalance row (including HOLD) so quiet days still have ledger rows.
    events: List[Dict[str, Any]] = []
    for row in table:
        if not isinstance(row, dict):
            continue
        ticker = row.get("ticker")
        action = row.get("action")
        if not ticker or not isinstance(ticker, str):
            continue

        action_u = str(action or "").upper()
        is_hold = action_u in ("HOLD", "")

        weight_pct = _parse_pct(row.get("recommended_pct"))
        prev_weight_pct = _parse_pct(row.get("current_pct"))
        weight_change_pct = _parse_pct(row.get("change_pct"))

        price = _fetch_open(sb, ticker, d)

        if is_hold:
            event = "HOLD"
        elif action_u in ("EXIT",):
            event = "EXIT"
        elif action_u in ("NEW",):
            event = "OPEN"
        elif action_u == "ADD":
            event = "ADD"
        elif action_u == "TRIM":
            event = "TRIM"
        else:
            # Legacy rows or unknown action: infer direction from weights (never emit REBALANCE).
            if weight_change_pct is not None and weight_change_pct < 0:
                event = "TRIM"
            elif weight_change_pct is not None and weight_change_pct > 0:
                event = "ADD"
            elif (
                prev_weight_pct is not None
                and weight_pct is not None
                and weight_pct < prev_weight_pct
            ):
                event = "TRIM"
            elif (
                prev_weight_pct is not None
                and weight_pct is not None
                and weight_pct > prev_weight_pct
            ):
                event = "ADD"
            else:
                event = "TRIM"

        rec: Dict[str, Any] = {
            "date": d,
            "ticker": ticker,
            "event": event,
            "weight_pct": weight_pct,
            "prev_weight_pct": prev_weight_pct,
            "weight_change_pct": weight_change_pct,
            "price": price,
            "reason": row.get("rationale"),
            "thesis_id": None,
        }
        events.append(rec)

    table_tickers: Set[str] = {str(e["ticker"]) for e in events if e.get("ticker")}
    pre_existing = _event_tickers_for_date(sb, d)
    skip_for_gap = table_tickers | pre_existing
    gap_holds = _hold_events_for_positions_not_in_rebalance(sb, d, skip_for_gap)
    if gap_holds:
        events.extend(gap_holds)

    if not events:
        print("rebalance_table produced no rows after filtering, and no positions to backfill.")
        return 0

    if gap_holds and table_tickers:
        print(
            f"➕ {len(gap_holds)} extra ticker(s) on book but not in rebalance_table → HOLD rows "
            f"({', '.join(e['ticker'] for e in gap_holds)})"
        )
    elif gap_holds:
        print(
            f"➕ {len(gap_holds)} HOLD row(s) from positions snapshot "
            f"({', '.join(e['ticker'] for e in gap_holds)})"
        )

    # Upsert by date,ticker (current schema)
    for e in events:
        sb.table("position_events").upsert(e, on_conflict="date,ticker").execute()

    null_px = sum(1 for e in events if e.get("price") is None)
    if null_px:
        print(
            f"⚠️  {null_px} event(s) have null price (no price_history.open for {d} yet). "
            f"After opens sync: python3 scripts/backfill_execution_prices.py --date {d}"
        )

    hold_n = sum(1 for e in events if e.get("event") == "HOLD")
    trade_n = len(events) - hold_n
    print(
        f"✅ recorded {len(events)} execution event(s) at market open for {d} "
        f"({trade_n} trade-related, {hold_n} HOLD)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


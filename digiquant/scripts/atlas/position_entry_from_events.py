"""
Shared helpers: resolve positions.entry_price / entry_date from position_events.

Earliest OPEN or ADD row with a non-null price on or before ``as_of`` (same rule as the dashboard).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def first_open_add_mark(sb: Any, ticker: str, as_of: str) -> Tuple[Optional[str], Optional[float]]:
    """Return (entry_date_iso, price) from the earliest OPEN/ADD with price, or (None, None)."""
    t = (ticker or "").strip().upper()
    if not t or t == "CASH":
        return None, None
    res = (
        sb.table("position_events")
        .select("date,price")
        .eq("ticker", t)
        .in_("event", ["OPEN", "ADD"])
        .lte("date", as_of)
        .order("date")
        .limit(400)
        .execute()
    )
    rows: list[Dict[str, Any]] = getattr(res, "data", None) or []
    for row in rows:
        p = row.get("price")
        if p is None:
            continue
        try:
            px = float(p)
        except (TypeError, ValueError):
            continue
        if px > 0:
            d = row.get("date")
            if d:
                return str(d)[:10], px
    return None, None


def _close_on_or_after(sb: Any, ticker: str, iso: str) -> Optional[float]:
    """First available close on or after ``iso`` for ticker (walk forward a few days)."""
    t = (ticker or "").strip().upper()
    if not t:
        return None
    res = (
        sb.table("price_history")
        .select("date,close")
        .eq("ticker", t)
        .gte("date", iso)
        .order("date")
        .limit(12)
        .execute()
    )
    for row in getattr(res, "data", None) or []:
        c = row.get("close")
        if c is not None:
            try:
                x = float(c)
            except (TypeError, ValueError):
                continue
            if x > 0:
                return x
    return None


def patch_positions_entries_for_date(sb: Any, metrics_date: str) -> int:
    """Update positions rows for ``metrics_date`` when entry_price is missing; returns rows updated."""
    res = sb.table("positions").select("ticker,entry_price,entry_date").eq("date", metrics_date).execute()
    rows: list[Dict[str, Any]] = getattr(res, "data", None) or []
    n = 0
    for r in rows:
        t = r.get("ticker")
        if not t or t == "CASH":
            continue
        ep = r.get("entry_price")
        try:
            has_price = ep is not None and float(ep) > 0
        except (TypeError, ValueError):
            has_price = False
        if has_price:
            continue
        ed, price = first_open_add_mark(sb, str(t), metrics_date)
        entry_date_existing = r.get("entry_date")
        if (price is None or price <= 0) and entry_date_existing:
            iso = str(entry_date_existing)[:10]
            c = _close_on_or_after(sb, str(t), iso)
            if c is not None and c > 0:
                price = c
                ed = ed or iso
        if price is not None and price > 0:
            patch: Dict[str, Any] = {"entry_price": price}
            if ed:
                patch["entry_date"] = ed
            sb.table("positions").update(patch).eq("date", metrics_date).eq("ticker", t).execute()
            n += 1
    return n

"""
Shared helpers: resolve positions.entry_price / entry_date from position_events.

``entry_price`` is NOT a weighted average entry. It is the mark of the EARLIEST OPEN or ADD
row with a non-null price on or before ``as_of`` -- the same rule the dashboard reads
(``averageEntryAsOf`` in ``apps/dashboard-api/src/ledger.ts`` and its twin in
``apps/dashboard/lib/position-event-economics.ts``), which is why that function is named
for an average it does not compute (DIG-2809).

Consequences a caller must know:

* Opening at 100 then ADDing at 200 leaves ``entry_price`` at 100. The quantity-weighted
  basis is derivable from the per-lot open marks (one row per open lot) and is derived
  nowhere. Do not name the lots table here: ``test_only_execution_io_names_the_fill_tables``
  greps this tree for it and treats any mention as a second writer.
* The value is a per-date snapshot, so a late or repaired OPEN/ADD mark at or before a date
  changes what a LATER date row receives. An already published event is therefore not
  immutable in its displayed basis.
* ``lte("date", as_of)`` is inclusive: on an ADD date the basis already includes that fill.
* When no OPEN/ADD mark exists but an ``entry_date`` does,
  :func:`patch_positions_entries_for_date` falls back to the first sealed-R2 close on or
  after ``entry_date`` -- a different basis rule writing the same column, with nothing
  recording which one produced the value.
* The basis is anchored on ``position_events``, so a REPLAYED event can become a ticker's
  permanent basis at a price never traded on that date.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple

from digiquant.dashboard.tenancy import house_workspace_id
from digiquant.research.data.queries import r2_close_rows


def _house_id() -> str:
    return str(house_workspace_id())


def first_open_add_mark(sb: Any, ticker: str, as_of: str) -> Tuple[Optional[str], Optional[float]]:
    """Return (entry_date_iso, price) from the earliest OPEN/ADD with price, or (None, None)."""
    t = (ticker or "").strip().upper()
    if not t or t == "CASH":
        return None, None
    res = (
        sb.table("position_events")
        .select("date,price")
        .eq("workspace_id", _house_id())
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
    """First sealed-R2 close on or after ``iso`` for ticker (walk forward a few days).

    An unsealed/unknown window returns ``None`` (the caller keeps the existing
    entry) — a missing generation is not an outage.
    """
    t = (ticker or "").strip().upper()
    if not t:
        return None
    since = str(iso)[:10]
    try:
        until = (date.fromisoformat(since) + timedelta(days=12)).isoformat()
    except (TypeError, ValueError):
        return None
    try:
        rows = r2_close_rows(tickers=[t], since=since, until=until)
    except LookupError:
        return None
    for row in rows:
        c = row.get("close")
        if c is None:
            continue
        try:
            x = float(c)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and x > 0:
            return x
    return None


def patch_positions_entries_for_date(sb: Any, metrics_date: str) -> int:
    """Update positions rows for ``metrics_date`` when entry_price is missing; returns rows updated."""
    res = (
        sb.table("positions")
        .select("ticker,entry_price,entry_date")
        .eq("workspace_id", _house_id())
        .eq("date", metrics_date)
        .execute()
    )
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
            sb.table("positions").update(patch).eq("workspace_id", _house_id()).eq(
                "date", metrics_date
            ).eq("ticker", t).execute()
            n += 1
    return n

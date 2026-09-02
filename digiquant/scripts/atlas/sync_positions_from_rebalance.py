#!/usr/bin/env python3
"""
sync_positions_from_rebalance.py

After Track B publishes rebalance_decision to Supabase documents, upsert the ``positions``
table for that date from ``body.proposed_portfolio`` so the dashboard and
``refresh_performance_metrics.py`` use the PM target book (not only digest-era weights).

For each non-CASH line, ``entry_price`` / ``entry_date`` are set from the earliest
``position_events`` OPEN or ADD row with a mark price on or before the rebalance date
(when present).

No-op if there is no rebalance_decision for the date or no proposed_portfolio.positions.

Intended to run from ``run_db_first.py`` before ``refresh_performance_metrics.py`` when
``--validate-mode`` is ``pm`` or ``full``.

Usage:
  python3 scripts/sync_positions_from_rebalance.py --date YYYY-MM-DD
Environment: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (see config/supabase.env)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from digiquant.olympus.tenancy import house_workspace_id

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

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from position_entry_from_events import first_open_add_mark  # noqa: E402


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    key = os.environ.get("CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
    return create_client(url, key)


def _house_id() -> str:
    return str(house_workspace_id())


def _eq_house(query: Any) -> Any:
    return query.eq("workspace_id", _house_id())


def _rebalance_payload_for_date(sb: Any, d: str) -> Optional[Dict[str, Any]]:
    res = (
        _eq_house(sb.table("documents").select("payload"))
        .eq("date", d)
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
        _eq_house(sb.table("documents").select("payload"))
        .eq("date", d)
        .order("document_key", desc=True)
        .execute()
    )
    for r in getattr(res2, "data", None) or []:
        p = r.get("payload")
        if isinstance(p, dict) and p.get("doc_type") == "rebalance_decision":
            return p
    return None


def sync_positions_for_date(sb: Any, d: str, *, dry_run: bool = False) -> int:
    """Upsert house ``positions`` from ``rebalance_decision`` for ``d``.

    Returns the number of rows that would be / were upserted (0 = skip).
    Stamps ``workspace_id`` and targets ``on_conflict='workspace_id,date,ticker'``
    so a later P6 drop of 097's ``UNIQUE(date, ticker)`` does not 42P10 this path.
    """
    payload = _rebalance_payload_for_date(sb, d)
    if not payload:
        print(f"sync_positions_from_rebalance: no rebalance_decision for {d} — skip")
        return 0

    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    pp = body.get("proposed_portfolio") if isinstance(body.get("proposed_portfolio"), dict) else {}
    positions = pp.get("positions")
    if not isinstance(positions, list) or not positions:
        print(f"sync_positions_from_rebalance: no body.proposed_portfolio.positions for {d} — skip")
        return 0

    cash_pct = pp.get("cash_residual_pct")
    try:
        cash_f = float(cash_pct) if cash_pct is not None else 0.0
    except (TypeError, ValueError):
        cash_f = 0.0

    pos_rows: List[Dict[str, Any]] = []
    for p in positions:
        if not isinstance(p, dict):
            continue
        t = p.get("ticker")
        if not t or not isinstance(t, str):
            continue
        try:
            w = float(p.get("weight_pct") or 0)
        except (TypeError, ValueError):
            w = 0.0
        if t != "CASH" and w == 0.0:
            continue
        tid = p.get("thesis_id")
        pos_rows.append(
            {
                "workspace_id": _house_id(),
                "date": d,
                "ticker": t,
                "weight_pct": w,
                "thesis_id": tid if isinstance(tid, str) else None,
                "rationale": None,
                "name": None,
                "category": None,
                "current_price": None,
                "entry_price": None,
                "entry_date": None,
                "pm_notes": None,
                "unrealized_pnl_pct": None,
                "day_change_pct": None,
                "since_entry_return_pct": None,
                "metrics_as_of": None,
            }
        )

    if cash_f > 0.001:
        if not any(r["ticker"] == "CASH" for r in pos_rows):
            pos_rows.append(
                {
                    "workspace_id": _house_id(),
                    "date": d,
                    "ticker": "CASH",
                    "weight_pct": round(cash_f, 4),
                    "thesis_id": None,
                    "rationale": None,
                    "name": None,
                    "category": None,
                    "current_price": None,
                    "entry_price": None,
                    "entry_date": None,
                    "pm_notes": None,
                    "unrealized_pnl_pct": None,
                    "day_change_pct": None,
                    "since_entry_return_pct": None,
                    "metrics_as_of": None,
                }
            )

    for row in pos_rows:
        tk = row.get("ticker")
        if not tk or tk == "CASH":
            continue
        ed, ep = first_open_add_mark(sb, str(tk), d)
        if ep is not None and ep > 0:
            row["entry_price"] = ep
            if ed:
                row["entry_date"] = ed

    if not pos_rows:
        print(f"sync_positions_from_rebalance: empty book after filtering for {d} — skip")
        return 0

    keep_tickers = {r["ticker"] for r in pos_rows if r.get("ticker")}

    if dry_run:
        print(f"[dry-run] would upsert {len(pos_rows)} position row(s) for {d}: {sorted(keep_tickers)}")
        return len(pos_rows)

    CHUNK = 500
    for i in range(0, len(pos_rows), CHUNK):
        sb.table("positions").upsert(
            pos_rows[i : i + CHUNK], on_conflict="workspace_id,date,ticker"
        ).execute()

    existing = _eq_house(sb.table("positions").select("ticker")).eq("date", d).execute()
    for row in getattr(existing, "data", None) or []:
        tk = row.get("ticker")
        if tk and tk not in keep_tickers:
            _eq_house(sb.table("positions").delete()).eq("date", d).eq("ticker", tk).execute()

    print(f"✅ sync_positions_from_rebalance: {len(pos_rows)} position row(s) for {d}")
    return len(pos_rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Upsert positions from rebalance_decision proposed_portfolio.")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD (documents.date)")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    args = ap.parse_args()
    sync_positions_for_date(_sb(), args.date, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

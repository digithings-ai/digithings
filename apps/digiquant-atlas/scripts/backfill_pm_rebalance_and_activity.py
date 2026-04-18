#!/usr/bin/env python3
"""
Backfill canonical PM output + Activity ledger for a date range.

1) For each **weekday** from --from through --through, ensure `documents` has
   **`rebalance-decision.json`** with a non-empty `rebalance_table`. When the PM
   artifact is missing or the table is empty, **synthesize** a schema-valid payload
   from `daily_snapshots.snapshot.portfolio.proposed_positions` (else the book in
   `positions` for that date) vs **prior trading day** `positions`, matching
   `execute_at_open` digest logic. Synthetic rows are tagged in
   `meta.tags`: `synthetic_backfill`. Per-ticker **`rebalance_table[].rationale`** is filled
   from published **`asset-recommendations/{DATE}/{TICKER}.json`** (or legacy **`asset-rec/{TICKER}.json`**)
   and **`deliberation-transcript/{DATE}/{TICKER}.json`**
   (same resolution order as `backfill_position_event_reasons.py`), then from a **non-synthetic**
   neighboring **`rebalance-decision.json`** if present. **HOLD** rows use a short default line.

2) Run **`execute_at_open.py --date`** for each day so **`position_events`** matches
   the rebalance table (OPEN/EXIT/TRIM/ADD/HOLD + gap HOLDs from `positions`).

3) Optionally run **`backfill_execution_prices.py`** per day when new rows have
   null opens.

Requires: SUPABASE_URL, SUPABASE_SERVICE_KEY (see config/supabase.env).

Examples:

  python3 scripts/backfill_pm_rebalance_and_activity.py --dry-run
  python3 scripts/backfill_pm_rebalance_and_activity.py --from 2026-04-01 --through 2026-04-15
  python3 scripts/backfill_pm_rebalance_and_activity.py --skip-rebalance-upsert --from 2026-04-01 --through 2026-04-15
  python3 scripts/backfill_pm_rebalance_and_activity.py --no-research-rationale   # skip document extraction (faster)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import date as dt_date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

try:
    import jsonschema  # type: ignore

    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

ROOT = Path(__file__).resolve().parents[1]


def _load_execute_at_open():
    path = ROOT / "scripts" / "execute_at_open.py"
    spec = importlib.util.spec_from_file_location("execute_at_open", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ex = _load_execute_at_open()
_rebalance_payload_for_date = _ex._rebalance_payload_for_date
_rebalance_table_nonempty = _ex._rebalance_table_nonempty
_sb = _ex._sb
build_events_from_digest_snapshot = _ex.build_events_from_digest_snapshot
build_events_from_positions_book = _ex.build_events_from_positions_book

_reasons_mod: Any = None


def _load_reasons_module():
    global _reasons_mod
    if _reasons_mod is not None:
        return _reasons_mod
    path = ROOT / "scripts" / "backfill_position_event_reasons.py"
    spec = importlib.util.spec_from_file_location("backfill_position_event_reasons", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _reasons_mod = mod
    return mod


def _calendar_candidate_dates(anchor_iso: str, forward: int = 10, backward: int = 14) -> List[str]:
    """Same neighborhood search as `backfill_position_event_reasons` (for reference rebalance docs)."""
    try:
        anchor = dt_date.fromisoformat(anchor_iso)
    except ValueError:
        return [anchor_iso]
    out: List[str] = [anchor.isoformat()]
    for i in range(1, forward + 1):
        out.append((anchor + timedelta(days=i)).isoformat())
    for i in range(1, backward + 1):
        out.append((anchor - timedelta(days=i)).isoformat())
    return out


def _clip_rationale(text: str, max_len: int = 2000) -> str:
    s = text.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def _document_payload(sb, date_iso: str, document_key: str) -> Optional[Dict[str, Any]]:
    res = (
        sb.table("documents")
        .select("payload")
        .eq("date", date_iso)
        .eq("document_key", document_key)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    p = rows[0].get("payload")
    return p if isinstance(p, dict) else None


def _per_ticker_research_reason_with_asset_paths(sb, anchor_date: str, ticker: str) -> Optional[str]:
    """
    Like `backfill_position_event_reasons._per_ticker_research_reason`, but also loads
    `asset-recommendations/{DATE}/{TICKER}.json` (DB-first naming used alongside legacy `asset-rec/`).
    """
    reasons_mod = _load_reasons_module()
    for d in _calendar_candidate_dates(anchor_date):
        for dk in (
            f"asset-recommendations/{d}/{ticker}.json",
            f"asset-rec/{ticker}.json",
        ):
            p = _document_payload(sb, d, dk)
            if p:
                t = reasons_mod._text_from_asset_rec(p)
                if t and not _is_stub_line_item(reasons_mod, t):
                    return t
        dk2 = f"deliberation-transcript/{d}/{ticker}.json"
        p2 = _document_payload(sb, d, dk2)
        if p2:
            t2 = reasons_mod._text_from_deliberation(p2, ticker)
            if t2 and not _is_stub_line_item(reasons_mod, t2):
                return t2
    return None


def _rationale_from_pm_memo(sb, d: str, ticker: str, reasons_mod: Any) -> Optional[str]:
    """Same-day `pm-allocation-memo/{date}.json` → body.target_weights_rationale[].rationale."""
    key = f"pm-allocation-memo/{d}.json"
    payload = _document_payload(sb, d, key)
    if not payload or payload.get("doc_type") != "pm_allocation_memo":
        return None
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    tw = body.get("target_weights_rationale")
    if not isinstance(tw, list):
        return None
    for row in tw:
        if not isinstance(row, dict):
            continue
        if str(row.get("ticker") or "").upper() != ticker.upper():
            continue
        r = row.get("rationale")
        if isinstance(r, str) and r.strip():
            return reasons_mod._strip_md_light(r.strip(), 2000)
    return None


def _is_stub_line_item(reasons_mod: Any, text: str) -> bool:
    """Reject terse labels from asset-rec / neighbor rows (e.g. '20% HOLD', '5% NEW')."""
    if not text or not str(text).strip():
        return True
    s = str(text).strip()
    if reasons_mod._is_placeholder_reason(s):
        return True
    if len(s) < 40:
        return True
    if re.match(r"^\d{1,3}(?:\.\d+)?%?\s+(HOLD|NEW|ADD|TRIM|EXIT)\s*$", s, re.IGNORECASE):
        return True
    return False


def _best_nonsynthetic_rebalance_payload(sb, execution_d: str) -> Optional[Dict[str, Any]]:
    """First PM-authored rebalance_decision with a rebalance_table (skips synthetic_backfill tags)."""
    for ds in _calendar_candidate_dates(execution_d):
        p = _rebalance_payload_for_date(sb, ds)
        if not p or p.get("doc_type") != "rebalance_decision":
            continue
        if not _rebalance_table_nonempty(p):
            continue
        if _is_synthetic_payload(p):
            continue
        return p
    return None


def _rationale_for_synthetic_row(
    sb,
    d: str,
    ticker: str,
    event_code: str,
    reb_action: str,
    ref_payload: Optional[Dict[str, Any]],
    use_research: bool,
) -> str:
    """HOLD: short line. Trades: asset-rec → deliberation → neighbor rebalance_table, else fallback."""
    if reb_action == "HOLD" or str(event_code).upper() == "HOLD":
        return "No allocation change vs prior session."

    if not use_research:
        return _clip_rationale(
            f"{ticker} ({reb_action}): Inferred weight change for ledger continuity "
            f"(`--no-research-rationale`; no document extraction)."
        )

    reasons = _load_reasons_module()
    r = _per_ticker_research_reason_with_asset_paths(sb, d, ticker)
    if r:
        return _clip_rationale(r)

    pm = _rationale_from_pm_memo(sb, d, ticker, reasons)
    if pm and not _is_stub_line_item(reasons, pm):
        return _clip_rationale(pm)

    if ref_payload:
        r2 = reasons._rationale_from_payload(ref_payload, ticker)
        if r2 and not _is_stub_line_item(reasons, r2):
            return _clip_rationale(r2)

    return _clip_rationale(
        f"{ticker} ({reb_action}): No line-item rationale found in asset recommendation or "
        f"deliberation transcripts near {d}, and no non-synthetic neighboring rebalance_decision "
        f"carried a row for this ticker. Weights were inferred for ledger continuity."
    )


def _iter_trading_days(start: dt_date, end: dt_date) -> List[str]:
    out: List[str] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _min_max_snapshot_dates(sb) -> Tuple[Optional[str], Optional[str]]:
    res = sb.table("daily_snapshots").select("date").order("date").execute()
    rows = getattr(res, "data", None) or []
    if not rows:
        return None, None
    d0 = rows[0].get("date")
    res2 = sb.table("daily_snapshots").select("date").order("date", desc=True).limit(1).execute()
    rows2 = getattr(res2, "data", None) or []
    d1 = rows2[0].get("date") if rows2 else d0
    return (str(d0)[:10] if d0 else None, str(d1)[:10] if d1 else None)


def _snapshot_portfolio_cash(sb, d: str) -> Optional[float]:
    res = sb.table("daily_snapshots").select("snapshot").eq("date", d).limit(1).execute()
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
    c = port.get("cash_pct")
    try:
        return float(c) if c is not None else None
    except (TypeError, ValueError):
        return None


def _thesis_map_for_date(sb, d: str) -> Dict[str, Optional[str]]:
    res = sb.table("positions").select("ticker,thesis_id").eq("date", d).execute()
    out: Dict[str, Optional[str]] = {}
    for row in getattr(res, "data", None) or []:
        if not isinstance(row, dict):
            continue
        t = row.get("ticker")
        if not t:
            continue
        tid = row.get("thesis_id")
        out[str(t).upper()] = str(tid) if tid else None
    return out


def _event_to_rebalance_action(ev: str) -> str:
    u = str(ev or "").upper()
    if u == "OPEN":
        return "NEW"
    return u


def _validate_rebalance_payload(payload: Dict[str, Any]) -> None:
    if not _HAS_JSONSCHEMA:
        return
    schema_path = ROOT / "templates" / "schemas" / "rebalance-decision.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)


def build_synthetic_rebalance_payload(
    sb,
    d: str,
    events: List[Dict[str, Any]],
    cash_residual_pct: Optional[float],
    thesis_map: Dict[str, Optional[str]],
    source_note: str,
    use_research: bool = True,
) -> Dict[str, Any]:
    ref_payload = _best_nonsynthetic_rebalance_payload(sb, d) if use_research else None
    eps = 1e-4
    rebalance_table: List[Dict[str, Any]] = []
    new_entries: List[str] = []
    exits: List[str] = []
    trade_tickers: List[str] = []
    largest_abs = 0.0
    largest_label = "None"
    for e in events:
        if not isinstance(e, dict):
            continue
        t = str(e.get("ticker") or "").upper()
        ev = str(e.get("event") or "").upper()
        cur = e.get("prev_weight_pct")
        rec = e.get("weight_pct")
        chg = e.get("weight_change_pct")
        try:
            cur_f = float(cur) if cur is not None else None
        except (TypeError, ValueError):
            cur_f = None
        try:
            rec_f = float(rec) if rec is not None else None
        except (TypeError, ValueError):
            rec_f = None
        try:
            chg_f = float(chg) if chg is not None else None
        except (TypeError, ValueError):
            chg_f = None
        if chg_f is None and cur_f is not None and rec_f is not None:
            chg_f = rec_f - cur_f
        action = _event_to_rebalance_action(ev)
        if ev == "OPEN":
            new_entries.append(t)
        if ev == "EXIT":
            exits.append(t)
        if ev != "HOLD":
            trade_tickers.append(t)
        if chg_f is not None and abs(chg_f) > largest_abs + eps:
            largest_abs = abs(chg_f)
            largest_label = f"{t} {chg_f:+.1f} pp"
        rationale = _rationale_for_synthetic_row(sb, d, t, ev, action, ref_payload, use_research)
        rebalance_table.append(
            {
                "ticker": t,
                "current_pct": cur_f,
                "recommended_pct": rec_f,
                "change_pct": chg_f,
                "action": action,
                "urgency": "NORMAL",
                "rationale": rationale,
            }
        )

    pos_rows: List[Dict[str, Any]] = []
    sum_w = 0.0
    for e in events:
        if not isinstance(e, dict):
            continue
        t = str(e.get("ticker") or "").upper()
        rec = e.get("weight_pct")
        try:
            w = float(rec) if rec is not None else 0.0
        except (TypeError, ValueError):
            w = 0.0
        if w <= eps:
            continue
        sum_w += w
        ev = str(e.get("event") or "").upper()
        st = "NEW" if ev == "OPEN" else "HOLD"
        pos_rows.append(
            {
                "ticker": t,
                "weight_pct": w,
                "thesis_id": thesis_map.get(t),
                "status": st,
            }
        )

    # Sleeve weights should sum with cash to ~100; snapshot cash can disagree with inferred sleeves.
    if cash_residual_pct is not None:
        try:
            c_raw = float(cash_residual_pct)
        except (TypeError, ValueError):
            c_raw = max(0.0, 100.0 - sum_w)
        if sum_w + c_raw > 100.01:
            cash = max(0.0, min(100.0, 100.0 - sum_w))
        else:
            cash = max(0.0, min(100.0, c_raw))
    else:
        cash = max(0.0, min(100.0, 100.0 - sum_w))
    total_pct = round(min(100.0, sum_w + cash), 4)

    held_count = sum(1 for e in events if str(e.get("event")).upper() == "HOLD")

    payload: Dict[str, Any] = {
        "schema_version": "1.0",
        "doc_type": "rebalance_decision",
        "date": d,
        "meta": {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "threshold_pct": 5,
            "investor_currency": "USD",
            "tags": ["synthetic_backfill", "digest_or_positions_aligned"],
        },
        "body": {
            "delta_summary": {
                "changes_triggered": int(len(trade_tickers)),
                "held_count": int(held_count),
                "largest_move": largest_label if largest_abs > eps else None,
                "new_entries": new_entries,
                "exits": exits,
            },
            "rebalance_table": rebalance_table,
            "proposed_portfolio": {
                "positions": pos_rows,
                "cash_residual_pct": cash,
                "total_pct": round(total_pct, 4),
            },
            "pm_notes": (
                f"**Backfilled rebalance_decision** for **{d}**.\n\n"
                f"{source_note}\n\n"
                "Per-ticker `rebalance_table` rationales use published **asset recommendation** and "
                "**deliberation** documents when available (see `meta.tags`: synthetic_backfill), "
                "then a non-synthetic neighboring rebalance decision. HOLD lines stay short. "
                "Replace with a PM-authored artifact when available."
            )[:12000],
            "invalidation_watch": [],
        },
    }
    _validate_rebalance_payload(payload)
    return payload


def _is_synthetic_payload(p: Dict[str, Any]) -> bool:
    meta = p.get("meta") if isinstance(p.get("meta"), dict) else {}
    tags = meta.get("tags")
    if not isinstance(tags, list):
        return False
    return "synthetic_backfill" in {str(x) for x in tags}


def _needs_rebalance_fill(sb, d: str, replace_synthetic: bool) -> bool:
    p = _rebalance_payload_for_date(sb, d)
    if not p or p.get("doc_type") != "rebalance_decision":
        return True
    if not _rebalance_table_nonempty(p):
        return True
    if replace_synthetic and _is_synthetic_payload(p):
        return True
    return False


def _upsert_rebalance_document(sb, d: str, payload: Dict[str, Any], dry_run: bool) -> None:
    row = {
        "date": d,
        "title": f"Rebalance decision ({d})",
        "doc_type": "Rebalance Decision",
        "phase": None,
        "category": "portfolio",
        "segment": "rebalance_decision",
        "sector": None,
        "run_type": payload.get("run_type"),
        "document_key": "rebalance-decision.json",
        "payload": payload,
        "content": None,
    }
    if dry_run:
        print(f"  [dry-run] would upsert rebalance-decision.json for {d}")
        return
    sb.table("documents").upsert(row, on_conflict="date,document_key").execute()
    print(f"  ✅ upserted rebalance-decision.json for {d}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", default=None, help="Start YYYY-MM-DD (default: min daily_snapshots.date)")
    ap.add_argument("--through", default=None, help="End YYYY-MM-DD (default: max daily_snapshots.date)")
    ap.add_argument(
        "--replace-synthetic",
        action="store_true",
        help="Re-write rebalance rows previously tagged synthetic_backfill (e.g. after re-running inference).",
    )
    ap.add_argument(
        "--skip-rebalance-upsert",
        action="store_true",
        help="Only run execute_at_open (and optional price backfill); do not write documents.",
    )
    ap.add_argument(
        "--skip-execute-at-open",
        action="store_true",
        help="Only upsert synthetic rebalance_decision rows; do not touch position_events.",
    )
    ap.add_argument(
        "--skip-price-backfill",
        action="store_true",
        help="Do not run backfill_execution_prices.py after each day.",
    )
    ap.add_argument(
        "--no-research-rationale",
        action="store_true",
        help="Do not pull rationales from asset-rec / deliberation / neighbor rebalance (faster; terse text).",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print planned actions only")
    args = ap.parse_args()

    sb = _sb()
    mn, mx = _min_max_snapshot_dates(sb)
    if not mn or not mx:
        print("No rows in daily_snapshots — cannot infer default date range.", file=sys.stderr)
        return 2

    through_s = args.through or mx
    from_s = args.from_date or mn
    start_d = dt_date.fromisoformat(from_s)
    end_d = dt_date.fromisoformat(through_s)
    if start_d > end_d:
        print(f"Nothing to do: --from {from_s} is after --through {through_s}", file=sys.stderr)
        return 2

    days = _iter_trading_days(start_d, end_d)
    if not days:
        print("No trading days in range.")
        return 0

    exe_script = ROOT / "scripts" / "execute_at_open.py"
    price_script = ROOT / "scripts" / "backfill_execution_prices.py"
    py = sys.executable

    print(f"Trading days: {len(days)} ({days[0]} … {days[-1]})")

    for d in days:
        print(f"\n=== {d} ===")
        digest_ev = build_events_from_digest_snapshot(sb, d)
        events = digest_ev or build_events_from_positions_book(sb, d)
        source_note = (
            "Targets from daily_snapshots.portfolio.proposed_positions vs prior session positions."
            if digest_ev
            else "Targets from positions vs prior session (digest proposed_positions missing or empty)."
        )

        if not args.skip_rebalance_upsert and _needs_rebalance_fill(sb, d, args.replace_synthetic):
            if not events:
                print(
                    "  ⚠️  skip rebalance upsert: no inference source (no digest targets and no positions book)"
                )
            else:
                cash_snap = _snapshot_portfolio_cash(sb, d)
                thesis_map = _thesis_map_for_date(sb, d)
                try:
                    payload = build_synthetic_rebalance_payload(
                        sb,
                        d,
                        events,
                        cash_snap,
                        thesis_map,
                        source_note,
                        use_research=not args.no_research_rationale,
                    )
                except Exception as ex:
                    print(f"  ❌ schema/build failed: {ex}", file=sys.stderr)
                else:
                    _upsert_rebalance_document(sb, d, payload, args.dry_run)
        elif not args.skip_rebalance_upsert:
            print("  (rebalance_decision already present; skip upsert)")

        if args.skip_execute_at_open:
            continue

        if args.dry_run:
            print(f"  [dry-run] {py} {exe_script} --date {d}")
            continue

        r1 = subprocess.run(
            [py, str(exe_script), "--date", d, "--no-rebalance-fallback"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        out1 = (r1.stdout or "") + (r1.stderr or "")
        print(out1.rstrip())
        if r1.returncode != 0:
            print(f"  ❌ execute_at_open exit {r1.returncode}", file=sys.stderr)
            continue

        wrote = "recorded" in out1.lower()
        if not args.skip_price_backfill and wrote:
            r3 = subprocess.run(
                [py, str(price_script), "--date", d],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            po = (r3.stdout or "").strip()
            if po:
                print(po)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

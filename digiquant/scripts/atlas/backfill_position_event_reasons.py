#!/usr/bin/env python3
"""
Fill or repair `position_events.reason` from published research artifacts:

1. **Per-ticker (preferred):** `asset-recommendations/{DATE}/{TICKER}.json` or `asset-rec/{TICKER}.json` → `body.verdict.rationale` (or bull_case),
   then `deliberation-transcript/{DATE}/{TICKER}.json` → `body.final_decisions[].pm_decision`.
2. **Session fallback:** `rebalance-decision.json` → `rebalance_table[].rationale` / pm_notes.

Resolves rebalance JSON the same way as `execute_at_open.py` (prior sessions + nearby calendar
dates) so weekend rows still link to an adjacent publish.

Usage:
  python3 scripts/backfill_position_event_reasons.py --dry-run
  python3 scripts/backfill_position_event_reasons.py --repair-placeholders
  python3 scripts/backfill_position_event_reasons.py --enrich-existing   # refresh rows with short/generic rebalance-only text
  python3 scripts/backfill_position_event_reasons.py --force
  python3 scripts/backfill_position_event_reasons.py --no-enrich        # rebalance table only
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date as dt_date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import execute_at_open as eat  # noqa: E402


def _rebalance_json_payload_for_date(sb, rebalance_date: str) -> Optional[Dict[str, Any]]:
    """Load only `rebalance-decision.json` (canonical table + rationales). Skip .md stubs."""
    res = (
        sb.table("documents")
        .select("payload")
        .eq("date", rebalance_date)
        .eq("document_key", "rebalance-decision.json")
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    p = rows[0].get("payload")
    if isinstance(p, dict) and p.get("doc_type") == "rebalance_decision":
        return p
    return None

# Reasons produced by tearsheet diffs or stale pipelines (single token, not real prose).
_PLACEHOLDER_UPPER = frozenset(
    {
        "HOLD",
        "ADD",
        "TRIM",
        "OPEN",
        "EXIT",
        "REBALANCE",
        "NEW",
        "",
    }
)


def _is_placeholder_reason(reason: Any) -> bool:
    if reason is None:
        return True
    if not isinstance(reason, str):
        return True
    s = reason.strip()
    if not s:
        return True
    if s.upper() in _PLACEHOLDER_UPPER:
        return True
    low = s.lower()
    if "legacy markdown" in low or "see pm notes" in low:
        return True
    # Very short all-caps token(s) only — likely action labels, not PM prose.
    if len(s) <= 12 and s.replace(" ", "").isalpha() and s.upper() == s:
        return True
    return False


def _normalize_pm_snippet(text: str, max_len: int = 420) -> str:
    t = text.replace("\r\n", "\n").strip()
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _fallback_rationale_from_payload(payload: Dict[str, Any], ticker: str) -> Optional[str]:
    """When rebalance_table row has no rationale, use session-level PM copy (trimmed)."""
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    ds = body.get("delta_summary") if isinstance(body.get("delta_summary"), dict) else {}
    lm = ds.get("largest_move")
    if isinstance(lm, str) and lm.strip() and lm.strip().lower() not in ("none", "null", "n/a"):
        s = lm.strip()
        if len(s) > 400:
            s = s[:399] + "…"
        return f"{ticker}: {s}"

    notes = body.get("pm_notes")
    if isinstance(notes, str) and notes.strip():
        snippet = _normalize_pm_snippet(notes, 450)
        if snippet:
            return f"{ticker} — {snippet}"
    return None


def _rationale_from_payload(payload: Dict[str, Any], ticker: str) -> Optional[str]:
    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    table = body.get("rebalance_table")
    if isinstance(table, list):
        for row in table:
            if not isinstance(row, dict):
                continue
            if row.get("ticker") != ticker:
                continue
            r = row.get("rationale")
            if isinstance(r, str) and r.strip():
                return r.strip()
            return _fallback_rationale_from_payload(payload, ticker)
        # Ticker not listed — still use session-level fallback
        return _fallback_rationale_from_payload(payload, ticker)
    return _fallback_rationale_from_payload(payload, ticker)


def _resolve_rebalance_doc_date(sb, execution_d: str) -> Optional[str]:
    if _rebalance_json_payload_for_date(sb, execution_d):
        return execution_d
    d = execution_d
    for _ in range(16):
        pd = eat._prior_trading_date(d)
        if not pd or pd == d:
            break
        if _rebalance_json_payload_for_date(sb, pd):
            return pd
        d = pd
    return None


def _find_rebalance_payload_near_calendar(
    sb, anchor_iso: str
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Find rebalance_decision JSON near anchor date: same day, then +1..+10 calendar (weekend
    rows → next publish), then -1..-14 (prior publish).
    """
    try:
        anchor = dt_date.fromisoformat(anchor_iso)
    except ValueError:
        return None

    order: List[dt_date] = [anchor]
    for i in range(1, 11):
        order.append(anchor + timedelta(days=i))
    for i in range(1, 15):
        order.append(anchor - timedelta(days=i))

    seen = set()
    for d in order:
        if d in seen:
            continue
        seen.add(d)
        ds = d.isoformat()
        p = _rebalance_json_payload_for_date(sb, ds)
        if isinstance(p, dict) and p.get("doc_type") == "rebalance_decision":
            return (ds, p)
    return None


def _best_payload_for_row(sb, execution_d: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Prefer prior-trading chain (execute_at_open parity), then calendar-neighbor search."""
    rd = _resolve_rebalance_doc_date(sb, execution_d)
    if rd:
        p = _rebalance_json_payload_for_date(sb, rd)
        if isinstance(p, dict):
            return (rd, p)
    return _find_rebalance_payload_near_calendar(sb, execution_d)


def _calendar_candidate_dates(anchor_iso: str, forward: int = 10, backward: int = 14) -> List[str]:
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


def _document_payload_for_key(sb, date_iso: str, document_key: str) -> Optional[Dict[str, Any]]:
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


def _strip_md_light(s: str, max_len: int) -> str:
    t = s.replace("\r\n", "\n").strip()
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _text_from_asset_rec(payload: Dict[str, Any]) -> Optional[str]:
    """Schema: body.verdict.rationale; legacy flat payloads with minimal fields."""
    body = payload.get("body")
    if isinstance(body, dict):
        verdict = body.get("verdict")
        if isinstance(verdict, dict):
            r = verdict.get("rationale")
            if isinstance(r, str) and r.strip():
                return _strip_md_light(r.strip(), 2000)
        for key in ("summary", "investment_thesis", "one_liner"):
            v = body.get(key)
            if isinstance(v, str) and v.strip():
                return _strip_md_light(v.strip(), 1200)
        bc = body.get("bull_case")
        if isinstance(bc, list) and bc:
            first = bc[0]
            if isinstance(first, str) and first.strip():
                return _strip_md_light(first.strip(), 800)
    # Flat / partial publishes
    for key in ("rationale", "summary"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return _strip_md_light(v.strip(), 600)
    return None


def _text_from_deliberation(payload: Dict[str, Any], ticker: str) -> Optional[str]:
    body = payload.get("body")
    if not isinstance(body, dict):
        return None
    fd = body.get("final_decisions")
    if isinstance(fd, list):
        for item in fd:
            if not isinstance(item, dict):
                continue
            if item.get("ticker") != ticker:
                continue
            pm = item.get("pm_decision")
            if isinstance(pm, str) and pm.strip():
                return _strip_md_light(pm.strip(), 1200)
            ar = item.get("analyst_recommendation")
            if isinstance(ar, str) and ar.strip():
                return _strip_md_light(ar.strip(), 1000)
    ts = body.get("trigger_summary")
    if isinstance(ts, list) and ts:
        parts = [t.strip() for t in ts if isinstance(t, str) and t.strip()]
        if parts:
            return _strip_md_light(" ".join(parts[:2]), 1000)
    return None


def _per_ticker_research_reason(sb, anchor_date: str, ticker: str) -> Optional[str]:
    """
    Prefer asset recommendation, then deliberation transcript, searching the same calendar
    neighborhood as rebalance resolution.

    Tries `asset-recommendations/{DATE}/{TICKER}.json` first (DB-first layout), then legacy
    `asset-rec/{TICKER}.json` for the same documents.date.
    """
    for d in _calendar_candidate_dates(anchor_date):
        for ak in (
            f"asset-recommendations/{d}/{ticker}.json",
            f"asset-rec/{ticker}.json",
        ):
            p = _document_payload_for_key(sb, d, ak)
            if p:
                t = _text_from_asset_rec(p)
                if t:
                    return t
        dk = f"deliberation-transcript/{d}/{ticker}.json"
        p2 = _document_payload_for_key(sb, d, dk)
        if p2:
            t2 = _text_from_deliberation(p2, ticker)
            if t2:
                return t2
    return None


def _pick_reason(
    sb,
    event_date: str,
    ticker: str,
    rebalance_payload: Dict[str, Any],
    enrich: bool,
) -> Optional[str]:
    if enrich:
        r = _per_ticker_research_reason(sb, event_date, ticker)
        if r:
            return r
    return _rationale_from_payload(rebalance_payload, ticker)


def _is_short_generic_rebalance_only(reason: str, threshold: int = 90) -> bool:
    """True when reason is likely a duplicated session line (enrich-existing target)."""
    s = reason.strip()
    if len(s) >= threshold:
        return False
    low = s.lower()
    if "session rebalance" in low or "monitoring " in low:
        return True
    return len(s) <= 45


def _needs_update(
    reason: Any, force: bool, repair_placeholders: bool
) -> bool:
    if force:
        return True
    if repair_placeholders:
        return _is_placeholder_reason(reason)
    if reason is None:
        return True
    if isinstance(reason, str) and not reason.strip():
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Backfill or repair position_events.reason from rebalance_decision JSON in documents."
    )
    ap.add_argument("--dry-run", action="store_true", help="Print counts only; no DB writes.")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite every row where a rebalance payload yields text (use with care).",
    )
    ap.add_argument(
        "--repair-placeholders",
        action="store_true",
        help="Only replace trivial/placeholder reasons (HOLD/ADD/…, very short ALLCAPS). Recommended.",
    )
    ap.add_argument(
        "--enrich-existing",
        action="store_true",
        help="Rewrite short/generic rebalance-only lines when asset-rec or deliberation has richer per-ticker text.",
    )
    ap.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip asset-rec / deliberation; use rebalance_decision JSON only.",
    )
    ap.add_argument("--limit", type=int, default=0, help="Max rows to update (0 = no cap).")
    args = ap.parse_args()

    if args.force and args.repair_placeholders:
        print("error: use only one of --force or --repair-placeholders", file=sys.stderr)
        return 2
    if args.force and args.enrich_existing:
        print("error: use only one of --force or --enrich-existing", file=sys.stderr)
        return 2
    if args.repair_placeholders and args.enrich_existing:
        print("error: use only one of --repair-placeholders or --enrich-existing", file=sys.stderr)
        return 2

    sb = eat._sb()
    applied = 0
    would_apply = 0
    skipped_no_doc = 0
    skipped_no_rationale = 0
    examined = 0

    start = 0
    page = 800
    while True:
        res = (
            sb.table("position_events")
            .select("id,date,ticker,event,reason")
            .order("date", desc=True)
            .range(start, start + page - 1)
            .execute()
        )
        rows: List[Dict[str, Any]] = getattr(res, "data", None) or []
        if not rows:
            break

        for row in rows:
            examined += 1
            rid = row.get("id")
            d = row.get("date")
            ticker = row.get("ticker")
            reason = row.get("reason")
            if not rid or not d or not ticker:
                continue

            if args.force:
                pass
            elif args.repair_placeholders:
                if not _needs_update(reason, False, True):
                    continue
            elif args.enrich_existing:
                if args.no_enrich:
                    continue
                if not (
                    _is_placeholder_reason(reason)
                    or _is_short_generic_rebalance_only(reason or "")
                ):
                    continue
            else:
                if not _needs_update(reason, False, False):
                    continue

            enrich = not args.no_enrich
            found = _best_payload_for_row(sb, str(d))
            if not found:
                skipped_no_doc += 1
                continue
            _doc_date, payload = found
            computed = _pick_reason(sb, str(d), str(ticker), payload, enrich)
            if not computed:
                skipped_no_rationale += 1
                continue

            if computed.strip() == (reason or "").strip():
                continue

            if args.dry_run:
                would_apply += 1
            else:
                sb.table("position_events").update({"reason": computed}).eq("id", rid).execute()
                applied += 1

            if args.limit and (would_apply if args.dry_run else applied) >= args.limit:
                print(
                    f"Done (limit {args.limit}): examined={examined} "
                    f"would_apply={would_apply} applied={applied} "
                    f"no_doc={skipped_no_doc} no_rationale={skipped_no_rationale}"
                )
                return 0

        if len(rows) < page:
            break
        start += page

    mode = "dry-run" if args.dry_run else "applied"
    print(
        f"✅ backfill_position_event_reasons ({mode}): examined={examined} "
        f"would_apply={would_apply} applied={applied} "
        f"no_rebalance_doc={skipped_no_doc} no_rationale_in_table={skipped_no_rationale}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

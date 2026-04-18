#!/usr/bin/env python3
"""
materialize_snapshot.py

DB-first digest compiler.

Supports:
- Pushing a full, materialized digest snapshot JSON for a date into Supabase.
- (Optionally) applying a small delta-ops file to a baseline snapshot to produce
  today's full snapshot.

This script is the replacement for filesystem-based DIGEST.md materialization.
It does not read or write the local agent scratch tree (see `data/agent-cache/`).
"""

import argparse
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from supabase import create_client  # type: ignore

    _HAS_SUPABASE = True
except ImportError:
    _HAS_SUPABASE = False

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass


ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "templates" / "digest-snapshot-schema.json"


def _require_supabase() -> None:
    if not _HAS_SUPABASE:
        raise RuntimeError("Supabase SDK not installed. Run: pip install supabase")
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        raise RuntimeError("Missing SUPABASE_URL and/or SUPABASE_SERVICE_KEY in environment.")


def _sb():
    _require_supabase()
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _safe_upsert(table: str, row: Dict[str, Any], on_conflict: str) -> None:
    """Upsert with graceful fallback when schema constraints don't match.

    on_conflict is a comma-separated list of key columns.
    """
    sb = _sb()
    try:
        sb.table(table).upsert(row, on_conflict=on_conflict).execute()
        return
    except Exception as e:
        msg = str(e)
        # Postgres error 42P10: ON CONFLICT target does not match a unique/exclusion constraint.
        if "42P10" not in msg and "no unique or exclusion constraint" not in msg.lower():
            raise

        # Fallback: SELECT then UPDATE or INSERT.
        key_cols = [c.strip() for c in on_conflict.split(",") if c.strip()]
        if not key_cols:
            raise

        q = sb.table(table).select(key_cols[0])
        for c in key_cols:
            if row.get(c) is None:
                raise
            q = q.eq(c, row[c])
        existing = q.limit(1).execute()
        data = getattr(existing, "data", None) or []
        if data:
            uq = sb.table(table).update(row)
            for c in key_cols:
                uq = uq.eq(c, row[c])
            uq.execute()
        else:
            sb.table(table).insert(row).execute()


def _load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_minimal(snapshot: Dict[str, Any]) -> None:
    # Avoid adding new Python deps (jsonschema). Enforce a minimal contract.
    # Note: `portfolio` is optional — Track A (research-only) snapshots do not include it.
    required = [
        "schema_version",
        "date",
        "run_type",
        "baseline_date",
        "regime",
        "market_data",
        "segment_biases",
        "sector_scorecard",
        "theses",
        "actionable",
        "risks",
        "narrative",
    ]
    missing = [k for k in required if k not in snapshot]
    if missing:
        raise ValueError(f"Snapshot missing required keys: {missing}")

    if snapshot["date"] is None or not isinstance(snapshot["date"], str):
        raise ValueError("snapshot.date must be a YYYY-MM-DD string")
    if snapshot["run_type"] not in ("baseline", "delta"):
        raise ValueError("snapshot.run_type must be baseline|delta")


def _json_pointer_tokens(ptr: str) -> List[str]:
    if not ptr.startswith("/"):
        raise ValueError(f"Invalid path (must start with '/'): {ptr}")
    # JSON Pointer unescaping: ~1 => /, ~0 => ~
    parts = ptr.lstrip("/").split("/")
    return [p.replace("~1", "/").replace("~0", "~") for p in parts if p != ""]


def _get_parent_and_key(doc: Any, path: str) -> Tuple[Any, str]:
    toks = _json_pointer_tokens(path)
    if not toks:
        raise ValueError("Path refers to document root; not allowed for ops")
    cur = doc
    for t in toks[:-1]:
        if isinstance(cur, list):
            idx = int(t)
            cur = cur[idx]
        else:
            if t not in cur or cur[t] is None:
                cur[t] = {}
            cur = cur[t]
    return cur, toks[-1]


def apply_ops(base: Dict[str, Any], ops: List[Dict[str, Any]]) -> Dict[str, Any]:
    doc: Any = deepcopy(base)
    for op in ops:
        op_type = op.get("op")
        path = op.get("path")
        if not op_type or not path:
            raise ValueError(f"Invalid op (missing op/path): {op}")

        parent, key = _get_parent_and_key(doc, path)
        if op_type == "set":
            value = op.get("value")
            if isinstance(parent, list):
                parent[int(key)] = value
            else:
                parent[key] = value
        elif op_type == "append":
            value = op.get("value")
            target: Any
            if isinstance(parent, list):
                target = parent[int(key)]
            else:
                target = parent.get(key)
            if target is None:
                target = []
                if isinstance(parent, list):
                    parent[int(key)] = target
                else:
                    parent[key] = target
            if not isinstance(target, list):
                raise ValueError(f"append op requires list at {path}")
            target.append(value)
        elif op_type == "remove":
            if isinstance(parent, list):
                parent.pop(int(key))
            else:
                parent.pop(key, None)
        else:
            raise ValueError(f"Unknown op type: {op_type}")
    return doc


def _normalize_sector_scorecard(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Backwards-compatible adapter for delta ops.

    Older snapshots stored `sector_scorecard` as a list of rows:
      [{"sector":"Energy","etf":"XLE",...}, ...]

    Newer delta ops address it as an object keyed by slug:
      /sector_scorecard/energy
      /sector_scorecard/consumer_staples
    """
    sc = snapshot.get("sector_scorecard")
    if not isinstance(sc, list):
        return snapshot

    def _slug(s: str) -> str:
        s = s.strip().lower()
        s = s.replace("&", "and")
        s = re.sub(r"[^a-z0-9]+", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        return s

    out: Dict[str, Any] = {}
    for row in sc:
        if not isinstance(row, dict):
            continue
        sector = row.get("sector")
        if isinstance(sector, str) and sector.strip():
            out[_slug(sector)] = row

    snapshot["sector_scorecard"] = out
    return snapshot


def render_digest_markdown(snapshot: Dict[str, Any]) -> str:
    # Keep this intentionally deterministic and minimal. The UI can render JSON directly,
    # but a markdown view helps with auditing and a “Library” experience.
    date = snapshot["date"]
    regime = snapshot["regime"]
    portfolio = snapshot["portfolio"]
    lines: List[str] = []

    lines.append(f"# DIGEST — {date}")
    lines.append("")
    lines.append("## Market Regime Snapshot")
    lines.append(f"**Overall Bias**: {regime.get('bias','')}\n")
    dom = regime.get("dominant_force")
    if dom:
        lines.append(f"- **Dominant force**: {dom}")
    lines.append(f"- **Label**: {regime.get('label','')}")
    lines.append(f"- **Conviction**: {regime.get('conviction','')}")
    lines.append("")
    if regime.get("summary"):
        lines.append(regime["summary"])
        lines.append("")

    lines.append("## Actionable Summary")
    for item in snapshot.get("actionable", [])[:10]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Risk Radar")
    for item in snapshot.get("risks", [])[:10]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Sector Scorecard")
    lines.append("| Sector | ETF | Bias | Confidence | Key Driver |")
    lines.append("|---|---|---|---|---|")
    sc = snapshot.get("sector_scorecard", [])
    if isinstance(sc, dict):
        rows = list(sc.values())
    else:
        rows = sc
    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {row.get('sector','')} | {row.get('etf','')} | {row.get('bias','')} | {row.get('confidence','')} | {row.get('key_driver','')} |"
        )
    lines.append("")

    lines.append("## Portfolio Positioning")
    lines.append(f"**Portfolio Posture**: {portfolio.get('posture','')}")
    if portfolio.get("cash_pct") is not None:
        lines.append(f"**Cash %**: {portfolio.get('cash_pct')}")
    lines.append("")
    lines.append("| Ticker | Weight% | Action | Rationale |")
    lines.append("|---|---:|---|---|")
    for p in portfolio.get("positions", []):
        lines.append(
            f"| {p.get('ticker','')} | {p.get('weight_pct','')} | {p.get('action','')} | {p.get('rationale','')} |"
        )
    lines.append("")

    # Narrative blocks
    nar = snapshot.get("narrative", {})
    if isinstance(nar, dict):
        lines.append("## Narrative")
        lines.append("")
        for key in ["alt_data", "institutional", "macro", "us_equities", "thesis_tracker", "portfolio_recs"]:
            val = nar.get(key)
            if val:
                title = key.replace("_", " ").title()
                lines.append(f"### {title}")
                lines.append(val.strip())
                lines.append("")

        ac = nar.get("asset_classes")
        if isinstance(ac, dict) and any(ac.get(k) for k in ac.keys()):
            lines.append("### Asset Classes")
            for k in ["bonds", "commodities", "forex", "crypto", "international"]:
                v = ac.get(k)
                if v:
                    lines.append(f"#### {k.title()}")
                    lines.append(v.strip())
                    lines.append("")

    return "\n".join(lines).strip() + "\n"


def _fetch_daily_snapshot(date_str: str) -> Optional[Dict[str, Any]]:
    res = _sb().table("daily_snapshots").select("date, run_type, baseline_date, snapshot").eq("date", date_str).single().execute()
    data = getattr(res, "data", None)
    if not data:
        return None
    snap = data.get("snapshot")
    return snap if isinstance(snap, dict) else None


def _upsert_snapshot(snapshot: Dict[str, Any], digest_markdown: Optional[str]) -> None:
    # Keep daily_snapshots backwards compatible: populate existing columns too.
    row = {
        "date": snapshot["date"],
        "run_type": snapshot["run_type"],
        "baseline_date": snapshot.get("baseline_date"),
        "regime": snapshot.get("regime", {}),
        "market_data": snapshot.get("market_data", {}),
        "segment_biases": snapshot.get("segment_biases", {}),
        "actionable": snapshot.get("actionable", []),
        "risks": snapshot.get("risks", []),
        "snapshot": snapshot,
        "digest_markdown": digest_markdown,
    }
    try:
        _safe_upsert("daily_snapshots", row, on_conflict="date")
    except Exception as e:
        # Migration safety: allow publishing even if new columns aren't deployed yet.
        msg = str(e)
        fallback = {k: v for k, v in row.items() if k not in ("snapshot", "digest_markdown")}
        _safe_upsert("daily_snapshots", fallback, on_conflict="date")
        if "snapshot" in msg or "digest_markdown" in msg or "42703" in msg:
            print(
                "⚠️  daily_snapshots upserted without snapshot/digest_markdown "
                "(migration 008 not applied yet).",
                file=sys.stderr,
            )
        else:
            print(
                "⚠️  daily_snapshots upserted in compatibility mode.",
                file=sys.stderr,
            )

    # Positions table: store today’s portfolio positions.
    positions = snapshot.get("portfolio", {}).get("positions", [])
    pos_rows = []
    for p in positions:
        t = p.get("ticker")
        try:
            w = float(p.get("weight_pct", 0) or 0)
        except (TypeError, ValueError):
            w = 0.0
        if t != "CASH" and w == 0.0:
            continue
        pos_rows.append(
            {
                "date": snapshot["date"],
                "ticker": t,
                "name": p.get("name"),
                "category": p.get("category"),
                "weight_pct": w,
                "thesis_id": p.get("thesis_id"),
                "rationale": p.get("rationale"),
                "current_price": p.get("current_price"),
                "entry_price": p.get("entry_price"),
                "entry_date": p.get("entry_date"),
            }
        )
    if pos_rows:
        for r in pos_rows:
            _safe_upsert("positions", r, on_conflict="date,ticker")
        # Remove stale tickers for this date (carry-forward refresh can leave exited names).
        keep_tickers = {r["ticker"] for r in pos_rows if r.get("ticker")}
        d = snapshot["date"]
        sb = _sb()
        existing = sb.table("positions").select("ticker").eq("date", d).execute()
        for row in getattr(existing, "data", None) or []:
            tk = row.get("ticker")
            if tk and tk not in keep_tickers:
                sb.table("positions").delete().eq("date", d).eq("ticker", tk).execute()

    # Theses table
    thesis_rows = []
    for t in snapshot.get("theses", []):
        thesis_rows.append(
            {
                "date": snapshot["date"],
                "thesis_id": t.get("id"),
                "name": t.get("name", ""),
                "vehicle": t.get("vehicle"),
                "invalidation": t.get("invalidation"),
                "status": t.get("status"),
                "notes": t.get("notes"),
            }
        )
    if thesis_rows:
        for r in thesis_rows:
            _safe_upsert("theses", r, on_conflict="date,thesis_id")

    # Documents: structured payload + rendered markdown for Research Library.
    if digest_markdown:
        doc_row = {
            "date": snapshot["date"],
            "title": "Digest",
            "doc_type": "Daily Digest",
            "phase": 7,
            "category": "synthesis",
            "segment": "digest",
            "sector": None,
            "run_type": snapshot["run_type"],
            "document_key": "digest",
            "payload": snapshot,
            "content": digest_markdown,
        }
        _safe_upsert("documents", doc_row, on_conflict="date,document_key")


def sync_digest_markdown_from_documents(dates: List[str]) -> None:
    """Copy documents.content (DIGEST.md) into daily_snapshots.digest_markdown when missing."""
    sb = _sb()
    q = sb.table("documents").select("date,content").eq("document_key", "digest")
    if dates:
        q = q.in_("date", dates)
    res = q.execute()
    docs = getattr(res, "data", None) or []
    for doc in docs:
        date_str = doc.get("date")
        content = doc.get("content")
        if not date_str or not content:
            continue
        sb.table("daily_snapshots").update({"digest_markdown": content}).eq("date", date_str).execute()
        print(f"✅ synced digest_markdown from documents for {date_str}")


def backfill_digest_markdown(dates: List[str]) -> None:
    """Re-render digest_markdown from stored snapshot jsonb; sync documents (DIGEST.md)."""
    sb = _sb()
    q = sb.table("daily_snapshots").select("date,run_type,snapshot")
    if dates:
        q = q.in_("date", dates)
    else:
        q = q.not_.is_("snapshot", "null")
    res = q.execute()
    rows = getattr(res, "data", None) or []
    if not rows:
        print("No daily_snapshots rows match (need non-null snapshot).")
        return
    for r in rows:
        snap = r.get("snapshot")
        date_str = r.get("date")
        if not isinstance(snap, dict):
            print(f"⚠️  skip {date_str}: snapshot missing or not an object", file=sys.stderr)
            continue
        try:
            _validate_minimal(snap)
        except ValueError as e:
            print(f"⚠️  skip {date_str}: {e}", file=sys.stderr)
            continue
        dm = render_digest_markdown(snap)
        sb.table("daily_snapshots").update({"digest_markdown": dm}).eq("date", date_str).execute()
        run_type = snap.get("run_type") or r.get("run_type") or "baseline"
        doc_row = {
            "date": date_str,
            "title": "Digest",
            "doc_type": "Daily Digest",
            "phase": 7,
            "category": "synthesis",
            "segment": "digest",
            "sector": None,
            "run_type": run_type,
            "document_key": "digest",
            "payload": snap,
            "content": dm,
        }
        _safe_upsert("documents", doc_row, on_conflict="date,document_key")
        print(f"✅ backfilled digest_markdown + document for {date_str}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="materialize_snapshot.py — DB-first digest compiler (baseline + delta ops → full snapshot)"
    )
    parser.add_argument(
        "--date",
        help="Target date (YYYY-MM-DD); required unless using --backfill-digest-markdown",
    )
    parser.add_argument(
        "--snapshot",
        dest="snapshot_path",
        help="Path to a full snapshot JSON file to push (materialized).",
    )
    parser.add_argument(
        "--snapshot-json",
        dest="snapshot_json",
        help="Inline full snapshot JSON payload (string). Useful for copy/paste from an agent output.",
    )
    parser.add_argument(
        "--baseline-date",
        dest="baseline_date",
        help="Which daily_snapshots row to load when applying --ops (prior day for chained deltas; "
        "Sunday baseline when ops are authored against the weekly baseline). "
        "Stored snapshot.baseline_date comes from the ops JSON envelope when present.",
    )
    parser.add_argument(
        "--ops",
        dest="ops_path",
        help="Path to delta ops JSON (applied to baseline snapshot from Supabase).",
    )
    parser.add_argument(
        "--ops-json",
        dest="ops_json",
        help="Inline ops JSON payload (string) containing an 'ops' array. Useful for copy/paste from an agent output.",
    )
    parser.add_argument("--no-markdown", action="store_true", help="Do not render/store digest_markdown")
    parser.add_argument("--dry-run", action="store_true", help="Compile only; print snapshot JSON to stdout")
    parser.add_argument(
        "--backfill-digest-markdown",
        nargs="*",
        default=None,
        metavar="DATE",
        help="Re-render digest_markdown from snapshot jsonb for each DATE; "
        "with no DATEs, backfill every row that has a non-null snapshot.",
    )
    parser.add_argument(
        "--sync-digest-from-documents",
        nargs="*",
        default=None,
        metavar="DATE",
        help="Copy DIGEST.md from documents table into digest_markdown (when snapshot jsonb is empty). "
        "Optional DATE list; omit to sync all DIGEST.md rows.",
    )
    args = parser.parse_args()

    if args.sync_digest_from_documents is not None:
        sync_digest_markdown_from_documents(list(args.sync_digest_from_documents))
        return

    if args.backfill_digest_markdown is not None:
        backfill_digest_markdown(list(args.backfill_digest_markdown))
        return

    if not args.date:
        raise ValueError(
            "--date is required unless using --backfill-digest-markdown or --sync-digest-from-documents"
        )

    date_str = args.date

    if args.snapshot_json:
        snapshot = json.loads(args.snapshot_json)
        if not isinstance(snapshot, dict):
            raise ValueError("--snapshot-json must be a JSON object")
        snapshot["date"] = date_str
    elif args.snapshot_path:
        snapshot = _load_json_file(Path(args.snapshot_path))
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot file must contain a JSON object")
        snapshot["date"] = date_str
    else:
        if not args.baseline_date or (not args.ops_path and not args.ops_json):
            raise ValueError("Either (--snapshot/--snapshot-json) OR (--baseline-date AND (--ops/--ops-json)) is required")
        baseline = _fetch_daily_snapshot(args.baseline_date)
        if not baseline:
            raise RuntimeError(f"Baseline snapshot not found in Supabase for {args.baseline_date}")
        baseline = _normalize_sector_scorecard(baseline)
        if args.ops_json:
            ops_payload = json.loads(args.ops_json)
        else:
            ops_payload = _load_json_file(Path(args.ops_path))
        ops = ops_payload.get("ops") if isinstance(ops_payload, dict) else None
        if not isinstance(ops, list):
            raise ValueError("ops file must be an object containing an 'ops' array")
        snapshot = apply_ops(baseline, ops)
        snapshot["date"] = date_str
        snapshot["run_type"] = "delta"
        # Row loaded from DB (`--baseline-date`) may be yesterday's full snapshot; weekly Sunday
        # baseline is often carried in the delta request JSON.
        if isinstance(ops_payload, dict) and ops_payload.get("baseline_date"):
            snapshot["baseline_date"] = ops_payload["baseline_date"]
        else:
            snapshot["baseline_date"] = args.baseline_date

    _validate_minimal(snapshot)

    digest_md = None if args.no_markdown else render_digest_markdown(snapshot)
    snapshot["generated_at"] = datetime.now().isoformat()

    if args.dry_run:
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
        return

    _upsert_snapshot(snapshot, digest_md)
    print(f"✅ Supabase upsert complete for {date_str}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


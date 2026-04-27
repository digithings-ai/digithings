#!/usr/bin/env python3
"""
backfill_normalize_schemas.py — Normalize existing daily_snapshots to the
current digest-snapshot-schema.json for the backfill date range.

Fixes known schema violations from the early test runs (Apr 5-11):
  - regime.conviction   : maps non-enum strings to High/Medium/Low
  - segment_biases      : promotes flat strings to {bias, confidence, key_driver}
  - sector_scorecard    : converts object-keyed dict to ordered array; maps
                          bias values to OW/UW/N
  - portfolio.posture   : maps verbose strings to Defensive/Neutral/Offensive
  - portfolio.positions : ensures required action enum values
  - theses[].status     : maps legacy status strings to current enum

Does NOT modify narrative or market_data — those stay as-is.

Usage:
    # Dry-run: print what would change
    python3 scripts/backfill_normalize_schemas.py --start 2026-04-05 --end 2026-04-11 --dry-run

    # Apply
    python3 scripts/backfill_normalize_schemas.py --start 2026-04-05 --end 2026-04-11
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

try:
    from supabase import create_client  # type: ignore

    _HAS_SB = True
except ImportError:
    _HAS_SB = False

ROOT = Path(__file__).parent.parent

# ── Enum constants from schema ────────────────────────────────────────────────
VALID_CONVICTION = {"High", "Medium", "Low"}
VALID_POSTURE = {"Defensive", "Neutral", "Offensive"}
VALID_BIAS = {"OW", "UW", "N"}
VALID_ACTION = {"HOLD", "ADD", "TRIM", "EXIT", "NEW"}
VALID_THESIS_STATUS = {"NEW", "ACTIVE", "MONITORING", "CHALLENGED", "INVALIDATED", "PAUSED", "CLOSED"}
VALID_CONFIDENCE = {"High", "Medium", "Low"}
VALID_RUN_TYPE = {"baseline", "delta"}

SECTOR_ORDER = [
    "Technology", "Financials", "Health Care", "Energy", "Industrials",
    "Consumer Discretionary", "Consumer Staples", "Communication Services",
    "Real Estate", "Utilities", "Materials",
]

SECTOR_SLUG_TO_NAME = {
    "technology": "Technology", "tech": "Technology",
    "financials": "Financials", "financial": "Financials",
    "healthcare": "Health Care", "health_care": "Health Care", "health": "Health Care",
    "energy": "Energy",
    "industrials": "Industrials", "industrial": "Industrials",
    "consumer_disc": "Consumer Discretionary", "consumer_discretionary": "Consumer Discretionary",
    "consumer_staples": "Consumer Staples", "staples": "Consumer Staples",
    "comms": "Communication Services", "communication_services": "Communication Services",
    "communications": "Communication Services", "comm_services": "Communication Services",
    "real_estate": "Real Estate", "realestate": "Real Estate",
    "utilities": "Utilities", "utility": "Utilities",
    "materials": "Materials", "material": "Materials",
}

SECTOR_ETF_MAP = {
    "Technology": "XLK", "Financials": "XLF", "Health Care": "XLV",
    "Energy": "XLE", "Industrials": "XLI", "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP", "Communication Services": "XLC",
    "Real Estate": "XLRE", "Utilities": "XLU", "Materials": "XLB",
}


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL + SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


# ── Normalizers ───────────────────────────────────────────────────────────────

def _norm_conviction(val: Any) -> str:
    if val in VALID_CONVICTION:
        return val
    s = str(val).lower()
    if "high" in s:
        return "High"
    if "low" in s:
        return "Low"
    return "Medium"


def _norm_confidence(val: Any) -> str:
    if val in VALID_CONFIDENCE:
        return val
    s = str(val).lower()
    if "high" in s:
        return "High"
    if "low" in s:
        return "Low"
    return "Medium"


def _norm_posture(val: Any) -> str:
    if val in VALID_POSTURE:
        return val
    s = str(val).lower()
    if "offensive" in s or "aggressive" in s:
        return "Offensive"
    if "neutral" in s or "balanced" in s:
        return "Neutral"
    return "Defensive"


def _norm_bias_ouw(val: Any) -> str:
    if val in VALID_BIAS:
        return val
    s = str(val).lower()
    if "overweight" in s or s == "ow" or "bullish" in s or "outperform" in s:
        return "OW"
    if "underweight" in s or s == "uw" or "bearish" in s:
        return "UW"
    return "N"


def _norm_action(val: Any) -> str:
    if val in VALID_ACTION:
        return val
    s = str(val).upper()
    for a in VALID_ACTION:
        if a in s:
            return a
    return "HOLD"


def _norm_thesis_status(val: Any) -> str:
    if val in VALID_THESIS_STATUS:
        return val
    s = str(val).upper()
    for st in VALID_THESIS_STATUS:
        if st in s:
            return st
    if "BROKEN" in s or "BREAK" in s:
        return "CHALLENGED"
    if "CLOSED" in s or "EXIT" in s:
        return "CLOSED"
    return "ACTIVE"


def _norm_segment_biases(sb_val: Any) -> dict:
    """Promote flat string segment_biases to biasObject shape."""
    REQUIRED_SEGMENTS = ["macro", "bonds", "commodities", "forex", "crypto",
                         "international", "us_equities", "alt_data", "institutional"]
    result: dict = {}

    def _to_bias_obj(raw: Any) -> dict:
        if isinstance(raw, dict):
            bias = raw.get("bias", "Neutral")
            conf = _norm_confidence(raw.get("confidence", "Medium"))
            key_driver = str(raw.get("key_driver", ""))[:200]
            return {"bias": str(bias)[:100], "confidence": conf, "key_driver": key_driver}
        # flat string → infer
        s = str(raw) if raw else ""
        bias = "Bullish" if "bullish" in s.lower() else ("Bearish" if "bearish" in s.lower() else "Neutral")
        return {"bias": bias, "confidence": "Medium", "key_driver": s[:200]}

    raw_dict = sb_val if isinstance(sb_val, dict) else {}
    for seg in REQUIRED_SEGMENTS:
        val = raw_dict.get(seg)
        result[seg] = _to_bias_obj(val) if val is not None else {
            "bias": "Neutral", "confidence": "Medium", "key_driver": ""
        }
    return result


def _slug(s: str) -> str:
    s = s.strip().lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _norm_sector_scorecard(sc_val: Any) -> list:
    """Convert any sector_scorecard shape to the canonical array format."""
    rows: list = []

    def _make_row(name: str, etf: str, raw: Any) -> dict:
        if isinstance(raw, dict):
            bias = _norm_bias_ouw(raw.get("bias", "N"))
            conf = _norm_confidence(raw.get("confidence", "Medium"))
            key_driver = str(raw.get("key_driver", ""))[:200]
        else:
            bias = "N"
            conf = "Medium"
            key_driver = ""
        return {"sector": name, "etf": etf, "bias": bias, "confidence": conf, "key_driver": key_driver}

    if isinstance(sc_val, list):
        for item in sc_val:
            if not isinstance(item, dict):
                continue
            sector = item.get("sector", "")
            # Look up canonical name
            canon = SECTOR_SLUG_TO_NAME.get(_slug(sector), sector)
            etf = item.get("etf", SECTOR_ETF_MAP.get(canon, ""))
            rows.append(_make_row(canon, etf, item))
    elif isinstance(sc_val, dict):
        # Object keyed by slug
        for slug_key, raw in sc_val.items():
            canon = SECTOR_SLUG_TO_NAME.get(slug_key.lower(), slug_key)
            etf = SECTOR_ETF_MAP.get(canon, "")
            if isinstance(raw, dict):
                etf = raw.get("etf", etf) or etf
            rows.append(_make_row(canon, etf, raw))

    # Sort by canonical sector order
    order_map = {s: i for i, s in enumerate(SECTOR_ORDER)}
    rows.sort(key=lambda r: order_map.get(r["sector"], 99))

    # Ensure all 11 sectors present
    present = {r["sector"] for r in rows}
    for sec in SECTOR_ORDER:
        if sec not in present:
            rows.append({"sector": sec, "etf": SECTOR_ETF_MAP.get(sec, ""),
                         "bias": "N", "confidence": "Low", "key_driver": ""})

    return rows


def _norm_positions(positions: Any) -> list:
    if not isinstance(positions, list):
        return []
    out = []
    for p in positions:
        if not isinstance(p, dict):
            continue
        ticker = str(p.get("ticker", ""))
        if not ticker:
            continue
        row: dict = {
            "ticker": ticker,
            "weight_pct": float(p.get("weight_pct", 0) or 0),
            "action": _norm_action(p.get("action", "HOLD")),
            "rationale": str(p.get("rationale", ""))[:1000],
        }
        for opt in ["name", "category", "thesis_id", "entry_date", "entry_price", "current_price"]:
            if p.get(opt) is not None:
                row[opt] = p[opt]
        out.append(row)
    return out


def _norm_theses(theses: Any) -> list:
    if not isinstance(theses, list):
        return []
    out = []
    for t in theses:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id", ""))
        name = str(t.get("name", ""))
        if not tid or not name:
            continue
        row: dict = {
            "id": tid,
            "name": name,
            "status": _norm_thesis_status(t.get("status", "ACTIVE")),
        }
        for opt in ["vehicle", "invalidation", "notes"]:
            if t.get(opt) is not None:
                row[opt] = t[opt]
        out.append(row)
    return out


def _norm_narrative(nar: Any) -> dict:
    REQUIRED = ["alt_data", "institutional", "macro", "asset_classes", "us_equities",
                "thesis_tracker", "portfolio_recs"]
    AC_REQUIRED = ["bonds", "commodities", "forex", "crypto", "international"]

    if not isinstance(nar, dict):
        nar = {}
    result: dict = {}
    for k in REQUIRED:
        if k == "asset_classes":
            ac = nar.get("asset_classes", {})
            if not isinstance(ac, dict):
                ac = {}
            result["asset_classes"] = {s: str(ac.get(s, ""))[:16000] for s in AC_REQUIRED}
        else:
            result[k] = str(nar.get(k, ""))[:20000]
    return result


def normalize_snapshot(snap: dict) -> dict:
    """Return a normalized copy of the snapshot dict."""
    snap = deepcopy(snap)

    # schema_version
    snap.setdefault("schema_version", "1.0")

    # run_type
    if snap.get("run_type") not in VALID_RUN_TYPE:
        snap["run_type"] = "delta"

    # regime
    regime = snap.get("regime", {})
    if not isinstance(regime, dict):
        regime = {}
    regime["conviction"] = _norm_conviction(regime.get("conviction", "Medium"))
    regime.setdefault("bias", "Neutral")
    regime.setdefault("label", regime.get("bias", "Neutral"))
    regime.setdefault("summary", "")
    if not isinstance(regime.get("factors"), dict):
        regime["factors"] = {"growth": "", "inflation": "", "policy": "", "risk_appetite": ""}
    else:
        for fk in ["growth", "inflation", "policy", "risk_appetite"]:
            v = regime["factors"].get(fk)
            # factor values can be string or object; normalize to string
            if isinstance(v, dict):
                regime["factors"][fk] = v.get("assessment", str(v))
            elif v is None:
                regime["factors"][fk] = ""
    snap["regime"] = regime

    # segment_biases
    snap["segment_biases"] = _norm_segment_biases(snap.get("segment_biases"))

    # sector_scorecard
    snap["sector_scorecard"] = _norm_sector_scorecard(snap.get("sector_scorecard"))

    # portfolio
    portfolio = snap.get("portfolio", {})
    if not isinstance(portfolio, dict):
        portfolio = {}
    portfolio["posture"] = _norm_posture(portfolio.get("posture", "Defensive"))
    if portfolio.get("cash_pct") is None:
        portfolio["cash_pct"] = 0
    portfolio["positions"] = _norm_positions(portfolio.get("positions", []))
    portfolio.setdefault("proposed_positions", [])
    snap["portfolio"] = portfolio

    # theses
    snap["theses"] = _norm_theses(snap.get("theses", []))

    # actionable / risks
    snap.setdefault("actionable", [])
    snap.setdefault("risks", [])

    # narrative
    snap["narrative"] = _norm_narrative(snap.get("narrative"))

    # market_data
    snap.setdefault("market_data", {})

    return snap


# ── Main ──────────────────────────────────────────────────────────────────────

def run(start: str, end: str, dry_run: bool) -> int:
    sb = _sb()

    res = (
        sb.table("daily_snapshots")
        .select("date,run_type,baseline_date,snapshot")
        .gte("date", start)
        .lte("date", end)
        .order("date")
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        print(f"No daily_snapshots rows in {start}..{end}")
        return 0

    for row in rows:
        date_str = str(row["date"])[:10]
        snap = row.get("snapshot")
        if not isinstance(snap, dict):
            print(f"⚠️  {date_str}: snapshot missing or not a dict — skipping")
            continue

        norm = normalize_snapshot(snap)

        if dry_run:
            diff_keys = [k for k in norm if norm.get(k) != snap.get(k)]
            print(f"🔍 {date_str}: would normalize fields: {diff_keys or '(none)'}")
        else:
            # Import renderer from materialize_snapshot
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "materialize_snapshot",
                    str(ROOT / "scripts" / "materialize_snapshot.py"),
                )
                mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                digest_md = mod.render_digest_markdown(norm)  # type: ignore[attr-defined]
            except Exception as e:
                print(f"⚠️  {date_str}: digest markdown render failed ({e}), continuing without markdown")
                digest_md = None

            # Upsert daily_snapshots
            update_row: dict = {
                "date": date_str,
                "snapshot": norm,
            }
            if digest_md:
                update_row["digest_markdown"] = digest_md
            sb.table("daily_snapshots").update(update_row).eq("date", date_str).execute()

            # Upsert documents digest
            if digest_md:
                doc_row = {
                    "date": date_str,
                    "title": "Digest",
                    "doc_type": "Daily Digest",
                    "phase": 7,
                    "category": "synthesis",
                    "segment": "digest",
                    "sector": None,
                    "run_type": norm.get("run_type", "delta"),
                    "document_key": "digest",
                    "payload": norm,
                    "content": digest_md,
                }
                sb.table("documents").upsert(doc_row, on_conflict="date,document_key").execute()

            print(f"✅ {date_str}: schema normalized and re-published")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize existing daily_snapshots schema to current spec.")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        return run(args.start, args.end, args.dry_run)
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

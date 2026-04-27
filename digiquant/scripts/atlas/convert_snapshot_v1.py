#!/usr/bin/env python3
"""
convert_snapshot_v1.py

Converts legacy `data/agent-cache/daily/<date>/snapshot.json` (schema 1.0 sidecar) into the
new DB-first digest snapshot schema (templates/digest-snapshot-schema.json).

This is a one-time bridge to bootstrap baselines into Supabase for the new flow.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).parent.parent


SECTOR_ETF = {
    "technology": "XLK",
    "healthcare": "XLV",
    "energy": "XLE",
    "financials": "XLF",
    "consumer-staples": "XLP",
    "consumer-disc": "XLY",
    "industrials": "XLI",
    "utilities": "XLU",
    "materials": "XLB",
    "real-estate": "XLRE",
    "comms": "XLC",
}


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bias_obj(bias: str, confidence: str = "Medium", key_driver: str = "") -> Dict[str, Any]:
    return {"bias": bias or "Unknown", "confidence": confidence, "key_driver": key_driver}


def convert(legacy: Dict[str, Any]) -> Dict[str, Any]:
    date = legacy.get("date")
    run_type = legacy.get("run_type", "baseline")
    baseline_date = legacy.get("baseline_date")

    regime_legacy = legacy.get("regime") or {}
    regime = {
        "bias": regime_legacy.get("bias", "Unknown"),
        "label": regime_legacy.get("label", regime_legacy.get("bias", "Unknown")),
        "conviction": regime_legacy.get("conviction", "Medium"),
        "summary": regime_legacy.get("summary", ""),
        "dominant_force": "",
        "factors": {
            "growth": "",
            "inflation": "",
            "policy": "",
            "risk_appetite": "",
        },
    }

    # Legacy has segment_biases as mostly strings; map into objects with placeholders.
    seg = legacy.get("segment_biases") or {}
    segment_biases = {
        "macro": _bias_obj(str(seg.get("macro", ""))),
        "bonds": _bias_obj(str(seg.get("bonds", ""))),
        "commodities": _bias_obj(str(seg.get("commodities", ""))),
        "forex": _bias_obj(str(seg.get("forex", ""))),
        "crypto": _bias_obj(str(seg.get("crypto", ""))),
        "international": _bias_obj(str(seg.get("international", ""))),
        "us_equities": _bias_obj(str(seg.get("us_equities", ""))),
        "alt_data": _bias_obj(str(seg.get("alt_data", ""))),
        "institutional": _bias_obj(str(seg.get("institutional", ""))),
    }

    portfolio_positions = []
    legacy_positions = legacy.get("positions") or []
    if isinstance(legacy_positions, dict):
        # scaffold bug safety
        legacy_positions = []
    for p in legacy_positions:
        portfolio_positions.append(
            {
                "ticker": p.get("ticker"),
                "name": p.get("name"),
                "category": p.get("category"),
                "weight_pct": p.get("weight_pct", 0),
                "action": p.get("action", "HOLD"),
                "thesis_id": p.get("thesis_id"),
                "rationale": p.get("rationale", ""),
                "entry_date": p.get("entry_date"),
                "entry_price": p.get("entry_price"),
                "current_price": p.get("current_price"),
            }
        )

    portfolio = {
        "posture": legacy.get("portfolio_posture", "Neutral") or "Neutral",
        "cash_pct": legacy.get("cash_pct"),
        "positions": portfolio_positions,
        "proposed_positions": [],
    }

    theses = []
    for t in legacy.get("theses") or []:
        theses.append(
            {
                "id": t.get("id"),
                "name": t.get("name", ""),
                "vehicle": t.get("vehicle"),
                "invalidation": t.get("invalidation"),
                # Legacy uses ACTIVE/MONITORING etc already in update_tearsheet normalization
                "status": t.get("status", "ACTIVE"),
                "notes": t.get("notes"),
            }
        )

    # We don't have the sector scorecard in legacy snapshot. Provide a stable 11-row scaffold
    # so deltas can update rows deterministically.
    sector_scorecard = []
    for sector, etf in SECTOR_ETF.items():
        sector_scorecard.append(
            {
                "sector": sector.replace("-", " ").title(),
                "etf": etf,
                "bias": "N",
                "confidence": "Medium",
                "key_driver": "",
            }
        )

    narrative = {
        "alt_data": "",
        "institutional": "",
        "macro": "",
        "asset_classes": {
            "bonds": "",
            "commodities": "",
            "forex": "",
            "crypto": "",
            "international": "",
        },
        "us_equities": "",
        "thesis_tracker": "",
        "portfolio_recs": "",
    }

    return {
        "schema_version": "1.0",
        "date": date,
        "run_type": run_type,
        "baseline_date": baseline_date,
        "regime": regime,
        "market_data": legacy.get("market_data") or {},
        "segment_biases": segment_biases,
        "sector_scorecard": sector_scorecard,
        "theses": theses,
        "portfolio": portfolio,
        "actionable": legacy.get("actionable") or [],
        "risks": legacy.get("risks") or [],
        "narrative": narrative,
        "source_refs": [],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert legacy snapshot.json → digest snapshot v1")
    ap.add_argument("--in", dest="in_path", required=True, help="Path to legacy snapshot.json")
    ap.add_argument("--out", dest="out_path", required=True, help="Path to write converted snapshot JSON")
    args = ap.parse_args()

    legacy = _load(Path(args.in_path))
    out = convert(legacy)

    Path(args.out_path).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"✅ Wrote {args.out_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


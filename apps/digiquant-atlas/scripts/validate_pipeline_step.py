#!/usr/bin/env python3
"""
Validate Supabase after discrete pipeline steps (research close-out, Track B phases).

Requires: pip install jsonschema supabase python-dotenv
Env: SUPABASE_URL, SUPABASE_SERVICE_KEY (e.g. config/supabase.env)

Examples:
  python3 scripts/validate_pipeline_step.py --date 2026-04-11 --step research_closeout
  python3 scripts/validate_pipeline_step.py --date 2026-04-11 --step track_b_1_market_thesis
  python3 scripts/validate_pipeline_step.py --date 2026-04-11 --chain track_b
  python3 scripts/validate_pipeline_step.py --list
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import jsonschema  # type: ignore

    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

try:
    from supabase import create_client  # type: ignore

    _HAS_SB = True
except ImportError:
    _HAS_SB = False

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).resolve().parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "templates" / "schemas"
DIGEST_SNAPSHOT_SCHEMA = ROOT / "templates" / "digest-snapshot-schema.json"

DOC_TYPE_TO_SCHEMA = {
    "market_thesis_exploration": "market-thesis-exploration.schema.json",
    "thesis_vehicle_map": "thesis-vehicle-map.schema.json",
    "pm_allocation_memo": "pm-allocation-memo.schema.json",
    "deliberation_transcript": "deliberation-transcript.schema.json",
    "deliberation_session_index": "deliberation-session-index.schema.json",
    "asset_recommendation": "asset-recommendation.schema.json",
    "rebalance_decision": "rebalance-decision.schema.json",
    "research_delta": "research-delta.schema.json",
    "pipeline_review": "pipeline-review.schema.json",
}

STEP_DESCRIPTIONS = {
    "research_closeout": "Track A: daily_snapshots.snapshot (JSON object) + documents.digest payload",
    "track_b_precheck": "Same as research_closeout (run before portfolio-pm-rebalance)",
    "track_b_1_market_thesis": "market-thesis-exploration/{date}.json + market_thesis_exploration schema",
    "track_b_2_vehicle_map": "thesis-vehicle-map/{date}.json + thesis_vehicle_map schema",
    "track_b_3_opportunity": "opportunity_screen payload OR document_key opportunity-screener.json",
    "track_b_4_asset_recommendations": "≥ min asset_recommendation rows for date (see --min-asset-recs)",
    "track_b_5_deliberation": "deliberation_session_index + each listed per-ticker transcript",
    "track_b_6_pm_memo": "pm-allocation-memo/{date}.json + pm_allocation_memo schema",
    "track_b_7_rebalance": "rebalance-decision.json + rebalance_decision schema",
}


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def _fail(msg: str) -> None:
    print(f"❌ {msg}", file=sys.stderr)


def _pass(msg: str) -> None:
    print(f"✅ {msg}")


def fetch_document_rows(sb, d: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    page = 500
    while True:
        res = (
            sb.table("documents")
            .select("document_key,payload")
            .eq("date", d)
            .range(start, start + page - 1)
            .execute()
        )
        batch = getattr(res, "data", None) or []
        rows.extend(batch)
        if len(batch) < page:
            break
        start += page
    return rows


def index_documents(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
    by_key: Dict[str, Any] = {}
    by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        k = str(r.get("document_key") or "")
        by_key[k] = r.get("payload")
        p = r.get("payload")
        if isinstance(p, dict) and p.get("doc_type"):
            by_type[str(p["doc_type"])].append(r)
    return by_key, by_type


def validate_payload_schema(payload: Any, doc_type: str, label: str) -> bool:
    if not _HAS_JSONSCHEMA:
        _fail("jsonschema not installed — cannot validate schema (pip install jsonschema)")
        return False
    if not isinstance(payload, dict):
        _fail(f"{label}: payload is not an object")
        return False
    fname = DOC_TYPE_TO_SCHEMA.get(doc_type)
    if not fname:
        _fail(f"{label}: no schema mapping for doc_type {doc_type}")
        return False
    schema_path = SCHEMAS_DIR / fname
    if not schema_path.is_file():
        _fail(f"{label}: missing schema file {schema_path}")
        return False
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=payload, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        _fail(f"{label}: schema validation failed: {e.message}")
        return False
    return True


def validate_digest_like(payload: Any, label: str) -> bool:
    if not _HAS_JSONSCHEMA:
        _pass(f"{label}: present (skip schema — jsonschema not installed)")
        return True
    if not isinstance(payload, dict):
        _fail(f"{label}: payload is not an object")
        return False
    if not DIGEST_SNAPSHOT_SCHEMA.is_file():
        _fail("digest-snapshot-schema.json missing")
        return False
    schema = json.loads(DIGEST_SNAPSHOT_SCHEMA.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=payload, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        _fail(f"{label}: digest snapshot schema: {e.message}")
        return False
    _pass(f"{label}: digest snapshot schema valid")
    return True


def step_research_closeout(sb, d: str) -> int:
    fails = 0
    snap = (
        sb.table("daily_snapshots")
        .select("date,snapshot")
        .eq("date", d)
        .limit(1)
        .execute()
    )
    srows = getattr(snap, "data", None) or []
    if not srows:
        _fail(f"daily_snapshots missing for {d}")
        fails += 1
    else:
        sv = srows[0].get("snapshot")
        if not isinstance(sv, dict):
            _fail(f"daily_snapshots.snapshot must be a JSON object for {d}")
            fails += 1
        else:
            _pass(f"daily_snapshots.snapshot present for {d}")
            if not validate_digest_like(sv, "daily_snapshots.snapshot"):
                fails += 1

    rows = fetch_document_rows(sb, d)
    by_key, _ = index_documents(rows)
    dig = by_key.get("digest")
    if dig is None:
        _fail(f"documents.digest missing for {d}")
        fails += 1
    elif not isinstance(dig, dict):
        _fail("documents.digest payload is not an object")
        fails += 1
    else:
        _pass("documents.digest row present")
        if not validate_digest_like(dig, "documents.digest"):
            fails += 1

    return fails


def step_track_b_1(sb, d: str) -> int:
    key = f"market-thesis-exploration/{d}.json"
    rows = fetch_document_rows(sb, d)
    by_key, _ = index_documents(rows)
    p = by_key.get(key)
    if not isinstance(p, dict) or p.get("doc_type") != "market_thesis_exploration":
        _fail(f"missing or wrong doc_type: {key}")
        return 1
    _pass(f"{key} present")
    return 0 if validate_payload_schema(p, "market_thesis_exploration", key) else 1


def step_track_b_2(sb, d: str) -> int:
    key = f"thesis-vehicle-map/{d}.json"
    rows = fetch_document_rows(sb, d)
    by_key, _ = index_documents(rows)
    p = by_key.get(key)
    if not isinstance(p, dict) or p.get("doc_type") != "thesis_vehicle_map":
        _fail(f"missing or wrong doc_type: {key}")
        return 1
    _pass(f"{key} present")
    return 0 if validate_payload_schema(p, "thesis_vehicle_map", key) else 1


def step_track_b_3(sb, d: str) -> int:
    rows = fetch_document_rows(sb, d)
    by_key, by_type = index_documents(rows)
    if by_type.get("opportunity_screen"):
        r = by_type["opportunity_screen"][0]
        k = str(r.get("document_key") or "")
        p = r.get("payload")
        _pass(f"opportunity_screen found ({k})")
        return 0
    p = by_key.get("opportunity-screener.json")
    if isinstance(p, dict) and p.get("doc_type") == "opportunity_screen":
        _pass("opportunity-screener.json present")
        return 0
    _fail("no opportunity_screen document for date (publish opportunity-screener.json or opportunity_screen payload)")
    return 1


def step_track_b_4(sb, d: str, min_count: int) -> int:
    rows = fetch_document_rows(sb, d)
    count = 0
    for r in rows:
        p = r.get("payload")
        if isinstance(p, dict) and p.get("doc_type") == "asset_recommendation":
            count += 1
    if count < min_count:
        _fail(f"expected >= {min_count} asset_recommendation rows, found {count}")
        return 1
    _pass(f"asset_recommendation count OK ({count})")
    return 0


def step_track_b_5(sb, d: str) -> int:
    fails = 0
    idx_key = f"deliberation-transcript-index/{d}.json"
    rows = fetch_document_rows(sb, d)
    by_key, _ = index_documents(rows)
    idx = by_key.get(idx_key)
    if not isinstance(idx, dict) or idx.get("doc_type") != "deliberation_session_index":
        _fail(f"missing {idx_key} (deliberation_session_index)")
        return 1
    _pass(idx_key)
    if not validate_payload_schema(idx, "deliberation_session_index", idx_key):
        fails += 1

    body = idx.get("body") if isinstance(idx.get("body"), dict) else {}
    entries = body.get("entries")
    if not isinstance(entries, list) or not entries:
        _fail("deliberation_session_index.body.entries empty or missing")
        return 1

    for ent in entries:
        if not isinstance(ent, dict):
            continue
        ticker = str(ent.get("ticker") or "")
        dk = str(ent.get("document_key") or "")
        if not dk:
            _fail(f"session index entry missing document_key for {ticker}")
            fails += 1
            continue
        tp = by_key.get(dk)
        if not isinstance(tp, dict) or tp.get("doc_type") != "deliberation_transcript":
            _fail(f"deliberation transcript missing or wrong type: {dk}")
            fails += 1
        else:
            if not validate_payload_schema(tp, "deliberation_transcript", dk):
                fails += 1
            else:
                _pass(f"deliberation transcript OK: {dk}")
    return fails


def step_track_b_6(sb, d: str) -> int:
    key = f"pm-allocation-memo/{d}.json"
    rows = fetch_document_rows(sb, d)
    by_key, _ = index_documents(rows)
    p = by_key.get(key)
    if not isinstance(p, dict) or p.get("doc_type") != "pm_allocation_memo":
        _fail(f"missing or wrong doc_type: {key}")
        return 1
    _pass(key)
    return 0 if validate_payload_schema(p, "pm_allocation_memo", key) else 1


def step_track_b_7(sb, d: str) -> int:
    rows = fetch_document_rows(sb, d)
    by_key, _ = index_documents(rows)
    p = by_key.get("rebalance-decision.json")
    if not isinstance(p, dict) or p.get("doc_type") != "rebalance_decision":
        _fail("rebalance-decision.json missing or wrong doc_type")
        return 1
    _pass("rebalance-decision.json present")
    return 0 if validate_payload_schema(p, "rebalance_decision", "rebalance-decision.json") else 1


STEP_HANDLERS = {
    "research_closeout": step_research_closeout,
    "track_b_precheck": step_research_closeout,
    "track_b_1_market_thesis": step_track_b_1,
    "track_b_2_vehicle_map": step_track_b_2,
    "track_b_3_opportunity": step_track_b_3,
    "track_b_5_deliberation": step_track_b_5,
    "track_b_6_pm_memo": step_track_b_6,
    "track_b_7_rebalance": step_track_b_7,
}

TRACK_B_CHAIN = [
    "track_b_1_market_thesis",
    "track_b_2_vehicle_map",
    "track_b_3_opportunity",
    "track_b_4_asset_recommendations",
    "track_b_5_deliberation",
    "track_b_6_pm_memo",
    "track_b_7_rebalance",
]


def _step_names_for_list() -> List[str]:
    names = sorted(STEP_HANDLERS.keys()) + ["track_b_4_asset_recommendations"]
    return sorted(set(names))


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate Supabase after a pipeline step.")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (required unless --list)")
    ap.add_argument(
        "--step",
        choices=_step_names_for_list(),
        help="Single step to validate",
    )
    ap.add_argument(
        "--chain",
        choices=("research", "track_b", "full"),
        help="Run multiple steps in order (full = research_closeout + track_b chain)",
    )
    ap.add_argument(
        "--min-asset-recs",
        type=int,
        default=1,
        help="Minimum count for step track_b_4_asset_recommendations (default 1)",
    )
    ap.add_argument("--list", action="store_true", help="List steps and exit")
    args = ap.parse_args()

    if args.list:
        for k in sorted(STEP_DESCRIPTIONS.keys()):
            print(f"{k}: {STEP_DESCRIPTIONS[k]}")
        return 0

    if not args.step and not args.chain:
        ap.error("pass --step, --chain, or --list")

    if not args.date:
        ap.error("--date is required unless using --list")

    d = args.date

    steps: List[str] = []
    if args.chain == "research":
        steps = ["research_closeout"]
    elif args.chain == "track_b":
        steps = ["track_b_precheck"] + TRACK_B_CHAIN
    elif args.chain == "full":
        steps = ["research_closeout"] + TRACK_B_CHAIN
    elif args.step:
        steps = [args.step]

    sb = _sb()
    total = 0
    for name in steps:
        print(f"── {name} ──")
        if name == "track_b_4_asset_recommendations":
            n = step_track_b_4(sb, d, args.min_asset_recs)
        else:
            n = STEP_HANDLERS[name](sb, d)
        total += n
        if n and args.chain:
            _fail(f"chain stopped after failure in {name}")
            return 1

    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())

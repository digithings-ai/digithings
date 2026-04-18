#!/usr/bin/env python3
"""
fold_document_deltas.py

For a run date D, load all `documents` rows on D whose payload.doc_type is `document_delta`,
fold each into a materialized full JSON document, upsert via publish_document.py, then
optionally publish `research_changelog` for D.

Prior source row: `date = prior_calendar(D)` and `document_key` = same as target if the key
has no embedded ISO date; otherwise replace the last YYYY-MM-DD in target with prior date.

Usage (repo root, SUPABASE_* set):
  python3 scripts/fold_document_deltas.py --date YYYY-MM-DD
  python3 scripts/fold_document_deltas.py --date YYYY-MM-DD --dry-run
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).resolve().parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

try:
    from supabase import create_client  # type: ignore

    _HAS_SB = True
except ImportError:
    _HAS_SB = False

ROOT = Path(__file__).resolve().parent.parent
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def _load_apply_ops():
    path = ROOT / "scripts" / "materialize_snapshot.py"
    spec = importlib.util.spec_from_file_location("_mat_snap_fold", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return getattr(mod, "apply_ops")


def prior_calendar(d: str) -> str:
    cur = datetime.fromisoformat(d).date()
    return (cur - timedelta(days=1)).isoformat()


def prior_document_key(target_key: str, prior_date: str) -> str:
    matches = list(ISO.finditer(target_key))
    if not matches:
        return target_key
    m = matches[-1]
    return target_key[: m.start()] + prior_date + target_key[m.end() :]


def fetch_payload(sb, doc_date: str, document_key: str) -> Optional[Dict[str, Any]]:
    res = (
        sb.table("documents")
        .select("payload")
        .eq("date", doc_date)
        .eq("document_key", document_key)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    p = rows[0].get("payload")
    return p if isinstance(p, dict) else None


def fetch_all_document_deltas(sb, d: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Return (document_key, payload) for document_delta rows on date d."""
    out: List[Tuple[str, Dict[str, Any]]] = []
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
        for row in batch:
            p = row.get("payload")
            if isinstance(p, dict) and p.get("doc_type") == "document_delta":
                out.append((str(row.get("document_key") or ""), p))
        if len(batch) < page:
            break
        start += page
    return out


def _validate_payload_json(payload: Dict[str, Any]) -> bool:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_artifact.py"), "-"],
        input=json.dumps(payload),
        text=True,
        cwd=str(ROOT),
        capture_output=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout or "validate failed\n")
        return False
    return True


def _publish(
    date_str: str,
    document_key: str,
    title: str,
    category: str,
    doc_type_label: str,
    payload: Dict[str, Any],
    dry_run: bool,
) -> int:
    if dry_run:
        print(f"[dry-run] would publish {date_str} {document_key} ({doc_type_label})")
        return 0
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "publish_document.py"),
            "--payload",
            "-",
            "--document-key",
            document_key,
            "--title",
            title,
            "--category",
            category,
            "--doc-type-label",
            doc_type_label,
            "--date",
            date_str,
        ],
        input=json.dumps(payload),
        text=True,
        cwd=str(ROOT),
    )
    return int(proc.returncode)


def _human_doc_type_label(payload: Dict[str, Any]) -> str:
    """Labels must match documents.chk_documents_doc_type (see supabase/migrations/019)."""
    dt = str(payload.get("doc_type") or "")
    mapping = {
        "sector_report": "Sector Report",
        "deep_dive": "Deep Dive",
        "asset_recommendation": "Asset Recommendation",
        "deliberation_transcript": "Deliberation Transcript",
        "rebalance_decision": "Rebalance Decision",
        "evolution_sources": "Evolution Sources",
        "evolution_quality_log": "Evolution Quality Log",
        "evolution_proposals": "Evolution Proposals",
        "pipeline_review": "Pipeline Review",
        "research_changelog": "Research Changelog",
        "research_baseline_manifest": "Research Baseline Manifest",
        "document_delta": "Document Delta",
        "research_delta": "Research Delta",
        "weekly_digest": "Weekly Rollup",
        "monthly_digest": "Monthly Summary",
        "market_thesis_exploration": "Market Thesis Exploration",
        "thesis_vehicle_map": "Thesis Vehicle Map",
        "pm_allocation_memo": "PM Allocation Memo",
        "deliberation_session_index": "Deliberation Session Index",
    }
    return mapping.get(dt, "Deep Dive")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fold document_delta rows into materialized documents.")
    ap.add_argument("--date", required=True, help="Run date D (YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-changelog", action="store_true")
    args = ap.parse_args()

    apply_ops = _load_apply_ops()
    sb = _sb()
    d = args.date
    prev = prior_calendar(d)

    deltas = fetch_all_document_deltas(sb, d)
    if not deltas:
        print(f"No document_delta rows for {d}", file=sys.stderr)
        return 1

    by_target: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
    for dk, p in deltas:
        tk = str(p.get("target_document_key") or "")
        if not tk:
            print(f"Skip delta {dk}: missing target_document_key", file=sys.stderr)
            continue
        by_target.setdefault(tk, []).append((dk, p))

    changelog_items: List[Dict[str, Any]] = []
    fails = 0

    for target_key, group in sorted(by_target.items()):
        group.sort(key=lambda x: (x[1].get("published_at") or "", x[0]))
        _delta_key, delta = group[-1]
        if len(group) > 1:
            print(f"Note: {len(group)} deltas for {target_key}; using last by published_at/key", file=sys.stderr)

        prior_key = prior_document_key(target_key, prev)
        base = fetch_payload(sb, prev, prior_key)
        if base is None and prior_key != target_key:
            base = fetch_payload(sb, prev, target_key)
        if base is None:
            print(f"WARN: missing prior payload date={prev} key={prior_key!r} (target={target_key})", file=sys.stderr)
            changelog_items.append(
                {
                    "target_document_key": target_key,
                    "status": "skipped",
                    "one_line_change": f"No prior doc ({prev})",
                    "severity": "low",
                }
            )
            fails += 1
            continue

        if delta.get("status") == "skipped":
            materialized = deepcopy(base)
            materialized["date"] = d
        else:
            ops = delta.get("ops")
            if not isinstance(ops, list):
                print(f"WARN: updated delta missing ops for {target_key}", file=sys.stderr)
                fails += 1
                continue
            materialized = apply_ops(deepcopy(base), ops)
            if isinstance(materialized, dict):
                materialized["date"] = d

        if not isinstance(materialized, dict):
            fails += 1
            continue

        inner_dt = str(materialized.get("doc_type") or "")
        if inner_dt and inner_dt not in ("document_delta", "research_changelog", "research_baseline_manifest"):
            if not _validate_payload_json(materialized):
                print(f"WARN: validate failed for materialized {target_key}", file=sys.stderr)
                fails += 1
                continue

        title = f"{inner_dt or 'Research'} {target_key.split('/')[-1]}"
        label = _human_doc_type_label(materialized)
        cat = "output"
        rc = _publish(d, target_key, title, cat, label, materialized, args.dry_run)
        if rc != 0:
            fails += 1
            continue

        sev = "medium" if delta.get("status") == "updated" else "low"
        line = (
            delta.get("one_line_summary")
            or delta.get("skip_reason")
            or ("Updated" if delta.get("status") == "updated" else "No change")
        )
        changelog_items.append(
            {
                "target_document_key": target_key,
                "status": delta.get("status") or "updated",
                "one_line_change": str(line)[:500],
                "severity": sev,
            }
        )

    if not args.skip_changelog and changelog_items:
        baseline_date = None
        for _, p in deltas:
            bd = p.get("baseline_date")
            if isinstance(bd, str):
                baseline_date = bd
                break
        ch = {
            "schema_version": "1.0",
            "doc_type": "research_changelog",
            "date": d,
            "baseline_date": baseline_date or d,
            "published_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "items": changelog_items,
        }
        if not _validate_payload_json(ch) and not args.dry_run:
            print("WARN: research_changelog validation failed", file=sys.stderr)
        else:
            ck = f"research-changelog/{d}.json"
            r2 = _publish(
                d,
                ck,
                f"Research changelog {d}",
                "output",
                "Research Changelog",
                ch,
                args.dry_run,
            )
            if r2 != 0:
                fails += 1

    if fails:
        print(f"fold_document_deltas completed with {fails} issue(s)", file=sys.stderr)
        return 1
    print(f"✅ fold_document_deltas {d} ({len(by_target)} target(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

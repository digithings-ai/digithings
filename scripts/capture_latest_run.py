#!/usr/bin/env python3
"""Record a metadata-only snapshot of the latest research pipeline run.

Writes ``apps/digiquant-web/app/_latest-run.json``. The digiquant.io pipeline
band renders that file as a dated "recorded run" (never "today"). Nothing in it
is hand-written; re-run this script to refresh it:

    SUPABASE_URL=https://<ref>.supabase.co SUPABASE_ANON_KEY=<anon key> \\
        python3 scripts/capture_latest_run.py

Source: the dashboard's own read path, the ``documents`` table over PostgREST
(the same rows ``apps/dashboard/lib/queries.ts`` groups into the pipeline graph).
Only the public anon key is accepted; a service-role key is refused. If RLS
returns nothing (or the credentials are absent) the script writes
``{"snapshot": null, "reason": ...}`` so the band renders an honest empty state.
It never fabricates a run.

Offline alternative: ``--documents-json rows.json`` reads a JSON array of
``documents`` metadata rows (document_key, title, doc_type, phase, run_type,
date) exported by someone who can read them.

Observer-tier allowlist:
  * per row only document_key, title, run_type, date are read (no payload, no
    body text, no workspace ids);
  * titles are emitted only for Inputs / Research / Synthesis;
  * Selection / Decision / Learning carry status and counts only, because
    portfolio documents (pm-rebalance, pm-direction-memo, commit-run/*,
    risk-debate) sit next to weight-bearing content;
  * titles are length-capped and dropped if they look like they carry numbers
    with a percent sign or a secret-shaped token.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "apps" / "digiquant-web" / "app" / "_latest-run.json"
STAGES = ["Inputs", "Research", "Synthesis", "Selection", "Decision", "Learning"]
TITLED_STAGES = {"Inputs", "Research", "Synthesis"}
SOURCE = "supabase:documents (metadata only, anon key)"
COLUMNS = "document_key,title,run_type,date"
MAX_TITLES = 6
MAX_TITLE_LEN = 80
PAGE = 1000
RESEARCH_PREFIXES = ("alt-", "inst-", "sector-")
ASSET_CLASSES = {"bonds", "commodities", "forex", "crypto", "equity", "international"}


def stage_for_key(key: str) -> str | None:
    """Mirror of apps/dashboard/lib/pipeline-links.ts stageForDocumentKey."""
    k = key.lower()
    if k in ("attention-plan", "inputs"):
        return "Inputs"
    if k in ("bias-row", "digest", "digest-delta"):
        return "Synthesis"
    if k.startswith(("analyst/", "deliberation/", "thesis/")):
        return "Selection"
    if k in ("opportunity-screener", "opportunity-screener.json", "pm-direction-memo", "pm-rebalance", "risk-debate"):
        return "Selection"
    if k.startswith("commit-run/"):
        return "Decision"
    if k == "beliefs":
        return "Learning"
    if k.startswith("document-deltas/"):
        return "Research"
    if k.startswith(RESEARCH_PREFIXES) or k == "macro" or k in ASSET_CLASSES:
        return "Research"
    return None


_SECRET_RE = re.compile(r"(eyJ[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{10,}|[A-Za-z0-9]{32,})")


def safe_title(title: object) -> str | None:
    if not isinstance(title, str):
        return None
    t = " ".join(title.split())
    if not t or "%" in t or _SECRET_RE.search(t):
        return None
    return t[:MAX_TITLE_LEN]


def empty(reason: str) -> dict:
    return {
        "capturedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": SOURCE,
        "snapshot": None,
        "reason": reason,
    }


def fetch_rows(url: str, key: str) -> list[dict]:
    base = url.rstrip("/") + "/rest/v1/documents"
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}

    def get(params: dict, extra: dict | None = None) -> list[dict]:
        req = urllib.request.Request(base + "?" + urllib.parse.urlencode(params), headers={**headers, **(extra or {})})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    latest = get({"select": "date", "order": "date.desc", "limit": "1"})
    if not latest:
        return []
    day = latest[0]["date"]
    rows: list[dict] = []
    offset = 0
    while True:
        page = get(
            {"select": COLUMNS, "date": f"eq.{day}", "order": "document_key.asc", "limit": str(PAGE), "offset": str(offset)}
        )
        rows.extend(page)
        if len(page) < PAGE:
            break
        offset += PAGE
    return rows


def build(rows: list[dict], source: str) -> dict:
    dates = sorted({str(r["date"]) for r in rows if r.get("date")})
    if not rows or not dates:
        return empty("Query succeeded but returned no readable documents for the latest run.")
    run_date = dates[-1]
    rows = [r for r in rows if str(r.get("date")) == run_date and r.get("document_key")]
    run_types = Counter(r["run_type"] for r in rows if r.get("run_type"))
    run_type = run_types.most_common(1)[0][0] if run_types else None

    by_stage: dict[str, list[dict]] = {s: [] for s in STAGES}
    for r in rows:
        stage = stage_for_key(r["document_key"])
        if stage in by_stage:
            by_stage[stage].append(r)

    stages = []
    for name in STAGES:
        docs = by_stage[name]
        entry: dict = {"name": name, "status": "recorded" if docs else "not-recorded", "documentCount": len(docs)}
        if name in TITLED_STAGES:
            titles = [t for t in (safe_title(d.get("title")) for d in docs) if t]
            entry["titles"] = sorted(set(titles))[:MAX_TITLES]
        stages.append(entry)

    return {
        "capturedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "snapshot": {"runDate": run_date, "runType": run_type, "stages": stages},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--documents-json", help="read documents metadata rows from this JSON file instead of Supabase")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = Path(args.out)

    if args.documents_json:
        rows = json.loads(Path(args.documents_json).read_text())
        result = build(rows, "local file: documents metadata export")
    else:
        url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        if os.environ.get("SUPABASE_SERVICE_ROLE_KEY") and not key:
            print("refusing: only the public anon key is used here", file=sys.stderr)
        if not url or not key:
            result = empty("No run source reachable: SUPABASE_URL and SUPABASE_ANON_KEY were not set when this was generated.")
        else:
            try:
                result = build(fetch_rows(url, key), SOURCE)
            except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
                result = empty(f"Run source unreachable or not readable with the anon key ({type(exc).__name__}).")

    out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {out} ({'snapshot' if result['snapshot'] else 'empty: ' + result['reason']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

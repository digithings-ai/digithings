#!/usr/bin/env python3
"""
Create GitHub Issues from a published `pipeline_review` document in Supabase `documents`.

Requires:
  - `gh` CLI installed and authenticated (`gh auth login`).
  - SUPABASE_URL + SUPABASE_SERVICE_KEY (see config/supabase.env).

Document keys (canonical):
  - pipeline-review/research/{YYYY-MM-DD}.json
  - pipeline-review/portfolio/{YYYY-MM-DD}.json

Idempotency: open issues whose body contains `dedupe_key: <value>` in the pipeline-review-meta
HTML comment are treated as already filed for that finding. Closed issues do **not** block a new
issue (same dedupe_key may open again — see EVOLUTION_GITHUB_IMPLEMENTATION_PLAN.md).

Usage:
  python3 scripts/pipeline_review_to_github.py --date 2026-04-16 --track research --dry-run
  python3 scripts/pipeline_review_to_github.py --date 2026-04-16 --track portfolio --severity-min warn
  cat review.json | python3 scripts/pipeline_review_to_github.py --date 2026-04-16 --track research --stdin
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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

ROOT = Path(__file__).resolve().parents[1]

_SEVERITY_RANK = {"info": 1, "warn": 2, "error": 3}

_CATEGORY_TO_TYPE_LABEL = {
    "prompt": "type/prompt-task",
    "script": "type/script",
    "data": "type/validation",
    "content": "type/semantic",
}

_SEVERITY_TO_LABEL = {
    "info": "severity/info",
    "warn": "severity/warn",
    "error": "severity/blocking",
}


def _sb():
    if not _HAS_SB:
        raise RuntimeError("pip install supabase")
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def _document_key(track: str, date_str: str) -> str:
    t = track.lower().strip()
    if t not in ("research", "portfolio"):
        raise ValueError("--track must be research or portfolio")
    return f"pipeline-review/{t}/{date_str}.json"


def _load_payload_from_supabase(sb, date_str: str, document_key: str) -> Dict[str, Any]:
    res = (
        sb.table("documents")
        .select("payload")
        .eq("date", date_str)
        .eq("document_key", document_key)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        raise SystemExit(f"No documents row for date={date_str} document_key={document_key}")
    p = rows[0].get("payload")
    if not isinstance(p, dict) or p.get("doc_type") != "pipeline_review":
        raise SystemExit("payload.doc_type must be pipeline_review")
    return p


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _gh_json(args: List[str]) -> Any:
    r = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if r.returncode != 0:
        raise RuntimeError(f"gh failed: {' '.join(args)}\n{r.stderr or r.stdout}")
    return json.loads(r.stdout or "[]")


def _open_issue_bodies_with_evolution_label() -> List[Dict[str, Any]]:
    """Open issues labeled `evolution` (and optionally source/post-mortem)."""
    return _gh_json(
        [
            "issue",
            "list",
            "--state",
            "open",
            "--label",
            "evolution",
            "--json",
            "number,body,labels",
            "--limit",
            "300",
        ]
    )


def _collect_dedupe_keys_from_open_issues() -> Set[str]:
    keys: Set[str] = set()
    for row in _open_issue_bodies_with_evolution_label():
        body = row.get("body") or ""
        for m in re.finditer(
            r"^\s*dedupe_key:\s*(.+?)\s*$", body, re.MULTILINE | re.IGNORECASE
        ):
            keys.add(m.group(1).strip())
    return keys


def _meets_severity(sev: str, min_rank: int) -> bool:
    r = _SEVERITY_RANK.get(str(sev).lower(), 0)
    return r >= min_rank


def _labels_for_finding(track: str, finding: Dict[str, Any]) -> List[str]:
    out = ["evolution", "source/post-mortem", f"track/{track}"]
    cat = str(finding.get("category") or "").lower()
    tl = _CATEGORY_TO_TYPE_LABEL.get(cat)
    if tl:
        out.append(tl)
    sev = str(finding.get("severity") or "info").lower()
    sl = _SEVERITY_TO_LABEL.get(sev, "severity/info")
    out.append(sl)
    return out


def _build_issue_body(
    finding: Dict[str, Any],
    date_str: str,
    track: str,
    document_key: str,
) -> str:
    detail = finding.get("detail") or ""
    actions = finding.get("suggested_actions")
    lines = [
        "## Finding",
        "",
        str(detail).strip() or "_(no detail)_",
        "",
    ]
    if isinstance(actions, list) and actions:
        lines.append("## Suggested actions")
        lines.append("")
        for a in actions:
            lines.append(f"- {a}")
        lines.append("")
    lines.extend(
        [
            "## Source",
            "",
            f"- **Date:** {date_str}",
            f"- **Track:** {track}",
            f"- **document_key:** `{document_key}`",
            f"- **finding id:** `{finding.get('id', '')}`",
            "",
            "<!-- pipeline-review-meta",
            f"dedupe_key: {finding.get('dedupe_key', '')}",
            f"date: {date_str}",
            f"track: {track}",
            f"finding_id: {finding.get('id', '')}",
            f"document_key: {document_key}",
            "-->",
        ]
    )
    return "\n".join(lines)


def _create_issue(title: str, body: str, labels: List[str], dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] would create issue: {title[:80]}...")
        return
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(body)
        tmp_path = tmp.name
    try:
        cmd = ["gh", "issue", "create", "--title", title, "--body-file", tmp_path]
        for lb in labels:
            cmd.extend(["--label", lb])
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        if r.returncode != 0:
            raise SystemExit(f"gh issue create failed: {r.stderr or r.stdout}")
        print((r.stdout or "").strip())
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True, help="Run date YYYY-MM-DD (matches documents.date)")
    ap.add_argument(
        "--track",
        required=True,
        choices=("research", "portfolio"),
        help="Which pipeline_review document to load",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print actions only; do not create issues")
    ap.add_argument(
        "--severity-min",
        choices=("info", "warn", "error"),
        default="info",
        help="Only file findings at or above this severity (default: info)",
    )
    ap.add_argument(
        "--max-issues",
        type=int,
        default=10,
        help="Max new issues to create this run (default: 10)",
    )
    ap.add_argument(
        "--stdin",
        action="store_true",
        help="Read pipeline_review JSON from stdin instead of Supabase",
    )
    args = ap.parse_args()

    if not _gh_available():
        print("error: `gh` CLI not found. Install https://cli.github.com/ and run `gh auth login`.", file=sys.stderr)
        return 2

    dk = _document_key(args.track, args.date)
    if args.stdin:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or payload.get("doc_type") != "pipeline_review":
            print("error: stdin must be a JSON object with doc_type pipeline_review", file=sys.stderr)
            return 2
    else:
        sb = _sb()
        payload = _load_payload_from_supabase(sb, args.date, dk)

    body = payload.get("body") if isinstance(payload.get("body"), dict) else {}
    findings = body.get("findings") if isinstance(body.get("findings"), list) else []
    min_rank = _SEVERITY_RANK[args.severity_min]

    try:
        existing_dedupes = _collect_dedupe_keys_from_open_issues()
    except RuntimeError as ex:
        if args.dry_run:
            print(
                f"warning: could not list open issues ({ex}); "
                "dedupe check skipped — use authenticated `gh` for accurate dry-run.",
                file=sys.stderr,
            )
            existing_dedupes = set()
        else:
            raise SystemExit(f"error: {ex}") from ex

    created = 0
    skipped = 0

    for finding in findings:
        if created >= args.max_issues:
            print(f"Stopped: reached --max-issues {args.max_issues}")
            break
        if not isinstance(finding, dict):
            continue
        if not finding.get("github_issue_candidate"):
            skipped += 1
            continue
        sev = str(finding.get("severity") or "info")
        if not _meets_severity(sev, min_rank):
            skipped += 1
            continue
        dedupe = str(finding.get("dedupe_key") or "").strip()
        if not dedupe:
            print(f"skip finding {finding.get('id')}: empty dedupe_key", file=sys.stderr)
            skipped += 1
            continue
        if dedupe in existing_dedupes:
            print(f"skip dedupe_key already in open issue: {dedupe}")
            skipped += 1
            continue

        title = f"[{args.track}] {finding.get('title', 'Finding')[:120]} ({args.date})"
        issue_body = _build_issue_body(finding, args.date, args.track, dk)
        labels = _labels_for_finding(args.track, finding)
        _create_issue(title, issue_body, labels, args.dry_run)
        if not args.dry_run:
            existing_dedupes.add(dedupe)
            created += 1
        else:
            created += 1

    print(f"Done. created={created} skipped_non_candidate_or_severity={skipped} document_key={dk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

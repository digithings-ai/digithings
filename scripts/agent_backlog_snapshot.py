#!/usr/bin/env python3
"""Write docs/agent-backlog/generated-snapshot.md from open GitHub issues (label agent-task)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "docs/agent-backlog/generated-snapshot.md"


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repo:
        print("agent_backlog_snapshot: GITHUB_REPOSITORY not set", file=sys.stderr)
        return 1
    cmd = [
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--label",
        "agent-task",
        "--state",
        "open",
        "--json",
        "number,title,url",
        "--limit",
        "200",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        print("agent_backlog_snapshot: gh CLI not found", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(e.stderr or e.stdout, file=sys.stderr)
        return 1
    issues = json.loads(proc.stdout) if proc.stdout.strip() else []
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Agent backlog snapshot",
        "",
        f"**Generated:** {now} · **repo:** `{repo}` · **label:** `agent-task`",
        "",
    ]
    if not issues:
        lines.append("*No open issues with label `agent-task`.*")
    else:
        for item in issues:
            title = item.get("title", "").strip() or f"Issue #{item.get('number')}"
            url = item.get("url", "")
            lines.append(f"- [{title}]({url})")
    lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"agent_backlog_snapshot: wrote {len(issues)} issue(s) to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Verify a PR is eligible for agent auto-merge (low-risk agent branches only).

Exits 0 when all changed paths are outside protected deny-list substrings.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DENY_PATH_SUBSTRINGS: tuple[str, ...] = (
    ".github/workflows/",
    "docs/scoring/",
    "SECURITY.md",
    "digikey/",
    "digiquant/live/",
    "config/live",
)

ALLOWED_BRANCH_PREFIXES: tuple[str, ...] = (
    "cursor/",
    "copilot/",
    "bot/",
    "task/",
)


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _changed_files(base_ref: str) -> list[str]:
    merge_base = _git("merge-base", base_ref, "HEAD")
    raw = _git("diff", "--name-only", merge_base, "HEAD")
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _is_allowed(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return not any(deny in normalized for deny in DENY_PATH_SUBSTRINGS)


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/develop"
    branch = sys.argv[2] if len(sys.argv) > 2 else ""
    if branch and not branch.startswith(ALLOWED_BRANCH_PREFIXES):
        print(
            f"verify_agent_automerge_pr: branch '{branch}' not an agent branch prefix",
            file=sys.stderr,
        )
        return 1
    try:
        files = _changed_files(base)
    except subprocess.CalledProcessError as exc:
        print(f"verify_agent_automerge_pr: git error: {exc}", file=sys.stderr)
        return 1
    bad = [path for path in files if not _is_allowed(path)]
    if bad:
        print("verify_agent_automerge_pr: disallowed paths:", file=sys.stderr)
        for path in bad:
            print(f"  {path}", file=sys.stderr)
        return 1
    print(f"verify_agent_automerge_pr: OK ({len(files)} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

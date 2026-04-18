#!/usr/bin/env python3
"""
Verify that git diff against merge-base only touches paths allowed for doc-only auto-merge.
Exits 0 if OK, 1 if any path is disallowed or SECURITY.md is touched.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Never auto-merge if these paths change.
DENY_PATH_SUBSTRINGS: tuple[str, ...] = (
    ".github/workflows/",
    "SECURITY.md",
)

# Basenames at repo root that are allowed when changed at root only.
ALLOW_ROOT_NAMES: frozenset[str] = frozenset(
    {
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "ARCHITECTURE.md",
        "CONTRIBUTING.md",
        "RELEASES.md",
        "ROADMAP.md",
    }
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
    # merge-base..HEAD
    merge_base = _git("merge-base", base_ref, "HEAD")
    raw = _git("diff", "--name-only", merge_base, "HEAD")
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _is_allowed(path: str) -> bool:
    p = path.replace("\\", "/")
    for deny in DENY_PATH_SUBSTRINGS:
        if deny in p or p == deny.strip("/"):
            return False
    if p.startswith("docs/"):
        return True
    if p.startswith("website/") and p.endswith(".md"):
        return True
    if "/" not in p:
        return p in ALLOW_ROOT_NAMES
    if p.endswith("/AGENTS.md") or p.endswith("/CLAUDE.md"):
        return True
    if p.endswith("/ARCHITECTURE.md"):
        return True
    return False


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/develop"
    try:
        files = _changed_files(base)
    except subprocess.CalledProcessError as e:
        print(f"verify_doc_only_pr: git error: {e}", file=sys.stderr)
        return 1
    bad = [f for f in files if not _is_allowed(f)]
    if bad:
        print("verify_doc_only_pr: disallowed paths:", file=sys.stderr)
        for f in bad:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"verify_doc_only_pr: OK ({len(files)} paths, all allowlisted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

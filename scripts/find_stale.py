#!/usr/bin/env python3
"""
find_stale.py — Detect unused Python functions, classes, and variables.

Uses vulture for dead code detection. Requires: pip install vulture

Usage:
  python3 scripts/find_stale.py                          # scan all source dirs
  python3 scripts/find_stale.py digigraph/src            # scan a specific path
  python3 scripts/find_stale.py --min-confidence 80      # stricter threshold
  python3 scripts/find_stale.py --whitelist .vulture_whitelist.py

Make: make find-stale

A whitelist file (.vulture_whitelist.py) can suppress known false positives:
  # .vulture_whitelist.py
  from digigraph.models import WorkflowState
  WorkflowState.workflow_id   # used dynamically by LangGraph

Exit code is always 0 — this is an informational tool, not a gate.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WHITELIST = REPO_ROOT / ".vulture_whitelist.py"

# Default Python source directories to scan
DEFAULT_PATHS = [
    "digigraph/src",
    "digiquant/src",
    "digisearch/src",
    "digismith/src",
    "digiclaw",
    "digibase/src",
    "digikey/src",
]


def check_vulture() -> bool:
    try:
        result = subprocess.run(["vulture", "--version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def run_vulture(
    paths: list[str],
    min_confidence: int,
    whitelist: Path | None,
) -> tuple[int, str, str]:
    cmd = ["vulture", "--min-confidence", str(min_confidence)]
    if whitelist and whitelist.exists():
        cmd.append(str(whitelist))
    cmd += paths

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return result.returncode, result.stdout, result.stderr


def summarize(output: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in output.splitlines():
        # vulture format: path:line: kind 'name' (confidence%)
        if "unused " in line:
            kind = "other"
            for k in ("function", "class", "variable", "attribute", "import", "method"):
                if f"unused {k}" in line:
                    kind = k
                    break
            counts[kind] = counts.get(kind, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS,
                        help="Paths to scan (default: all Python source dirs)")
    parser.add_argument("--min-confidence", type=int, default=60, metavar="PCT",
                        help="Minimum confidence %% to report (default: 60)")
    parser.add_argument("--whitelist", type=Path, default=DEFAULT_WHITELIST, metavar="FILE",
                        help="Whitelist file for known false positives")
    args = parser.parse_args()

    if not check_vulture():
        print("ERROR: vulture not found. Install with: pip install vulture", file=sys.stderr)
        print("       (dev-only tool — not required for production)")
        return 0  # informational tool, always exit 0

    # Filter to existing paths
    scan_paths = [p for p in args.paths if (REPO_ROOT / p).exists()]
    if not scan_paths:
        print("find-stale: no source paths found to scan")
        return 0

    whitelist = args.whitelist if args.whitelist and args.whitelist.exists() else None
    if args.whitelist and not whitelist:
        # Silently skip missing whitelist — it's optional
        pass

    returncode, stdout, stderr = run_vulture(scan_paths, args.min_confidence, whitelist)

    if stdout.strip():
        print(stdout)
        summary = summarize(stdout)
        total = sum(summary.values())
        breakdown = ", ".join(f"{v} {k}s" for k, v in sorted(summary.items()))
        print(f"\nfind-stale: {total} candidate(s) found at ≥{args.min_confidence}% confidence ({breakdown})")
        print("           Review manually — not all are true dead code (Pydantic models, MCP tools, etc.)")
        print(f"           Add false positives to {args.whitelist}")
    else:
        print(f"find-stale: no dead code found at ≥{args.min_confidence}% confidence")

    if stderr.strip():
        print(stderr, file=sys.stderr)

    return 0  # always informational


if __name__ == "__main__":
    sys.exit(main())

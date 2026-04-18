#!/usr/bin/env python3
"""
clean_imports.py — Remove unused Python imports using ruff.

Usage:
  python3 scripts/clean_imports.py              # report unused imports (default)
  python3 scripts/clean_imports.py --fix        # apply fixes in-place
  python3 scripts/clean_imports.py src/ --fix   # fix a specific path
  python3 scripts/clean_imports.py --diff       # show unified diff of changes

Make:
  make clean-imports         # report unused imports (default, no changes)
  make clean-imports APPLY=1 # apply fixes in-place
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Default Python source directories to scan
DEFAULT_PATHS = [
    "digigraph/src",
    "digiquant/src",
    "digisearch/src",
    "digismith/src",
    "digiclaw",
    "digibase/src",
    "digikey/src",
    "scripts",
]


def run_ruff(paths: list[str], fix: bool, show_diff: bool) -> tuple[int, str, str]:
    cmd = ["ruff", "check", "--select", "F401"]
    if fix:
        cmd.append("--fix")
    if show_diff:
        cmd.append("--diff")
    cmd += paths

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return result.returncode, result.stdout, result.stderr


def count_findings(output: str) -> int:
    return sum(1 for line in output.splitlines() if "F401" in line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS,
                        help="Paths to scan (default: all Python source dirs)")
    parser.add_argument("--fix", action="store_true",
                        help="Apply fixes in-place (default: dry-run)")
    parser.add_argument("--diff", action="store_true",
                        help="Show unified diff of what would change (implies dry-run)")
    args = parser.parse_args()

    # Validate ruff is available
    try:
        check = subprocess.run(["ruff", "--version"], capture_output=True, text=True)
        if check.returncode != 0:
            raise FileNotFoundError
    except FileNotFoundError:
        print("ERROR: ruff not found. Install with: pip install ruff", file=sys.stderr)
        return 1

    # Filter to existing paths only
    scan_paths = [p for p in args.paths if (REPO_ROOT / p).exists()]
    if not scan_paths:
        print("clean-imports: no source paths found to scan")
        return 0

    show_diff = args.diff and not args.fix
    fix = args.fix and not args.diff

    returncode, stdout, stderr = run_ruff(scan_paths, fix=fix, show_diff=show_diff)

    if show_diff:
        if stdout.strip():
            print(stdout)
        else:
            print("clean-imports: no unused imports found")
        return 0

    if fix:
        n = count_findings(stderr) if stderr else 0
        fixed = count_findings(stdout) if stdout else 0
        if stdout.strip():
            print(stdout)
        print(f"clean-imports: fixed {fixed} unused import(s) across {len(scan_paths)} path(s)")
    else:
        # Dry run
        if stdout.strip():
            print(stdout)
            n = count_findings(stdout)
            print(f"\nclean-imports: {n} unused import(s) found (dry-run — use --fix to apply)")
        else:
            print("clean-imports: no unused imports found")

    if stderr.strip():
        print(stderr, file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

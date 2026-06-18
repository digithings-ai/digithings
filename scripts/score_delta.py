#!/usr/bin/env python3
"""
score_delta.py — Compare per-dimension scores between staged changes and origin/develop baseline.

Usage:
  python3 scripts/score_delta.py [--baseline BASELINE_REF] [--format text|json]

Semantics:
  Baseline  = diff score of the full branch vs BASELINE_REF (origin/develop by default),
              i.e. "what does the whole branch add on top of develop?"
  Current   = diff score of staged changes only.

A regression is any dimension where current score < baseline score, regardless of
whether both scores are above the pass threshold.

Exit code:
  0 — no regression detected, or nothing staged to compare
  1 — one or more dimensions regressed (current < baseline)

Run `make score` for the absolute threshold check; `make score-delta` for regression detection.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Allow importing score.py from the same directory
_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))
import score as _score  # noqa: E402

REPO_ROOT = _SCRIPTS_DIR.parent
DIMENSIONS = ("security", "quality", "optimization", "accuracy")


def _score_for_ref(diff_ref: str) -> dict[str, int]:
    """Return per-dimension scores for a git diff ref, defaulting absent dims to 10."""
    diff = _score.get_diff(diff_ref)
    if not diff.strip():
        return {dim: 10 for dim in DIMENSIONS}
    results = _score.scan(diff)
    return {dim: results[dim].score for dim in DIMENSIONS}


def _score_staged() -> dict[str, int]:
    """Return per-dimension scores for staged changes, defaulting to 10 if nothing staged."""
    diff = _score.get_diff("staged")
    if not diff.strip():
        return {dim: 10 for dim in DIMENSIONS}
    results = _score.scan(diff)
    return {dim: results[dim].score for dim in DIMENSIONS}


def _compute_regressions(baseline: dict[str, int], current: dict[str, int]) -> list[str]:
    return [dim for dim in DIMENSIONS if current[dim] < baseline[dim]]


def format_table(baseline: dict[str, int], current: dict[str, int]) -> str:
    regressions = _compute_regressions(baseline, current)
    lines = [
        "",
        "── Score Delta Report ────────────────────────────────────────────────",
        "  Dimension     Baseline   Current   Delta   Status",
        "  ─────────────────────────────────────────────────────────────────",
    ]
    for dim in DIMENSIONS:
        delta = current[dim] - baseline[dim]
        if delta < 0:
            status = "REGRESSED"
        elif delta == 0:
            status = "unchanged"
        else:
            status = "improved"
        lines.append(
            f"  {dim.capitalize():<14s}  {baseline[dim]:>5d}/10   {current[dim]:>5d}/10"
            f"  {delta:>+5d}   {status}"
        )
    lines.append("  ─────────────────────────────────────────────────────────────────")
    if regressions:
        lines.append(f"\n  REGRESSION detected in: {', '.join(regressions)}")
        lines.append("  Staged changes score lower than the develop baseline on these dimensions.")
        lines.append("  Run `make score` for the full threshold check and finding details.")
    else:
        lines.append("\n  No regression — staged changes match or improve the develop baseline.")
    lines.append("")
    return "\n".join(lines)


def format_json_output(baseline: dict[str, int], current: dict[str, int]) -> str:
    regressions = _compute_regressions(baseline, current)
    return json.dumps(
        {
            "regression": bool(regressions),
            "regressed_dimensions": regressions,
            "dimensions": {
                dim: {
                    "baseline": baseline[dim],
                    "current": current[dim],
                    "delta": current[dim] - baseline[dim],
                    "regressed": current[dim] < baseline[dim],
                }
                for dim in DIMENSIONS
            },
        },
        indent=2,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--baseline",
        metavar="REF",
        default="origin/develop",
        help="Git ref to use as baseline (default: origin/develop)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
    )
    args = parser.parse_args()

    # Refresh baseline ref; warn but continue on failure (offline / no remote).
    fetch = subprocess.run(
        ["git", "fetch", "origin", "develop"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if fetch.returncode != 0:
        print(
            f"score-delta: warning: git fetch origin develop failed: {fetch.stderr.strip()}",
            file=sys.stderr,
        )

    # Nothing staged → nothing to compare.
    has_staged = subprocess.run(
        ["git", "diff", "--staged", "--quiet"], cwd=REPO_ROOT
    ).returncode != 0

    if not has_staged:
        if args.format == "json":
            print(json.dumps({"regression": False, "message": "nothing staged to compare", "dimensions": {}}))
        else:
            print("score-delta: nothing staged — no delta to report (exit 0)")
        return 0

    baseline = _score_for_ref(args.baseline)
    current = _score_staged()

    if args.format == "json":
        print(format_json_output(baseline, current))
    else:
        print(format_table(baseline, current))

    return 1 if _compute_regressions(baseline, current) else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
score.py — Self-score staged or recent changes against the 4-dimension rubrics.

Usage:
  python3 scripts/score.py                  # score staged changes (default)
  python3 scripts/score.py --diff HEAD~1    # score last commit
  python3 scripts/score.py --format json    # machine-readable output

Exit code:
  0 — all dimensions meet thresholds (Security ≥8, Quality ≥8, Optimization ≥7, Accuracy ≥9)
  1 — one or more dimensions below threshold, or no diff to score

This is a heuristic scanner — it flags known anti-patterns by regex.
It is NOT a full static analyzer. Treat results as a checklist aide, not a gate.
Review edge cases before opening a PR.

Full rubric criteria: docs/scoring/
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Score thresholds (mirrors agents.yml scoring_thresholds)
THRESHOLDS = {
    "security": 8,
    "quality": 8,
    "optimization": 7,
    "accuracy": 9,
}

# Paths where flagged patterns are intentional (document reason per entry).
SCORE_PATH_SUPPRESSIONS: tuple[tuple[str, str], ...] = (
    (
        "digigraph/src/digigraph/tools/analytics/execute_python_worker.py",
        "bare exec()",
    ),
    (
        "digigraph/src/digigraph/tools/analytics/execute_python_sandbox.py",
        "subprocess",
    ),
    (
        "digigraph/src/digigraph/llm.py",
        "blocking sleep",
    ),
    ("digiquant/src/digiquant/tearsheet", "pandas"),
    ("digiquant/src/digiquant/tearsheet", "pd."),
    # Atlas agent scripts: yfinance/pandas_ta boundary (SIMP-038/039 deferred Polars migration)
    ("digiquant/scripts/atlas/preload-history.py", "pandas"),
    ("digiquant/scripts/atlas/preload-history.py", "pd."),
    ("digiquant/scripts/atlas/update_tearsheet.py", "pandas"),
    # Wave 7 partial typing — full Pydantic pass tracked in WAVE7-COMPLETION.md
    ("digiquant/src/digiquant/atlas/testing/simulator.py", "untyped any"),
    ("digiquant/src/digiquant/data/prices/macro_ingest.py", "untyped any"),
    ("digisearch/src/digisearch/orchestrator_tools.py", "untyped any"),
    # RegExp.exec in terminal highlighter — not Python exec() (DESLOP-027)
    ("frontend/design/terminal/highlight-dom.js", "bare exec()"),
)

# Paths excluded from scoring (meta-tooling, audit prose, security policy docs).
SCORE_SKIP_PATH_FRAGMENTS: tuple[str, ...] = (
    "scripts/score.py",
    "docs/reviews/",
    "digigraph/docs/SECURITY.md",
    "digigraph/src/digigraph/tools/analytics/execute_python.py",
)

# ── Anti-pattern definitions ──────────────────────────────────────────────────
# Each entry: (pattern, description, dimension, only_added_lines)
# only_added_lines=True means only flag lines starting with "+" in the diff

PATTERNS: list[tuple[re.Pattern, str, str, bool]] = [
    # Security
    (re.compile(r"import pandas"), "pandas import (use Polars)", "security", True),
    (re.compile(r"\beval\s*\("), "bare eval() — code injection risk", "security", True),
    (re.compile(r"\bexec\s*\("), "bare exec() — code injection risk", "security", True),
    (
        re.compile(r"shell\s*=\s*True"),
        "subprocess shell=True — command injection risk",
        "security",
        True,
    ),
    (
        re.compile(r"(?i)(api_key|password|secret|token)\s*=\s*['\"][^'\"]{8,}['\"]"),
        "potential hardcoded secret",
        "security",
        True,
    ),
    (re.compile(r"0\.0\.0\.0"), "binding to 0.0.0.0 (loopback-only rule)", "security", True),
    (
        re.compile(r"DIGICHAT_DEV_AUTH.*=.*1|DIGIKEY_ALLOW_DEV_GLOBAL.*=.*1"),
        "dev-only flag that must not reach production",
        "security",
        True,
    ),
    (
        re.compile(r"\b(live_trading|execute_trade|place_order)\b"),
        "live-trading path touched — requires human approval (see agents.yml human_gates)",
        "security",
        True,
    ),
    # Quality
    (
        re.compile(r"from typing import.*\bAny\b(?!.*# noqa)"),
        "untyped Any without # noqa annotation",
        "quality",
        True,
    ),
    (
        re.compile(r"@validator\b"),
        "Pydantic v1 @validator (use @field_validator v2)",
        "quality",
        True,
    ),
    (re.compile(r"\bpd\."), "pandas usage (pd.) — use Polars", "quality", True),
    (re.compile(r"import pandas"), "pandas import — use Polars", "quality", True),
    (
        re.compile(r"except\s*:\s*$|except\s*:\s*#"),
        "bare except clause — hides errors",
        "quality",
        True,
    ),
    (
        re.compile(r"# type: ignore(?!\s*\[)"),
        "unscoped type: ignore — be specific",
        "quality",
        True,
    ),
    # Optimization
    (
        re.compile(r"openai\.(?:ChatCompletion|Completion|chat\.completions)"),
        "direct openai.* call — route through LiteLLM (digigraph/llm.py)",
        "optimization",
        True,
    ),
    (
        re.compile(r"\.collect\(\)\s*\.\s*filter\("),
        "Polars .collect() before .filter() — apply filter before collecting",
        "optimization",
        True,
    ),
    (
        re.compile(r"for .+ in .+:\s*\n.*\.query\(|for .+ in .+:\s*\n.*\.get\("),
        "possible N+1 query pattern in loop",
        "optimization",
        True,
    ),
    (
        re.compile(r"time\.sleep\((?!0)"),
        "blocking sleep in sync code — use asyncio.sleep in async context",
        "optimization",
        True,
    ),
    (
        re.compile(r"^import requests\b|^from requests\b"),
        "direct `requests` import — prefer httpx (async-safe) or the shared HTTP client in digibase",
        "optimization",
        True,
    ),
    # Accuracy
    (
        re.compile(r"except\s+Exception\s*:\s*\n\s*pass"),
        "silenced exception (except Exception: pass) — errors must not be swallowed",
        "accuracy",
        True,
    ),
    (
        re.compile(r"except\s*:\s*\n\s*pass"),
        "silenced bare exception — errors must not be swallowed",
        "accuracy",
        True,
    ),
    (re.compile(r"TODO|FIXME|HACK|XXX"), "unresolved TODO/FIXME in diff", "accuracy", True),
    (
        re.compile(r"raise NotImplementedError"),
        "NotImplementedError stub in production path",
        "accuracy",
        True,
    ),
]


@dataclass
class Finding:
    dimension: str
    description: str
    file: str
    line_no: int
    line: str


@dataclass
class DimensionResult:
    name: str
    threshold: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def score(self) -> int:
        return max(0, 10 - len(self.findings))

    @property
    def passed(self) -> bool:
        return self.score >= self.threshold


def get_diff(mode: str) -> str:
    if mode == "staged":
        result = subprocess.run(
            ["git", "diff", "--staged"], capture_output=True, text=True, cwd=REPO_ROOT
        )
    else:
        result = subprocess.run(
            ["git", "diff", mode], capture_output=True, text=True, cwd=REPO_ROOT
        )
    return result.stdout


def parse_diff_lines(diff: str) -> list[tuple[str, int, str, bool]]:
    """Parse diff into (filename, line_no, content, is_added)."""
    entries: list[tuple[str, int, str, bool]] = []
    current_file = ""
    current_line = 0

    for raw_line in diff.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
            current_line = 0
        elif raw_line.startswith("@@ "):
            match = re.search(r"\+(\d+)", raw_line)
            if match:
                current_line = int(match.group(1)) - 1
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            current_line += 1
            entries.append((current_file, current_line, raw_line[1:], True))
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            # Don't advance line counter for removed lines
            entries.append((current_file, current_line, raw_line[1:], False))
        elif not raw_line.startswith("\\"):
            current_line += 1

    return entries


def _skip_file(filename: str) -> bool:
    return any(fragment in filename for fragment in SCORE_SKIP_PATH_FRAGMENTS)


def _is_test_fixture_file(filename: str) -> bool:
    """Vitest/pytest fixtures often set *_TOKEN env vars — not production secrets."""
    return (
        filename.startswith("tests/")
        or "/tests/" in filename
        or ".test." in filename
        or filename.endswith("_test.py")
    )


def _is_suppressed(filename: str, description: str) -> bool:
    if _skip_file(filename):
        return True
    if description == "potential hardcoded secret" and _is_test_fixture_file(filename):
        return True
    for path_fragment, desc_fragment in SCORE_PATH_SUPPRESSIONS:
        if path_fragment in filename and desc_fragment.lower() in description.lower():
            return True
    return False


def scan(diff: str) -> dict[str, DimensionResult]:
    results = {dim: DimensionResult(dim, thresh) for dim, thresh in THRESHOLDS.items()}
    diff_lines = parse_diff_lines(diff)

    for pattern, description, dimension, only_added in PATTERNS:
        for filename, line_no, content, is_added in diff_lines:
            if _is_suppressed(filename, description):
                continue
            # Skip non-Python/non-relevant files for certain checks
            if only_added and not is_added:
                continue
            # Only check Python files for Python-specific patterns
            if "pandas" in description.lower() or "polars" in description.lower():
                if not filename.endswith(".py"):
                    continue
            if pattern.search(content):
                results[dimension].findings.append(
                    Finding(dimension, description, filename, line_no, content.strip())
                )

    return results


def format_text(results: dict[str, DimensionResult], diff_mode: str) -> str:
    lines = [f"\n── Score Report ({diff_mode}) ──────────────────────────────────────────\n"]
    all_passed = all(r.passed for r in results.values())

    for dim, result in results.items():
        status = "✓ PASS" if result.passed else "✗ FAIL"
        lines.append(
            f"  {status}  {dim.capitalize():12s}  {result.score}/10  (threshold ≥{result.threshold})"
        )
        for f in result.findings:
            lines.append(f"           ↳  {f.file}:{f.line_no}  —  {f.description}")
            lines.append(f"              {f.line[:100]}")

    lines.append("")
    if all_passed:
        lines.append("  All dimensions meet thresholds — PR eligible for review.")
    else:
        failed = [d for d, r in results.items() if not r.passed]
        lines.append(f"  Dimensions below threshold: {', '.join(failed)}")
        lines.append("  Address findings above before opening a PR.")
    lines.append("")
    return "\n".join(lines)


def format_json(results: dict[str, DimensionResult]) -> str:
    out = {
        "passed": all(r.passed for r in results.values()),
        "dimensions": {
            dim: {
                "score": r.score,
                "threshold": r.threshold,
                "passed": r.passed,
                "findings": [
                    {"file": f.file, "line": f.line_no, "description": f.description}
                    for f in r.findings
                ],
            }
            for dim, r in results.items()
        },
    }
    return json.dumps(out, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        default=False,
        help="Score staged changes (default if no flag given)",
    )
    parser.add_argument(
        "--diff", metavar="REF", default=None, help="Score diff against ref, e.g. HEAD~1 or main"
    )
    parser.add_argument(
        "--diff-file",
        metavar="PATH",
        default=None,
        help="Score a precomputed unified diff file (e.g. code-only paths from CI)",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if args.diff_file:
        diff = Path(args.diff_file).read_text(encoding="utf-8")
        diff_mode = args.diff_file
    else:
        diff_mode = args.diff if args.diff else "staged"
        diff = get_diff(diff_mode)

    if not diff.strip():
        if args.format == "json":
            print(json.dumps({"passed": True, "message": "nothing to score", "dimensions": {}}))
        else:
            print(f"score: nothing to score (no diff for '{diff_mode}')")
        return 0

    results = scan(diff)

    if args.format == "json":
        print(format_json(results))
    else:
        print(format_text(results, diff_mode))

    return 0 if all(r.passed for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

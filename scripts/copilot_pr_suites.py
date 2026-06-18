#!/usr/bin/env python3
"""Map changed files to CI suites for Copilot targeted PR checks."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_PATHS = REPO_ROOT / "scripts" / "ci_paths.yaml"

# Heavy or flaky suites omitted from the Copilot fast path.
SKIP_SUITES = frozenset({"compose", "pip_audit", "nautilus_smoke", "e2e_contract"})

SUITE_TEST_COMMANDS: dict[str, list[str]] = {
    "digibase": ["python -m pytest tests/db/ -m unit -v --tb=short"],
    "digikey": ["python -m pytest tests/dk/ -m unit -v --tb=short"],
    "digismith": ["python -m pytest tests/dsm/ -m unit -v --tb=short"],
    "digiclaw": ["python -m pytest tests/dc/ -m unit -v --tb=short"],
    "digiquant": ["python -m pytest tests/dq/ -m unit -v --tb=short --ignore=tests/dq/test_nautilus_runner.py"],
    "digisearch": ["python -m pytest tests/ds/ -m unit -v --tb=short"],
    "digigraph": ["python -m pytest tests/dg/ -m unit -v --tb=short"],
    "digichat": ["npm ci", "npm run test --workspace digichat"],
    "olympus": ["npm ci", "npm run test --workspace olympus"],
    "atlas_graph": [
        "python -m pytest tests/dq/atlas/ tests/dq/hermes/ -m unit -v --tb=short",
    ],
    "ruff_and_scripts": [
        "python -m pytest tests/scripts/ tests/agents/ -m 'unit or baseline' -v --tb=short",
        "bash scripts/check_pandas_boundary.sh",
    ],
}

RUFF_PATHS = [
    "digibase/src",
    "digiclaw/src",
    "digigraph/src",
    "digiquant/src",
    "digisearch/src",
    "digismith/src",
    "digikey/src",
    "tests",
    "scripts",
]


def _load_filters() -> dict[str, list[str]]:
    data = yaml.safe_load(CI_PATHS.read_text(encoding="utf-8"))
    return {str(k): [str(p) for p in v] for k, v in data.items()}


def _matches(path: str, pattern: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    pat = pattern.replace("\\", "/").lstrip("./")
    return fnmatch.fnmatch(normalized, pat) or fnmatch.fnmatch(f"./{normalized}", pat)


def suites_for_files(files: list[str]) -> list[str]:
    filters = _load_filters()
    matched: set[str] = set()
    for suite, patterns in filters.items():
        if suite in SKIP_SUITES:
            continue
        for path in files:
            if any(_matches(path, pat) for pat in patterns):
                matched.add(suite)
                break
    if files and not matched:
        matched.add("ruff_and_scripts")
    if any(f.endswith(".py") for f in files):
        matched.add("ruff_and_scripts")
    return sorted(matched)


def changed_files(base_ref: str, head_ref: str = "HEAD") -> list[str]:
    merge_base = subprocess.check_output(
        ["git", "merge-base", base_ref, head_ref],
        cwd=REPO_ROOT,
        text=True,
    ).strip()
    raw = subprocess.check_output(
        ["git", "diff", "--name-only", merge_base, head_ref],
        cwd=REPO_ROOT,
        text=True,
    )
    return [line.strip() for line in raw.splitlines() if line.strip()]


def ruff_targets(files: list[str]) -> list[str]:
    targets: list[str] = []
    for path in files:
        if not path.endswith(".py"):
            continue
        normalized = path.replace("\\", "/")
        if any(normalized.startswith(prefix) for prefix in RUFF_PATHS):
            targets.append(path)
    return sorted(set(targets))


def run_suite_commands(suites: list[str], *, changed: list[str]) -> int:
    """Run install once then suite commands. Used by Copilot targeted CI workflow."""
    subprocess.run(
        [
            "python",
            "-m",
            "pip",
            "install",
            "-U",
            "pip",
            "ruff",
            "pytest",
            "polars",
            "pydantic",
            "pyyaml",
            "tabulate",
            "httpx",
            "cryptography",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    for pkg in ("digibase", "digikey", "digisearch", "digiquant", "digigraph", "digismith", "digiclaw"):
        pyproject = REPO_ROOT / pkg / "pyproject.toml"
        if pyproject.exists():
            subprocess.run(
                ["pip", "install", "-e", f"./{pkg}[dev]"],
                cwd=REPO_ROOT,
                check=False,
            )

    targets = ruff_targets(changed)
    if targets:
        subprocess.run(["python", "-m", "ruff", "check", *targets], cwd=REPO_ROOT, check=True)

    if "digichat" in suites or "olympus" in suites:
        subprocess.run(["npm", "ci"], cwd=REPO_ROOT, check=True)

    for suite in suites:
        if suite == "score":
            continue
        for cmd in SUITE_TEST_COMMANDS.get(suite, []):
            subprocess.run(cmd, cwd=REPO_ROOT, check=True, shell=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan or run Copilot targeted CI suites")
    parser.add_argument("--base-ref", default="origin/develop")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--json", action="store_true", help="Print suite plan as JSON")
    parser.add_argument("--run", action="store_true", help="Run planned suite commands")
    args = parser.parse_args()

    files = changed_files(args.base_ref, args.head_ref)
    suites = suites_for_files(files)
    plan = {
        "changed_files": files,
        "suites": suites,
        "ruff_targets": ruff_targets(files),
        **{suite: suite in suites for suite in sorted(_load_filters()) if suite not in SKIP_SUITES},
    }
    if args.json:
        print(json.dumps(plan, indent=2))
        return 0
    print(f"Changed: {len(files)} file(s)")
    print(f"Suites: {', '.join(suites) or '(none)'}")
    if args.run:
        return run_suite_commands(suites, changed=files)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

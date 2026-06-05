#!/usr/bin/env python3
"""Validate scripts/project_fields.tsv against open agent-task issues."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TSV = REPO_ROOT / "scripts" / "project_fields.tsv"
VALID_MODELS = frozenset({"sonnet", "opus"})


def _gh_json(args: list[str]) -> list[dict]:
    out = subprocess.check_output(["gh", *args], text=True, cwd=REPO_ROOT)
    return json.loads(out)


def _load_tsv() -> dict[int, list[str]]:
    rows: dict[int, list[str]] = {}
    with TSV.open(encoding="utf-8") as handle:
        next(handle, None)  # header
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            rows[int(parts[0])] = parts
    return rows


def main() -> int:
    if not TSV.is_file():
        print(f"TSV not found: {TSV}", file=sys.stderr)
        return 1

    rows = _load_tsv()
    issues = _gh_json(
        [
            "issue",
            "list",
            "--label",
            "agent-task",
            "--state",
            "open",
            "--limit",
            "500",
            "--json",
            "number,title",
        ]
    )
    if not issues:
        print("No open agent-task issues — nothing to check.")
        return 0

    failures: list[str] = []
    for issue in issues:
        num = issue["number"]
        title = issue["title"]
        parts = rows.get(num)
        if parts is None:
            failures.append(f"#{num} «{title}» — missing from {TSV.relative_to(REPO_ROOT)}")
            continue
        if len(parts) < 6:
            failures.append(f"#{num} «{title}» — expected 6 columns, got {len(parts)}")
            continue
        phase, model = parts[1], parts[5]
        if phase.lower().startswith("phase-") and phase[6:7].isdigit():
            failures.append(f"#{num} «{title}» — placeholder phase: «{phase}»")
            continue
        if model not in VALID_MODELS:
            failures.append(
                f"#{num} «{title}» — invalid model «{model}» (must be sonnet or opus)"
            )
            continue
        print(f"✅  #{num} — phase: {phase} | model: {model}")

    if failures:
        print(file=sys.stderr)
        for line in failures:
            print(f"❌  {line}", file=sys.stderr)
        print(
            "\nFix: update scripts/project_fields.tsv (tab-separated, 6 columns) "
            "or run scripts/infer_project_fields_row.py for new issues.",
            file=sys.stderr,
        )
        return 1

    print(f"\nAll {len(issues)} open agent-task issues are covered. ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

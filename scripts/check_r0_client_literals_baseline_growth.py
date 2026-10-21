#!/usr/bin/env python3
"""R0 client-literal allowance baseline growth guard (DIG-4577).

The R0 client-literal allowance baseline
(``scripts/r0_client_literals_baseline.json``) lists the paths whose guarded
client literals are grandfathered. The baseline may only SHRINK: a new literal
must be removed from the source, never added to the allowance.

This gate compares the baseline in the tree under test against the baseline at
the tip of the base branch and fails when the tree's baseline grew:

  * a path listed in the tree but not in the base baseline (a new entry),
  * a path whose count is higher than the base baseline's count,
  * a base branch that has no baseline file at all (the whole allowance would
    be new).

A smaller or identical baseline passes: shrinking the allowance is the point.

Why the base branch TIP and not the merge base: the question is "would merging
this branch increase the allowance?", so the comparison is the branch's own
baseline against the base branch as it stands today. That also attributes any
growth to this branch rather than to a base that moved underneath it.

Only file paths and counts are printed, never a literal value: CI logs on this
repo are public. The failure text tells the reader to remove the literal from
the source instead of allowlisting it.

The gate fails closed. A tool error (unresolvable base ref, unreadable or
malformed baseline) exits 2 and is never reported as clean.

Exit codes: 0 clean, 1 growth found, 2 tool error.

Run locally:
    python3 scripts/check_r0_client_literals_baseline_growth.py \
        --base-ref origin/develop
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_REL = "scripts/r0_client_literals_baseline.json"
DEFAULT_BASE_REF = "origin/develop"


class ToolError(RuntimeError):
    """The gate could not measure; it must fail closed rather than pass."""


def _git(root: Path, args: list[str]) -> str:
    """Run a git command in ``root``; raise ToolError on failure."""
    proc = subprocess.run(
        ["git", "-C", str(root)] + args,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit {proc.returncode}"
        raise ToolError(f"git {' '.join(args)} failed: {tail}")
    return proc.stdout


def resolve_base_commit(root: Path, base_ref: str) -> str:
    """The commit the base branch points at; unresolvable is a tool error."""
    out = _git(root, ["rev-parse", "--verify", f"{base_ref}^{{commit}}"])
    sha = out.strip()
    if not sha:
        raise ToolError(f"base ref '{base_ref}' does not resolve to a commit")
    return sha


def base_has_baseline(root: Path, base_sha: str) -> bool:
    """True when the base commit carries the baseline file."""
    out = _git(root, ["ls-tree", base_sha, "--", BASELINE_REL])
    return bool(out.strip())


def read_head_baseline(root: Path) -> str:
    """The baseline of the tree under test (read from the working tree)."""
    path = root / BASELINE_REL
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ToolError(f"{BASELINE_REL} is not readable in this tree: {exc.strerror}")


def read_base_baseline(root: Path, base_sha: str) -> str:
    """The baseline as of the base commit."""
    return _git(root, ["show", f"{base_sha}:{BASELINE_REL}"])


def load_entries(raw: str, source: str) -> dict[str, int]:
    """path -> count from a baseline document."""
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ToolError(f"{source} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise ToolError(f"{source} is not a JSON object")
    entries = data.get("entries")
    if not isinstance(entries, dict):
        raise ToolError(f"{source} has no 'entries' object")
    counts: dict[str, int] = {}
    for path, spec in entries.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("count"), int):
            raise ToolError(f"{source} entry '{path}' has no integer 'count'")
        counts[path] = spec["count"]
    return counts


def compare(
    base_entries: dict[str, int],
    head_entries: dict[str, int],
    base_missing: bool = False,
) -> list[str]:
    """Findings; empty means the allowance did not grow."""
    if base_missing:
        return [
            f"BASE-MISSING: the base branch has no {BASELINE_REL} "
            f"(0 baselined file(s)); this branch lists {len(head_entries)} file(s)"
        ]
    findings: list[str] = []
    for path in sorted(head_entries):
        head_count = head_entries[path]
        base_count = base_entries.get(path)
        if base_count is None:
            findings.append(
                f"NEW {path}: allowance entry with count {head_count} "
                "is not present in the base baseline"
            )
        elif head_count > base_count:
            findings.append(
                f"GROW {path}: baseline count {base_count} -> {head_count}"
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(REPO_ROOT))
    ap.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    args = ap.parse_args(argv)
    root = Path(args.root)

    try:
        head_entries = load_entries(read_head_baseline(root), BASELINE_REL)
        base_sha = resolve_base_commit(root, args.base_ref)
        base_present = base_has_baseline(root, base_sha)
        base_entries: dict[str, int] = {}
        if base_present:
            base_entries = load_entries(
                read_base_baseline(root, base_sha),
                f"{args.base_ref}:{BASELINE_REL}",
            )
    except ToolError as exc:
        print(f"r0-client-literal-baseline-growth: FAIL (tool error) - {exc}")
        print("This gate fails closed: a tool error is never reported as clean.")
        return 2

    findings = compare(base_entries, head_entries, base_missing=not base_present)
    if findings:
        print(
            f"r0-client-literal-baseline-growth: {len(findings)} finding(s) - "
            "the allowance baseline may only shrink."
        )
        print(
            "Remove the offending literal from the source instead of allowlisting it: "
            f"do not add a path to {BASELINE_REL} and do not raise an existing count."
        )
        for finding in findings:
            print(f"  FAIL  [{finding}]")
        print(
            f"FILES: the base baseline lists {len(base_entries)} file(s); "
            f"this branch lists {len(head_entries)} file(s)"
        )
        return 1

    print(
        "r0-client-literal-baseline-growth: clean - the baseline is unchanged "
        f"or smaller than the base branch ({len(head_entries)} file(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Shared CI check gating for agent PR auto-merge."""

from __future__ import annotations

import json
import subprocess

AGENT_BRANCH_PREFIXES = ("cursor/", "copilot/", "bot/", "task/", "claude/")
# copilot/* stays a valid branch name in BRANCHING.md, so the prefix above keeps it —
# but there is no Copilot-specific check any more. The "Copilot targeted CI" arm was
# removed with copilot-pr-targeted-ci.yml (2026-08-05): that check run can never be
# posted again, so a branch matching copilot/* is now gated on main CI like any other.
# task/* and claude/* added 2026-08: these are the two largest sources of agent PR
# volume in this repo (38 + 19 of the last 100 PRs) and previously had zero
# automerge-eligibility coverage at all — the allowlist here only ever tracked
# cursor/bot, which covered a smaller slice than it excluded.
# Optional rubric job (reusable workflow → ``score / score``). AGENTS.md: not a
# merge gate. Keep out of hard-fail lists so score-only red does not block
# automerge / merge-when-ready (#3528).
IGNORED_CHECK_NAMES: frozenset[str] = frozenset({"score / score"})


def _gh_json(*args: str) -> object:
    out = subprocess.check_output(["gh", *args], text=True)
    return json.loads(out)


def agent_checks_ok(repo: str, pr_number: int, head_branch: str, head_sha: str) -> tuple[bool, str]:
    """Return (ok, reason)."""
    if not head_branch.startswith(AGENT_BRANCH_PREFIXES):
        checks = _gh_json(
            "pr",
            "checks",
            str(pr_number),
            "--repo",
            repo,
            "--json",
            "name,state",
        )
        bad = [
            c
            for c in checks
            if c.get("state") != "SUCCESS" and c.get("name") not in IGNORED_CHECK_NAMES
        ]
        if bad:
            return False, f"{len(bad)} check(s) not SUCCESS"
        return True, "all checks SUCCESS"

    if head_branch.startswith("copilot/"):
        checks = _gh_json("pr", "checks", str(pr_number), "--repo", repo, "--json", "name,state")
        main_ci = [c for c in checks if c.get("name") == "CI" and c.get("state") == "SUCCESS"]
        if main_ci:
            return True, "main CI success"
        return False, "missing or failed main CI"

    checks = _gh_json(
        "pr",
        "checks",
        str(pr_number),
        "--repo",
        repo,
        "--json",
        "name,state",
    )
    bad = [
        c
        for c in checks
        if c.get("state") != "SUCCESS" and c.get("name") not in IGNORED_CHECK_NAMES
    ]
    if bad:
        return False, f"{len(bad)} non-ignored check(s) not SUCCESS"
    return True, "agent checks SUCCESS"


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 5:
        print(
            "usage: agent_pr_checks.py <repo> <pr_number> <head_branch> <head_sha>", file=sys.stderr
        )
        raise SystemExit(2)
    ok, reason = agent_checks_ok(sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4])
    print(reason)
    raise SystemExit(0 if ok else 1)

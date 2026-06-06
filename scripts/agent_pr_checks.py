#!/usr/bin/env python3
"""Shared CI check gating for agent PR auto-merge."""

from __future__ import annotations

import json
import subprocess

COPILOT_TARGETED_CI = "Copilot targeted CI"
AGENT_BRANCH_PREFIXES = ("cursor/", "copilot/", "bot/")
# Main CI from bot actors stays action_required — ignore for agent branches.
IGNORED_CHECK_NAMES = frozenset({"CI"})


def _gh_json(*args: str) -> object:
    out = subprocess.check_output(["gh", *args], text=True)
    return json.loads(out)


def copilot_targeted_ci_state(repo: str, head_sha: str) -> str:
    """Return missing, pending, success, or failure for the Copilot targeted CI check."""
    owner, name = repo.split("/", 1)
    data = _gh_json(
        "api",
        f"repos/{owner}/{name}/commits/{head_sha}/check-runs",
        "--jq",
        f'[.check_runs[] | select(.name == "{COPILOT_TARGETED_CI}")] | last',
    )
    if not data:
        return "missing"
    conclusion = (data.get("conclusion") or "").lower()
    status = (data.get("status") or "").lower()
    if conclusion == "success":
        return "success"
    if conclusion == "failure":
        return "failure"
    if status in {"in_progress", "queued", "pending"}:
        return "pending"
    return "missing"


def copilot_targeted_ci_ok(repo: str, head_sha: str) -> bool:
    return copilot_targeted_ci_state(repo, head_sha) == "success"


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
        bad = [c for c in checks if c.get("state") != "SUCCESS"]
        if bad:
            return False, f"{len(bad)} check(s) not SUCCESS"
        return True, "all checks SUCCESS"

    if head_branch.startswith("copilot/"):
        if copilot_targeted_ci_ok(repo, head_sha):
            return True, f"{COPILOT_TARGETED_CI} success"
        return False, f"missing or failed {COPILOT_TARGETED_CI}"

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
        print("usage: agent_pr_checks.py <repo> <pr_number> <head_branch> <head_sha>", file=sys.stderr)
        raise SystemExit(2)
    ok, reason = agent_checks_ok(sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4])
    print(reason)
    raise SystemExit(0 if ok else 1)

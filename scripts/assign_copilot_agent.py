#!/usr/bin/env python3
"""Assign GitHub Copilot coding agent to an issue via REST API."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

DEFAULT_OWNER = "digithings-ai"
DEFAULT_REPO = "digithings"
DEFAULT_BASE = "develop"
COPILOT_ASSIGNEE = "copilot-swe-agent[bot]"
COPILOT_LOGINS = frozenset({"copilot", "copilot-swe-agent", "copilot-swe-agent[bot]"})


def _gh_json(*args: str) -> object:
    out = subprocess.check_output(["gh", *args], text=True)
    return json.loads(out)


def _issue_assignees(owner: str, repo: str, issue_number: int) -> list[str]:
    data = _gh_json("issue", "view", str(issue_number), "--repo", f"{owner}/{repo}", "--json", "assignees")
    return [a["login"] for a in data.get("assignees", [])]


def is_copilot_assigned(assignees: list[str]) -> bool:
    return any(login.lower() in {name.lower() for name in COPILOT_LOGINS} for login in assignees)


def assign_copilot(
    *,
    owner: str,
    repo: str,
    issue_number: int,
    base_ref: str = DEFAULT_BASE,
    custom_instructions: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Assign Copilot to an issue. Returns True when assignment is present or created."""
    issue = _gh_json(
        "issue",
        "view",
        str(issue_number),
        "--repo",
        f"{owner}/{repo}",
        "--json",
        "title,body,assignees",
    )
    assignees = [a["login"] for a in issue.get("assignees", [])]
    if is_copilot_assigned(assignees):
        print(f"Copilot already assigned to issue #{issue_number}: {assignees}")
        return True

    instructions = custom_instructions or (
        f"Complete issue #{issue_number}: {issue['title']}\n\n"
        f"{(issue.get('body') or '')[:4000]}\n\n"
        f"Open a PR targeting `{base_ref}` with `Fixes #{issue_number}` in the body. "
        "Run CI locally where possible; keep the diff minimal."
    )

    payload = {
        "assignees": [COPILOT_ASSIGNEE],
        "agent_assignment": {
            "target_repo": f"{owner}/{repo}",
            "base_branch": base_ref,
            "custom_instructions": instructions[:8000],
            "custom_agent": "",
            "model": "",
        },
    }

    if dry_run:
        print(
            json.dumps(
                {
                    "issue": issue_number,
                    "base_branch": base_ref,
                    "instructions_preview": instructions[:300],
                },
                indent=2,
            )
        )
        return False

    subprocess.check_output(
        [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{owner}/{repo}/issues/{issue_number}/assignees",
            "--input",
            "-",
        ],
        input=json.dumps(payload),
        text=True,
    )
    updated = _issue_assignees(owner, repo, issue_number)
    if is_copilot_assigned(updated):
        print(f"Assigned Copilot to issue #{issue_number}: {updated}")
        return True
    raise SystemExit(f"Assignment API succeeded but Copilot not in assignees: {updated}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Assign Copilot coding agent to a GitHub issue")
    parser.add_argument("issue_number", type=int, nargs="?", default=None)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", f"{DEFAULT_OWNER}/{DEFAULT_REPO}").split("/")[
            -1
        ],
    )
    parser.add_argument("--base-ref", default=os.environ.get("COPILOT_BASE_REF", DEFAULT_BASE))
    parser.add_argument("--instructions", default=None)
    parser.add_argument("--check-only", action="store_true", help="Exit 0 if Copilot assigned")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.check_only:
        if args.issue_number is None:
            print("issue_number required with --check-only", file=sys.stderr)
            return 2
        return 0 if is_copilot_assigned(_issue_assignees(args.owner, args.repo, args.issue_number)) else 1

    if args.issue_number is None:
        parser.error("issue_number is required unless --check-only is set")

    assign_copilot(
        owner=args.owner,
        repo=args.repo,
        issue_number=args.issue_number,
        base_ref=args.base_ref,
        custom_instructions=args.instructions,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

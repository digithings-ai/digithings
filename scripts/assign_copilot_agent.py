#!/usr/bin/env python3
"""Assign GitHub Copilot coding agent to an issue via GraphQL API."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

GRAPHQL_FEATURES = "issues_copilot_assignment_api_support,coding_agent_model_selection"
DEFAULT_OWNER = "digithings-ai"
DEFAULT_REPO = "digithings"
DEFAULT_BASE = "develop"
COPILOT_LOGINS = frozenset({"copilot-swe-agent", "copilot", "copilot-swe-agent[bot]"})

MUTATION = """
mutation($input: ReplaceActorsForAssignableInput!) {
  replaceActorsForAssignable(input: $input) {
    assignable {
      ... on Issue {
        id
        number
        assignees(first: 5) { nodes { login } }
        assignedActors(first: 5) {
          nodes {
            ... on User { login }
            ... on Bot { login }
          }
        }
      }
    }
  }
}
"""

ISSUE_QUERY = """
query($o: String!, $n: String!, $num: Int!) {
  repository(owner: $o, name: $n) {
    id
    issue(number: $num) {
      id
      title
      body
      assignees(first: 5) { nodes { login } }
      assignedActors(first: 5) {
        nodes {
          ... on User { login }
          ... on Bot { login }
        }
      }
    }
  }
  copilot: user(login: "copilot-swe-agent") { id }
}
"""


def _graphql(query: str, variables: dict, *, preview: bool = False) -> dict:
    payload = json.dumps({"query": query, "variables": variables})
    cmd = ["gh", "api", "graphql", "--input", "-"]
    if preview:
        cmd.extend(["-H", f"GraphQL-Features: {GRAPHQL_FEATURES}"])
    out = subprocess.check_output(cmd, input=payload, text=True)
    result = json.loads(out)
    if result.get("errors"):
        raise SystemExit(f"GraphQL errors: {json.dumps(result['errors'], indent=2)}")
    return result["data"]


def _actor_logins(issue: dict) -> set[str]:
    logins: set[str] = set()
    for node in issue.get("assignees", {}).get("nodes", []):
        if node.get("login"):
            logins.add(node["login"].lower())
    for node in issue.get("assignedActors", {}).get("nodes", []):
        if node.get("login"):
            logins.add(node["login"].lower())
    return logins


def is_copilot_assigned(issue: dict) -> bool:
    return bool(_actor_logins(issue) & {login.lower() for login in COPILOT_LOGINS})


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
    meta = _graphql(ISSUE_QUERY, {"o": owner, "n": repo, "num": issue_number}, preview=True)
    issue = meta["repository"]["issue"]
    if issue is None:
        raise SystemExit(f"Issue #{issue_number} not found in {owner}/{repo}")

    if is_copilot_assigned(issue):
        print(f"Copilot already assigned to issue #{issue_number}")
        return True

    instructions = custom_instructions or (
        f"Complete issue #{issue_number}: {issue['title']}\n\n"
        f"{(issue.get('body') or '')[:4000]}\n\n"
        f"Open a PR targeting `{base_ref}` with `Fixes #{issue_number}` in the body. "
        "Run CI locally where possible; keep the diff minimal."
    )

    if dry_run:
        print(
            json.dumps(
                {
                    "issue": issue_number,
                    "baseRef": base_ref,
                    "instructions_preview": instructions[:300],
                },
                indent=2,
            )
        )
        return False

    data = _graphql(
        MUTATION,
        {
            "input": {
                "assignableId": issue["id"],
                "actorIds": [meta["copilot"]["id"]],
                "agentAssignment": {
                    "targetRepositoryId": meta["repository"]["id"],
                    "baseRef": base_ref,
                    "customInstructions": instructions[:8000],
                },
            }
        },
        preview=True,
    )
    assignable = data["replaceActorsForAssignable"]["assignable"]
    actors = _actor_logins(assignable)
    if actors & {login.lower() for login in COPILOT_LOGINS}:
        print(f"Assigned Copilot to issue #{assignable['number']}: {sorted(actors)}")
        return True

    # GraphQL mutation succeeded but assignedActors may lag; treat mutation success as ok.
    print(
        f"Copilot assignment mutation completed for issue #{assignable['number']} "
        f"(actors={sorted(actors) or 'pending'})"
    )
    return True


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
        meta = _graphql(
            ISSUE_QUERY,
            {"o": args.owner, "n": args.repo, "num": args.issue_number},
            preview=True,
        )
        issue = meta["repository"]["issue"]
        if issue is None:
            return 1
        return 0 if is_copilot_assigned(issue) else 1

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

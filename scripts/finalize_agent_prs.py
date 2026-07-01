#!/usr/bin/env python3
"""
Evaluate open agent PRs and emit actions for the daily PR finalizer workflow.

States:
  ready_merge   — CI green, no blocking review, eligible paths → add automerge-agent
  needs_fix     — CI failed or Copilot requested changes → dispatch fix agent
  needs_human   — risk:high, needs-human, protected paths, or unresolved human review
  waiting       — pending CI/review or PR too new
  skip          — not an agent PR or already merged/closed
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_BRANCH_PREFIXES = ("cursor/", "copilot/", "bot/")
COPILOT_REVIEW_LOGINS = frozenset({"copilot", "copilot-swe-agent", "copilot-swe-agent[bot]"})
ISSUE_LINK_RE = re.compile(r"(?i)(?:fixes|closes|resolves)\s+#(\d+)")
FINALIZER_MARKER = "**Agent PR finalizer**"
MIN_AGE_HOURS = 2  # let the authoring agent finish before we intervene


@dataclass
class PrAction:
    pr_number: int
    head_branch: str
    state: str
    reason: str
    issue_number: int | None = None
    fix_via: str | None = None  # cursor | copilot | none


def _gh_json(*args: str) -> object:
    out = subprocess.check_output(["gh", *args], text=True)
    return json.loads(out)


def _list_agent_prs(repo: str) -> list[dict]:
    prs = _gh_json(
        "pr",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--limit",
        "100",
        "--json",
        "number,headRefName,baseRefName,title,body,labels,createdAt,isDraft,mergeable,reviewRequests,reviews,statusCheckRollup",
    )
    return [pr for pr in prs if pr["headRefName"].startswith(AGENT_BRANCH_PREFIXES)]


def _issue_labels(repo: str, issue_number: int) -> list[str]:
    data = _gh_json(
        "issue",
        "view",
        str(issue_number),
        "--repo",
        repo,
        "--json",
        "labels",
    )
    return [label["name"] for label in data.get("labels", [])]


def _linked_issue(body: str, title: str) -> int | None:
    match = ISSUE_LINK_RE.search(f"{body}\n{title}")
    return int(match.group(1)) if match else None


def _ci_pending_or_failed(checks: list[dict]) -> tuple[bool, bool]:
    failed = False
    pending = False
    for check in checks:
        state = (check.get("state") or check.get("conclusion") or "").upper()
        if state in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT"}:
            failed = True
        elif state in {"PENDING", "IN_PROGRESS", "QUEUED", "WAITING"}:
            pending = True
        elif state not in {"SUCCESS", "SKIPPED", "NEUTRAL"}:
            pending = True
    return failed, pending


def _copilot_review_state(reviews: list[dict], review_requests: list[dict]) -> str:
    """Return approved | commented | changes_requested | pending | none."""
    copilot_states: list[str] = []
    for review in reviews:
        login = (review.get("author", {}) or {}).get("login", "").lower()
        if login not in {name.lower() for name in COPILOT_REVIEW_LOGINS}:
            continue
        copilot_states.append((review.get("state") or "").upper())
    if "CHANGES_REQUESTED" in copilot_states:
        return "changes_requested"
    if "APPROVED" in copilot_states:
        return "approved"
    if copilot_states:
        return "commented"
    for req in review_requests:
        login = (req.get("login") or "").lower()
        if login in {name.lower() for name in COPILOT_REVIEW_LOGINS}:
            return "pending"
    return "none"


def _human_review_blocking(reviews: list[dict]) -> bool:
    for review in reviews:
        login = (review.get("author", {}) or {}).get("login", "").lower()
        if login in {name.lower() for name in COPILOT_REVIEW_LOGINS}:
            continue
        if login.endswith("[bot]"):
            continue
        state = (review.get("state") or "").upper()
        if state == "CHANGES_REQUESTED":
            return True
    return False


def _protected_paths_ok(base_ref: str, head_branch: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "verify_agent_automerge_pr.py"),
            base_ref,
            head_branch,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return True, "paths ok"
    return False, (proc.stderr or proc.stdout or "protected path check failed").strip()[:200]


def _pr_age_hours(created_at: str) -> float:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return (datetime.now(UTC) - created).total_seconds() / 3600


def _recent_finalizer_comment(repo: str, pr_number: int, hours: int = 24) -> bool:
    data = _gh_json("pr", "view", str(pr_number), "--repo", repo, "--json", "comments")
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    for comment in data.get("comments", []):
        body = comment.get("body") or ""
        if FINALIZER_MARKER not in body:
            continue
        created = datetime.fromisoformat(comment["createdAt"].replace("Z", "+00:00"))
        if created >= cutoff:
            return True
    return False


def evaluate_pr(repo: str, pr: dict, *, fetch_base: bool) -> PrAction:
    number = pr["number"]
    branch = pr["headRefName"]
    base = pr["baseRefName"]
    labels = [label["name"] for label in pr.get("labels", [])]

    if pr.get("isDraft"):
        return PrAction(number, branch, "waiting", "draft PR")

    issue_num = _linked_issue(pr.get("body") or "", pr.get("title") or "")
    if issue_num is None:
        return PrAction(number, branch, "needs_human", "no Fixes #N linkage", fix_via="none")

    issue_labels = _issue_labels(repo, issue_num)
    if "risk:high" in issue_labels or "needs-human" in issue_labels:
        return PrAction(
            number,
            branch,
            "needs_human",
            f"issue #{issue_num} is human-gated",
            issue_number=issue_num,
            fix_via="none",
        )

    if pr.get("mergeable") == "CONFLICTING":
        return PrAction(
            number,
            branch,
            "needs_fix",
            "merge conflicts",
            issue_number=issue_num,
            fix_via="cursor" if branch.startswith("cursor/") else "copilot",
        )

    checks = pr.get("statusCheckRollup") or []
    ci_failed, ci_pending = _ci_pending_or_failed(checks)
    if ci_failed:
        via = "cursor" if branch.startswith("cursor/") else "copilot"
        return PrAction(
            number,
            branch,
            "needs_fix",
            "CI failed",
            issue_number=issue_num,
            fix_via=via,
        )
    if ci_pending:
        return PrAction(number, branch, "waiting", "CI pending", issue_number=issue_num)

    if _human_review_blocking(pr.get("reviews") or []):
        return PrAction(
            number,
            branch,
            "needs_human",
            "human reviewer requested changes",
            issue_number=issue_num,
            fix_via="none",
        )

    copilot_state = _copilot_review_state(pr.get("reviews") or [], pr.get("reviewRequests") or [])
    if copilot_state == "changes_requested":
        via = "cursor" if branch.startswith("cursor/") else "copilot"
        return PrAction(
            number,
            branch,
            "needs_fix",
            "Copilot requested changes",
            issue_number=issue_num,
            fix_via=via,
        )
    if copilot_state == "pending":
        age = _pr_age_hours(pr["createdAt"])
        if age < MIN_AGE_HOURS:
            return PrAction(
                number,
                branch,
                "waiting",
                "Copilot review pending (young PR)",
                issue_number=issue_num,
            )
        return PrAction(number, branch, "waiting", "Copilot review pending", issue_number=issue_num)

    if fetch_base:
        subprocess.run(
            ["git", "fetch", "origin", base], cwd=REPO_ROOT, check=False, capture_output=True
        )
        subprocess.run(
            ["git", "fetch", "origin", branch], cwd=REPO_ROOT, check=False, capture_output=True
        )
        ok, detail = _protected_paths_ok(f"origin/{base}", branch)
        if not ok:
            return PrAction(
                number,
                branch,
                "needs_human",
                detail,
                issue_number=issue_num,
                fix_via="none",
            )

    if "needs-human-review" in labels:
        return PrAction(
            number, branch, "needs_human", "PR labeled needs-human-review", issue_number=issue_num
        )

    if "automerge-agent" in labels:
        return PrAction(
            number, branch, "skip", "automerge-agent already set", issue_number=issue_num
        )

    if copilot_state == "none" and _pr_age_hours(pr["createdAt"]) >= MIN_AGE_HOURS:
        # eligible but review not requested yet — finalizer will request it
        return PrAction(number, branch, "waiting", "request Copilot review", issue_number=issue_num)

    if copilot_state in {"approved", "commented"}:
        return PrAction(
            number, branch, "ready_merge", "eligible for automerge", issue_number=issue_num
        )

    return PrAction(number, branch, "waiting", "unclassified", issue_number=issue_num)


def evaluate_all(repo: str, *, fetch_base: bool = True, cursor_only: bool = False) -> list[PrAction]:
    prs = _list_agent_prs(repo)
    if cursor_only:
        prs = [pr for pr in prs if pr["headRefName"].startswith("cursor/")]
    return [evaluate_pr(repo, pr, fetch_base=fetch_base) for pr in prs]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate agent PRs for daily finalization")
    parser.add_argument(
        "--repo", default=os.environ.get("GITHUB_REPOSITORY", "digithings-ai/digithings")
    )
    parser.add_argument("--json", action="store_true", help="Print actions as JSON array")
    parser.add_argument("--no-fetch", action="store_true", help="Skip git fetch for path checks")
    parser.add_argument(
        "--cursor-only",
        action="store_true",
        help="Only evaluate cursor/* PRs (copilot/* handled by gh-aw lifecycle)",
    )
    args = parser.parse_args()

    actions = evaluate_all(args.repo, fetch_base=not args.no_fetch, cursor_only=args.cursor_only)
    if args.json:
        print(json.dumps([asdict(a) for a in actions], indent=2))
        return 0

    for action in actions:
        extra = f" issue=#{action.issue_number}" if action.issue_number else ""
        fix = f" fix={action.fix_via}" if action.fix_via else ""
        print(
            f"PR #{action.pr_number} [{action.head_branch}] → {action.state}: {action.reason}{extra}{fix}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

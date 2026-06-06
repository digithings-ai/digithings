#!/usr/bin/env python3
"""
Plan actions for the Copilot PR orchestrator (trusted scheduled actor).

Bypasses GitHub's bot-triggered pull_request CI gate by dispatching targeted CI
and managing review → fix → merge loop for copilot/* PRs.
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
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from agent_pr_checks import (  # noqa: E402
    COPILOT_TARGETED_CI,
    copilot_targeted_ci_ok,
    copilot_targeted_ci_state,
)
ISSUE_LINK_RE = re.compile(r"(?i)(?:fixes|closes|resolves)\s+#(\d+)")
COPILOT_REVIEW_LOGINS = frozenset(
    {"copilot", "copilot-swe-agent", "copilot-swe-agent[bot]", "copilot-pull-request-reviewer[bot]"}
)
ORCHESTRATOR_MARKER = "**Copilot PR orchestrator**"
MAX_FIX_ROUNDS = 3
MIN_READY_AGE_MIN = 10


@dataclass
class PipelineAction:
    pr_number: int
    head_branch: str
    head_sha: str
    action: str
    reason: str
    issue_number: int | None = None
    extra: str | None = None


def _gh_json(*args: str) -> object:
    out = subprocess.check_output(["gh", *args], text=True)
    return json.loads(out)


def _list_copilot_prs(repo: str) -> list[dict]:
    prs = _gh_json(
        "pr",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--limit",
        "50",
        "--json",
        "number,title,headRefName,baseRefName,body,isDraft,additions,createdAt,labels",
    )
    return [pr for pr in prs if pr["headRefName"].startswith("copilot/")]


def _pr_detail(repo: str, number: int) -> dict:
    return _gh_json(
        "pr",
        "view",
        str(number),
        "--repo",
        repo,
        "--json",
        "files,reviews,reviewRequests",
    )


def _open_copilot_issues(repo: str) -> list[dict]:
    return _gh_json(
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--label",
        "exec:copilot",
        "--json",
        "number,title,assignees",
        "--limit",
        "50",
    )


def _linked_issue(body: str, title: str) -> int | None:
    match = ISSUE_LINK_RE.search(f"{body}\n{title}")
    return int(match.group(1)) if match else None


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return slug.strip("-")[:50]


def _infer_issue(pr: dict, issues: list[dict]) -> int | None:
    branch_slug = pr["headRefName"].removeprefix("copilot/")
    title_slug = _slug(pr["title"])
    for iss in issues:
        iss_slug = _slug(iss["title"])
        if iss_slug[:25] in branch_slug or iss_slug[:25] in title_slug:
            return iss["number"]
        if branch_slug and branch_slug[:20] in iss_slug:
            return iss["number"]
    return None


def _copilot_review_state(reviews: list[dict], review_requests: list[dict]) -> str:
    states: list[str] = []
    for review in reviews:
        login = (review.get("author", {}) or {}).get("login", "").lower()
        if login not in {n.lower() for n in COPILOT_REVIEW_LOGINS}:
            continue
        states.append((review.get("state") or "").upper())
    if "CHANGES_REQUESTED" in states:
        return "changes_requested"
    if "APPROVED" in states:
        return "approved"
    if states:
        return "commented"
    for req in review_requests:
        login = (req.get("login") or "").lower()
        if login in {n.lower() for n in COPILOT_REVIEW_LOGINS}:
            return "pending"
    return "none"


def _fix_rounds(repo: str, pr_number: int) -> int:
    data = _gh_json("pr", "view", str(pr_number), "--repo", repo, "--json", "comments")
    count = 0
    for comment in data.get("comments", []):
        if ORCHESTRATOR_MARKER in (comment.get("body") or "") and "fix round" in comment.get("body", "").lower():
            count += 1
    return count


def _recent_orchestrator_action(repo: str, pr_number: int, action: str, minutes: int = 30) -> bool:
    data = _gh_json("pr", "view", str(pr_number), "--repo", repo, "--json", "comments")
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
    for comment in data.get("comments", []):
        body = comment.get("body") or ""
        if ORCHESTRATOR_MARKER not in body or action not in body:
            continue
        created = datetime.fromisoformat(comment["createdAt"].replace("Z", "+00:00"))
        if created >= cutoff:
            return True
    return False


def _protected_paths_block(base_ref: str, head_branch: str) -> bool:
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_agent_automerge_pr.py"), base_ref, head_branch],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode != 0


def plan_pr(repo: str, pr: dict, issues: list[dict]) -> PipelineAction:
    number = pr["number"]
    branch = pr["headRefName"]
    base = pr["baseRefName"]
    body = pr.get("body") or ""
    title = pr.get("title") or ""
    detail = _pr_detail(repo, number)
    pr = {**pr, **detail}
    head_sha = _gh_json("pr", "view", str(number), "--repo", repo, "--json", "headRefOid")["headRefOid"]

    issue_num = _linked_issue(body, title) or _infer_issue(pr, issues)
    labels = [label["name"] for label in pr.get("labels", [])]
    if "needs-human-review" in labels:
        return PipelineAction(number, branch, head_sha, "skip", "already needs-human-review", issue_num)

    if issue_num:
        issue_labels = [
            label["name"]
            for label in _gh_json(
                "issue",
                "view",
                str(issue_num),
                "--repo",
                repo,
                "--json",
                "labels",
            )["labels"]
        ]
        if "risk:high" in issue_labels or "needs-human" in issue_labels:
            return PipelineAction(number, branch, head_sha, "needs_human", "human-gated issue", issue_num)

    if _protected_paths_block(f"origin/{base}", branch):
        return PipelineAction(number, branch, head_sha, "needs_human", "protected paths in diff", issue_num)

    if not _linked_issue(body, title) and issue_num:
        return PipelineAction(number, branch, head_sha, "patch_issue_link", f"append Fixes #{issue_num}", issue_num)

    file_count = len(pr.get("files") or [])
    if pr.get("isDraft") and file_count == 0 and (pr.get("additions") or 0) == 0:
        return PipelineAction(number, branch, head_sha, "wait", "draft WIP — no changes yet", issue_num)

    if pr.get("isDraft") and file_count > 0:
        created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
        if datetime.now(UTC) - created >= timedelta(minutes=MIN_READY_AGE_MIN):
            return PipelineAction(number, branch, head_sha, "mark_ready", "draft has changes — mark ready for review", issue_num)

    ci_state = copilot_targeted_ci_state(repo, head_sha)
    if file_count > 0 and ci_state == "pending":
        return PipelineAction(number, branch, head_sha, "wait", "targeted CI pending", issue_num)

    if file_count > 0 and ci_state in {"missing", "failure"}:
        if ci_state == "failure" and issue_num:
            rounds = _fix_rounds(repo, number)
            if rounds >= MAX_FIX_ROUNDS:
                return PipelineAction(
                    number,
                    branch,
                    head_sha,
                    "needs_human",
                    "targeted CI failed after max fix rounds",
                    issue_num,
                )
            if not _recent_orchestrator_action(repo, number, "dispatch_fix"):
                return PipelineAction(
                    number,
                    branch,
                    head_sha,
                    "dispatch_fix",
                    "targeted CI failed",
                    issue_num,
                    extra="ci",
                )
        elif ci_state == "missing" and not _recent_orchestrator_action(repo, number, "dispatch_ci"):
            return PipelineAction(number, branch, head_sha, "dispatch_ci", COPILOT_TARGETED_CI, issue_num)

    if not pr.get("isDraft"):
        review_state = _copilot_review_state(pr.get("reviews") or [], pr.get("reviewRequests") or [])
        if review_state == "changes_requested":
            rounds = _fix_rounds(repo, number)
            if rounds >= MAX_FIX_ROUNDS:
                return PipelineAction(
                    number,
                    branch,
                    head_sha,
                    "needs_human",
                    f"max fix rounds ({MAX_FIX_ROUNDS})",
                    issue_num,
                )
            if issue_num and not _recent_orchestrator_action(repo, number, "dispatch_fix"):
                return PipelineAction(
                    number,
                    branch,
                    head_sha,
                    "dispatch_fix",
                    "Copilot requested changes",
                    issue_num,
                    extra="review",
                )

        if review_state in {"none", "pending"} and not _recent_orchestrator_action(repo, number, "request_review"):
            return PipelineAction(number, branch, head_sha, "request_review", "request Copilot PR review", issue_num)

        if review_state in {"approved", "commented", "none"} and copilot_targeted_ci_ok(repo, head_sha):
            if "automerge-agent" not in labels:
                return PipelineAction(number, branch, head_sha, "autolabel", "CI + review path clear", issue_num)

    return PipelineAction(number, branch, head_sha, "wait", "in progress", issue_num)


def plan_all(repo: str) -> list[PipelineAction]:
    issues = _open_copilot_issues(repo)
    return [plan_pr(repo, pr, issues) for pr in _list_copilot_prs(repo)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan Copilot PR orchestrator actions")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "digithings-ai/digithings"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    actions = plan_all(args.repo)
    if args.json:
        print(json.dumps([asdict(a) for a in actions], indent=2))
        return 0

    for action in actions:
        extra = f" issue=#{action.issue_number}" if action.issue_number else ""
        print(f"PR #{action.pr_number} → {action.action}: {action.reason}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

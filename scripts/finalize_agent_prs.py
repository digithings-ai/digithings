#!/usr/bin/env python3
"""
Evaluate open agent PRs and emit actions for the daily PR finalizer workflow.

States:
  ready_merge   — CI green, no blocking review, eligible paths → add automerge-agent
  needs_fix     — CI failed → dispatch fix agent
  needs_human   — claude-tier issue, minimal-gate/protected paths, or unresolved human review
  waiting       — pending CI or PR too new
  skip          — not an agent PR or already merged/closed
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_BRANCH_PREFIXES = ("cursor/", "copilot/", "bot/", "task/", "claude/")
# Kept in sync with scripts/agent_pr_checks.py and
# scripts/verify_agent_automerge_pr.py by hand (three separate copies of this
# tuple — flagged by CodeRabbit on #2341 as worth centralizing; not done here
# to keep this fix minimal, but the next branch-prefix change should define it
# once and import it in all three places).
COPILOT_REVIEW_LOGINS = frozenset({"copilot", "copilot-swe-agent", "copilot-swe-agent[bot]"})
ISSUE_LINK_RE = re.compile(r"(?i)(?:fixes|closes|resolves)\s+#(\d+)")
FINALIZER_MARKER = "**Agent PR finalizer**"
MIN_AGE_HOURS = 2  # let the authoring agent finish before we intervene

# --- Query shape (DIG-3066) -------------------------------------------------
# The single wide query this script used to make
#   (--limit 100 + body, reviews, statusCheckRollup, ...)
# is ~1.6 MB and exceeded the GraphQL request deadline on *every* attempt:
# measured 2026-10-12 from the repo host, 4/4 attempts failed with
# HTTP 502/504, all at 11.5-11.7 s, against a ~11 s upstream deadline. That is
# the cause of the daily "no PR finalization output" failure, not a transient
# blip — every other gh call in this script is single-PR and tiny.
#
# So the scan is split: a SMALL candidate query returns every open PR cheaply,
# the filter runs on that, and the expensive fields are fetched per PR only for
# the candidates that survive. Measured on the same host: candidate query
# 8.1 s / 22 KB for all 129 open PRs; per-PR hydration ~1.1 s / ~12 KB each.
CANDIDATE_FIELDS = "number,headRefName,baseRefName,isCrossRepository,isDraft,createdAt"
# Fetched per candidate PR. Every one of these is consumed by evaluate_pr.
HYDRATE_FIELDS = "title,body,labels,mergeable,reviewRequests,reviews,statusCheckRollup"
# Raised from 100: the old page silently truncated the scan (23 of 42 agent-branch
# PRs were never evaluated). The cheap query returns the full set in one call.
PR_LIST_LIMIT = 300

# Bounded retry for the GraphQL deadline. Retrying alone is NOT sufficient at the
# old page size (4/4 attempts failed), which is why the query is also split above;
# the retry is here for the genuinely transient tail.
MAX_GH_ATTEMPTS = 3
_GH_BACKOFF_SECONDS = (2.0, 8.0)
# 4xx and "could not resolve" are deterministic — retrying them only burns the
# job's 45-minute budget, so only transport/upstream failures are retried.
_TRANSIENT_MARKERS = (
    "500",
    "502",
    "503",
    "504",
    "bad gateway",
    "gateway timeout",
    "service unavailable",
    "incomplete read",
    "timed out",
    "timeout",
    "connection reset",
    "connection refused",
    "temporarily unavailable",
    "eof occurred",
)


@dataclass
class PrAction:
    pr_number: int
    head_branch: str
    state: str
    reason: str
    issue_number: int | None = None
    fix_via: str | None = None  # cursor | none


def _is_transient(stderr: str) -> bool:
    low = stderr.lower()
    return any(marker in low for marker in _TRANSIENT_MARKERS)


def _gh_json(*args: str) -> object:
    """Run a `gh` JSON call, retrying only failures that can plausibly clear.

    Raises ``subprocess.CalledProcessError`` when the attempts are exhausted, so
    a hard failure still fails the step exactly as before (DIG-3066).
    """
    proc = subprocess.run(["gh", *args], text=True, capture_output=True)
    last_stderr = proc.stderr
    for attempt in range(MAX_GH_ATTEMPTS):
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        last_stderr = proc.stderr
        if attempt == MAX_GH_ATTEMPTS - 1 or not _is_transient(proc.stderr):
            break
        delay = _GH_BACKOFF_SECONDS[min(attempt, len(_GH_BACKOFF_SECONDS) - 1)]
        tail = (proc.stderr.strip().splitlines() or ["(no stderr)"])[-1]
        print(
            f"gh call failed ({tail}); retry {attempt + 1}/{MAX_GH_ATTEMPTS} in {delay}s",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(delay)
        proc = subprocess.run(["gh", *args], text=True, capture_output=True)
    raise subprocess.CalledProcessError(
        proc.returncode, ["gh", *args], output=proc.stdout, stderr=last_stderr
    )


def _list_agent_prs(repo: str) -> list[dict]:
    """Candidate scan: cheap fields only, filtered down to agent PRs.

    The heavy fields (``body``, ``reviews``, ``statusCheckRollup``) are NOT
    requested here — see the DIG-3066 note on CANDIDATE_FIELDS. They are filled
    in per PR by ``_hydrate_pr`` once this filter has run.
    """
    prs = _gh_json(
        "pr",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--limit",
        str(PR_LIST_LIMIT),
        "--json",
        CANDIDATE_FIELDS,
    )
    # CWE-862 guard, same as agent-pr-autolabel.yml / agent-pr-automerge.yml: a
    # branch name matching an agent prefix is not proof of origin, and this
    # finalizer's ready_merge path does the same label-add + auto-merge those
    # two workflows guard — this script just didn't have the check yet.
    # isCrossRepository comes from the live PR object via the API, not the
    # (attacker-controlled) branch name. It is a cheap field, so it stays in the
    # candidate query.
    #
    # Fail closed: require the field to be exactly `False`, not merely falsy.
    # `.get(..., False)` treats a MISSING field the same as a confirmed
    # same-repo PR — the one case where we can't confirm the PR isn't a fork,
    # that reads as "trust it." A field GitHub always returns for this query
    # shouldn't be missing in practice, but if it ever is, exclude rather than
    # include (CodeRabbit finding on #2345).
    return [
        pr
        for pr in prs
        if pr["headRefName"].startswith(AGENT_BRANCH_PREFIXES)
        and pr.get("isCrossRepository") is False
    ]


def _hydrate_pr(repo: str, number: int) -> dict[str, Any] | None:
    """Fetch the expensive fields for one candidate PR.

    Returns None when the read fails. Callers must treat None as "state unknown"
    and must not let the PR reach ready_merge: an absent statusCheckRollup makes
    _ci_pending_or_failed return (False, False), which would otherwise read as
    "CI green".
    """
    try:
        data = _gh_json(
            "pr",
            "view",
            str(number),
            "--repo",
            repo,
            "--json",
            HYDRATE_FIELDS,
        )
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


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


def _issue_tier(repo: str, issue_number: int) -> str:
    """Dispatch tier for the linked issue's component (tiers in project_routing.json).

    Fail CLOSED: unreadable config routes to claude-tier (supervised), never to
    auto-execution.
    """
    try:
        routing = json.loads((REPO_ROOT / "scripts" / "project_routing.json").read_text())
    except (OSError, json.JSONDecodeError):
        return "claude"
    tiers = routing.get("tiers", {})
    names = _issue_labels(repo, issue_number)
    comp = next((n for n in names if n.startswith("component:")), None)
    return tiers.get(comp, tiers.get("default", "claude"))


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

    # Label simplification 2026-09: no label-based human gate remains. Claude-tier
    # (human-supervised) components route here instead; merge-time safety for the
    # rest is path-based (_protected_paths_ok + verify_agent_automerge_pr.py).
    if _issue_tier(repo, issue_num) == "claude":
        return PrAction(
            number,
            branch,
            "needs_human",
            f"issue #{issue_num} is claude-tier (human-supervised)",
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
            fix_via="cursor" if branch.startswith("cursor/") else "none",
        )

    checks = pr.get("statusCheckRollup") or []
    ci_failed, ci_pending = _ci_pending_or_failed(checks)
    if ci_failed:
        via = "cursor" if branch.startswith("cursor/") else "none"
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

    if "automerge-agent" in labels:
        return PrAction(
            number, branch, "skip", "automerge-agent already set", issue_number=issue_num
        )

    if _pr_age_hours(pr["createdAt"]) < MIN_AGE_HOURS:
        return PrAction(number, branch, "waiting", "PR too young", issue_number=issue_num)

    # No review gate here any more. It used to require a Copilot review, which can
    # never arrive now the subscription has lapsed — that made ready_merge
    # unreachable and parked every eligible PR at "waiting" forever. Review is
    # enforced where it is actually checkable: `bugbot run` or /review on the task
    # PR, recorded by a reviewed:* label, and asserted for the whole range by
    # ci-review-coverage.yml before anything reaches main.
    return PrAction(number, branch, "ready_merge", "eligible for automerge", issue_number=issue_num)


def evaluate_all(
    repo: str, *, fetch_base: bool = True, cursor_only: bool = False
) -> list[PrAction]:
    prs = _list_agent_prs(repo)
    if cursor_only:
        prs = [pr for pr in prs if pr["headRefName"].startswith("cursor/")]
    actions: list[PrAction] = []
    for pr in prs:
        heavy = _hydrate_pr(repo, pr["number"])
        if heavy is None:
            # Fail CLOSED (DIG-3066). The candidate query succeeded but the
            # per-PR read did not, so we have no CI/review state. evaluate_pr
            # would read the missing statusCheckRollup as "no checks", i.e.
            # green, and could emit ready_merge for a PR whose CI is red. A
            # human must look at this one.
            actions.append(
                PrAction(
                    pr["number"],
                    pr["headRefName"],
                    "needs_human",
                    "could not read CI/review state (gh query failed after retries)",
                    fix_via="none",
                )
            )
            continue
        merged = dict(pr)
        merged.update(heavy)
        actions.append(evaluate_pr(repo, merged, fetch_base=fetch_base))
    return actions


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
        help="Only evaluate cursor/* PRs",
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

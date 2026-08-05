#!/usr/bin/env python3
"""Refuse a promotion to main that carries an unreviewed commit.

The invariant this enforces is *not* "Bugbot ran on the promotion PR". Reviewing
a promotion is the wrong moment and the wrong price: its diff is an accumulation
of already-merged work — historically up to 100 files and 12k lines (PR #1877) —
so it is the most expensive review Bugbot will quote and the least actionable one,
because acting on a finding means a fresh task PR plus another promotion.

The invariant is: **every commit reaching production was reviewed where it was
cheap to fix — at its own task PR.** This script checks that, at the last moment
it can still be checked.

Deliberately NOT implemented as a required "Cursor Bugbot" status check on main.
That check reports `neutral` when the Cursor account hits its usage limit, and a
required check must report success — on 2026-08-05 every one of ten promotions
would have been unmergeable, including the one carrying a fix for false copy
already live. A metered third-party service must never hold a veto over deploys.
This gate depends on nothing outside the repository's own history and labels.

"Reviewed" means any one of, on the source pull request:

  1. a completed Cursor Bugbot run — check run "Cursor Bugbot" concluded
     ``success``. A ``neutral`` conclusion is the usage-limit skip and does NOT
     count, which is the whole reason this script exists;
  2. an APPROVED review from a human;
  3. the label ``risk:low`` — an explicit, auditable decision that the change did
     not warrant one. Reusing the label the repo already has rather than minting a
     ``review:skip`` synonym.

Commits that are exempt by nature, not by decision:

  * merge commits (a promotion or module-sync merge carries no new work of its
    own — its parents are checked on their own PRs);
  * commits authored by a bot account listed in ``BOT_AUTHORS``, which are
     generated (TSV stubs, provider snapshots) and have no human diff to review.

Anything at or before ``BASELINE_SHA`` is skipped, so introducing the gate does
not retroactively fail on history. Move the baseline forward only deliberately.

Usage:
    scripts/check_review_coverage.py                 # main..develop
    scripts/check_review_coverage.py --base main --head develop
    scripts/check_review_coverage.py --json          # machine-readable
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The gate starts here. e03c7095 is develop at the time this script landed;
# everything up to and including it predates the rule.
BASELINE_SHA = "e03c7095"

# Squash merges land as "subject (#1234)"; GitHub merge commits as
# "Merge pull request #1234 from ...". Both are how a commit names its PR here.
_SQUASH_PR = re.compile(r"\(#(\d+)\)\s*$")
_MERGE_PR = re.compile(r"^Merge pull request #(\d+)\b")

BOT_AUTHORS = frozenset({"github-actions[bot]", "dependabot[bot]", "cursor[bot]"})

SKIP_LABEL = "risk:low"
BUGBOT_CHECK = "Cursor Bugbot"


def _run(args: list[str]) -> str:
    return subprocess.check_output(args, text=True, cwd=REPO_ROOT).strip()


def _gh_json(args: list[str]) -> dict | list:
    return json.loads(_run(["gh", *args]))


def parse_pr_number(subject: str) -> int | None:
    """Return the PR number a commit subject names, or None."""
    for pattern in (_SQUASH_PR, _MERGE_PR):
        found = pattern.search(subject)
        if found:
            return int(found.group(1))
    return None


def is_merge_commit(parents: str) -> bool:
    return len(parents.split()) > 1


def commits_in_range(base: str, head: str) -> list[dict]:
    """Commits on head and not base, oldest first, with the fields we judge on."""
    # \x1f between fields and \x1e between records: a commit subject may contain
    # anything, including the tab and pipe characters a lazier delimiter would use.
    fmt = "%H\x1f%s\x1f%an\x1f%P\x1e"
    raw = _run(["git", "log", "--reverse", f"--format={fmt}", f"{base}..{head}"])
    out: list[dict] = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        sha, subject, author, parents = record.split("\x1f")
        out.append({"sha": sha, "subject": subject, "author": author, "parents": parents})
    return out


def _pr_review_state(number: int) -> dict:
    """How a PR was reviewed. Network-bound; one call per distinct PR."""
    data = _gh_json(
        [
            "pr",
            "view",
            str(number),
            "--json",
            "labels,reviews,statusCheckRollup,title",
        ]
    )
    labels = {label["name"] for label in data.get("labels") or []}
    approvals = [
        review["author"]["login"]
        for review in data.get("reviews") or []
        if review.get("state") == "APPROVED"
        and (review.get("author") or {}).get("login") not in BOT_AUTHORS
    ]
    bugbot = None
    for check in data.get("statusCheckRollup") or []:
        if (check.get("name") or check.get("context")) == BUGBOT_CHECK:
            bugbot = (check.get("conclusion") or check.get("status") or "").upper()
            break
    return {
        "labels": labels,
        "approvals": approvals,
        "bugbot": bugbot,
        "title": data.get("title") or "",
    }


def verdict_for(state: dict) -> tuple[bool, str]:
    """(reviewed, why) for one PR's review state."""
    if state["bugbot"] == "SUCCESS":
        return True, "Cursor Bugbot completed"
    if state["approvals"]:
        return True, f"approved by {', '.join(state['approvals'])}"
    if SKIP_LABEL in state["labels"]:
        return True, f"labelled {SKIP_LABEL}"
    if state["bugbot"] == "NEUTRAL":
        return False, (
            f"{BUGBOT_CHECK} reported neutral — that is the usage-limit skip, not a review"
        )
    if state["bugbot"]:
        return False, f"{BUGBOT_CHECK} reported {state['bugbot'].lower()}"
    return False, "no completed Bugbot run, no human approval, no risk:low label"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="origin/develop")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    commits = commits_in_range(args.base, args.head)
    if not commits:
        print(f"review coverage: {args.base}..{args.head} is empty — nothing to promote.")
        return 0

    try:
        baseline_ok = True
        _run(["git", "rev-parse", "--verify", f"{BASELINE_SHA}^{{commit}}"])
    except subprocess.CalledProcessError:
        baseline_ok = False

    checked: list[dict] = []
    unreviewed: list[dict] = []
    cache: dict[int, dict] = {}

    for commit in commits:
        short = commit["sha"][:8]
        row = {"sha": short, "subject": commit["subject"][:72]}

        if baseline_ok and _is_ancestor(commit["sha"], BASELINE_SHA):
            row.update(reviewed=True, why=f"at or before baseline {BASELINE_SHA}")
            checked.append(row)
            continue
        if is_merge_commit(commit["parents"]):
            row.update(reviewed=True, why="merge commit — its parents carry the work")
            checked.append(row)
            continue
        if commit["author"] in BOT_AUTHORS:
            row.update(reviewed=True, why=f"generated by {commit['author']}")
            checked.append(row)
            continue

        number = parse_pr_number(commit["subject"])
        if number is None:
            row.update(
                reviewed=False,
                why="names no pull request — pushed straight to the branch?",
            )
            unreviewed.append(row)
            checked.append(row)
            continue

        row["pr"] = number
        if number not in cache:
            cache[number] = _pr_review_state(number)
        reviewed, why = verdict_for(cache[number])
        row.update(reviewed=reviewed, why=why)
        checked.append(row)
        if not reviewed:
            unreviewed.append(row)

    if args.as_json:
        print(json.dumps({"commits": checked, "unreviewed": unreviewed}, indent=2))
        return 1 if unreviewed else 0

    print(f"review coverage: {len(commits)} commit(s) in {args.base}..{args.head}\n")
    for row in checked:
        mark = "✅" if row["reviewed"] else "❌"
        pr = f"#{row['pr']} " if "pr" in row else ""
        print(f"  {mark}  {row['sha']}  {pr}{row['subject']}")
        print(f"        {row['why']}")

    if unreviewed:
        print(file=sys.stderr)
        for row in unreviewed:
            pr = f"PR #{row['pr']}" if "pr" in row else f"commit {row['sha']}"
            print(f"❌  {pr}: {row['why']}", file=sys.stderr)
        print(
            "\nFix, per commit, whichever is true:\n"
            f"  • it needs a review  → comment `bugbot run` on its PR, wait for the "
            f"{BUGBOT_CHECK} check to conclude success\n"
            f"  • it did not need one → label the PR `{SKIP_LABEL}`, which records the "
            "decision and who made it\n"
            "  • a human read it     → approve the PR\n"
            "\nThis gate never fails because an external service is unavailable: a "
            "label or an approval always clears it.",
            file=sys.stderr,
        )
        return 1

    print(f"\nAll {len(commits)} commit(s) reaching main were reviewed. ✅")
    return 0


def _is_ancestor(sha: str, maybe_descendant: str) -> bool:
    """True when sha is at or before maybe_descendant."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, maybe_descendant],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    return result.returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())

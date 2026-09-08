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

The intent is an **agent review loop** on every task PR, not a specific vendor:

  1. An agent reviews the diff with clean context (Bugbot, CodeRabbit, Claude,
     Copilot, any other PR-review bot, or an in-session / subagent review).
  2. Findings are posted on the PR.
  3. The author addresses them. After that the PR is green.
  4. If the fixes were large, run another loop. Repeat until the remaining
     comments are nits or none.

This script only checks that step 1 left an artifact. Addressing comments is
required before merging the task PR; it is not re-checked at promotion time
(unresolved CodeRabbit threads stay open even after a follow-up commit, and
encoding that here is how the gate started blocking already-reviewed work).

"Reviewed" means any one of, on the source pull request, strongest first:

  1. a completed Cursor Bugbot run — check run "Cursor Bugbot" concluded
     ``success``. A ``neutral`` conclusion is the usage-limit skip and does NOT
     count. This is the only hatch that cannot be self-granted;
  2. an APPROVED review from a human other than a bot;
  3. a completed agent-tool review — CodeRabbit (submitted review, completed
     findings comment, or check ``success``), Claude ``/code-review`` check
     ``success``, or a submitted review from another bot in ``REVIEW_BOTS``.
     A skip, rate-limit, failure, or "PR is closed" notice is NOT a review;
  4. the label ``reviewed:agent`` PLUS a comment carrying ``AGENT_REVIEW_MARKER`` —
     an in-session review ran against the diff and posted its findings. The
     label without the comment is REFUSED;
  5. the label ``reviewed:owner`` — "I read this myself." The verdict names who
     applied it and when.

All five hang off a pull request, so a commit pushed **straight to a branch** can
carry none of them — see ``direct_push_review`` for the one hatch that addresses
the commit instead of the branch, and why it is not a sixth way to clear a PR.

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
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The gate starts here. e03c7095 is develop at the time this script landed;
# everything up to and including it predates the rule.
#
# Do NOT "fix" old orphaned PRs (e.g. #1265, #1247 -- merged in early July, long
# before this gate existed) by advancing this value. Checked while investigating
# exactly that on 2026-08-11: those two commits are not ancestors of e03c7095
# *or* of any later commit on main's post-squash lineage (PR #2124 squash-merged
# develop -> main and discarded prior commits as recognized ancestors), so no
# baseline value skips them -- advancing the baseline to main's current tip
# changed zero commits' status when tested against a live 111-commit range.
# e03c7095 itself is still a correct, working ancestor of both main and develop
# today and needs no change. Orphaned pre-gate commits like these need their own
# hatch label (reviewed:owner) applied directly -- there is no
# baseline value that retroactively covers a severed-ancestry commit.
BASELINE_SHA = "e03c7095"

# Squash merges land as "subject (#1234)"; GitHub merge commits as
# "Merge pull request #1234 from ...". Child commits preserved by a merge commit
# name no PR, so those fall back to GitHub's commit association.
_SQUASH_PR = re.compile(r"\(#(\d+)\)\s*$")
_MERGE_PR = re.compile(r"^Merge pull request #(\d+)\b")

BOT_AUTHORS = frozenset({"github-actions[bot]", "dependabot[bot]", "cursor[bot]"})

# Bots that *review* PRs. cursor[bot] is the author, not a reviewer — a router
# pass approving its own work is not a review loop. github-actions is CI.
#
# ``gh pr view --json`` returns the bare login (``coderabbitai``); the REST
# timeline/reviews API often returns the ``[bot]`` suffix. Match both.
REVIEW_BOTS = frozenset(
    {
        "coderabbitai",
        "coderabbitai[bot]",
        "github-code-quality",
        "github-code-quality[bot]",
        "copilot-pull-request-reviewer",
        "copilot-pull-request-reviewer[bot]",
        "claude",
        "claude[bot]",
        "chatgpt-codex-connector",
        "chatgpt-codex-connector[bot]",
    }
)
CODERABBIT_LOGINS = frozenset({"coderabbitai", "coderabbitai[bot]"})
REVIEW_BOT_CHECK_NAMES = frozenset({"CodeRabbit", "Claude /code-review"})
REVIEW_STATES = frozenset({"COMMENTED", "APPROVED", "CHANGES_REQUESTED"})

# CodeRabbit posts skip/quota notices in the same summarize comment as a real
# walkthrough would use. Skip wins: a rate-limit or "PR is closed" failure is
# not a completed review even if the comment also contains a review-stack header.
CODERABBIT_SKIP_MARKERS = (
    "Review skipped",
    "Review failed",
    "Review limit reached",
    "rate limited by coderabbit.ai",
    "Auto reviews are disabled",
)
CODERABBIT_COMPLETED_MARKERS = (
    "No actionable comments were generated",
    "<!-- walkthrough_start -->",
    "<!-- final_review_risk_start -->",
    "<!-- recent_review_start -->",
)

OWNER_REVIEW_LABEL = "reviewed:owner"
AGENT_REVIEW_LABEL = "reviewed:agent"
BUGBOT_CHECK = "Cursor Bugbot"

# The marker an in-session review posts in its findings comment. `reviewed:agent`
# alone does NOT clear the gate — the comment has to exist. That is the point: a
# bare label is free to apply, whereas this hatch costs you an actual review whose
# output anyone can read afterwards.
AGENT_REVIEW_MARKER = "<!-- in-session-review -->"

# How much of a commit sha an in-session review has to quote to hatch a commit
# that has no source pull request. Eight is what `git log --oneline` and this
# script's own output print, so the reviewer names the sha they were shown.
AGENT_REVIEW_SHA_LEN = 8

# GraphQL aliases per query. GitHub's complexity budget is 5000; 25 PRs with
# labels/reviews/comments/checks stays well under it and turns a 169-PR promotion
# range into a handful of round-trips instead of one `gh pr view` each.
_GRAPHQL_PR_BATCH = 25
_GRAPHQL_SHA_BATCH = 50
_REST_POOL = 8

# `reviewed:owner` exists because of a hole the gate's own first run exposed. In a
# single-maintainer org every PR is authored by the same account, so GitHub blocks
# self-approval; with Bugbot out of quota the only satisfiable hatch was going to
# be a self-granted "no review needed" label, which would have trained the
# maintainer to bypass their own gate under pressure. Mislabelling under pressure
# from your own gate is worse than having no gate.
#
# (A `risk:low` "did not warrant a review" hatch existed for this until the
# 2026-09 label simplification retired the whole risk:* family. Truly trivial
# diffs now clear the gate via `reviewed:owner` — "I read it, it needed no
# further reading" — which keeps the timestamped accountability record.)
# Be honest about its strength: with one account holding write access, this is an
# ACCOUNTABILITY record, not an enforcement mechanism — whoever can merge can also
# apply it. What it buys is a timestamped, attributed claim in the timeline instead
# of a silent bypass, which is why the verdict below names the actor and the date
# rather than just returning true. A completed Bugbot run remains the only hatch
# that cannot be self-granted.


def _run(args: list[str]) -> str:
    return subprocess.check_output(args, text=True, cwd=REPO_ROOT).strip()


def _gh_json(args: list[str]) -> dict | list:
    return json.loads(_run(["gh", *args]))


def _gh_graphql(query: str, variables: dict | None = None) -> dict:
    """One `gh api graphql` round-trip. Tests mock this; CI never hits live GitHub."""
    args = ["api", "graphql", "-f", f"query={query}"]
    if variables:
        args.extend(["-F", f"variables={json.dumps(variables)}"])
    data = _gh_json(args)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("graphql envelope was not an object", "", 0)
    return data


def _chunks(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


@lru_cache(maxsize=1)
def _repo_slug() -> str:
    return _run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])


def _repo_owner_name() -> tuple[str, str]:
    owner, name = _repo_slug().split("/", 1)
    return owner, name


def baseline_ancestor_shas(baseline: str) -> set[str]:
    """Every commit at or before `baseline` — one `git rev-list`, not N merge-bases."""
    return set(_run(["git", "rev-list", baseline]).split())


_PR_GRAPHQL_FIELDS = """
number
title
labels(first: 40) { nodes { name } }
reviews(last: 80) { nodes { state author { login } } }
comments(last: 100) { nodes { author { login } body createdAt url } }
timelineItems(last: 80, itemTypes: [LABELED_EVENT]) {
  nodes {
    ... on LabeledEvent {
      createdAt
      actor { login }
      label { name }
    }
  }
}
commits(last: 1) {
  nodes {
    commit {
      statusCheckRollup {
        contexts {
          ... on CheckRun { name conclusion }
          ... on StatusContext { context state }
        }
      }
    }
  }
}
"""


def _pr_batch_query(numbers: list[int]) -> str:
    owner, name = _repo_owner_name()
    aliases = " ".join(
        f"p{n}: pullRequest(number: {n}) {{ {_PR_GRAPHQL_FIELDS} }}" for n in numbers
    )
    return f'query {{ repository(owner: "{owner}", name: "{name}") {{ {aliases} }} }}'


def _sha_batch_query(shas: list[str]) -> str:
    owner, name = _repo_owner_name()
    aliases = " ".join(
        (
            f'c{i}: object(expression: "{sha}") {{ '
            "... on Commit { associatedPullRequests(first: 10) { nodes { number mergedAt } } } }"
        )
        for i, sha in enumerate(shas)
    )
    return f'query {{ repository(owner: "{owner}", name: "{name}") {{ {aliases} }} }}'


def _author_login(node: dict | None) -> str:
    return ((node or {}).get("author") or (node or {}).get("user") or {}).get("login") or ""


def _agent_review_from_comments(comments: list[dict], naming: str | None = None) -> dict | None:
    latest = None
    for comment in comments:
        body = comment.get("body") or ""
        if AGENT_REVIEW_MARKER not in body:
            continue
        if naming is not None and naming not in body:
            continue
        latest = {
            "actor": _author_login(comment) or "unknown",
            "at": comment.get("createdAt") or comment.get("created_at") or "",
            "url": comment.get("url") or comment.get("html_url") or "",
        }
    return latest


def _owner_review_from_events(events: list[dict], label: str) -> dict | None:
    latest = None
    for event in events:
        event_name = event.get("event")
        label_name = (event.get("label") or {}).get("name")
        if event_name and event_name != "labeled":
            continue
        if label_name != label:
            continue
        actor = (event.get("actor") or {}).get("login") or "unknown"
        latest = {"actor": actor, "at": event.get("createdAt") or event.get("created_at") or ""}
    return latest


def _apply_reviews_checks_comments(
    state: dict,
    *,
    reviews: list[dict],
    checks: list[dict],
    comments: list[dict],
) -> dict:
    state["approvals"] = [
        _author_login(review)
        for review in reviews
        if review.get("state") == "APPROVED"
        and _author_login(review) not in BOT_AUTHORS
        and _author_login(review)
    ]
    agent_tool: list[dict] = []
    for check in checks:
        name = check.get("name") or check.get("context") or ""
        conclusion = (
            check.get("conclusion") or check.get("state") or check.get("status") or ""
        ).upper()
        if name == BUGBOT_CHECK:
            state["bugbot"] = conclusion
        elif name in REVIEW_BOT_CHECK_NAMES and conclusion == "SUCCESS":
            agent_tool.append({"bot": name, "via": "check"})
    for review in reviews:
        login = _author_login(review)
        if login in REVIEW_BOTS and review.get("state") in REVIEW_STATES:
            agent_tool.append({"bot": login, "via": "review"})
    for comment in comments:
        login = _author_login(comment)
        body = comment.get("body") or ""
        if login in CODERABBIT_LOGINS and coderabbit_comment_is_completed_review(body):
            agent_tool.append({"bot": "coderabbitai", "via": "comment"})
    state["agent_tool"] = agent_tool
    if AGENT_REVIEW_LABEL in state["labels"]:
        state["agent_review"] = _agent_review_from_comments(comments)
    return state


def state_from_graphql_pr(node: dict) -> dict:
    """Map a GraphQL pullRequest node onto the dict `verdict_for` already judges."""
    labels = {
        item.get("name")
        for item in ((node.get("labels") or {}).get("nodes") or [])
        if item.get("name")
    }
    reviews = (node.get("reviews") or {}).get("nodes") or []
    comments = (node.get("comments") or {}).get("nodes") or []
    labeled = (node.get("timelineItems") or {}).get("nodes") or []
    commits = (node.get("commits") or {}).get("nodes") or []
    rollup = ((commits[0].get("commit") or {}).get("statusCheckRollup") if commits else None) or {}
    checks = rollup.get("contexts") or []
    state = {
        "labels": labels,
        "approvals": [],
        "bugbot": None,
        "title": node.get("title") or "",
        "owner_review": None,
        "agent_tool": [],
        "agent_review": None,
    }
    _apply_reviews_checks_comments(state, reviews=reviews, checks=checks, comments=comments)
    if OWNER_REVIEW_LABEL in labels:
        state["owner_review"] = _owner_review_from_events(labeled, OWNER_REVIEW_LABEL)
    return state


def prefetch_pr_states(numbers: list[int], cache: dict[int, dict], invalid: set[int]) -> None:
    """Fill `cache` / `invalid` for distinct PR numbers via batched GraphQL."""
    pending = [n for n in dict.fromkeys(numbers) if n not in cache and n not in invalid]
    if not pending:
        return
    try:
        for chunk in _chunks(pending, _GRAPHQL_PR_BATCH):
            payload = _gh_graphql(_pr_batch_query(chunk))
            repo = (payload.get("data") or {}).get("repository") or {}
            for number in chunk:
                node = repo.get(f"p{number}")
                if node is None:
                    invalid.add(number)
                else:
                    cache[number] = state_from_graphql_pr(node)
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, TypeError):
        _prefetch_pr_states_rest(pending, cache, invalid)


def _prefetch_pr_states_rest(numbers: list[int], cache: dict[int, dict], invalid: set[int]) -> None:
    def one(number: int) -> tuple[int, dict | None]:
        try:
            return number, _pr_review_state(number)
        except subprocess.CalledProcessError:
            return number, None

    with ThreadPoolExecutor(max_workers=_REST_POOL) as pool:
        futures = [pool.submit(one, number) for number in numbers]
        for future in as_completed(futures):
            number, state = future.result()
            if state is None:
                invalid.add(number)
            else:
                cache[number] = state


def prefetch_associated_prs(shas: list[str]) -> dict[str, int | None]:
    """Merged source PR per SHA, one GraphQL query per chunk of commits."""
    pending = list(dict.fromkeys(shas))
    if not pending:
        return {}
    try:
        found: dict[str, int | None] = {}
        for chunk in _chunks(pending, _GRAPHQL_SHA_BATCH):
            payload = _gh_graphql(_sha_batch_query(chunk))
            repo = (payload.get("data") or {}).get("repository") or {}
            for index, sha in enumerate(chunk):
                found[sha] = _merged_number_from_associated(repo.get(f"c{index}"))
        return found
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, TypeError):
        with ThreadPoolExecutor(max_workers=_REST_POOL) as pool:
            return dict(zip(pending, pool.map(associated_pr_number, pending), strict=True))


def _merged_number_from_associated(node: dict | None) -> int | None:
    if not node:
        return None
    pulls = (node.get("associatedPullRequests") or {}).get("nodes") or []
    for pull in pulls:
        if pull.get("mergedAt") and pull.get("number") is not None:
            return int(pull["number"])
    return None


def parse_pr_number(subject: str) -> int | None:
    """Return the PR number a commit subject names, or None."""
    for pattern in (_SQUASH_PR, _MERGE_PR):
        found = pattern.search(subject)
        if found:
            return int(found.group(1))
    return None


def associated_pr_number(sha: str, associated: dict[str, int | None] | None = None) -> int | None:
    """Return the merged source PR associated with an unnumbered commit."""
    if associated is not None and sha in associated:
        return associated[sha]
    try:
        pulls = _gh_json(["api", f"repos/{_repo_slug()}/commits/{sha}/pulls"])
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None
    for pull in pulls if isinstance(pulls, list) else []:
        if pull.get("merged_at") and pull.get("number") is not None:
            return int(pull["number"])
    return None


def is_merge_commit(parents: str) -> bool:
    return len(parents.split()) > 1


def resolve_pr_number(
    subject: str,
    sha: str,
    cache: dict[int, dict],
    invalid: set[int] | None = None,
    associated: dict[str, int | None] | None = None,
) -> int | None:
    """The PR whose review state judges this commit, or None if it has none.

    `parse_pr_number`'s trailing "(#N)" match assumes a squash-merge PR
    reference, but a commit subject can cite an issue number in the same
    shape (e.g. "docs: foo (#2103)" naming issue #2103, not a PR) --
    `_pr_review_state` on a number that isn't a real PR raises. Rather than
    letting that crash the whole gate, fall back to the real commit -> PR
    association, the same path unnumbered commits already use.

    `invalid` memoizes numbers already found bogus this run, so a repo where
    several commits cite the same non-PR number (e.g. a whole PR's worth of
    commits referencing one tracking issue) doesn't re-attempt the same
    failing `gh pr view` call per commit.
    """
    number = parse_pr_number(subject)
    if number is not None and invalid is not None and number in invalid:
        number = None
    elif number is not None and number not in cache:
        try:
            cache[number] = _pr_review_state(number)
        except subprocess.CalledProcessError:
            if invalid is not None:
                invalid.add(number)
            number = None
    if number is None:
        if associated is not None and sha in associated:
            number = associated[sha]
        else:
            number = associated_pr_number(sha)
    return number


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


def coderabbit_comment_is_completed_review(body: str) -> bool:
    """True when a CodeRabbit issue comment is a finished review, not a skip.

    Skip/quota/failure notices share the summarize comment with a real
    walkthrough, so skip markers win.
    """
    if any(marker in body for marker in CODERABBIT_SKIP_MARKERS):
        return False
    return any(marker in body for marker in CODERABBIT_COMPLETED_MARKERS)


def _pr_review_state(number: int) -> dict:
    """How a PR was reviewed. REST fallback when GraphQL batching is unavailable."""
    data = _gh_json(
        [
            "pr",
            "view",
            str(number),
            "--json",
            "labels,reviews,comments,statusCheckRollup,title",
        ]
    )
    labels = {label["name"] for label in data.get("labels") or []}
    comments = data.get("comments") or []
    state = {
        "labels": labels,
        "approvals": [],
        "bugbot": None,
        "title": data.get("title") or "",
        "owner_review": None,
        "agent_tool": [],
        "agent_review": None,
    }
    _apply_reviews_checks_comments(
        state,
        reviews=data.get("reviews") or [],
        checks=data.get("statusCheckRollup") or [],
        comments=comments,
    )
    # Extra REST only when the hatch is claimed and the first page did not prove it.
    if OWNER_REVIEW_LABEL in labels and not state.get("owner_review"):
        state["owner_review"] = label_provenance(number, OWNER_REVIEW_LABEL)
    if AGENT_REVIEW_LABEL in labels and not state.get("agent_review"):
        state["agent_review"] = agent_review_comment(number)
    return state


def agent_review_comment(number: int, naming: str | None = None) -> dict | None:
    """The most recent in-session review comment on this PR or issue, or None.

    Looked up rather than trusted, because `reviewed:agent` claims a review *ran*.
    Without the comment the claim has no artifact and the gate must refuse it.

    `naming` additionally requires the comment to quote that string — the short
    sha of a commit with no source pull request. Without it, one review would
    hatch every direct push in the range at once (see `direct_push_review`).
    """
    try:
        comments = _gh_json(["api", "--paginate", f"repos/{_repo_slug()}/issues/{number}/comments"])
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None
    return _agent_review_from_comments(
        comments if isinstance(comments, list) else [], naming=naming
    )


def _issue_labels(number: int) -> set[str]:
    """Labels on an issue or PR. Fails closed (empty) on any API or parse error."""
    try:
        data = _gh_json(["api", f"repos/{_repo_slug()}/issues/{number}"])
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return set()
    labels = data.get("labels") if isinstance(data, dict) else None
    return {
        label["name"] for label in labels or [] if isinstance(label, dict) and label.get("name")
    }


def _sha_mentioned_in(short_sha: str) -> list[int]:
    """Issue/PR numbers whose comments quote `short_sha`.

    Discovery only. Every candidate it returns is re-verified against the issue's
    own labels and comments, so this never has to be trusted — which is what makes
    it safe to lean on a search index that is eventually consistent and matches on
    tokenized text. Fails closed (empty) like `associated_pr_number`.
    """
    query = f"repo:{_repo_slug()} {short_sha} in:comments"
    try:
        found = _gh_json(["api", "-X", "GET", "search/issues", "-f", f"q={query}"])
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []
    items = found.get("items") if isinstance(found, dict) else None
    return [
        int(item["number"])
        for item in items or []
        if isinstance(item, dict) and item.get("number") is not None
    ]


def direct_push_review(sha: str) -> dict | None:
    """The in-session review artifact for a commit with no source PR, or None.

    All five PR hatches hang off a pull request, so a commit pushed straight to
    develop can never carry one: `resolve_pr_number` returns None and the gate
    refuses it permanently. The only ways out were advancing `BASELINE_SHA` —
    which retroactively skips unrelated history — or never promoting.

    So this demands the same artifact the `reviewed:agent` hatch does, addressed
    to the *commit* rather than to the branch: a comment carrying
    `AGENT_REVIEW_MARKER` **and** the commit's short sha, on an issue or PR that
    is itself labelled `reviewed:agent`.

    Both halves are load-bearing. The marker alone would let one in-session review
    clear every direct push in the range; the sha alone would let any prose that
    quotes a sha stand in for a review.

    Be honest about its strength, as `reviewed:owner` is: requiring both narrows
    the claim, it does not prove this specific commit was read. A promotion review
    routinely names the range tip in its header table ("origin/develop (reviewed
    tip) | 46c9ab76…"), and such a comment does clear that commit. Tightening
    further means guessing at prose structure, which would refuse real reviews to
    catch a case the review author has no reason to game. So this is an
    ACCOUNTABILITY record, like the label hatches: the reviewer's own words, on the
    record, naming the sha, under a label they had to apply. A completed Bugbot run
    remains the only hatch nobody can self-grant.

    Deliberately unreachable for a commit that HAS a source pull request — that one
    is still judged by its own PR's state and nothing else. This is a hatch for
    commits the gate could not otherwise judge, not a new way to clear a PR.
    """
    short = sha[:AGENT_REVIEW_SHA_LEN]
    for number in _sha_mentioned_in(short):
        if AGENT_REVIEW_LABEL not in _issue_labels(number):
            continue
        found = agent_review_comment(number, naming=short)
        if found:
            return {**found, "on": number}
    return None


def label_provenance(number: int, label: str) -> dict | None:
    """Who applied `label` to this PR and when — the last application wins.

    A bare "the label is present" would let the hatch read as a silent bypass.
    Naming the actor and the date puts the claim on the record, which is the only
    thing a self-applicable hatch can honestly offer.
    """
    try:
        events = _gh_json(
            [
                "api",
                "--paginate",
                f"repos/{_repo_slug()}/issues/{number}/timeline",
            ]
        )
    except subprocess.CalledProcessError:
        return None
    latest = None
    for event in events if isinstance(events, list) else []:
        if event.get("event") != "labeled":
            continue
        if ((event.get("label") or {}).get("name")) != label:
            continue
        latest = {
            "actor": (event.get("actor") or {}).get("login") or "unknown",
            "at": event.get("created_at") or "",
        }
    return latest


def verdict_for(state: dict) -> tuple[bool, str]:
    """(reviewed, why) for one PR's review state.

    Order is strongest-evidence-first, so `why` reports the best claim available
    rather than the first one that happens to match.
    """
    if state["bugbot"] == "SUCCESS":
        return True, "Cursor Bugbot completed"
    if state["approvals"]:
        return True, f"approved by {', '.join(state['approvals'])}"
    agent_tool = state.get("agent_tool") or []
    if agent_tool:
        bots = list(dict.fromkeys(item["bot"] for item in agent_tool))
        return True, f"agent review by {', '.join(bots)}"
    agent = state.get("agent_review")
    if AGENT_REVIEW_LABEL in state["labels"]:
        if agent:
            return True, (
                f"{AGENT_REVIEW_LABEL}: in-session review by {agent['actor']} "
                f"at {agent['at']} — {agent['url']}"
            )
        return False, (
            f"{AGENT_REVIEW_LABEL} is set but no comment carries "
            f"{AGENT_REVIEW_MARKER!r} — the label claims a review ran, so the "
            "findings have to be posted"
        )
    if OWNER_REVIEW_LABEL in state["labels"]:
        who = state.get("owner_review") or {}
        if who.get("actor"):
            return True, f"{OWNER_REVIEW_LABEL} applied by {who['actor']} at {who['at']}"
        return True, f"labelled {OWNER_REVIEW_LABEL}"
    if state["bugbot"] == "NEUTRAL":
        return False, (
            f"{BUGBOT_CHECK} reported neutral — that is the usage-limit skip, not a review"
        )
    if state["bugbot"]:
        return False, f"{BUGBOT_CHECK} reported {state['bugbot'].lower()}"
    return False, (
        "no completed agent review (Bugbot, CodeRabbit, Claude, in-session), "
        f"no approval, and no {OWNER_REVIEW_LABEL}"
    )


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
        ancestors = baseline_ancestor_shas(BASELINE_SHA)
    except subprocess.CalledProcessError:
        baseline_ok = False
        ancestors = set()

    checked: list[dict] = []
    unreviewed: list[dict] = []
    cache: dict[int, dict] = {}
    invalid_numbers: set[int] = set()
    associated: dict[str, int | None] = {}

    needed_numbers: list[int] = []
    unnumbered_shas: list[str] = []
    for commit in commits:
        if baseline_ok and commit["sha"] in ancestors:
            continue
        if is_merge_commit(commit["parents"]) or commit["author"] in BOT_AUTHORS:
            continue
        parsed = parse_pr_number(commit["subject"])
        if parsed is not None:
            needed_numbers.append(parsed)
        else:
            unnumbered_shas.append(commit["sha"])

    prefetch_pr_states(needed_numbers, cache, invalid_numbers)
    need_assoc = list(unnumbered_shas)
    for commit in commits:
        parsed = parse_pr_number(commit["subject"])
        if parsed is not None and parsed in invalid_numbers:
            need_assoc.append(commit["sha"])
    associated = prefetch_associated_prs(need_assoc)
    extra = [
        n
        for n in associated.values()
        if n is not None and n not in cache and n not in invalid_numbers
    ]
    prefetch_pr_states(extra, cache, invalid_numbers)

    for commit in commits:
        short = commit["sha"][:8]
        row = {"sha": short, "subject": commit["subject"][:72]}

        if baseline_ok and commit["sha"] in ancestors:
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

        number = resolve_pr_number(
            commit["subject"], commit["sha"], cache, invalid_numbers, associated
        )
        if number is None:
            direct = direct_push_review(commit["sha"])
            if direct:
                row.update(
                    reviewed=True,
                    why=(
                        f"no source pull request; in-session review naming {short} on "
                        f"#{direct['on']} by {direct['actor']} at {direct['at']} — "
                        f"{direct['url']}"
                    ),
                )
                checked.append(row)
                continue
            row.update(
                reviewed=False,
                why=(
                    "has no merged source pull request — pushed straight to the branch? "
                    f"Post an in-session review quoting {short} on an issue or PR "
                    f"labelled {AGENT_REVIEW_LABEL}"
                ),
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
            "  • a review bot already ran  → CodeRabbit / Claude / Bugbot with a "
            "completed review (not a skip, rate-limit, or failure notice) clears it\n"
            f"  • it needs a machine review → comment `bugbot run` or `@coderabbitai "
            f"review` on its PR, or wait for the {BUGBOT_CHECK} check to conclude "
            "success\n"
            f"  • an agent can review it    → run `/review <N>`; it posts findings and "
            f"applies `{AGENT_REVIEW_LABEL}`\n"
            f"  • you read it yourself      → label the PR `{OWNER_REVIEW_LABEL}`; the "
            "actor and timestamp are recorded in the verdict\n"
            "  • someone else read it      → approve the PR\n"
            "  • it has no PR at all       → review it, then post the findings with "
            f"`{AGENT_REVIEW_MARKER}` and the commit's {AGENT_REVIEW_SHA_LEN}-char sha "
            f"on an issue or PR labelled `{AGENT_REVIEW_LABEL}`\n"
            "Address the findings on the same branch before merge. A large follow-up "
            "fix is a new review loop, not a reason to skip this one.\n"
            "\nThe label hatches are accountability records: "
            f"`{OWNER_REVIEW_LABEL}` means you read it, with actor and timestamp recorded.\n"
            "This gate never fails because an external service is unavailable — a "
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

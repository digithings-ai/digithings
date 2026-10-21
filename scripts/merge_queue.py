#!/usr/bin/env python3
"""Merge queue for develop branches that have no server-side merge queue.

GitHub's native merge queue is configured *through* branch protection, so it is
unavailable to any private repository on a Free plan. That is the situation in
``digithings-ai/twelve-x`` and in every other private repo we own; the survey and
the evidence are in ``docs/MERGE_QUEUE.md``. This script is the queue for those
branches: it reads the open PRs targeting a base, evaluates each against the
gates the absent server-side rules would have enforced, and merges the eligible
ones one at a time in creation order, re-reading the queue after every merge.

Because a base branch that requires up-to-date checks means every merge pushes every
other PR behind its base — and a PR behind its base is refused, not fixed, by merging
it — ``run`` also brings one stale branch up to date per tick. That step is the
difference between a queue that drains and one that needs an operator to clear a path
after every single merge.

Two things this deliberately does not do, because reading a green run as if it
proved more than it does is how a queue gets mistaken for a fence:

* It does not enforce anything. Without branch protection on the branch, nothing
  stops ``git push origin develop``. The gates below run only because somebody on
  the merge-authority roster invoked this script. It is a merge *path*, and it
  genuinely removes the per-merge decision card — but it is not a merge *fence*.
* It never passes ``--admin``. When a PR fails a gate, the queue reports the
  reason and stops. An operator can always escalate by hand; a queue that
  escalates for you would be indistinguishable from a queue that ignores the
  gates.

Every merge posts an audit comment naming the acting role and the verdicts it
relied on. That comment is the evidence that no decision card was needed. If a
merge ever does need one, the trail shows which role claimed the merge was
already covered.

Usage::

    python3 scripts/merge_queue.py list --repo digithings-ai/twelve-x --acting-role cto
    python3 scripts/merge_queue.py run  --repo digithings-ai/twelve-x --acting-role em --dry-run
    python3 scripts/merge_queue.py run  --repo digithings-ai/twelve-x --acting-role em
"""

from __future__ import annotations

import argparse
import datetime
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

POLICY_PATH = Path(__file__).resolve().parent / "merge_queue_policy.json"

# Only SUCCESS passes a required check. NEUTRAL and SKIPPED are GitHub's way of
# reporting that a check declined to run, and for a required gate that is the
# failure mode this queue exists to stop: a path-filtered workflow leaves its
# check unreported or waived, and a PR then reaches the base without ever being
# tested. docs/BRANCH_PROTECTION.md records the same trap from the other side —
# a path-skipped required check blocks the merge button forever. Blocking is the
# direction that fails safe, so the runner refuses and names the check.
PASSING_CONCLUSIONS: frozenset[str] = frozenset({"SUCCESS"})
FAILING_CONCLUSIONS: frozenset[str] = frozenset(
    {"ACTION_REQUIRED", "CANCELLED", "FAILURE", "STALE", "STARTUP_FAILURE", "TIMED_OUT"}
)

# `gh pr list --json reviews` reports a review state per review; only these two
# say something about the code. COMMENTED is a discussion, not a verdict.
BLOCKING_REVIEW_STATES: frozenset[str] = frozenset({"CHANGES_REQUESTED"})

# `mergeStateStatus` values that must never queue. `BLOCKED` is the obvious one.
# `BEHIND` is the dangerous one — see `evaluate`.
STALE_MERGE_STATES: frozenset[str] = frozenset({"BLOCKED", "BEHIND", "DIRTY", "UNKNOWN"})

# Statuses the queue does not read at all, in either direction. QA is not in the
# review path (Chris, 2026-10-17): a `qa/gate` status QA posts on a PR head neither
# clears nor blocks a merge, so it is dropped before any gate sees the rollup, and
# it is left out of the audit comment's check list.
IGNORED_STATUS_CONTEXTS: frozenset[str] = frozenset({"qa/gate"})

EXIT_OK = 0
EXIT_OPERATIONAL = 1
EXIT_NOT_AUTHORISED = 2
EXIT_REFUSED_BASE = 3


class QueueError(RuntimeError):
    """An operational failure — gh was missing, unauthenticated, or errored."""


@dataclass(frozen=True)
class Authority:
    """One role allowed to merge through the queue."""

    role: str
    title: str
    github_login: str
    note: str = ""


#: The three ways the reviewer-independence gate can run. `shadow` measures what
#: the gate would refuse and merges anyway; `enforce` refuses. DIG-4809 named the
#: two-step rollout: 48 hours of shadow, then a separate small PR that flips the
#: switch to `enforce`.
REVIEW_INDEPENDENCE_MODES = ("off", "shadow", "enforce")


@dataclass(frozen=True)
class ReviewIndependence:
    """How the queue treats a review marker that may come from the author's seat.

    `mode` is the switch: `off` reads no provenance at all, `shadow` measures
    what the gate would refuse and merges anyway, `enforce` refuses. The env
    var `MQ_REVIEW_INDEPENDENCE` overrides the policy file, and a value that is
    not one of the three is read as `enforce`: a misspelled switch must never
    turn a gate off.
    """

    mode: str = "off"
    api_url: str = "http://127.0.0.1:3100"
    keychain_service: str = ""
    keychain_account: str = ""
    log_path: str = "~/.config/digithings/merge-queue/reviewer-independence.log"


def _effective_mode(cfg: ReviewIndependence) -> str:
    """The mode this gate runs in: the env var wins over the policy file."""
    raw = os.environ.get("MQ_REVIEW_INDEPENDENCE")
    if raw is None:
        mode = str(cfg.mode or "off").strip().lower()
        return mode if mode in REVIEW_INDEPENDENCE_MODES else "enforce"
    mode = raw.strip().lower()
    return mode if mode in REVIEW_INDEPENDENCE_MODES else "enforce"


@dataclass(frozen=True)
class Policy:
    """The merge-path policy, loaded from scripts/merge_queue_policy.json."""

    merge_authorities: tuple[Authority, ...]
    blocked_bases: tuple[str, ...]
    merge_method: str
    delete_branch: bool
    required_checks: tuple[str, ...]
    ignored_checks: frozenset[str] = frozenset()
    required_checks_by_repo: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    status_context_checks: frozenset[str] = frozenset()
    review_independence: ReviewIndependence = field(default_factory=ReviewIndependence)

    def authority(self, role: str) -> Authority | None:
        return next((a for a in self.merge_authorities if a.role == role), None)

    def is_blocked_base(self, base: str) -> bool:
        """A base is blocked by name or by prefix, so `release/v1.2.3` is covered."""
        return any(base == b or base.startswith(f"{b}/") for b in self.blocked_bases)

    def required_for(self, repo: str) -> tuple[str, ...]:
        """The check names this repo's gate is written against.

        One org owns repos whose CI reports different names for the same idea.
        `digithings` drives every suite through reusable workflows, so GitHub reports
        each as `<caller> / test` and names nothing `test`; `twelve-x` runs a single
        job and does report a bare `test`. A single global list can therefore only
        ever be right for one of them — and when it is wrong it is *silently* wrong,
        because an unmatched required name reads exactly like a red CI run. See
        DIG-690, where `required check 'test' has not reported` blocked all 28 open
        PRs on digithings and nobody could tell that from CI being broken.

        The per-repo entry is the required list; `required_checks` is the fallback for
        a repo with no entry, so an unlisted repo still gets a gate. Falling back to
        *nothing* would be the one failure that matters here — a queue that stops
        checking is worse than one that refuses.
        """
        return tuple(self.required_checks_by_repo.get(repo, ())) or self.required_checks

    def for_repo(self, repo: str) -> Policy:
        """A copy whose `required_checks` are this repo's.

        Resolving once here rather than passing `repo` down to every gate is what
        keeps the resolved list and the *reported* list from diverging: `_gate_checks`
        and `_audit_body` both read `policy.required_checks`, so the check the merge
        depended on and the check the audit comment names cannot come from two places.
        """
        return replace(self, required_checks=self.required_for(repo))


@dataclass
class Verdict:
    """The gate outcome for one PR, and why it landed there."""

    number: int
    title: str
    head_ref: str
    created_at: str
    head_sha: str
    eligible: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    checks: tuple[str, ...] = field(default_factory=tuple)
    review_evidence: str = ""
    #: The base moved and nothing else is wrong: the only thing that can make this PR
    #: queueable is updating its branch, which a merge cannot do. Kept separate from
    #: `reasons` so the update step can act on a stale branch without also acting on
    #: one that is merely broken — an update spends a full CI run either way.
    stale_base_only: bool = False

    def order_key(self) -> tuple[str, int]:
        """FIFO on creation time, PR number breaking ties.

        Queue order is deliberately oldest-first and not "greenest first". Picking
        whatever happens to be green reorders work by CI latency, which is how a
        queue silently becomes a race the loudest PR always wins.
        """
        return (self.created_at, self.number)


def load_policy(path: Path = POLICY_PATH) -> Policy:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != 1:
        raise QueueError(f"{path}: unsupported schema {raw.get('schema')!r}")
    defaults = raw.get("defaults", {})
    return Policy(
        merge_authorities=tuple(
            Authority(
                role=a["role"],
                title=a["title"],
                github_login=a["github_login"],
                note=a.get("note", ""),
            )
            for a in raw["merge_authorities"]
        ),
        blocked_bases=tuple(raw["blocked_bases"]),
        merge_method=defaults.get("merge_method", "squash"),
        delete_branch=bool(defaults.get("delete_branch", True)),
        required_checks=tuple(defaults.get("required_checks", ())),
        status_context_checks=frozenset(
            str(name) for name in (raw.get("status_context_checks") or [])
        ),
        ignored_checks=frozenset(defaults.get("ignored_checks", ())),
        # Reject a non-string entry rather than coercing it: a typo'd check name is
        # the exact failure DIG-690 was, and `str(42)` would turn that into a gate
        # that silently matches nothing.
        required_checks_by_repo={
            str(repo): tuple(str(name) for name in names)
            for repo, names in (raw.get("required_checks_by_repo") or {}).items()
        },
        review_independence=_load_review_independence(raw, path),
    )


def _load_review_independence(raw: Mapping[str, Any], path: Path) -> ReviewIndependence:
    """The reviewer-independence block of the policy file.

    A mode that is not one of the three is a broken policy file, and a broken
    policy file stops the queue rather than quietly turning a security gate
    off: the queue refuses to start on a policy it cannot read.
    """
    block = raw.get("review_independence")
    if not isinstance(block, Mapping):
        # No block at all. The gate still measures: shadow never refuses, so a
        # policy file that lost the block keeps the measurement instead of
        # silently turning the gate off. `off` has to be written down to be
        # meant.
        block = {}
        mode = "shadow"
    else:
        mode = str(block.get("mode") or "shadow").strip().lower()
    if mode not in REVIEW_INDEPENDENCE_MODES:
        raise QueueError(
            f"{path}: review_independence.mode must be one of "
            f"{', '.join(REVIEW_INDEPENDENCE_MODES)}, not {mode!r}"
        )
    return ReviewIndependence(
        mode=mode,
        api_url=str(block.get("api_url") or "http://127.0.0.1:3100"),
        keychain_service=str(block.get("keychain_service") or ""),
        keychain_account=str(block.get("keychain_account") or ""),
        log_path=str(
            block.get("log_path")
            or "~/.config/digithings/merge-queue/reviewer-independence.log"
        ),
    )


def _gh_json(*args: str) -> Any:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        # A non-zero exit is an operational transport failure (auth, rate
        # limit, 504 deadline), never a parse problem: name the exit status
        # and say the read is safe to retry. fetch_queue only reads, so a
        # transient here must not read as a bug in the response handling.
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        detail = stderr or stdout or "no output"
        empty_note = "" if stdout else " with empty stdout"
        raise QueueError(
            f"gh {' '.join(args[:2])} failed with exit {proc.returncode}{empty_note}: "
            f"{detail} (retryable transport error; retry the read)"
        )
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise QueueError(f"gh {' '.join(args[:2])} returned non-JSON: {proc.stdout[:200]}") from exc


def fetch_queue(repo: str, base: str, limit: int) -> list[dict[str, Any]]:
    """Open PRs targeting `base`, oldest first, with everything the gates need."""
    prs = _gh_json(
        "pr",
        "list",
        "--repo",
        repo,
        "--base",
        base,
        "--state",
        "open",
        # `gh pr list` returns newest-first and `--limit N` keeps the *newest* N,
        # so sorting afterwards cannot recover the oldest ones: above the limit the
        # queue would silently starve its head, which is the opposite of what FIFO
        # is for. Ask GitHub for the oldest order so `--limit` truncates the tail.
        "--search",
        "sort:created-asc",
        "--limit",
        str(limit),
        "--json",
        "number,title,headRefName,headRefOid,baseRefName,isDraft,mergeable,"
        "mergeStateStatus,statusCheckRollup,reviewDecision,author,createdAt,reviews,"
        "comments,commits,labels",
    )
    if not isinstance(prs, list):
        raise QueueError(f"gh pr list did not return a list for {repo}:{base}")
    return sorted(prs, key=lambda p: (p.get("createdAt", ""), p.get("number", 0)))


def _check_name(entry: dict[str, Any]) -> str:
    # CheckRun carries `name`; StatusContext (external CI) carries `context`. gh
    # normalises most fields, but a third-party integration can post either.
    return str(entry.get("name") or entry.get("context") or "")


def _rollup(pr: dict[str, Any]) -> list[dict[str, Any]]:
    """The PR's check rollup without the statuses the queue ignores."""
    return [
        e
        for e in (pr.get("statusCheckRollup") or [])
        if isinstance(e, dict) and _check_name(e) not in IGNORED_STATUS_CONTEXTS
    ]


def _is_check_run(entry: dict[str, Any]) -> bool:
    """True when the report came from a workflow run rather than a commit status.

    A StatusContext is only as trustworthy as whoever posted it: "any person or
    integration with write permissions can set the state of any status check"
    (GitHub's commit status docs). So a bare status named `test` is not
    evidence that `test` ran, and accepting one would let any agent with write
    access green-light its own PR by posting a status. A CheckRun is bound to an
    Actions run, so it cannot be written by hand.
    """
    return entry.get("__typename") == "CheckRun"


def _near_misses(unmatched: tuple[str, ...], reported: tuple[str, ...]) -> list[str]:
    """Reported checks that share a word with a gate that matched nothing.

    The point of this announcement is to be actionable without opening a second tool.
    Dumping all 58 check names a digithings PR reports is not action — the reader
    cannot compare that against a name they were told is wrong. Sharing a word is a
    good enough proxy for "this is what you meant": `test` finds `digibase / test`,
    `mypy` finds `mypy — digibase + digikey`. Word, not substring, so `test` does not
    match `path-filter`'s neighbours and `foo_test` does not match `test`.
    """
    near: list[str] = []
    for wanted in unmatched:
        wanted_words = set(re.split(r"[^0-9A-Za-z]+", wanted.lower())) - {""}
        if not wanted_words:
            continue
        for name in reported:
            if name in near:
                continue
            name_words = set(re.split(r"[^0-9A-Za-z]+", name.lower())) - {""}
            if wanted_words & name_words:
                near.append(name)
    return near[:4]


def unmatched_required_checks(
    prs: list[dict[str, Any]], required: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Required names that *no* PR in the queue reports, and everything that was reported.

    A required check that is missing from one PR is the case this script exists for:
    a path-filtered workflow, a skip, a waiver — the change lands untested. A required
    check that is missing from *every* PR is a different thing entirely: the gate is
    naming something this repo's CI does not produce. DIG-690 was 28 open PRs, all
    blocked on `required check 'test' has not reported`, in a repo where nothing has
    ever reported `test` — and the message is byte-identical to the untested-PR case,
    so the only sensible operator move was to go read CI logs that were fine.

    So compare against the union of what the queue did report. Requiring every PR to
    agree would misfire on correct behaviour (one Python-only PR legitimately has no
    `digichat / test`), which would train operators to ignore this. The second element
    is the reported union, so the caller can name what it should have said.

    This reports; it never unblocks. A gate that cannot match must still block.
    """
    reported: set[str] = set()
    for pr in prs:
        for entry in _rollup(pr):
            reported.add(_check_name(entry))
    if not reported:
        # Nothing ran anywhere. That is CI being absent, not a naming mistake, and
        # conflating the two would send the reader to the policy file.
        return (), ()
    return tuple(r for r in required if r not in reported), tuple(sorted(reported))


def _gate_checks(pr: dict[str, Any], policy: Policy) -> list[str]:
    """Required checks must have reported, and must have passed. No exceptions."""
    rollup = _rollup(pr)
    reasons: list[str] = []

    by_name: dict[str, list[dict[str, Any]]] = {}
    for entry in rollup:
        by_name.setdefault(_check_name(entry), []).append(entry)

    for required in policy.required_checks:
        entries = by_name.get(required, [])
        if not entries:
            reasons.append(f"required check '{required}' has not reported")
            continue
        bad = [
            e
            for e in entries
            if str(e.get("conclusion") or e.get("state") or "") not in PASSING_CONCLUSIONS
        ]
        if bad:
            states = sorted({str(e.get("conclusion") or e.get("state") or "?") for e in bad})
            reasons.append(f"required check '{required}' is {', '.join(states)}")
            continue
        # All green, but a green that anyone with write access could have typed is
        # not a passing build. Require the evidence to come from a workflow run -
        # except for the checks named in `status_context_checks`: digithings'
        # branch protection requires `local-ci` as a commit status (DIG-3707), and
        # twelve-x requires the same name because its Actions job cannot start while
        # billing is blocked (DIG-4454). For those a SUCCESS status is the strongest
        # evidence that exists - and on twelve-x it is the only one.
        if required in policy.status_context_checks:
            continue
        if not any(_is_check_run(e) for e in entries):
            reasons.append(
                f"required check '{required}' only reported as a commit status, which any "
                "writer can set; the queue needs a workflow run"
            )

    # A non-required check that failed is still a red build. The base branch has a
    # CI contract whether or not GitHub enforces it.
    for name, entries in by_name.items():
        if name in policy.required_checks or name in policy.ignored_checks:
            continue
        for entry in entries:
            state = str(entry.get("conclusion") or entry.get("state") or "")
            if state in FAILING_CONCLUSIONS:
                reasons.append(f"check '{name}' is {state}")
    return reasons


# --- a code-review verdict posted as a PR comment -----------------------------
#
# `docs/agents/CODE_REVIEW_POLICY.md` makes a PR comment the sanctioned place for
# review findings, and a reviewer's verdict posted there is a real review signal
# that GitHub's `reviewDecision` cannot see. twelve-x PR #347 posted "changes
# requested — one finding blocks approval" at 22:07:11Z and merged at 22:13:57Z on
# an attestation, because the queue only ever fetched `reviews`.
#
# Only the marker's `key=value` fields are read. The prose is not a contract: a
# matcher on `## Verdict: changes requested (narrow)` would have to survive a
# reviewer reformatting a heading, and a heading someone forgets to update is
# indistinguishable from a verdict someone forgot to post.

_MARKER_RE = re.compile(r"<!--\s*opencode-power-pack:code-review\b(?P<fields>[^>]*?)\s*-->")
_MARKER_FIELD_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)=(?P<value>\S+)")
_SCOPE_SHA_RE = re.compile(r"@(?P<sha>[0-9a-f]{7,40})\b")

# `changes_needed` is read alongside `changes_requested` because DIG-1021's interim
# discipline named the two verdicts "approve" and "changes needed"; a reviewer
# writing that spelling must not slip past the gate.
BLOCKING_VERDICTS = frozenset({"changes_requested", "changes_needed"})
READABLE_VERDICTS = BLOCKING_VERDICTS | {"approved", "approve"}


def _normalise_verdict(value: str) -> str:
    return value.strip().strip("'\";").lower().replace("-", "_")


def _posted_verdict(comment: dict[str, Any]) -> tuple[str, str] | None:
    """`(verdict, scope_sha)` from a review marker comment, or None.

    None means "this comment is not a verdict the queue can read" — which covers
    both a plain comment and a marker whose `verdict=` is missing or misspelled.
    That is a missing signal, not a clearance, and it must not be treated as one.
    """
    body = str(comment.get("body") or "")
    for marker in _MARKER_RE.finditer(body):
        fields = {
            m.group("key").lower(): m.group("value")
            for m in _MARKER_FIELD_RE.finditer(marker.group("fields"))
        }
        verdict = _normalise_verdict(fields.get("verdict", ""))
        if verdict not in READABLE_VERDICTS:
            continue
        scope_sha = _SCOPE_SHA_RE.search(fields.get("scope", ""))
        return verdict, (scope_sha.group("sha") if scope_sha else "")
    return None


def _on_pr_history(pr: dict[str, Any], sha: str) -> bool:
    """Whether `sha` is the PR head, or a commit behind it.

    Every commit GitHub lists for a PR is an ancestor of its head, so the commit
    list is the ancestry proof the gate needs — without a repository or a network
    round trip, which is what keeps `evaluate` a pure function the tests can pin.
    """
    if not sha:
        return False
    head = str(pr.get("headRefOid") or "")
    if head and sha == head:
        return True
    return sha in {str(c.get("oid") or "") for c in (pr.get("commits") or [])}


def _latest_readable_verdict(pr: dict[str, Any]) -> tuple[dict[str, Any], str, str] | None:
    """The newest comment carrying a verdict the queue can read, with its scope.

    Newest wins, so a reviewer who blocked and then came back and approved clears
    their own block. Comments the queue cannot read are skipped rather than
    counted as the newest: letting a typo'd marker displace a real block would
    hand anyone who can comment a way to unlock the queue.
    """
    best: tuple[dict[str, Any], str, str] | None = None
    best_at = ""
    for comment in pr.get("comments") or []:
        if not isinstance(comment, Mapping):
            continue
        parsed = _posted_verdict(comment)
        if parsed is None:
            continue
        verdict, scope_sha = parsed
        posted_at = str(comment.get("createdAt") or "")
        if best is None or posted_at >= best_at:
            best, best_at = (comment, verdict, scope_sha), posted_at
    return best


def _posted_verdict_reason(pr: dict[str, Any]) -> list[str]:
    """A refusal when the newest readable posted verdict blocks this PR.

    A block stands while the commit it names is still on the branch, which is what
    `_on_pr_history` answers from `pr["commits"]`. When the row carries no commit
    list that question cannot be answered at all, and answering "gone" would retire a
    live block — the second leg of the `#5903` hole, where a verdict scoped to a
    commit that was still on the branch was cleared by a row that never said which
    commits the branch had. Unverifiable blocks; only a branch that is *known* not to
    carry the commit spends the verdict.
    """
    latest = _latest_readable_verdict(pr)
    if latest is None:
        return []
    comment, verdict, scope_sha = latest
    if verdict not in BLOCKING_VERDICTS:
        return []
    on_history = _on_pr_history(pr, scope_sha)
    if not on_history and pr.get("commits") is not None:
        return []
    login = str((comment.get("author") or {}).get("login") or "?")
    where = (
        f"comment {comment.get('id') or '?'}" if comment.get("id") else f"a comment from {login}"
    )
    scope = scope_sha[:12] if scope_sha else "an unstated commit"
    still = (
        "and that commit is still on this branch"
        if on_history
        else (
            "and this row carries no commit list, so that commit could not be "
            "checked against the branch"
        )
    )
    return [
        f"a code-review verdict of '{verdict}' was posted on this PR by {login} "
        f"({where}) against {scope}, {still}; a new review must clear it"
    ]


def _evidence_reviews(pr: dict[str, Any]) -> list[dict[str, Any]]:
    """The PR's reviews, minus the entry that is not review evidence.

    Any review by the PR's own author is dropped: GitHub refuses a self-approval in
    production, so the APPROVED shape is a fixture rather than a live one, and an
    author's own review is not evidence that anyone else read the change.

    Bot reviews are deliberately NOT stripped here (2026-10-19, DIG-4298). The
    `[bot]`-suffix strip this hatch used to apply was the queue's only bot rule,
    bare logins slipped past it into the coverage module's approvals sink, and the
    strip itself starved the `REVIEW_BOTS` hatch: a `coderabbitai[bot]` approval
    counted as NO evidence through this queue while its bare spelling counted as a
    person's approval through the promotion gate - two spellings, two verdicts, for
    one review. There is now one rule for "this login is a bot",
    `check_review_coverage.is_bot_login`, applied once at the sink
    (`_apply_reviews_checks_comments`) that both the queue and the promotion gate
    call: bot logins are excluded from `approvals` there, while listed
    reviewer-bot reviews still flow through to the `REVIEW_BOTS` hatch.
    """
    author = str((pr.get("author") or {}).get("login") or "")
    kept: list[dict[str, Any]] = []
    for review in pr.get("reviews") or []:
        login = str((review.get("author") or {}).get("login") or "")
        if login and login == author:
            continue
        kept.append(review)
    return kept


def _ensure_comments(pr: dict[str, Any], repo: str | None) -> str | None:
    """Give the row its comments, or say why it cannot. Returns a refusal, or None.

    `_posted_verdict_reason` reads `pr["comments"]`, and a PR can carry a
    `changes_requested` verdict with **no label at all** — so this is not the
    `reviewed:agent` lazy fetch's client, and it runs before both review gates rather
    than inside the coverage one.

    `#5903` merged on 2026-10-19T08:23:06Z with four review passes on it and the
    newest a `changes_requested` verdict. The gate was not wrong: run against the
    real payload it refuses. The *row* was wrong — the host tick fetched it with a
    field list that left `comments` out, so `_posted_verdict_reason` read nothing,
    `_gate_review` stayed silent, and `_gate_review_coverage` authorised the merge on
    a label. The queue's own audit comment says which gate carried it:
    `review: review evidence via the coverage gate (_gate_review_coverage)`.

    An absent comment list is a missing signal, not a clearance — the sentence
    `_posted_verdict` already applies to a marker it cannot parse. So the row is
    completed here when it can be, and refused when it cannot: with no repo there is
    nothing to read, and a failed read is not an empty one.
    """
    comments = pr.get("comments")
    if isinstance(comments, list):
        return None
    if comments is not None:
        return (
            "the review record could not be read: this row's comments field is "
            f"{type(comments).__name__}, not a list, so a posted code-review "
            "verdict cannot be ruled out"
        )
    if repo is None:
        return (
            "the review record could not be read: this row carries no comments and "
            "no repo was given to fetch them from, so a posted code-review verdict "
            "cannot be ruled out"
        )
    try:
        data = _gh_json(
            "pr",
            "view",
            str(pr.get("number")),
            "--repo",
            repo,
            "--json",
            "comments",
        )
    except (QueueError, ValueError, OSError):
        return (
            "the review record could not be read: fetching this PR's comments "
            "failed, so a posted code-review verdict cannot be ruled out"
        )
    if not isinstance(data, dict) or not isinstance(data.get("comments"), list):
        # A payload with no comment list is a failed read, not an empty one.
        # `_gh_json` returns None for empty stdout, and `gh` is not promised to
        # answer in any particular shape; reading either as "no verdict was
        # posted" is the hole this function exists to close.
        return (
            "the review record could not be read: fetching this PR's comments "
            "returned no comment list, so a posted code-review verdict cannot "
            "be ruled out"
        )
    pr["comments"] = data["comments"]
    return None


def _gate_review(pr: dict[str, Any]) -> list[str]:
    """Open change requests block: a formal one, or a verdict posted as a comment.

    This gate no longer demands an approving review from a non-author, and it no
    longer accepts a role attestation in place of one. Every agent on this org
    pushes under one GitHub login, so no agent can give a non-author approval and
    the old gate could only ever be met by `--attest-review`, a declared role with
    no review act behind it (Chris, 2026-10-17: "Drop the false QA attestation").
    The review that counts is the board's own review pass, read by
    `_gate_review_coverage`, with its comments addressed (`_gate_review_threads`)
    — Chris's 2026-10-15 definition. A human approval still counts there.
    """
    reasons: list[str] = []
    if str(pr.get("reviewDecision") or "").upper() == "CHANGES_REQUESTED":
        reasons.append("review has outstanding change requests")
    # twelve-x PR #347 merged on an attestation 6m37s after a posted "changes
    # requested". A posted blocking verdict stays a block until a newer one clears it.
    reasons.extend(_posted_verdict_reason(pr))
    return reasons


# --- review comments addressed -----------------------------------------------
#
# A review pass that left comments is only half of Chris's 2026-10-15 rule; the
# other half is that those comments were resolved or addressed before merge. A
# review thread GitHub marks `isResolved` was resolved. One marked `isOutdated`
# sits on code that has since changed under it, which is the closest artifact
# GitHub has for "addressed by a follow-up commit" (CodeRabbit threads stay
# unresolved after the fix lands, see check_review_coverage.py). Anything else
# is a comment on the current code that nobody has answered, and it blocks.

_THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        totalCount
        nodes { isResolved isOutdated path comments(first: 1) { nodes { author { login } } } }
      }
    }
  }
}
"""


def _fetch_review_threads(repo: str, number: int) -> list[dict[str, Any]]:
    owner, _, name = repo.partition("/")
    data = _gh_json(
        "api",
        "graphql",
        "-f",
        f"query={_THREADS_QUERY}",
        "-F",
        f"owner={owner}",
        "-F",
        f"name={name}",
        "-F",
        f"number={number}",
    )
    threads = (
        (((data or {}).get("data") or {}).get("repository") or {}).get("pullRequest") or {}
    ).get("reviewThreads") or {}
    nodes = threads.get("nodes")
    if not isinstance(nodes, list):
        raise QueueError(f"review threads for #{number} came back without a node list")
    if int(threads.get("totalCount") or 0) > len(nodes):
        # More than one page. Treat the unread tail as unanswered rather than
        # paging: a PR with 100+ review threads is not one a cron should merge.
        nodes = nodes + [{"isResolved": False, "isOutdated": False, "path": "(unread page)"}]
    return nodes


def _open_threads(threads: list[Any]) -> list[dict[str, Any]]:
    return [
        t
        for t in threads
        if isinstance(t, dict) and not t.get("isResolved") and not t.get("isOutdated")
    ]


def _gate_review_threads(pr: dict[str, Any], repo: str | None) -> list[str]:
    """Unresolved review threads on the current code block the merge.

    A row that already carries `reviewThreads` (a test fixture, or a caller that
    fetched them) is judged as given. Otherwise they are read from `repo`; a read
    that fails holds the PR, because "could not see the comments" must not read as
    "the comments were addressed". With neither, there is nothing to judge.
    """
    threads = pr.get("reviewThreads")
    if threads is None:
        if repo is None:
            return []
        try:
            threads = _fetch_review_threads(repo, int(pr.get("number") or 0))
        except (QueueError, ValueError):
            return [
                "review comments: the PR's review threads could not be read, so the "
                "queue cannot tell they were addressed"
            ]
    open_threads = _open_threads(threads if isinstance(threads, list) else [])
    if not open_threads:
        return []
    paths = sorted({str(t.get("path") or "?") for t in open_threads})
    shown = ", ".join(paths[:3]) + (f" and {len(paths) - 3} more" if len(paths) > 3 else "")
    return [
        f"review comments not addressed: {len(open_threads)} unresolved review "
        f"thread(s) on the current code ({shown}); resolve them, or push the fix "
        "that makes them outdated"
    ]


def _coverage_module() -> Any:
    """scripts/check_review_coverage.py: the main gate's hatch vocabulary.

    Imported lazily so the label names, the marker, and the comment matching
    have exactly one source of truth: whatever the promotion gate accepts here
    is what this queue enforces. The module is stdlib-only with no import-time
    side effects, so importing it changes nothing about this script's startup.
    """
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import check_review_coverage

    return check_review_coverage


def _label_names(pr: dict[str, Any]) -> set[str]:
    """Label names on a `gh pr list --json labels` row (dicts) or a test fixture."""
    names: set[str] = set()
    for label in pr.get("labels") or []:
        name = label.get("name") if isinstance(label, dict) else label
        if name:
            names.add(str(name))
    return names


def _gate_review_coverage(pr: dict[str, Any], repo: str | None) -> list[str]:
    return _review_coverage(pr, repo)[0]


# --- reviewer independence: the review must come from another seat ------------
#
# DIG-4795. Every seat in this org pushes and comments under one GitHub login
# (`chrizefan`), so GitHub cannot say which seat wrote a review comment, and a
# comment that says "Review verdict: approve" carries no seat either. The seat
# identity has to travel inside the artifact, and the queue has to check it.
#
# Two facts decide whether a review marker counts as coverage:
#
#   1. It names the head it reviewed, and that head is the PR's current head.
#      A marker written against an older head says nothing about the code that
#      is about to merge. The release lane measured this on #5994: the only
#      marker on the PR named head `22d4b3126` while the PR stood at
#      `15414f011d`.
#
#   2. It did not come from a seat that wrote the PR — not that seat itself,
#      and not a marker that seat posted while its own run on that ticket was
#      still active. That window covers the author's own subagents and
#      same-session reviewers, which is how twelve-x #369 got its "in-session
#      review" and how #425 merged with review coverage from its author seat.
#      It is not a veto on other seats: a review from another seat posted while
#      the author was still working is that seat's review. The author is read
#      from the branch — the commit trailers and the runs on the PR's own ticket
#      that were open when the commits were committed — not from the ticket's
#      assignee: ownership is not authorship.
#
# Both halves are one question — "did a different seat look at this head?" —
# so they live in one gate and one marker.
#
# The marker is `<!-- digithings-review agent=<uuid> run=<uuid> head=<sha> -->`.
# `agent` and `run` are Paperclip identities: the queue resolves the run
# through the Paperclip API to the agent (the seat) that ran it, so the seat a
# marker claims is checked against the seat that actually ran. `head` is the
# reviewed head. A marker with no provenance is a missing signal, not a
# clearance: it cannot be shown to come from another seat, so it does not count.
#
# The `<!-- in-session-review -->` marker stays exactly as it is. It is what
# `scripts/check_review_coverage.py` matches, and putting the provenance in a
# second marker keeps every other consumer of that literal working — including
# the other repos that share this policy.
#
# What this gate cannot do: prove that the comment was written by the seat it
# names. All seats share one GitHub login, so GitHub's own record says nothing.
# The queue checks the claim against the Paperclip side — a run id that the API
# does not know is refused, and a run that belongs to another seat than the
# marker claims is refused too — and the remaining gap is closed by the
# per-seat GitHub identity DIG-4803 is for.

REVIEW_PROVENANCE_MARKER = "digithings-review"

_PROVENANCE_RE = re.compile(r"<!--\s*digithings-review\b(?P<fields>[^>]*?)\s*-->")
_VERDICT_LINE_RE = re.compile(r"^[ \t]*Review verdict:", re.MULTILINE)
_ISSUE_KEY_RE = re.compile(r"\bDIG-(?P<number>\d+)\b", re.IGNORECASE)
_AGENT_TRAILER_RE = re.compile(
    r"^Paperclip-Agent-Id:\s*(?P<agent>[0-9a-fA-F-]{36})\s*$", re.MULTILINE
)
#: The run that wrote the commit. Resolved through the API to the seat that
#: owned that run, so it names the author exactly.
_RUN_TRAILER_RE = re.compile(
    r"^Paperclip-Run-Id:\s*(?P<run>[0-9a-fA-F-]{36})\s*$", re.MULTILINE
)


class _PaperclipUnavailable(RuntimeError):
    """The queue could not read the Paperclip facts the reviewer gate needs."""


class _PaperclipMissing(_PaperclipUnavailable):
    """The API answered, and the answer is "no such record".

    This is a fact about the world, not a failure to read it: a ticket key
    that names no issue, or a run id nobody has ever heard of, is something
    the gate has to judge. It is kept apart from `_PaperclipUnavailable` so a
    missing record is never read as "the API is down".
    """


@dataclass(frozen=True)
class ReviewMarker:
    """One review comment the queue reads as review evidence."""

    comment_id: str
    at: str
    agent: str
    run: str
    head: str


@dataclass(frozen=True)
class Independence:
    """What the reviewer gate decided about one PR's review markers."""

    #: Comment ids that must not count as review coverage.
    disqualified: frozenset[str] = frozenset()
    #: One line per marker that does not count, and why.
    problems: tuple[str, ...] = ()
    #: The reviewer the gate accepted, for the audit comment.
    note: str = ""
    #: A failure to judge at all — the facts could not be read, or the author's
    #: seat could not be identified. Nothing was concluded about any marker.
    unverifiable: str = ""


#: How long one read of the Paperclip API may take, and how many times it may
#: be tried.
#:
#: The queue reads Paperclip over a link that is sometimes slow: on 2026-10-21
#: the Code Reviewer measured `GET /api/issues/{id}` at 31.5 s, 36.5 s and
#: 30.7 s in a slow window, `GET /api/heartbeat-runs/{id}` at 12.6 s to 27.7 s,
#: and `GET /api/issues/{id}/runs` with no answer at all in 60 s. The old
#: 10-second read turned every one of those into a refusal, and a refusal for
#: a transport reason is indistinguishable from a refusal for a real one — so
#: in `enforce` mode a slow API would have blocked pull requests for a reason
#: that has nothing to do with review independence.
#:
#: The read is a GET, so it is safe to try again: a second attempt asks the
#: same question, and a question that was not answered is not an answer. The
#: budget bounds one read, so a slow answer costs at most that much. It is a
#: budget per path and not per tick: the gate reads a ticket, a run and a pull
#: request's runs, so a control plane that does not answer costs that much
#: again for each of them.
#:
#: The four numbers are the fix, and the suite pins them: a timeout below the
#: slowest answer measured turns a slow API back into a refusal, a budget
#: below the timeout leaves no room for the second attempt, and a backoff that
#: hammers a struggling control plane makes the second attempt likelier to
#: fail than the first.
PAPERCLIP_READ_TIMEOUT = 45
PAPERCLIP_READ_BUDGET = 60.0
PAPERCLIP_READ_ATTEMPTS = 2
PAPERCLIP_RETRY_BACKOFF = 3.0


class ReviewerProvenance:
    """The Paperclip facts the reviewer gate needs: tickets, seats and runs.

    The queue runs from launchd with no Paperclip credential in its
    environment, so the key is read from the macOS keychain — the same
    credential `kit/bin/dt-paperclip-key` manages and the same one
    `com.digithings.decide-poll.plist` exports. The key is a header value and
    nothing else: it is never printed, logged or written anywhere.
    """

    def __init__(self, cfg: ReviewIndependence) -> None:
        self._cfg = cfg
        self._token = ""
        self._cache: dict[str, Any] = {}

    def _bearer(self) -> str:
        if self._token:
            return self._token
        from_env = os.environ.get("PAPERCLIP_API_KEY", "").strip()
        if from_env:
            self._token = from_env
            return from_env
        if not self._cfg.keychain_service or not self._cfg.keychain_account:
            raise _PaperclipUnavailable(
                "no Paperclip credential is configured for the reviewer gate"
            )
        try:
            proc = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    self._cfg.keychain_service,
                    "-a",
                    self._cfg.keychain_account,
                    "-w",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise _PaperclipUnavailable(
                f"the Paperclip credential could not be read: {exc}"
            ) from exc
        if proc.returncode != 0:
            raise _PaperclipUnavailable(
                "the Paperclip credential could not be read from the keychain"
            )
        token = proc.stdout.strip()
        if not token:
            raise _PaperclipUnavailable(
                "the Paperclip credential in the keychain is empty"
            )
        self._token = token
        return token

    def _get(self, path: str) -> Any:
        cached = self._cache.get(path)
        if cached is not None:
            return cached
        url = f"{self._cfg.api_url.rstrip('/')}{path}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._bearer()}",
                "Accept": "application/json",
            },
        )
        deadline = time.monotonic() + PAPERCLIP_READ_BUDGET
        attempts = 0
        failure: Exception | None = None
        for attempt in range(1, PAPERCLIP_READ_ATTEMPTS + 1):
            if attempt > 1:
                # The pause is inside the budget, not on top of it: a retry
                # that starts after the deadline spends the read on a question
                # that was never going to be asked in time.
                pause = min(
                    PAPERCLIP_RETRY_BACKOFF, max(0.0, deadline - time.monotonic())
                )
                if pause <= 0:
                    break
                time.sleep(pause)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            attempts += 1
            try:
                with urllib.request.urlopen(
                    request, timeout=min(PAPERCLIP_READ_TIMEOUT, remaining)
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    # A fact, not a failure: the API answered, and the answer is
                    # "no such record". A ticket key that names no issue, or a run
                    # id nobody has ever heard of, is exactly what the gate has to
                    # judge — it must not be read as "the API is down". The same
                    # holds for any other 4xx: the API answered, and its answer
                    # does not change when we ask again.
                    raise _PaperclipMissing(f"Paperclip has no {path}") from exc
                if exc.code < 500:
                    raise _PaperclipUnavailable(
                        f"Paperclip answered {exc.code} for {path}"
                    ) from exc
                # A server-side error can be transient, so it earns one more try.
                failure = exc
            except OSError as exc:
                # A timeout and a refused connection are both transport facts and
                # neither is a fact about the world: nothing was answered, so
                # nothing was judged, and both earn one more try.
                failure = exc
            except (http.client.HTTPException, ValueError) as exc:
                # The answer was cut off or was not JSON: a truncated or proxied
                # response. It is not the fact the gate needs, so it earns one
                # more try.
                failure = exc
            else:
                self._cache[path] = payload
                return payload
        if failure is None:
            raise _PaperclipUnavailable(
                f"Paperclip could not be read for {path}: the read budget was spent"
            )
        if isinstance(failure, urllib.error.HTTPError):
            detail = f"Paperclip answered {failure.code} for {path}"
        else:
            detail = f"Paperclip could not be read for {path}: {failure}"
        raise _PaperclipUnavailable(f"{detail} (after {attempts} attempts)") from failure

    def ticket(self, key: str) -> dict[str, Any] | None:
        """The Paperclip issue behind a ticket key, or None when there is none."""
        try:
            data = self._get(f"/api/issues/{key}")
        except _PaperclipMissing:
            return None
        return data if isinstance(data, dict) else None

    def issue_runs(self, issue_id: str) -> list[dict[str, Any]]:
        """Every run that happened on one issue."""
        try:
            data = self._get(f"/api/issues/{issue_id}/runs")
        except _PaperclipMissing:
            return []
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []

    def run(self, run_id: str) -> dict[str, Any] | None:
        """One run by id — the record that says which seat ran it.

        None means the API does not know that run: a marker naming it is
        refused, not a marker that passes because the lookup failed.
        """
        try:
            data = self._get(f"/api/heartbeat-runs/{run_id}")
        except _PaperclipMissing:
            return None
        return data if isinstance(data, dict) else None


#: One provenance reader per policy, shared across the PRs of a tick: the
#: credential is read once and every answer is cached for the tick.
_PROVENANCE: dict[tuple[str, str, str], ReviewerProvenance] = {}


def _provenance_for(cfg: ReviewIndependence) -> ReviewerProvenance:
    """The shared provenance reader for this policy."""
    key = (cfg.api_url, cfg.keychain_service, cfg.keychain_account)
    reader = _PROVENANCE.get(key)
    if reader is None:
        reader = ReviewerProvenance(cfg)
        _PROVENANCE[key] = reader
    return reader


def _provenance_fields(body: str) -> dict[str, str]:
    """The `digithings-review` marker's fields, lower-cased keys."""
    fields: dict[str, str] = {}
    for marker in _PROVENANCE_RE.finditer(body):
        for match in _MARKER_FIELD_RE.finditer(marker.group("fields")):
            fields[match.group("key").lower()] = match.group("value")
    return fields


def _marker_fields(marker: re.Match[str]) -> dict[str, str]:
    """One marker's `key=value` fields, lower-cased keys."""
    return {
        match.group("key").lower(): match.group("value")
        for match in _MARKER_FIELD_RE.finditer(marker.group("fields"))
    }


def _scope_head(body: str) -> str:
    """The head sha a posted verdict names, if it names one.

    The power-pack marker carries the reviewed commit as
    `scope=owner/repo#12@<sha>`. That is a real head binding, so it counts as
    one when the comment carries no provenance marker of its own.
    """
    head = ""
    for marker in _MARKER_RE.finditer(body):
        found = _SCOPE_SHA_RE.search(_marker_fields(marker).get("scope", ""))
        if found:
            head = found.group("sha")
    return head


def _carries_review_evidence(body: str, marker_literal: str) -> bool:
    """Whether a comment is review evidence the queue reads.

    Three shapes count: the in-session marker, a `Review verdict:` line, and a
    posted verdict marker. The first is the coverage hatch, the second is the
    review rule's own format, and the third is the marker the queue reads for
    a blocking verdict.
    """
    if marker_literal in body:
        return True
    if _VERDICT_LINE_RE.search(body):
        return True
    for marker in _MARKER_RE.finditer(body):
        verdict = _normalise_verdict(_marker_fields(marker).get("verdict", ""))
        if verdict in READABLE_VERDICTS:
            return True
    return False


def _review_markers(comments: list[Any]) -> list[ReviewMarker]:
    """Every comment on the PR that carries review evidence."""
    crc = _coverage_module()
    literal = str(getattr(crc, "AGENT_REVIEW_MARKER", "<!-- in-session-review -->"))
    markers: list[ReviewMarker] = []
    for comment in comments:
        if not isinstance(comment, Mapping):
            continue
        body = str(comment.get("body") or "")
        if not _carries_review_evidence(body, literal):
            continue
        fields = _provenance_fields(body)
        markers.append(
            ReviewMarker(
                comment_id=str(comment.get("id") or ""),
                at=str(comment.get("createdAt") or ""),
                agent=str(fields.get("agent") or ""),
                run=str(fields.get("run") or ""),
                head=str(fields.get("head") or _scope_head(body)),
            )
        )
    return markers


def _ticket_key(pr: dict[str, Any]) -> str:
    """The one Paperclip ticket this PR is about.

    The title comes first, then the branch: the ticket a PR is about is named
    in its title or its branch. The body is not read, because `fetch_queue`
    does not fetch it — a key taken from the body would be a key the gate can
    never see in production, so the body branch was dead code that read as
    a rule. And only one ticket is taken: a PR that names two tickets does not
    have two authors, and the ticket that decides who wrote the code is the
    ticket the PR ships.
    """
    for source in (pr.get("title"), pr.get("headRefName")):
        match = _ISSUE_KEY_RE.search(str(source or ""))
        if match:
            return f"DIG-{match.group('number')}"
    return ""


def _author_dates(pr: dict[str, Any]) -> list[str]:
    """When each of this PR's own commits was written.

    A merge commit is not one of the PR's own commits: merging `develop` into
    a branch is branch maintenance, and the seat that ran the merge did not
    write the code the PR carries. Counting it makes the seat that merged
    `develop` an author of every PR it rebased — measured on #6145, whose
    merge of `develop` landed inside the QA Lead's run window.

    The stamp is the commit's **author date**, never its committer date. A
    rebase rewrites the commits it replays: the author date and the message
    stay, the committer date becomes the rebasing seat's. So the committer
    date names whoever rebased the branch last, and the author date names
    whoever wrote the code — which is the question this gate asks. Read from
    the committer date, the seat that rebased a branch became the PR's
    author, the real author's own review counted as coverage, and a rebase
    that landed outside every run window left the PR with no author at all
    and no way to merge (the QA Lead's finding on #6145, 21 Oct).

    A commit that carries no author date says nothing about who wrote it, so
    it is left out. Nothing is guessed from the committer date: that is
    exactly the date a rewrite moves.
    """
    stamps: list[str] = []
    for commit in pr.get("commits") or []:
        if not isinstance(commit, Mapping):
            continue
        headline = str(commit.get("messageHeadline") or "").strip().lower()
        if headline.startswith("merge "):
            continue
        stamp = str(commit.get("authoredDate") or "").strip()
        if stamp:
            stamps.append(stamp)
    return stamps


def _author_context(
    pr: dict[str, Any], prov: ReviewerProvenance
) -> tuple[set[str], list[tuple[str, str, str]]]:
    """The seats that wrote this PR, and their runs on this PR's ticket.

    Ownership is not authorship. The seat a ticket is assigned to is the seat
    that is asked to move the ticket along; the seat that wrote the code is
    the seat whose commits are on the branch. Reading the assignee as the
    author refused the review of the very seat that owns the ticket (the QA
    Lead's finding on #6145, 21 Oct) and — worse — let the author seat's own
    review through on every branch that carried no provenance trailer, which
    was 28 of the 30 open develop PRs.

    So the author is read from the code:

    * the seats the commits declare: `Paperclip-Agent-Id:`, and the
      `Paperclip-Run-Id:` resolved through the API to the seat that owned
      that run;
    * the seat whose run on this PR's own ticket was open when the PR's
      commits were written — the author date of each commit, which a rebase
      preserves. A run that was about a different ticket is not evidence about
      this one — the reviewer that works from its own review ticket is not the
      author of the PR it reviews.

    When more than one seat is a candidate, the seat that the most commits
    fall into is the author. A reviewer woken on the ticket while the author
    pushes a fix shares a window with the author, and it is not the author.

    The attribution is **per commit**. A commit that falls inside exactly one
    seat's window was written by that seat, so that seat is an author — and a
    seat that pushed one commit of a PR is an author even when the other seat
    pushed more of them. Only a commit that falls inside several windows is
    ambiguous, and there the count breaks the tie. Marking a seat as an author
    costs that seat its own review coverage and nobody else's, so where the
    evidence cannot separate two seats, both are treated as authors.
    """
    authors: set[str] = set()
    windows: dict[str, list[tuple[str, str, str]]] = {}
    for commit in pr.get("commits") or []:
        if not isinstance(commit, Mapping):
            continue
        body = str(commit.get("messageBody") or commit.get("message") or "")
        for match in _AGENT_TRAILER_RE.finditer(body):
            authors.add(match.group("agent"))
        for match in _RUN_TRAILER_RE.finditer(body):
            run = prov.run(match.group("run"))
            seat = str((run or {}).get("agentId") or "")
            if seat:
                authors.add(seat)
    key = _ticket_key(pr)
    ticket = prov.ticket(key) if key else None
    if ticket:
        issue_id = str(ticket.get("id") or "")
        stamps = _author_dates(pr)
        counts: dict[str, int] = {}
        for run in prov.issue_runs(issue_id):
            seat = str(run.get("agentId") or "")
            if not seat:
                continue
            if str(run.get("contextIssueId") or "") != issue_id:
                # The run was about another ticket. It says nothing about who
                # wrote this PR.
                continue
            window = (
                str(run.get("runId") or run.get("id") or ""),
                str(run.get("startedAt") or ""),
                str(run.get("finishedAt") or ""),
            )
            windows.setdefault(seat, []).append(window)
            for stamp in stamps:
                if _within_window(stamp, window[1], window[2]):
                    counts[seat] = counts.get(seat, 0) + 1
        for stamp in stamps:
            candidates = [
                seat
                for seat, seat_windows in windows.items()
                if any(
                    _within_window(stamp, start, end)
                    for _, start, end in seat_windows
                )
            ]
            if not candidates:
                continue
            if len(candidates) == 1:
                # One seat was working on this ticket when the commit was
                # written. It wrote it.
                authors.add(candidates[0])
                continue
            # Several seats were awake. The seat the most commits fall into is
            # the author; a tie leaves both as authors, because calling a seat
            # an author only takes away that seat's own coverage.
            best = max(counts.get(seat, 0) for seat in candidates)
            for seat in candidates:
                if counts.get(seat, 0) == best:
                    authors.add(seat)
    author_runs: list[tuple[str, str, str]] = []
    for seat in sorted(authors):
        author_runs.extend(windows.get(seat, []))
    return authors, author_runs


def _parse_ts(value: str) -> float | None:
    """A timestamp as seconds, or None when it cannot be read."""
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _within_window(at: str, start: str, end: str) -> bool:
    """Whether `at` falls inside the run window `[start, end]`.

    A run with no end time is still running, so its window is open.
    """
    at_ts = _parse_ts(at)
    start_ts = _parse_ts(start)
    if at_ts is None or start_ts is None:
        return False
    end_ts = _parse_ts(end)
    if end_ts is None:
        end_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    return start_ts <= at_ts <= end_ts


MIN_HEAD_BINDING = 7


def _head_binds(marked: str, head: str) -> bool:
    """Whether a posted sha binds this PR's head.

    Reviewers write the reviewed sha at whatever length they have at hand:
    the QA Lead's census of the open develop PRs found markers naming the
    head as 7, 8, 12 and 40 characters. So the binding is a prefix
    comparison against the head, not a fixed-width match — a check that
    looked for exactly 12 hex characters would read a valid 7-character
    marker as naming nothing at all. A sha shorter than git's own minimum
    abbreviation binds no head.
    """
    marked = str(marked or "").strip().lower()
    head = str(head or "").strip().lower()
    if not head or len(marked) < MIN_HEAD_BINDING:
        return False
    return head.startswith(marked)


def _marker_problems(
    marker: ReviewMarker,
    *,
    head: str,
    authors: set[str],
    author_runs: list[tuple[str, str, str]],
    prov: ReviewerProvenance,
) -> tuple[list[str], str]:
    """What is wrong with one review marker, and the seat that made it.

    An empty problem list means the marker counts: it names the head the PR
    stands at, and it came from a seat that is not the author.
    """
    problems: list[str] = []
    if not marker.head:
        problems.append(
            f"names no head SHA, so it says nothing about the head `{head[:12]}` "
            "this PR stands at"
        )
    elif not _head_binds(marker.head, head):
        problems.append(
            f"names head `{marker.head[:12]}` while this PR stands at `{head[:12]}`"
        )
    reviewer = ""
    if marker.run:
        run = prov.run(marker.run)
        if run is None:
            problems.append(
                f"names run `{marker.run[:8]}`, which the Paperclip API does not know"
            )
        else:
            reviewer = str(run.get("agentId") or "")
            if marker.agent and reviewer and marker.agent != reviewer:
                problems.append(
                    f"names seat `{marker.agent[:8]}` while run `{marker.run[:8]}` "
                    f"belongs to seat `{reviewer[:8]}`"
                )
    elif marker.agent:
        reviewer = marker.agent
        problems.append(
            f"names seat `{marker.agent[:8]}` but no run to check that seat against"
        )
    else:
        problems.append("carries neither a seat nor a run")
    if reviewer and reviewer in authors:
        problems.append(f"came from the PR author's own seat (`{reviewer[:8]}`)")
        # The authoring seat's own run window. A marker of the author's own
        # seat that lands inside that window is the author's review, and the
        # seat's subagents share its run id, so the window says which run
        # spoke. It is not a veto on other seats: a review from another seat
        # posted while the author was still working is that seat's review
        # (the QA Lead's finding on #6145, 21 Oct — a gate that refuses other
        # seats inside the author's window refuses every honest review).
        for run_id, started, finished in author_runs:
            if _within_window(marker.at, started, finished):
                problems.append(
                    f"was posted while the authoring seat's run `{run_id[:8]}` on this "
                    "PR's ticket was still active"
                )
                break
    return problems, reviewer


def _governing_marker(markers: list[ReviewMarker]) -> ReviewMarker:
    """The marker that speaks for the PR: the newest one.

    The queue has always read the last review marker on a PR, so the gate
    judges that one and no other. Falling back to an earlier marker would
    paper over a stale last marker with an older review — and the head only
    moves forward, so an earlier marker can only ever bind an older head.
    The remedy for a stale last marker has to be a new review, not an older
    one, so a stale last marker is a refusal.
    """
    best: ReviewMarker | None = None
    best_key: tuple[bool, float, int] = (False, 0.0, -1)
    for index, marker in enumerate(markers):
        stamp = _parse_ts(marker.at)
        key = (stamp is not None, stamp if stamp is not None else 0.0, index)
        if key > best_key:
            best, best_key = marker, key
    if best is None:
        raise ValueError("no marker to govern")
    return best


def _reviewer_independence(
    pr: dict[str, Any],
    cfg: ReviewIndependence,
    prov: ReviewerProvenance,
    comments: list[Any],
) -> Independence:
    """Judge the review marker that speaks for this PR.

    The newest review marker governs, and it is judged on two counts: it must
    name the head the PR stands at now, and it must come from a seat that is
    not one of the seats that wrote the PR. A marker that fails is dropped
    from the coverage evidence, and every other marker goes with it, so that
    no older review is used in its place.
    """
    mode = _effective_mode(cfg)
    if mode == "off":
        return Independence()
    markers = _review_markers(comments)
    if not markers:
        return Independence()
    head = str(pr.get("headRefOid") or "")
    # A marker the gate cannot judge does not count: an unjudged marker is
    # dropped from the evidence, exactly like a judged-and-refused one.
    every_marker = frozenset(m.comment_id for m in markers if m.comment_id)
    try:
        authors, author_runs = _author_context(pr, prov)
    except _PaperclipUnavailable as exc:
        return Independence(
            disqualified=every_marker,
            unverifiable=f"the review seats could not be checked: {exc}",
        )
    if not authors:
        return Independence(
            disqualified=every_marker,
            unverifiable=(
                "the PR's authoring seat could not be identified, so no review on "
                "it can be shown to come from a different seat"
            )
        )
    governing = _governing_marker(markers)
    try:
        found, reviewer = _marker_problems(
            governing,
            head=head,
            authors=authors,
            author_runs=author_runs,
            prov=prov,
        )
    except _PaperclipUnavailable as exc:
        # The API went away mid-judgement. Nothing is concluded about any
        # marker: a partial judgement is not a judgement.
        return Independence(
            disqualified=every_marker,
            unverifiable=f"the review seats could not be checked: {exc}",
        )
    if found:
        return Independence(
            # Every marker goes, not just the one that failed: an older review
            # is not used in place of a last marker that does not count.
            disqualified=every_marker,
            problems=(
                "the last review posted at "
                f"{governing.at or 'an unknown time'} " + "; ".join(found),
            ),
        )
    seat = reviewer or governing.agent
    note = (
        f"reviewer seat `{seat[:8]}`"
        + (f" (run `{governing.run[:8]}`)" if governing.run else "")
        + f" on head `{head[:12]}`"
    )
    return Independence(
        # The older markers are dropped too, so the coverage evidence carries
        # the governing marker and nothing else.
        disqualified=every_marker - {governing.comment_id},
        note=note,
    )


#: The shadow log is a measurement, not an archive: one generation, one
#: reader, and a line only when the measurement changes.
SHADOW_LOG_MAX_BYTES = 1_048_576
SHADOW_LOG_TAIL_BYTES = 65_536


def _rotate_shadow_log(path: Path) -> None:
    """Keep the shadow log to one generation, and to one reader.

    The queue writes it every tick, so an unrotated file grows without end
    and a world-readable one hands the queue's own record to every account
    on the machine. The file holds no secret — it names PRs, seats and the
    reason a review did not count — but it is still the queue's record, so it
    is written for its owner alone.
    """
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    if size > SHADOW_LOG_MAX_BYTES:
        try:
            path.replace(path.with_name(path.name + ".1"))
        except OSError:
            pass
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _shadow_log_says(path: Path, number: Any, payload: str) -> bool:
    """Whether the shadow log already records this verdict for this PR.

    The queue judges a PR on every tick. A log that repeats the same verdict
    every ten minutes is a heartbeat, not a measurement: it buries the change
    it is supposed to show. So a verdict that is already the last word on
    that PR is not written again.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return False
    try:
        with path.open("rb") as handle:
            handle.seek(max(0, size - SHADOW_LOG_TAIL_BYTES))
            tail = handle.read().decode("utf-8", "replace")
    except OSError:
        return False
    marker = f"PR #{number} "
    last = ""
    for line in tail.splitlines():
        if marker in line:
            last = line
    if not last:
        return False
    return last.split("would refuse: ", 1)[-1] == payload


def _log_shadow(
    cfg: ReviewIndependence | None,
    pr: dict[str, Any],
    repo: str | None,
    lines: Sequence[str],
) -> None:
    """Write what the gate would have refused, to the shadow log.

    A shadow log that cannot be written is a lost measurement, not a reason to
    stop merging: the gate is measuring, so it keeps its hands off the merge.
    """
    if cfg is None:
        return
    path = Path(str(cfg.log_path)).expanduser()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = " | ".join(str(line) for line in lines)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_shadow_log(path)
        if _shadow_log_says(path, pr.get("number"), payload):
            return
        with path.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(
                    f"{stamp} reviewer independence (shadow): PR #{pr.get('number')} "
                    f"{repo or '?'} — would refuse: {line}\n"
                )
        os.chmod(path, 0o600)
    except OSError:
        pass


def _comment_id(comment: Any) -> str:
    """The id of a comment row, whether it is a dict or a fixture."""
    if isinstance(comment, Mapping):
        return str(comment.get("id") or "")
    return ""


def _review_coverage(
    pr: dict[str, Any],
    repo: str | None,
    cfg: ReviewIndependence | None = None,
    prov: ReviewerProvenance | None = None,
) -> tuple[list[str], str]:
    """The promotion gate's evidence, enforced at merge time.

    `scripts/check_review_coverage.py` refuses an unreviewed commit at promotion;
    the queue merged such commits twice in one night as PR #5526 (a
    `reviewed:agent` claim with no findings comment, DIG-3154) and PRs #5489 /
    #5277 via `--attest-review` with no review artifact at all (this issue's
    reopen). The failure in all three cases is the same: the queue accepted
    something the promotion gate rejects. So the queue judges the exact same
    evidence — a completed Bot run, an approval, a Bot review, an in-session
    review with its findings comment, or `reviewed:owner` — by calling the main
    gate's own `verdict_for` on the already-fetched PR dict.

    Two deliberate properties worth stating plainly:

    * This is the review gate. Both reopen cases merged attested by `qa` with
      zero reviews and zero comments; attestation is an assertion, and an
      assertion with no artifact is exactly what the promotion gate refuses.
      `--attest-review` is gone (2026-10-17), and no non-author approval is
      required on top of this evidence (Chris's 2026-10-15 definition).
    * The comments this gate scores are supplied by `fetch_queue` and, when the
      row arrives without them, completed by `_ensure_comments` — which runs
      before this function precisely because an unreadable review record must
      fail here rather than be read as "no verdict was posted". The lazy fetch
      below survives only as a defence for callers that hand in a raw row. An
      unreadable comments read fails closed, for the same reason an absent
      check fails closed: the alternative reads "no evidence" as "approved".
    """
    crc = _coverage_module()
    labels = _label_names(pr)
    comments = pr.get("comments")
    if crc.AGENT_REVIEW_LABEL in labels and comments is None:
        if repo is None:
            return [
                "review coverage: `reviewed:agent` is set but the findings "
                "comment cannot be verified without a repo to read it from"
            ], ""
        try:
            data = _gh_json(
                "pr",
                "view",
                str(pr.get("number")),
                "--repo",
                repo,
                "--json",
                "comments",
            )
        except QueueError:
            return [
                "review coverage: `reviewed:agent` is set but its findings "
                "comment could not be read"
            ], ""
        comments = (data or {}).get("comments") or []
    counted = list(comments) if isinstance(comments, list) else []

    mode = _effective_mode(cfg) if cfg is not None else "off"
    independence = Independence()
    if cfg is not None and mode != "off":
        independence = _reviewer_independence(pr, cfg, prov or _provenance_for(cfg), counted)
    kept = [c for c in counted if _comment_id(c) not in independence.disqualified]

    def state_for(entries: list[Any]) -> dict[str, Any]:
        state: dict[str, Any] = {
            "labels": labels,
            "approvals": [],
            "bugbot": None,
            "title": str(pr.get("title") or ""),
            "owner_review": None,
            "agent_tool": [],
            "agent_review": None,
        }
        crc._apply_reviews_checks_comments(
            state,
            reviews=_evidence_reviews(pr),
            checks=_rollup(pr),
            comments=entries,
        )
        return state

    if mode == "enforce":
        reviewed, why = crc.verdict_for(state_for(kept))
    else:
        # Shadow mode scores the row as it stands, then scores it again without the
        # markers the gate would drop. The difference between the two answers is the
        # measurement: "this PR would have been refused".
        reviewed, why = crc.verdict_for(state_for(counted))
        would_review, would_why = crc.verdict_for(state_for(kept))
        if independence.unverifiable:
            _log_shadow(
                cfg,
                pr,
                repo,
                [f"could not check the review seats: {independence.unverifiable}"],
            )
        elif independence.problems and not would_review:
            _log_shadow(cfg, pr, repo, list(independence.problems))
        elif independence.problems:
            _log_shadow(
                cfg,
                pr,
                repo,
                [
                    f"dropped {len(independence.disqualified)} review marker(s) that "
                    f"did not count; the PR would still have merged on {would_why}"
                ],
            )

    if reviewed:
        evidence = why
        if independence.note:
            evidence = f"{evidence}; {independence.note}"
        elif independence.problems:
            evidence = (
                f"{evidence}; {len(independence.disqualified)} review marker(s) did "
                "not count"
            )
        return [], evidence

    if mode == "enforce" and independence.unverifiable:
        return [f"reviewer independence: {independence.unverifiable}"], ""
    if mode == "enforce" and independence.problems:
        head = str(pr.get("headRefOid") or "")[:12]
        return [
            "reviewer independence: "
            + "; ".join(independence.problems[:3])
            + " — the queue needs a review from a different seat, on the head "
            f"this PR stands at (`{head}`)"
        ], ""
    return [
        f"review coverage: {why} — the queue needs a review pass that left its "
        "findings on the PR, the same evidence scripts/check_review_coverage.py "
        "enforces at promotion (completed Bot run, a reviewer bot such as "
        "CodeRabbit or Copilot, an in-session review with its findings comment, "
        "an approval, or reviewed:owner)"
    ], ""


def evaluate(
    pr: dict[str, Any],
    policy: Policy,
    *,
    base: str,
    acting_role: str,
    repo: str | None = None,
    prov: ReviewerProvenance | None = None,
) -> Verdict:
    """Apply every gate to one PR. Returns the verdict, including why it failed."""
    reasons: list[str] = []

    # `--base` already filters the fetch, and `blocked_bases` already refuses the
    # branches a human must sign off on. Asserting the base again here is cheap and
    # closes the gap between the two: without it, losing the `--base` flag would
    # silently widen the queue from `develop` to every open PR in the repo, and the
    # roster would merge them without anyone noticing the target moved.
    if str(pr.get("baseRefName") or "") != base:
        reasons.append(f"baseRefName={pr.get('baseRefName') or '?'}, expected {base}")

    if pr.get("isDraft"):
        reasons.append("draft")
    mergeable = str(pr.get("mergeable") or "")
    if mergeable != "MERGEABLE":
        reasons.append(f"mergeable={mergeable or 'UNKNOWN'}")
    # `BEHIND` matters as much as `BLOCKED`, and this is the subtle one. When this
    # queue merges PR #1, PR #2's base moves but its checks do not re-run: GitHub
    # reports #2 as MERGEABLE + BEHIND, and its green `test` is the run against the
    # *previous* base. Merging on that evidence is exactly what a merge queue exists
    # to prevent, and the ruleset path catches it with `strict_required_status_checks_policy`.
    # The local queue has to catch it itself.
    state = str(pr.get("mergeStateStatus") or "")
    stale_reason = f"mergeStateStatus={state} (base moved since the checks ran)"
    if state in STALE_MERGE_STATES:
        reasons.append(stale_reason)

    reasons.extend(_gate_checks(pr, policy))
    # The verdict gate reads the review record, so the row is completed before either
    # review gate runs. `_review_coverage`'s own lazy fetch is not enough on its own:
    # it runs *after* `_gate_review` and so cannot repair a row that `_gate_review`
    # has already read as verdict-free — which is how #5903 was authorised on a
    # label while a `changes_requested` verdict stood (#5903 post-mortem).
    unreadable = _ensure_comments(pr, repo)
    if unreadable:
        reasons.append(unreadable)
    reasons.extend(_gate_review(pr))
    coverage_reasons, review_evidence = _review_coverage(
        pr, repo, policy.review_independence, prov
    )
    reasons.extend(coverage_reasons)
    # Read last, and only for a PR every other gate passed: it is one GraphQL read
    # per PR, and a PR already refused elsewhere needs no second reason to wait.
    if not reasons:
        reasons.extend(_gate_review_threads(pr, repo))

    # BEHIND is the one stale state an update can clear, and only when it is the sole
    # reason: the checks passed, just against the base this merge would land on top of.
    # Every other reason — a conflict, a red check, missing review evidence — would
    # still be there after the update, so paying for a full CI run to clear nothing is
    # how a queue burns its own capacity. Read off the finished `reasons` rather than
    # re-testing each gate, so a gate added later cannot silently become updatable.
    stale_base_only = state == "BEHIND" and reasons == [stale_reason]

    rollup = _rollup(pr)
    return Verdict(
        number=int(pr.get("number", 0)),
        title=str(pr.get("title") or ""),
        head_ref=str(pr.get("headRefName") or ""),
        created_at=str(pr.get("createdAt") or ""),
        head_sha=str(pr.get("headRefOid") or ""),
        eligible=not reasons,
        reasons=tuple(reasons),
        review_evidence=review_evidence,
        checks=tuple(
            f"{_check_name(e)}={e.get('conclusion') or e.get('state') or '?'}" for e in rollup
        ),
        stale_base_only=stale_base_only,
    )


def evaluate_all(
    prs: list[dict[str, Any]],
    policy: Policy,
    *,
    base: str,
    acting_role: str,
    repo: str | None = None,
) -> list[Verdict]:
    """Every PR, in queue order, with its verdict."""
    verdicts = [evaluate(pr, policy, base=base, acting_role=acting_role, repo=repo) for pr in prs]
    verdicts.sort(key=Verdict.order_key)
    return verdicts


def _audit_body(verdict: Verdict, authority: Authority, policy: Policy) -> str:
    checks = "\n".join(f"- `{c}`" for c in verdict.checks) or "- (no checks reported)"
    review = (verdict.review_evidence or "review coverage passed") + (
        "; no unresolved review threads on the current code"
    )
    return (
        "Merged through the `develop` merge queue — no decision card required.\n\n"
        f"- merging role: `{authority.role}` ({authority.title})\n"
        f"- head: `{verdict.head_ref}` @ `{verdict.head_sha[:12]}`\n"
        f"- method: `{policy.merge_method}`\n"
        f"- review: {review}\n"
        f"- required checks: {', '.join(f'`{c}`' for c in policy.required_checks)}\n"
        f"- checks reported: {len(verdict.checks)}\n\n"
        f"{checks}\n\n"
        "Gate definition and the roster: `docs/MERGE_QUEUE.md`, "
        "`scripts/merge_queue_policy.json`."
    )


def merge_one(repo: str, verdict: Verdict, authority: Authority, policy: Policy) -> None:
    """Merge one PR, pinned to the head SHA the gates were evaluated against.

    `--match-head-commit` is what makes re-reading the queue after each merge
    sufficient. If someone pushed to the PR between evaluation and merge, the
    merge aborts instead of landing tests we never looked at.
    """
    args = [
        "pr",
        "merge",
        str(verdict.number),
        "--repo",
        repo,
        f"--{policy.merge_method}",
        "--match-head-commit",
        verdict.head_sha,
    ]
    if policy.delete_branch:
        args.append("--delete-branch")
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise QueueError(f"merge of #{verdict.number} failed: {proc.stderr.strip()}")


def stale_candidates(verdicts: list[Verdict], limit: int) -> list[Verdict]:
    """Return up to ``limit`` branches that are stale only because the base moved.

    A PR whose *only* reason for being refused is a moved base is not broken: a
    merge of the base into its branch puts it back in flight, and its checks
    run again against the base the queue is on. That is the only action that can
    clear it, so the update step is what keeps the queue draining.

    The list is FIFO — the same order the queue merges in — because an update
    spends a full CI run, and the oldest PR is the one that has been waiting
    longest for it. The order is taken from the verdicts themselves rather than
    from the order they arrive in, so a caller that hands the list over in any
    other order still refreshes the oldest first. ``limit`` is the number of
    branches one tick may refresh: each one costs a CI run, and refreshing more
    than the checks can absorb turns the queue into a treadmill of runs that all
    finish at once.

    A limit of zero or less returns nothing, so a caller that does not want to
    update anything does not have to special-case it.
    """
    if limit <= 0:
        return []
    stale = sorted((v for v in verdicts if v.stale_base_only), key=Verdict.order_key)
    return stale[:limit]


def update_branch(repo: str, verdict: Verdict) -> bool:
    """Bring a stale PR's branch onto the base, so its checks run against it.

    `mergeStateStatus=BEHIND` means the checks on this PR ran against a base that has
    since moved, so merging them would land evidence about different code — the queue
    refuses, and refusing is right. What was missing is what comes next. Every merge
    this script performs moves the base for every other PR, so with no update step the
    queue is a one-way door: it drains exactly one PR and then dead-ends on a state
    nothing in it can clear. Measured on `digithings` on 2026-10-19: fourteen
    hand-run `gh pr update-branch` calls moved a single PR, and the queue reported
    `0 eligible` again the moment that merge landed.

    Updating is safe where merging is not. It writes a merge of the base *into* the
    branch, so it loses no work and cannot land a change that was not reviewed; it
    re-triggers the checks. The `expected_head_sha` is still pinned, exactly as
    `merge_one` pins `--match-head-commit`: an update is only ever applied to the head
    the gates were read from, so a push landing in between is reported rather than
    silently merged under. The PR is re-evaluated on a later tick, never merged on the
    read that prompted the update.

    Returns `False` when GitHub refused the update, which leaves the branch exactly as
    it was: the caller must not report a refusal as an update.
    """
    proc = subprocess.run(
        [
            "gh",
            "api",
            "--method",
            "PUT",
            f"repos/{repo}/pulls/{verdict.number}/update-branch",
            "-f",
            f"expected_head_sha={verdict.head_sha}",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        # A refusal arrives as 422 for two different reasons and the response does not
        # separate them: a real one (a conflict, or a head that moved between the read
        # and this call) and the benign "there are no new commits on the base branch",
        # which a concurrent tick or a retry produces. Neither is an operational
        # failure — the branch is left exactly as it was and the next tick tries again —
        # and failing the run would report the tick as broken *after* its merges had
        # already landed, which is worse than the refusal it is reporting. Anything else
        # (a token that lost write access, a 5xx) is a real failure and stops the run.
        # The status is read out of `gh`'s own rendering of a REST error, which is
        # `<message> (HTTP 422)`. If that format ever changes this raises instead, which
        # is the safe direction: a refused update is never reported as a done one.
        if "HTTP 422" in proc.stderr:
            print(
                f"warning: update-branch of #{verdict.number} refused (422) — the branch "
                f"is unchanged and the next tick retries: {proc.stderr.strip()}",
                file=sys.stderr,
            )
            return False
        raise QueueError(f"update-branch of #{verdict.number} failed: {proc.stderr.strip()}")
    return True


def comment_audit(repo: str, verdict: Verdict, body: str) -> None:
    proc = subprocess.run(
        ["gh", "pr", "comment", str(verdict.number), "--repo", repo, "--body", body],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        # The merge already landed; losing the audit comment must not fail the run
        # silently, and must not be reported as a successful merge either.
        print(
            f"warning: audit comment on #{verdict.number} failed: {proc.stderr.strip()}",
            file=sys.stderr,
        )


def print_queue(verdicts: list[Verdict], *, queued_only: bool) -> None:
    eligible = [v for v in verdicts if v.eligible]
    blocked = [v for v in verdicts if not v.eligible]
    if eligible:
        print(f"queued ({len(eligible)}), oldest first:")
        for i, v in enumerate(eligible, start=1):
            print(f"  {i:>2}. #{v.number} {v.head_ref} — {v.title}")
    else:
        print("queued: none")
    # Stale, not blocked: named separately and before the blocked list, because the
    # action on them is different — nobody has to fix anything, a run tick clears
    # them — and reporting them as blocked is what made 10 green PRs look like work.
    stale = stale_candidates(verdicts, len(verdicts))
    if stale and not queued_only:
        print(
            f"\nstale ({len(stale)}) — green against a base we have left, and counted "
            "below as not eligible; nobody has to fix these, a run tick updates "
            "branches, oldest first, up to --max-updates of them:"
        )
        for v in stale:
            print(f"  #{v.number} {v.head_ref} — {v.title}")
    if blocked and not queued_only:
        print(f"\nblocked ({len(blocked)}):")
        for v in blocked:
            print(f"  #{v.number} {v.head_ref} — {v.title}")
            for reason in v.reasons:
                print(f"       · {reason}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["list", "run"])
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--base", default="develop", help="base branch to queue into")
    parser.add_argument(
        "--acting-role",
        required=True,
        help="the merge-authority role invoking the queue; must be on the roster",
    )
    # DIG-3240: the --json field list below costs ~10,502 possible GraphQL nodes
    # per PR, and GitHub rejects requests above 500,000 nodes. A default of 50
    # (~525k nodes) made every `run` at the default exit 1 with an unreadable
    # queue; 40 (~420k) leaves headroom. Keep comments/commits: the
    # review-coverage gate reads them and fails closed when comments is None.
    parser.add_argument("--limit", type=int, default=40, help="max PRs to inspect")
    parser.add_argument("--max-merges", type=int, default=1, help="max merges in run mode")
    parser.add_argument(
        "--max-updates",
        type=int,
        default=1,
        help=(
            "max stale branches to bring up to date in run mode (0 disables). One by "
            "default: a merge moves the base for every other PR, so updating a whole "
            "stale set at once queues CI runs that the next merge invalidates"
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="evaluate and report; change nothing"
    )
    args = parser.parse_args(argv)

    try:
        policy = load_policy()
    except (OSError, ValueError, KeyError, QueueError) as exc:
        print(f"merge_queue: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL

    # Resolve the gate to this repo's real check names before any evaluation. Every
    # consumer below — the check gate and the audit comment — reads the resolved
    # policy, so what the merge relied on and what the trail claims cannot diverge.
    policy = policy.for_repo(args.repo)

    if args.limit < 1 or args.max_merges < 1:
        print("merge_queue: --limit and --max-merges must be >= 1", file=sys.stderr)
        return EXIT_OPERATIONAL

    if args.max_updates < 0:
        print("merge_queue: --max-updates must be >= 0", file=sys.stderr)
        return EXIT_OPERATIONAL

    authority = policy.authority(args.acting_role)
    if authority is None:
        roster = ", ".join(f"{a.role} ({a.title})" for a in policy.merge_authorities)
        print(
            f"merge_queue: '{args.acting_role}' is not on the merge-authority roster: {roster}. "
            f"Hand the PR to one of them; see {POLICY_PATH.name}.",
            file=sys.stderr,
        )
        return EXIT_NOT_AUTHORISED

    if policy.is_blocked_base(args.base):
        print(
            f"merge_queue: refusing to queue into '{args.base}'. "
            f"Blocked bases: {', '.join(policy.blocked_bases)}.",
            file=sys.stderr,
        )
        return EXIT_REFUSED_BASE

    try:

        def read_queue() -> list[Verdict]:
            prs = fetch_queue(args.repo, args.base, args.limit)
            # No once-per-invocation guard is needed, and that is worth stating rather
            # than assuming: a required name reported by *no* PR means every PR fails
            # the check gate, so nothing is eligible and `run` breaks out of its loop
            # after this single read. An eligible PR always reports every required
            # name, so the warning cannot coexist with a merge and cannot repeat.
            unmatched, reported = unmatched_required_checks(prs, policy.required_checks)
            if unmatched:
                near = _near_misses(unmatched, reported)
                print(
                    f"merge_queue: this gate cannot be satisfied in {args.repo} — no open PR "
                    "reports "
                    + ", ".join(f"'{name}'" for name in unmatched)
                    + ". That is a misconfigured required check, not a red build: "
                    f"{len(reported)} distinct checks did report"
                    + (", nearest: " + ", ".join(f"'{n}'" for n in near) if near else "")
                    + f". Fix the name in {POLICY_PATH.name} "
                    f"(required_checks_by_repo['{args.repo}'], or defaults.required_checks); "
                    f"`gh pr checks <n> --repo {args.repo}` lists what a PR actually ran.",
                    file=sys.stderr,
                )
            return evaluate_all(
                prs,
                policy,
                base=args.base,
                acting_role=args.acting_role,
                repo=args.repo,
            )

        if args.command == "list":
            print_queue(read_queue(), queued_only=False)
            return EXIT_OK

        if args.dry_run:
            verdicts = read_queue()
            eligible = [v for v in verdicts if v.eligible]
            print(f"dry run — nothing merged. {len(eligible)} would merge, oldest first:")
            for i, v in enumerate(eligible[: args.max_merges], start=1):
                print(f"  {i:>2}. #{v.number} {v.head_ref} — {v.title}")
            remaining = eligible[args.max_merges :]
            if remaining:
                print(f"  … {len(remaining)} more eligible, not reached under --max-merges")
            blocked = [v for v in verdicts if not v.eligible]
            if blocked:
                print(f"\nblocked ({len(blocked)}) — see `list` for reasons")
            return EXIT_OK

        updated: list[Verdict] = []
        merged: list[Verdict] = []
        verdicts: list[Verdict] = []
        while len(merged) < args.max_merges:
            # Re-read every iteration: merging one PR can turn the next one dirty or
            # re-run its checks, and merging from a queue computed before the last
            # merge is how two PRs end up claiming the same clean state. The read
            # also doubles as the report, so there is no separate fetch up front.
            verdicts = read_queue()
            head = next((v for v in verdicts if v.eligible), None)
            if head is None:
                break
            merge_one(args.repo, head, authority, policy)
            comment_audit(
                args.repo,
                head,
                _audit_body(head, authority, policy),
            )
            merged.append(head)
            print(f"merged #{head.number} {head.head_ref} as {authority.role}")

        if args.max_updates:
            # Clear a stale base *after* the merges, so the update lands on the base the
            # merge just produced rather than the one it replaced. `verdicts` is the last
            # read, so this costs no extra API call, and a PR that only became stale
            # *because* of this tick's merge is not in it — it still read CLEAN — so it is
            # picked up on the next tick instead of being updated twice.
            for candidate in stale_candidates(verdicts, args.max_updates):
                if not update_branch(args.repo, candidate):
                    # Refused: the branch is exactly as it was, so this is not an update
                    # and must not be reported, counted or dropped from the dump as one.
                    # The queue is FIFO, so a refusal stops the tick rather than skipping
                    # past the oldest PR to a younger one.
                    break
                updated.append(candidate)
                print(
                    f"updated #{candidate.number} {candidate.head_ref} onto {args.base} — "
                    "checks re-run against the current base; the next tick re-evaluates it"
                )

        if not merged:
            print("nothing merged — no PR passed the queue gates")
        if len(merged) < args.max_merges:
            # The loop drained, so `verdicts` is the queue as it stands now and the
            # blocked list is worth showing. When --max-merges cut the run short,
            # `verdicts` still lists what we just merged, and printing it would
            # report a landed PR as queued. A branch updated on this read is dropped
            # for the same reason — it is no longer stale — but only that PR: losing
            # the rest of the dump would hide the tick's "why is nothing else merging".
            just_updated = {v.number for v in updated}
            print_queue([v for v in verdicts if v.number not in just_updated], queued_only=False)
        else:
            print("`list` shows the current queue.")
        return EXIT_OK
    except QueueError as exc:
        print(f"merge_queue: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL


if __name__ == "__main__":
    raise SystemExit(main())

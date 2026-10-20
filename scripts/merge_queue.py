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
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

# The "what is not a review pass" rules (DIG-4631) live beside this script so
# the host CI producer applies the same rules. The module is imported by path,
# not by package, because `scripts/` is not a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_pass_filter as rpf

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
    #: The local-ci status that says the review was applied (DIG-3842). Required
    #: SUCCESS on the exact head the queue merges; "" switches the gate off for a
    #: repo whose CI does not post it (twelve-x, see the policy note).
    review_applied_context: str = "review-applied"
    review_applied_by_repo: Mapping[str, str] = field(default_factory=dict)

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

    def review_applied_for(self, repo: str) -> str:
        """The review-applied context this repo must report on its head, or "".

        An unlisted repo falls back to the default, so a new repo gets the gate
        rather than silently losing it; only an explicit "" entry switches it off.
        """
        if repo in self.review_applied_by_repo:
            return self.review_applied_by_repo[repo]
        return self.review_applied_context

    def for_repo(self, repo: str) -> Policy:
        """A copy whose `required_checks` are this repo's.

        Resolving once here rather than passing `repo` down to every gate is what
        keeps the resolved list and the *reported* list from diverging: `_gate_checks`
        and `_audit_body` both read `policy.required_checks`, so the check the merge
        depended on and the check the audit comment names cannot come from two places.
        """
        return replace(
            self,
            required_checks=self.required_for(repo),
            review_applied_context=self.review_applied_for(repo),
        )


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
        review_applied_context=str(defaults.get("review_applied_context", "review-applied")),
        review_applied_by_repo={
            str(repo): str(name)
            for repo, name in (raw.get("review_applied_context_by_repo") or {}).items()
        },
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
        # `body` carries the authoring seat's identity (see `_author_identity`).
        "number,title,body,headRefName,headRefOid,baseRefName,isDraft,mergeable,"
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

    A review whose verdict is CHANGES_REQUESTED is dropped too, whatever form the
    verdict takes (a formal review state, a `Verdict:` line under the in-session
    marker, or a power-pack `verdict=` field): it blocks, and it never counts.
    """
    author = str((pr.get("author") or {}).get("login") or "")
    kept: list[dict[str, Any]] = []
    for review in pr.get("reviews") or []:
        if not isinstance(review, dict):
            continue
        login = str((review.get("author") or {}).get("login") or "")
        if login and login == author:
            continue
        # A review that requests changes blocks (`_gate_review`); it is never also
        # the evidence that the PR was reviewed. Before #5863's follow-up a bot's
        # CHANGES_REQUESTED fed the REVIEW_BOTS hatch as a completed agent review.
        if _review_state(review) == "CHANGES_REQUESTED":
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
    # #5863 merged with review-applied green over an in-session review whose
    # latest verdict read CHANGES: the gate counted the pass and its threads but
    # never read what the pass concluded.
    reasons.extend(_reviewer_verdict_reasons(pr))
    return reasons


# --- each reviewer's latest verdict ------------------------------------------
#
# A review pass is evidence only if its conclusion is read. Every reviewer's
# latest verdict is taken in time order across formal reviews (humans and bots
# alike) and in-session review comments. A latest CHANGES_REQUESTED blocks until
# the same reviewer posts a later APPROVED or COMMENTED review, or the review is
# dismissed (GitHub reports a dismissed review with state DISMISSED). An
# in-session review is read from its `Verdict:` line, and only in a comment that
# carries the in-session marker, so ordinary prose never becomes a verdict.

IN_SESSION_REVIEW_MARKER = "<!-- in-session-review -->"
_IN_SESSION_VERDICT_RE = re.compile(
    r"^[\s>#*_]*verdict\s*[:=]\s*[*_`]*\s*(?P<word>[A-Za-z][A-Za-z_ -]*)", re.I | re.M
)
_BLOCKING_WORDS = ("changes", "request_changes", "changes_requested", "changes_needed", "block")
_APPROVING_WORDS = ("approve", "approved", "lgtm", "pass", "ship")
_REVIEW_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"})


def _reviewer_key(login: Any) -> str:
    """One key per reviewer: case-folded, `[bot]` suffix dropped (REST and
    `gh pr view` disagree on the suffix for the same bot)."""
    key = str(login or "").strip().lower()
    return key[: -len("[bot]")] if key.endswith("[bot]") else key


def _in_session_state(body: str) -> str:
    """CHANGES_REQUESTED / APPROVED / COMMENTED for an in-session review body."""
    m = _IN_SESSION_VERDICT_RE.search(body)
    if not m:
        return "COMMENTED"
    word = m.group("word").strip().lower().replace("-", "_").replace(" ", "_")
    if word.startswith(_BLOCKING_WORDS):
        return "CHANGES_REQUESTED"
    if word.startswith(_APPROVING_WORDS):
        return "APPROVED"
    return "COMMENTED"


def _review_events(pr: dict[str, Any]) -> list[tuple[str, int, str, str, str]]:
    """(at, seq, reviewer, state, where) for every readable review act, oldest first.

    `seq` keeps GitHub's own order for rows without a timestamp."""
    events: list[tuple[str, int, str, str, str]] = []
    seq = 0
    for review in pr.get("reviews") or []:
        seq += 1
        if not isinstance(review, Mapping):
            continue
        state = str(review.get("state") or "").upper()
        body = str(review.get("body") or "")
        if state == "COMMENTED" and IN_SESSION_REVIEW_MARKER in body:
            state = _in_session_state(body)
        if state not in _REVIEW_STATES:
            continue  # PENDING and unknown states are not a submitted verdict
        login = (review.get("author") or review.get("user") or {}).get("login")
        at = str(review.get("submittedAt") or review.get("submitted_at") or "")
        events.append(
            (
                at,
                seq,
                _seat_reviewer_key(login, body),
                state,
                f"review {review.get('id') or seq}{_seat_suffix(body)}",
            )
        )
    for comment in pr.get("comments") or []:
        seq += 1
        if not isinstance(comment, Mapping):
            continue
        body = str(comment.get("body") or "")
        if IN_SESSION_REVIEW_MARKER not in body:
            continue
        login = (comment.get("author") or comment.get("user") or {}).get("login")
        at = str(comment.get("createdAt") or comment.get("created_at") or "")
        events.append(
            (
                at,
                seq,
                _seat_reviewer_key(login, body),
                _in_session_state(body),
                f"in-session review comment {comment.get('id') or seq}{_seat_suffix(body)}",
            )
        )
    events.sort(key=lambda e: (e[0], e[1]))
    return events


def _reviewer_verdict_reasons(pr: dict[str, Any]) -> list[str]:
    """A refusal per reviewer whose latest verdict is CHANGES_REQUESTED."""
    latest: dict[str, tuple[str, str, str]] = {}
    for at, _seq, reviewer, state, where in _review_events(pr):
        latest[reviewer] = (state, where, at)
    return [
        f"review verdict: {reviewer.split(_SEAT_KEY_SEP)[0] or '?'}'s latest review ({where}"
        f"{' at ' + at if at else ''}) requests changes and no later approval, "
        "comment-review or dismissal from that reviewer has cleared it"
        for reviewer, (state, where, at) in sorted(latest.items())
        if state == "CHANGES_REQUESTED"
    ]


def _seat_reviewer_key(login: Any, body: str) -> str:
    """The reviewer a verdict belongs to: the login, narrowed by the seat it names.

    Every board seat posts as one GitHub login, so the login alone would let any
    seat's later approval (the author's included) clear another seat's change
    request. A verdict that names its seat (`_identity`) is keyed by login and
    seat; one that names none keys by login alone, as before, so an unnamed block
    is cleared only by an unnamed later verdict from that login.
    """
    seats = _identity(body).get("seat")
    key = _reviewer_key(login)
    return f"{key}{_SEAT_KEY_SEP}{','.join(sorted(seats))}" if seats else key


def _seat_suffix(body: str) -> str:
    seats = _identity(body).get("seat")
    return f" by seat {','.join(sorted(seats))}" if seats else ""


_SEAT_KEY_SEP = "\x1f"


# --- review evidence: never a change request, never the author's own seat ----
#
# Follow-up to #5863 (QA review monitor, 2026-10-20). Three ways a review record
# could still authorise a merge it should not:
#
# (a) A CHANGES_REQUESTED verdict was read by the verdict gate as a block, but the
#     very same comment or review was also handed to the coverage gate as evidence
#     that a review ran. A change request now only blocks; it is dropped from the
#     evidence wherever it appears (formal review, in-session `Verdict:` line, or
#     power-pack `verdict=` field).
# (b) Every board seat posts as `chrizefan`, so an in-session review comment on a
#     `chrizefan` PR could be the authoring session attesting its own work (the
#     DIG-4459 chat PRs were "reviewed" seconds after they were opened). The login
#     cannot tell seats apart, so the identity is read from what the seat writes:
#     a `<!-- dt-seat agent=<PAPERCLIP_AGENT_ID> run=<PAPERCLIP_RUN_ID>
#     session=<id> -->` marker, or `Paperclip-Agent-Id:` / `Paperclip-Seat:` /
#     `Paperclip-Run-Id:` / `Session-Id:` trailer lines, in the PR body and commit
#     messages (the author) and in the review comment (the reviewer). Same-login
#     review evidence counts only when it names a seat (or, for a PR authored
#     outside Paperclip, a session) that is provably not the author's. Unnamed is
#     not independent: it is refused, and the refusal says what to add.
# (c) `review-applied` is posted per commit. The queue now requires it SUCCESS on
#     the exact head it merges (`_gate_review_applied`); `merge_one` pins that
#     same head with `--match-head-commit`.

SEAT_MARKER = "dt-seat"
_SEAT_MARKER_RE = re.compile(r"<!--\s*dt-seat\b(?P<fields>[^>]*?)\s*-->", re.I)
_SEAT_FIELD_KINDS = {"agent": "seat", "seat": "seat", "run": "run", "session": "session"}
_SEAT_TRAILER_KINDS = {
    "paperclip-agent-id": "seat",
    "paperclip-agent": "seat",
    "paperclip-seat": "seat",
    "paperclip-run-id": "run",
    "session-id": "session",
}
_SEAT_TRAILER_RE = re.compile(
    r"^[ \t>*_-]*(?P<key>Paperclip-Agent-Id|Paperclip-Agent|Paperclip-Seat|Paperclip-Run-Id"
    r"|Session-Id)[*_`]*[ \t]*:[ \t]*[*_`]*[ \t]*(?P<value>[A-Za-z0-9][A-Za-z0-9._:/@-]*)",
    re.I | re.M,
)
_PLACEHOLDER_IDS = frozenset({"?", "-", "none", "null", "unknown", "n/a", "tbd"})


def _identity(text: str) -> dict[str, frozenset[str]]:
    """{kind: values} for the seat identity a body names; kinds: seat, session, run.

    The vocabulary lives in `review_pass_filter` (DIG-4631) so the merge queue
    and the host CI producer read one implementation of it.
    """
    return rpf.identity_from_text(text)


def _merge_identities(*ids: dict[str, frozenset[str]]) -> dict[str, frozenset[str]]:
    return rpf.merge_identities(*ids)


def _author_identity(pr: dict[str, Any]) -> dict[str, frozenset[str]]:
    """Every seat, session and run the PR's body and commits name as their author."""
    return rpf.author_identity(pr)


def _show(identity: dict[str, frozenset[str]]) -> str:
    return rpf.show_identity(identity)


def _not_independent(
    author: dict[str, frozenset[str]], reviewer: dict[str, frozenset[str]]
) -> str | None:
    """Why a same-login review cannot be shown to come from another seat, or None.

    The rule lives in `review_pass_filter` (DIG-4631) so the merge queue and
    the host CI producer apply one version of it.
    """
    return rpf.independence_reason(author, reviewer)


def _comment_verdict(body: str) -> str | None:
    """CHANGES_REQUESTED / APPROVED / COMMENTED for a review comment, or None.

    A power-pack marker's `verdict=` is read first, then the in-session marker's
    `Verdict:` line; a comment carrying neither is not a review verdict.
    """
    for marker in _MARKER_RE.finditer(body or ""):
        fields = {
            m.group("key").lower(): m.group("value")
            for m in _MARKER_FIELD_RE.finditer(marker.group("fields"))
        }
        verdict = _normalise_verdict(fields.get("verdict", ""))
        if verdict in BLOCKING_VERDICTS:
            return "CHANGES_REQUESTED"
        if verdict in READABLE_VERDICTS:
            return "APPROVED"
    if IN_SESSION_REVIEW_MARKER in (body or ""):
        return _in_session_state(body)
    return None


def _review_state(review: Mapping[str, Any]) -> str:
    """A formal review's effective state, reading a verdict carried in its body."""
    state = str(review.get("state") or "").upper()
    if state == "COMMENTED":
        return _comment_verdict(str(review.get("body") or "")) or state
    return state


def _evidence_comments(pr: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """(comments the coverage gate may score, why each dropped one was dropped).

    Dropped: any comment whose verdict is a change request (a), and any in-session
    review comment under the PR author's own login that does not prove it came
    from a different seat (b). Everything else passes through untouched, so the
    CodeRabbit and marker matching in check_review_coverage stays the one source
    of truth for what counts.
    """
    author_login = _reviewer_key((pr.get("author") or {}).get("login"))
    author_id: dict[str, frozenset[str]] | None = None
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    for comment in pr.get("comments") or []:
        if not isinstance(comment, Mapping):
            continue
        body = str(comment.get("body") or "")
        where = f"comment {comment.get('id') or comment.get('createdAt') or '?'}"
        if _comment_verdict(body) == "CHANGES_REQUESTED":
            dropped.append(f"{where} requests changes, which blocks and is never review evidence")
            continue
        if IN_SESSION_REVIEW_MARKER in body:
            login = _reviewer_key((comment.get("author") or comment.get("user") or {}).get("login"))
            if not login or login == author_login:
                if author_id is None:
                    author_id = _author_identity(pr)
                why = _not_independent(author_id, _identity(body))
                if why:
                    dropped.append(f"{where}: {why}")
                    continue
        kept.append(dict(comment))
    return kept, dropped


def _gate_review_applied(pr: dict[str, Any], policy: Policy, repo: str | None) -> list[str]:
    """`review-applied` must be SUCCESS on the exact head this merge would land.

    local-ci posts the status per commit, so a green verdict on an earlier push
    says nothing about the commits pushed after it. The row's rollup is read
    first (it is the head commit's); when a repo is given, the head's own combined
    status is then read by SHA and must name that same SHA, so a stale row or a
    moved head cannot carry an older green. `merge_one` pins the same SHA with
    `--match-head-commit`. Every read that fails refuses.
    """
    ctx = policy.review_applied_context
    if not ctx:
        return []
    head = str(pr.get("headRefOid") or "")
    if not head:
        return [f"'{ctx}': the row names no head SHA, so it cannot be checked on the merged tip"]
    entries = [e for e in _rollup(pr) if _check_name(e) == ctx]
    if not entries:
        return [
            f"'{ctx}' has not reported on the head {head[:12]}; a {ctx} verdict on an "
            "earlier commit does not cover the commits pushed after it"
        ]
    states = sorted({str(e.get("conclusion") or e.get("state") or "?").upper() for e in entries})
    if states != ["SUCCESS"]:
        return [f"'{ctx}' is {', '.join(states)} on the head {head[:12]}"]
    if repo is None:
        return []
    try:
        data = _gh_json("api", f"repos/{repo}/commits/{head}/status?per_page=100")
    except (QueueError, ValueError, OSError):
        return [f"'{ctx}': the head {head[:12]}'s statuses could not be read"]
    if not isinstance(data, dict) or str(data.get("sha") or "") != head:
        got = str((data or {}).get("sha") or "") if isinstance(data, dict) else ""
        return [
            f"'{ctx}': the status read for {head[:12]} came back for "
            f"{got[:12] or 'no commit'}, so it is not evidence about the merged tip"
        ]
    on_head = [
        s
        for s in (data.get("statuses") or [])
        if isinstance(s, Mapping) and s.get("context") == ctx
    ]
    if not on_head:
        return [f"'{ctx}' has not reported on the head {head[:12]}"]
    head_states = sorted({str(s.get("state") or "?").lower() for s in on_head})
    if head_states != ["success"]:
        return [f"'{ctx}' is {', '.join(head_states)} on the head {head[:12]}"]
    return []


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
        nodes {
          isResolved
          isOutdated
          path
          resolvedBy { login }
          comments(first: 3) { nodes { author { login } body createdAt } }
        }
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
    return [_normalise_thread(node) for node in nodes]


def _normalise_thread(node: Any) -> Any:
    """A thread node with the resolver and the replies in the shape the filters read."""
    if not isinstance(node, Mapping):
        return node
    out = dict(node)
    resolved_by = node.get("resolvedBy")
    if isinstance(resolved_by, Mapping):
        out["resolved_by_login"] = str(resolved_by.get("login") or "")
    comments = node.get("comments")
    listed = comments.get("nodes") or [] if isinstance(comments, Mapping) else (comments or [])
    out["comments"] = [
        {
            "author_login": str((c.get("author") or {}).get("login") or "")
            if isinstance(c.get("author"), Mapping)
            else str(c.get("author") or ""),
            "body": str(c.get("body") or ""),
            "created_at": str(c.get("createdAt") or ""),
        }
        for c in listed
        if isinstance(c, Mapping)
    ]
    return out


def _open_threads(
    threads: list[Any], pr: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Threads that are not addressed: unresolved, or resolved by the PR's own author.

    Every seat posts under one GitHub login, so a thread resolved under the
    author's own login is not evidence that the reviewer was answered. Such a
    thread stays open (DIG-4631).
    """
    author_login = ""
    author_identity: dict[str, frozenset[str]] = {}
    if isinstance(pr, Mapping):
        author = pr.get("author")
        if isinstance(author, Mapping):
            author_login = str(author.get("login") or "")
        author_identity = rpf.author_identity(pr)
    out: list[dict[str, Any]] = []
    for t in threads:
        if not isinstance(t, dict):
            continue
        if t.get("isOutdated"):
            continue
        if t.get("isResolved") and not rpf.thread_resolved_by_author(
            t, author_login, author_identity
        ):
            continue
        out.append(t)
    return out


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
    open_threads = _open_threads(threads if isinstance(threads, list) else [], pr)
    if not open_threads:
        return []
    paths = sorted({str(t.get("path") or "?") for t in open_threads})
    shown = ", ".join(paths[:3]) + (f" and {len(paths) - 3} more" if len(paths) > 3 else "")
    author = pr.get("author")
    author_login = str(author.get("login") or "") if isinstance(author, Mapping) else ""
    author_identity = rpf.author_identity(pr)
    author_resolved = sum(
        1
        for t in open_threads
        if t.get("isResolved")
        and rpf.thread_resolved_by_author(t, author_login, author_identity)
    )
    extra = (
        f"; {author_resolved} of them were resolved by the PR's own author, which does "
        "not show the reviewer was answered"
        if author_resolved
        else ""
    )
    return [
        f"review comments not addressed: {len(open_threads)} unresolved review "
        f"thread(s) on the current code ({shown}){extra}; resolve them, or push the fix "
        "that makes them outdated"
    ]


def _push_times(pr: dict[str, Any]) -> dict[str, str]:
    """{commit oid: the time that commit was pushed} from the PR's commit list."""
    pushes: dict[str, str] = {}
    for commit in pr.get("commits") or []:
        if not isinstance(commit, Mapping):
            continue
        oid = str(commit.get("oid") or "")
        at = str(commit.get("committedDate") or "")
        if oid and at:
            pushes[oid] = at
    return pushes


def _review_evidence_items(pr: dict[str, Any]) -> list[dict[str, Any]]:
    """Every review and comment on the PR, as {body, at, commit, where} items."""
    items: list[dict[str, Any]] = []
    for review in pr.get("reviews") or []:
        if not isinstance(review, Mapping):
            continue
        body = str(review.get("body") or "")
        if not body.strip():
            continue
        commit = review.get("commit")
        oid = str(commit.get("oid") or "") if isinstance(commit, Mapping) else ""
        items.append(
            {
                "body": body,
                "at": str(review.get("submittedAt") or review.get("submitted_at") or ""),
                "commit": oid,
                "where": "review",
            }
        )
    for comment in pr.get("comments") or []:
        if not isinstance(comment, Mapping):
            continue
        body = str(comment.get("body") or "")
        if not body.strip():
            continue
        items.append(
            {
                "body": body,
                "at": str(comment.get("createdAt") or comment.get("created_at") or ""),
                "commit": "",
                "where": "comment",
            }
        )
    return items


def _gate_review_pass_evidence(
    pr: dict[str, Any], corpus: list[Mapping[str, Any]] | None = None
) -> list[str]:
    """The review evidence has to survive the DIG-4631 filters.

    Two classes are refused: a review posted within 60 s of the push it claims
    to cover, and a review whose text repeats a review on another PR. When every
    piece of evidence on the PR falls in one of those classes, the PR has no
    review pass and the queue says why.
    """
    items = _review_evidence_items(pr)
    if not items:
        return []
    pushes = _push_times(pr)
    number = pr.get("number")
    survivors: list[dict[str, Any]] = []
    refusals: list[str] = []
    for item in items:
        pushed = pushes.get(item["commit"]) if item["commit"] else None
        if pushed and rpf.review_too_close_to_push(item["at"], pushed):
            gap = int(
                (rpf.parse_ts(item["at"]) or 0) - (rpf.parse_ts(pushed) or 0)
            )
            refusals.append(
                f"the {item['where']} was posted {gap}s after the push it claims to cover"
            )
            continue
        copies = rpf.duplicate_reviews(
            rpf.normalise_review_text(item["body"]), number, corpus
        )
        if copies:
            refusals.append(
                f"the {item['where']} repeats the review on #{copies[0].get('pr')} "
                f"(text similarity {copies[0].get('ratio')})"
            )
            continue
        survivors.append(item)
    if survivors or not refusals:
        return []
    return ["review evidence is not a review pass: " + "; ".join(refusals[:2]) + " (DIG-4631)"]


def _review_corpus(prs: list[dict[str, Any]]) -> list[Mapping[str, Any]]:
    """Every review seen on the queued PRs, plus the rolling store.

    A review copied from another PR is only recognisable against reviews seen
    elsewhere, so the queue keeps a rolling corpus of the review text it has
    seen (DIG-4631). The corpus is a cache of public review text and decides
    nothing on its own.
    """
    entries: list[Mapping[str, Any]] = list(rpf.load_corpus())
    for pr in prs:
        texts = [
            (item["at"], item["body"])
            for item in _review_evidence_items(pr)
            if item["where"] == "review"
        ]
        if not texts:
            continue
        author = pr.get("author")
        login = str(author.get("login") or "") if isinstance(author, Mapping) else ""
        entries.extend(rpf.corpus_entries(pr.get("number"), texts, login=login))
    return entries


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


def _review_coverage(pr: dict[str, Any], repo: str | None) -> tuple[list[str], str]:
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
    state: dict[str, Any] = {
        "labels": labels,
        "approvals": [],
        "bugbot": None,
        "title": str(pr.get("title") or ""),
        "owner_review": None,
        "agent_tool": [],
        "agent_review": None,
    }
    evidence, dropped = _evidence_comments(
        {**pr, "comments": comments if isinstance(comments, list) else []}
    )
    crc._apply_reviews_checks_comments(
        state,
        reviews=_evidence_reviews(pr),
        checks=_rollup(pr),
        comments=evidence,
    )
    reviewed, why = crc.verdict_for(state)
    if reviewed:
        return [], why
    not_counted = ""
    if dropped:
        shown = "; ".join(dropped[:3]) + (
            f"; and {len(dropped) - 3} more" if len(dropped) > 3 else ""
        )
        not_counted = f". Not counted as review evidence: {shown}"
    return [
        f"review coverage: {why} — the queue needs a review pass that left its "
        "findings on the PR, the same evidence scripts/check_review_coverage.py "
        "enforces at promotion (completed Bot run, a reviewer bot such as "
        "CodeRabbit or Copilot, an in-session review from a seat other than the "
        "author's with its findings comment, an approval, or reviewed:owner)"
        f"{not_counted}"
    ], ""


def evaluate(
    pr: dict[str, Any],
    policy: Policy,
    *,
    base: str,
    acting_role: str,
    repo: str | None = None,
    corpus: list[Mapping[str, Any]] | None = None,
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
    coverage_reasons, review_evidence = _review_coverage(pr, repo)
    reasons.extend(coverage_reasons)
    # The review evidence itself has to be a real review pass (DIG-4631): not a
    # copy of another PR's review, and not a review posted seconds after the
    # push it claims to cover.
    reasons.extend(_gate_review_pass_evidence(pr, corpus))
    # review-applied on the exact tip. The rollup half is free; the by-SHA read is
    # one REST call, so it is spent only on a PR every earlier gate passed.
    reasons.extend(_gate_review_applied(pr, policy, repo if not reasons else None))
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
    corpus = _review_corpus(prs)
    verdicts = [
        evaluate(pr, policy, base=base, acting_role=acting_role, repo=repo, corpus=corpus)
        for pr in prs
    ]
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
        + (
            f"- `{policy.review_applied_context}`: SUCCESS on `{verdict.head_sha[:12]}`, "
            "the merged head\n"
            if policy.review_applied_context
            else ""
        )
        + f"- checks reported: {len(verdict.checks)}\n\n"
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
    stale = [v for v in verdicts if v.stale_base_only]
    if stale and not queued_only:
        print(
            f"\nstale ({len(stale)}) — green against a base we have left, and counted "
            "below as not eligible; nobody has to fix these, a run tick updates one "
            "branch, oldest first:"
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
            for candidate in [v for v in verdicts if v.stale_base_only][: args.max_updates]:
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

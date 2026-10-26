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
import atexit
import datetime
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
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

# --- CI provenance (DIG-4794) -------------------------------------------------
#
# `local-ci` is a commit status, and GitHub's own documentation says what that is
# worth: "any person or integration with write permissions can set the state of
# any status check". Both repositories the queue manages name `local-ci` as their
# required check, and neither has a server-side branch protection on the private
# plan, so this queue is the only gate between a seat and a merge it approved
# itself.
#
# The gate therefore asks a second question. Not "is the status green" but "which
# build made it green, and did that build check this commit". The CI worker runs
# inside Woodpecker, so the status it posts names the build that ran it
# (`target_url`), and the queue reads that build back from the Woodpecker API
# before it counts the status as evidence. A status with no URL, a URL on another
# host, a build that is not there, a build that did not succeed, a build that did
# not run this repository's check, and a build that ran another commit are all the
# same answer: no evidence.
#
# The gate ships in shadow mode, because the launcher pipeline that runs the check
# is bound to the launcher's own commit rather than to the pull request head, so a
# strict commit comparison refuses every pull request until the launcher runs one
# build per pull request. DIG-4809 owns that window and the switch to `enforce`.

#: The three modes. `off` is today's behaviour: the status is trusted as written.
PROVENANCE_OFF = "off"
#: Log what the gate would have refused, and merge anyway.
PROVENANCE_SHADOW = "shadow"
#: Refuse the pull request when the build cannot be verified.
PROVENANCE_ENFORCE = "enforce"
PROVENANCE_MODES: tuple[str, ...] = (PROVENANCE_OFF, PROVENANCE_SHADOW, PROVENANCE_ENFORCE)

#: The three ways the comparison between the build's own commit and the pull
#: request head can be applied.
#:
#: The launcher pipeline that runs the check is bound to the commit its own
#: repository checked out - the launcher's `main` commit, never the pull request
#: head - so that comparison can never succeed while the launcher runs one
#: build for the whole repository (DIG-4809). `enforce` is today's behaviour: a
#: build that ran another commit is a refusal. `shadow` measures it: the
#: mismatch is written to the log and the queue merges anyway. `off` does not
#: look at the commit at all.
#:
#: The comparison is the only thing that ties a build to a pull request head,
#: so it cannot be softened on its own: a queue that no longer compares the
#: commit and still trusts a `local-ci` row would accept a row that says
#: nothing about this head. The trusted receipt is what replaces it - a status
#: written by the CI's own GitHub App installation, on the head commit, which
#: no seat can write. A policy that softens the comparison without asking for
#: that receipt is refused when the policy file is read.
COMMIT_MATCH_ENFORCE = "enforce"
COMMIT_MATCH_SHADOW = "shadow"
COMMIT_MATCH_OFF = "off"
COMMIT_MATCH_MODES: tuple[str, ...] = (COMMIT_MATCH_ENFORCE, COMMIT_MATCH_SHADOW, COMMIT_MATCH_OFF)

#: DIG-4809 names this switch: the environment wins over the policy file, so the
#: mode can be changed on the running host without a code change.
PROVENANCE_MODE_ENV = "MQ_CI_PROVENANCE"

#: The rollback flag, shared with the broker and the seat shim (DIG-4805).
#: Chris writes it, as root, into the account that owns the broker: a seat can
#: read it and cannot write it, so no seat can turn the broker off.
AUTH_MODE_FLAG_PATH = Path("/Users/_dtbroker/.config/digithings/github-auth-mode")
#: The value that switches the broker off and restores today's behaviour.
AUTH_MODE_HOST = "host"

#: The same for the commit comparison: the environment wins over the file.
COMMIT_MATCH_ENV = "MQ_CI_COMMIT_MATCH"
#: Where the shadow log goes. The launchd job's own error log keeps the line too.
PROVENANCE_LOG_ENV = "MQ_CI_PROVENANCE_LOG"
PROVENANCE_LOG_PATH = Path.home() / ".config" / "digithings" / "merge-queue" / "ci-provenance.log"

#: The path segments that say "this is a pipeline". Woodpecker's own pipeline
#: link is a web link and its shape has changed across versions - 3.19 documents
#: `CI_PIPELINE_URL` as `<system url>/repos/<id>/pipeline/<number>`, while older
#: builds and the API use `/api/repos/<id>/pipelines/<number>` and the web UI
#: uses `/repo/<owner>/<name>/pipelines/<number>` - so the path is read by
#: shape rather than matched against one exact form.
_PIPELINE_PATH_WORDS: frozenset[str] = frozenset({"pipelines", "pipeline"})

#: A build in one of these states has not finished, so nothing it says about a
#: step is final yet. The launcher pipeline runs both repositories' checks side
#: by side, so the build's own status is not decisive - one repository's check
#: can fail while the other one passes - and the step that answers for the
#: repository is. What the build's status does decide is whether the run is
#: over: a step can be green while the rest of the build is still going.
#:
#: The list is Woodpecker's own vocabulary (3.19): `created`, `pending`,
#: `running`, `blocked` and `skipped` are the states in which a build has not
#: reached a verdict. The states that end a build badly - `failure`, `killed`,
#: `canceled`, `error`, `declined` - are caught by the step requirement instead,
#: because the build as a whole is not what answers for a repository.
_PIPELINE_UNFINISHED_STATES: frozenset[str] = frozenset(
    {"created", "pending", "running", "started", "waiting", "blocked", "skipped"}
)

#: How long the queue waits for one Woodpecker read. The queue evaluates up to
#: 200 pull requests per tick and the launchd job fires every three minutes, so
#: a read that blocks for its full timeout can outlast the tick. Shadow mode is
#: given less: there the read is a measurement, not a verdict.
PROVENANCE_READ_TIMEOUT = 5.0
PROVENANCE_READ_TIMEOUT_SHADOW = 2.0
#: The read of the commit statuses, which is a GitHub call rather than a call
#: to the deployment's own network. It gets its own limit because a read that
#: hangs is a tick that hangs, and the queue reads one commit per pull request.
PROVENANCE_STATUS_TIMEOUT = 10.0

#: How many times one URL is read before the read is called a failed read. A
#: dropped connection says nothing about the build behind the URL, so the read
#: is tried again: one dropped connection used to refuse a pull request on a
#: transport fact that had nothing to do with the build. The read is a GET, so
#: the question is the same every time, and a question that was not answered
#: is not an answer.
PROVENANCE_READ_ATTEMPTS = 3

#: The pause before the next attempt, in seconds. The pause is short because
#: the queue has a tick to finish, and it is there so the second attempt does
#: not arrive while the first one is still being answered.
PROVENANCE_RETRY_BACKOFF = 0.5

#: The whole cost of one URL, attempts and pauses together. The pause before
#: an attempt and the attempt itself both happen inside it, so one path costs
#: the budget once and not once per attempt. It is a deadline and not only a
#: sum of timeouts: the body is read one socket read at a time and the read
#: gives up when the deadline has passed, so a server that answers the headers
#: and then trickles the body cannot hold the read open past the budget. It is
#: the budget of ONE URL read, not of the tick.
PROVENANCE_READ_BUDGET = 20.0

#: How long a host that could not be read is remembered, in seconds. The queue
#: asks the same host about every pull request of the tick, so a host that
#: could not be read is asked once more - briefly - and the rest of the tick
#: is answered from the memory instead of waiting for a host that is not
#: answering. The memory does not outlive its minute: after it the host is
#: read again with the whole budget.
PROVENANCE_HOST_COOLDOWN = 60.0

#: How long the host is asked again after it did not answer, in seconds. The
#: ask is one attempt and not three, and it is brief: the host either answers
#: or it does not, and a host that was asleep for a moment answers at once.
#: The queue asks the host once per pull request, so this is the cost of a
#: dead host per pull request, and it has to stay small: the tick has an
#: interval to keep.
PROVENANCE_REPROBE_TIMEOUT = 2.0

#: The provenance log grows by one line per pull request per tick, so it is
#: capped: the oldest file is dropped when the log passes this size.
PROVENANCE_LOG_MAX_BYTES = 1_000_000

#: Where the shadow log's index goes. The index is what keeps the log readable.
#: The queue looks at every open pull request on every tick, so a log with one
#: line per refusal per tick grows by tens of thousands of lines a day and the
#: 48 hour window stops being a file a human can read. The index remembers which
#: refusals the log already holds, so a refusal that repeats says so in the
#: index instead of writing the same line again.
PROVENANCE_INDEX_ENV = "MQ_CI_PROVENANCE_INDEX"
PROVENANCE_INDEX_PATH = (
    Path.home() / ".config" / "digithings" / "merge-queue" / "ci-provenance.index.json"
)

#: The index is a memory of the log, not a log of its own: it is capped, and an
#: entry that has not been seen for this long is dropped, so a window that ends
#: does not leave the index growing forever.
PROVENANCE_INDEX_MAX_ENTRIES = 2000
PROVENANCE_INDEX_MAX_AGE_DAYS = 14

#: The token and the build reads are read once per queue run, not once per pull
#: request.
_TOKEN_CACHE: dict[tuple[str, str], str] = {}
_READ_CACHE: dict[str, tuple[int, Any]] = {}
#: The hosts that could not be read, with the answer they gave and the moment
#: they gave it. The key is the scheme and the host, because two services on
#: one machine are two hosts and one of them can answer while the other does
#: not.
_HOST_FAILURE: dict[str, tuple[float, tuple[int, Any]]] = {}
#: The allowed hosts, read once per queue run from the deployment's own files.
_HOST_CACHE: dict[tuple[Any, ...], tuple[tuple[str, ...], str]] = {}
#: The log index, by the path it is written to.
_INDEX_CACHE: dict[str, dict[str, Any]] = {}
#: The lines the provenance log holds, by the path it is written to, with the
#: size of the file they were read from.
_LOG_CACHE: dict[str, tuple[int, set[str]]] = {}

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


#: The three ways the reviewer-independence gate can run. `off` reads no
#: provenance at all. `shadow` and `enforce` both refuse a marker the gate
#: dropped; `shadow` additionally records the refusal (and what the row would
#: have said with every comment counted) in the shadow log, while `enforce`
#: decides without it. DIG-4809 named the two-step rollout: 48 hours of shadow,
#: then a separate small PR that flips the switch to `enforce`. The flip shipped
#: in DIG-5220 (22 Oct 2026), and the same change closed the shadow loophole:
#: #6277 and #6197 merged while an author-lane write-up stood in for the
#: non-author review, because shadow merged what it had just measured.
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
    #: Where the answers outlive one tick. Empty means the reader keeps them in
    #: memory only, which is what every test that builds its own config wants:
    #: a test must not write the live queue's cache. The policy loader fills
    #: this in with `PROVENANCE_CACHE_PATH_DEFAULT`.
    cache_path: str = ""


def _effective_mode(cfg: ReviewIndependence) -> str:
    """The mode this gate runs in: the env var wins over the policy file."""
    raw = os.environ.get("MQ_REVIEW_INDEPENDENCE")
    if raw is None:
        mode = str(cfg.mode or "off").strip().lower()
        return mode if mode in REVIEW_INDEPENDENCE_MODES else "enforce"
    mode = raw.strip().lower()
    return mode if mode in REVIEW_INDEPENDENCE_MODES else "enforce"


@dataclass(frozen=True)
class TrustedReceipt:
    """The receipt a seat cannot write: a status written by a known CI writer.

    A commit status is worth exactly what its writer is worth: "any person or
    integration with write permissions can set the state of any status check"
    (GitHub's commit status documentation). The `local-ci` row is written with a
    user token, so it is a statement - anybody with a token can write it, and
    the queue cannot tell that statement from the CI's own.

    A row written by the GitHub App installation is a receipt. The app's token
    is the CI's own and nobody else's, so a row it wrote on a commit says that
    the CI ran on that commit. That is what binds a check to a pull request
    head, which the build's own `commit` field cannot do while the launcher
    runs one build for a whole repository.

    `creators` are the logins allowed to write the receipt. A `Bot` login is
    the shape an app installation writes under; a human login in that list
    would make the receipt forgeable again, so the list is the trust decision
    and it is read from the policy file rather than guessed.
    """

    #: The status context the trusted receipt is written under.
    context: str = ""
    #: The logins allowed to write the trusted receipt.
    creators: tuple[str, ...] = ()
    #: Whether the queue asks for a receipt at all. A policy that does not ask
    #: for one does not read the status list: the chain is switched on by the
    #: policy change that comes with the CI's own installation token.
    required: bool = False


@dataclass(frozen=True)
class CiProvenance:
    """How the queue decides that a `local-ci` status came from a real build.

    `woodpecker_repos` maps a GitHub repository to the numeric Woodpecker
    repository that runs its check, `woodpecker_names` gives that repository's
    `owner/name` so a URL in the web shape can be resolved, and `steps` names the
    step inside the build that answers for that repository. The step is what
    binds a build to a repository: the launcher pipeline runs the digithings check
    and the twelve-x check side by side, so the pipeline on its own says nothing
    about which repository it answered for.

    Two of these settings are deployment facts rather than choices, so they are
    read rather than written down: the hosts a build link may name come from the
    deployment's own configuration (`host_files`, `host_url_keys`), and the
    numeric repository id comes from the repository's name (`woodpecker_repo_names`)
    resolved against the Woodpecker API. A file that carries an address that has
    moved, or an id that a recreated repository has changed, is how a gate ends
    up refusing every pull request or reading the wrong repository's build.
    """

    mode: str = PROVENANCE_OFF
    #: Hosts a build URL may name. Empty means "any host", which is not a setting
    #: worth shipping: the point of the check is that the URL points at our
    #: Woodpecker and nowhere else. This list is the part that never changes -
    #: the addresses the deployment actually uses are read from the deployment's
    #: own configuration, so a change of local IP is not a change of this file.
    hosts: tuple[str, ...] = ()
    #: Files the deployment's own addresses are read from, as `KEY=value` lines.
    #: The queue reads only the keys named in `host_url_keys`, so pointing this
    #: at a file that holds other secrets is safe.
    host_files: tuple[str, ...] = ()
    #: The keys in `host_files` whose values are the deployment's URLs. The
    #: host and port of each URL are hosts a build link may name.
    host_url_keys: tuple[str, ...] = ()
    #: Whether the deployment configuration must be readable for the gate to
    #: have an answer. Without it a stale allow-list is trusted silently, and a
    #: stale allow-list under `enforce` refuses every pull request.
    require_config: bool = False
    #: The environment variable that carries the Woodpecker API token.
    token_env: str = "WOODPECKER_TOKEN"
    #: A file to read the token from when the environment does not carry it. The
    #: value never leaves the file: the queue uses it and forgets it.
    token_file: str = ""
    #: The status context the gate reads.
    context: str = "local-ci"
    woodpecker_repos: Mapping[str, str] = field(default_factory=dict)
    woodpecker_names: Mapping[str, str] = field(default_factory=dict)
    #: The Woodpecker repository that runs a repository's check, named as
    #: `owner/name`. The numeric id is resolved from this name at check time, so
    #: a repository that is recreated under a new id does not make the gate read
    #: the wrong repository.
    woodpecker_repo_names: Mapping[str, str] = field(default_factory=dict)
    steps: Mapping[str, str] = field(default_factory=dict)
    #: The receipt the queue trusts in addition to the build check. Empty means
    #: no receipt is asked for, which is today's state: the CI worker writes the
    #: app row only when it holds an app installation token, and it does not
    #: hold one yet (DIG-4803, DIG-4809).
    trusted_receipt: TrustedReceipt = field(default_factory=TrustedReceipt)
    #: How the comparison between the build's commit and the head is applied.
    commit_match: str = COMMIT_MATCH_ENFORCE


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
    ci_provenance: CiProvenance = field(default_factory=CiProvenance)
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
    #: A fact the queue could not read, so it could not judge — not a gate the PR
    #: failed. It is deliberately not in `reasons`: a gate is a statement about the
    #: branch, and this is a statement about the API. The handback poster keys its
    #: comment on `reasons`, so a transient that appeared there re-armed the poster
    #: every other tick (DIG-5573, 42 handbacks on #6418 in 29 h). Such a PR is not
    #: eligible — an unread gate is not a cleared gate — it is skipped this tick.
    deferred: str = ""

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
        ci_provenance=_load_ci_provenance(raw.get("ci_provenance"), path),
        review_independence=_load_review_independence(raw, path),
    )


def _load_ci_provenance(raw: Mapping[str, Any] | None, path: Path) -> CiProvenance:
    """Read the `ci_provenance` block of the policy file.

    No block at all means no gate: a policy file written before this gate
    existed must still load, and the gate is off until somebody writes the
    block. A block without a mode means the gate is wanted but nobody has
    chosen a mode yet, and that is `shadow` - the mode that measures without
    refusing - rather than `off`, which would turn the gate off because a key
    was left out.

    A mode that is not one of the three names is refused here rather than
    defaulted: this switch decides whether the queue trusts a status, and a
    misspelled mode that silently meant "off" would turn the gate off without
    anybody deciding to.
    """
    if raw is None:
        return CiProvenance()
    mode = str(raw.get("mode") or PROVENANCE_SHADOW)
    if mode not in PROVENANCE_MODES:
        raise QueueError(
            f"{path}: ci_provenance.mode is {mode!r}; it must be one of "
            f"{', '.join(PROVENANCE_MODES)}"
        )
    hosts_raw = raw.get("hosts")
    if isinstance(hosts_raw, str) or (
        hosts_raw is not None and not isinstance(hosts_raw, list)
    ):
        raise QueueError(
            f"{path}: ci_provenance.hosts must be a list of host names, not a string"
        )
    for key in ("host_files", "host_url_keys"):
        value = raw.get(key)
        if isinstance(value, str) or (value is not None and not isinstance(value, list)):
            raise QueueError(
                f"{path}: ci_provenance.{key} must be a list, not a string"
            )
    require_config = raw.get("require_config")
    if require_config is not None and not isinstance(require_config, bool):
        raise QueueError(
            f"{path}: ci_provenance.require_config must be true or false"
        )
    commit_match = str(raw.get("commit_match") or COMMIT_MATCH_ENFORCE).strip().lower()
    if commit_match not in COMMIT_MATCH_MODES:
        raise QueueError(
            f"{path}: ci_provenance.commit_match is {commit_match!r}; it must be one of "
            f"{', '.join(COMMIT_MATCH_MODES)}"
        )
    receipt = _load_trusted_receipt(raw.get("trusted_receipt"), path)
    if commit_match != COMMIT_MATCH_ENFORCE and not receipt.required:
        # The commit comparison is the only thing that ties a build to a pull
        # request head, and it cannot succeed while the launcher runs one build
        # for a whole repository. A policy that softens it without asking for a
        # trusted receipt would leave the queue trusting a row that says nothing
        # about this head - so the policy file is refused rather than loaded.
        raise QueueError(
            f"{path}: ci_provenance.commit_match is {commit_match!r}, so the queue needs "
            "a trusted receipt to bind a status to the head commit, but "
            "ci_provenance.trusted_receipt does not require one"
        )
    return CiProvenance(
        mode=mode,
        hosts=tuple(str(host) for host in (hosts_raw or [])),
        host_files=tuple(str(item) for item in (raw.get("host_files") or [])),
        host_url_keys=tuple(str(item) for item in (raw.get("host_url_keys") or [])),
        require_config=bool(require_config),
        token_env=str(raw.get("token_env") or "WOODPECKER_TOKEN"),
        token_file=str(raw.get("token_file") or ""),
        context=str(raw.get("context") or "local-ci"),
        woodpecker_repos={
            str(repo): str(repo_id)
            for repo, repo_id in (raw.get("woodpecker_repos") or {}).items()
        },
        woodpecker_names={
            str(repo_id): str(name)
            for repo_id, name in (raw.get("woodpecker_names") or {}).items()
        },
        woodpecker_repo_names={
            str(repo): str(name)
            for repo, name in (raw.get("woodpecker_repo_names") or {}).items()
        },
        steps={str(repo): str(step) for repo, step in (raw.get("steps") or {}).items()},
        trusted_receipt=receipt,
        commit_match=commit_match,
    )


def _load_trusted_receipt(raw: Any, path: Path) -> TrustedReceipt:
    """Read the `trusted_receipt` block of the policy file.

    No block at all means no receipt is asked for: the CI worker writes the app
    row only when it holds an app installation token, and it does not hold one
    yet, so a policy that demanded the receipt today would refuse every pull
    request for a reason nobody could fix.

    A block that is present but incomplete is refused rather than ignored. A
    receipt with no context names nothing, and a receipt with no trusted
    writer is a receipt anybody can write - the two failures of this gate
    would come back as a queue that trusts the wrong thing.
    """
    if raw is None:
        return TrustedReceipt()
    if not isinstance(raw, Mapping):
        raise QueueError(f"{path}: ci_provenance.trusted_receipt must be an object")
    context = str(raw.get("context") or "").strip()
    creators_raw = raw.get("creators")
    if isinstance(creators_raw, str) or (
        creators_raw is not None and not isinstance(creators_raw, list)
    ):
        raise QueueError(
            f"{path}: ci_provenance.trusted_receipt.creators must be a list of logins, "
            "not a string"
        )
    creators = tuple(
        str(login).strip() for login in (creators_raw or []) if str(login).strip()
    )
    require = raw.get("require")
    if require is not None and not isinstance(require, bool):
        raise QueueError(
            f"{path}: ci_provenance.trusted_receipt.require must be true or false"
        )
    # A block with no `require` key at all means the receipt is required. That
    # is the fail-closed direction: a hand edit that drops the key must not
    # turn a security gate off. The price is a loud refusal of every pull
    # request until the CI writes a receipt, so the key is written down in the
    # policy note and in docs/MERGE_QUEUE.md and the rule is pinned by a test.
    required = True if require is None else bool(require)
    if required and (not context or not creators):
        raise QueueError(
            f"{path}: ci_provenance.trusted_receipt must name a context and at least one "
            "creator when it is required"
        )
    return TrustedReceipt(context=context, creators=creators, required=required)


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
        cache_path=str(block.get("cache_path") or PROVENANCE_CACHE_PATH_DEFAULT),
    )


def _gh_json(*args: str, timeout: float | None = None) -> Any:
    try:
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise QueueError(
            f"gh {' '.join(args[:2])} timed out after {timeout} seconds "
            "(retryable transport error; retry the read)"
        ) from exc
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


@dataclass(frozen=True)
class Provenance:
    """The outcome of reading one status as evidence of a build.

    `reason` says what is wrong in words that do not change from tick to tick.
    The live driver keys its handback comment on the reason text, so a reason
    that carried the build's number would post a fresh comment on the pull
    request every time the CI ran. `detail` holds the volatile part - the build
    number, the shas, the URL - and it goes to the log, never to the verdict.

    `measured` is a condition that was found and deliberately not refused: the
    commit comparison in `shadow` mode finds a build that ran another commit
    and writes it down instead of blocking on it. It is the same kind of text
    as `reason` and it goes to the log under its own verb, so a measurement is
    never read as a verdict.
    """

    ok: bool
    reason: str
    detail: str = ""
    target_url: str = ""
    measured: str = ""


def commit_match_mode(policy: Policy) -> str:
    """How the build's commit is compared with the head. The environment wins.

    An unreadable value is read as `enforce`, not as `off`: a typo in the
    switch that decides what the queue trusts must not silence it.
    """
    raw = str(os.environ.get(COMMIT_MATCH_ENV) or "").strip().lower()
    if not raw:
        return policy.ci_provenance.commit_match
    if raw not in COMMIT_MATCH_MODES:
        return COMMIT_MATCH_ENFORCE
    return raw


def _rollback_is_host() -> bool:
    """True when Chris has switched the broker off.

    The flag lives in the account that owns the broker, in a file a seat can
    read and cannot write. An unreadable flag, or one that says something
    else, is not `host`: the flag lowers a gate and never raises one, so a
    switch that cannot be read leaves the gate where the policy put it.
    """
    try:
        raw = AUTH_MODE_FLAG_PATH.read_text(encoding="utf-8").strip().lower()
    except (OSError, UnicodeDecodeError):
        return False
    return raw == AUTH_MODE_HOST


def provenance_mode(policy: Policy) -> str:
    """The mode in force. The environment wins over the policy file.

    An unreadable value is treated as `enforce`, not as `off`: a typo in the
    switch that decides whether the queue trusts a status must not silence the
    gate. `off` has to be spelled correctly to switch it off.

    The rollback flag (DIG-4805) has the last word, and it can only lower
    the gate: `host` puts an enforcing gate back into shadow, because the
    trusted receipt this gate checks is written by the broker, and with the
    broker off there is nothing to enforce against.
    """
    raw = str(os.environ.get(PROVENANCE_MODE_ENV) or "").strip().lower()
    if not raw:
        mode = policy.ci_provenance.mode
    elif raw not in PROVENANCE_MODES:
        mode = PROVENANCE_ENFORCE
    else:
        mode = raw
    if mode == PROVENANCE_ENFORCE and _rollback_is_host():
        return PROVENANCE_SHADOW
    return mode


def _newest_status(entries: list[dict[str, Any]], context: str) -> dict[str, Any] | None:
    """The newest status reported under one context.

    The rollup carries one row per context, but a status posted twice can arrive
    twice, and the newest row is the one that answers for the head commit.
    GitHub timestamps a commit status with `startedAt` and, on the other
    spelling of the same row, with `createdAt`; both are read, in that order,
    because the field GitHub sends depends on the API version in front of us.
    """
    rows = [entry for entry in entries if _check_name(entry) == context]
    if not rows:
        return None

    def stamp(entry: dict[str, Any]) -> str:
        return str(
            entry.get("startedAt") or entry.get("createdAt") or entry.get("completedAt") or ""
        )

    return max(enumerate(rows), key=lambda pair: (stamp(pair[1]), pair[0]))[1]


def _status_target_url(entry: dict[str, Any]) -> str:
    """The build URL a status names, if it names one.

    `targetUrl` is GitHub's field for a commit status; `target_url` is the shape
    the API itself uses. A CheckRun's `detailsUrl` is deliberately not read here:
    that is a workflow run, not a build, and the gate is about builds.
    """
    for key in ("targetUrl", "target_url"):
        value = str(entry.get(key) or "").strip()
        if value:
            return value
    return ""


def _parse_pipeline_url(path: str) -> tuple[str, str, str] | None:
    """Read a Woodpecker pipeline URL path as `(kind, repository, number)`.

    `kind` is `id` when the path names the repository by its numeric Woodpecker
    id, `name` when it names it as `owner/name`, and empty when the path names
    no repository at all. The number is the pipeline number.

    The path is read by shape rather than matched against one exact form,
    because the same Woodpecker release publishes the pipeline link in more than
    one shape and the worker posts whatever `CI_PIPELINE_URL` holds. A path
    that is not a pipeline link at all returns None.

    The number has to be ASCII digits: the URL comes from a commit status, so
    it is written by whoever posted the status, and a Unicode digit would
    otherwise reach the API call as a byte that cannot be encoded.
    """
    segments = [part for part in path.strip("/").split("/") if part]
    if len(segments) < 2:
        return None
    number = segments[-1]
    if not (number.isascii() and number.isdigit()):
        return None
    if segments[-2] not in _PIPELINE_PATH_WORDS:
        return None
    head = segments[:-2]
    if "repos" in head:
        index = head.index("repos")
        if index + 1 < len(head):
            return ("id", head[index + 1], number)
    if "repo" in head:
        index = head.index("repo")
        name = "/".join(head[index + 1 :])
        if name:
            # A repository named by its number is named by its id, not by its name.
            return ("id", name, number) if name.isdigit() else ("name", name, number)
    if len(head) >= 2:
        return ("name", "/".join(head), number)
    return ("", "", number)


def _value_from_text(text: str, key: str) -> str:
    """The value of one key in a `KEY=value` file's text.

    The text is read as a list of `KEY=value` lines and only the key asked for
    is taken, so a file that holds other secrets is safe to point at. The value
    goes back to the caller and to nobody else: it is never logged, never
    written to disk, and never part of a refusal message.
    """
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        words = name.split(None, 1)
        if words and words[0] == "export":
            # `export KEY=value` is the same line in a different dialect. A file
            # that uses it says the value under a name the key does not match,
            # so the key would never be found.
            name = words[1].strip() if len(words) > 1 else ""
        if name == key:
            return value.strip().strip("'\"")
    return ""


def _token_from_file(path: str, key: str) -> str:
    """The value of one key in a `KEY=value` file, or an empty string.

    The file is read as a list of `KEY=value` lines and only the key asked for
    is taken, so a file that holds other secrets is safe to point at. The value
    is returned to the caller and to nobody else: it is never logged, never
    written to disk, and never part of a refusal message.
    """
    try:
        text = Path(path).expanduser().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    return _value_from_text(text, key)


def _deployment_config_files(prov: CiProvenance) -> tuple[str, ...]:
    """The files the deployment's own addresses are read from.

    The deployment's address is a fact about the machine the queue runs on, so
    it is read from the machine rather than written down here. This is the one
    place that knows where the files are, so the test suite can point it at a
    fixture without the gate reading the real deployment.
    """
    return prov.host_files


def _host_of_url(value: str) -> str:
    """The `host:port` an URL names, or an empty string.

    The host and the port are read apart, so an URL that carries a user name
    (`http://user:pass@host:8000`) names the host and not the credentials, and
    the credentials never reach the allow-list.
    """
    parsed = urllib.parse.urlparse(value.strip())
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
    if ":" in host:
        host = f"[{host}]"
    return f"{host}:{port}" if port else host


def _redacted_url(value: str) -> str:
    """An URL without its credentials.

    The status writer chose the URL, so it may carry a user name and a password
    or a token in its query. The gate compares the host, and the host is all
    that anybody reading the log needs: the log outlives the tick and the
    launchd error log is kept, so a credential that was written into it stays
    there.
    """
    text = (value or "").strip()
    try:
        parsed = urllib.parse.urlparse(text)
    except ValueError:
        return text
    if not parsed.scheme:
        return text
    host = _host_of_url(text)
    if not host:
        return text
    return urllib.parse.urlunparse((parsed.scheme, host, parsed.path, "", "", ""))


def _allowed_hosts(prov: CiProvenance) -> tuple[tuple[str, ...], str]:
    """The hosts a build link may name, and why the deployment is unknown.

    The static list in the policy is the part that never changes. The
    deployment's own addresses are read from the files the policy names, so a
    change of local IP is a change of the deployment and not a change of this
    repository: an allow-list that carries a DHCP address goes stale, and under
    `enforce` a stale allow-list refuses every pull request.

    The second value is why the configuration could not be read, or an empty
    string when it could.
    """
    cache_key = (prov.hosts, _deployment_config_files(prov), prov.host_url_keys)
    cached = _HOST_CACHE.get(cache_key)
    if cached is not None:
        return cached
    hosts = {host.lower() for host in prov.hosts}
    found = False
    problems: list[str] = []
    for path_str in _deployment_config_files(prov):
        path = Path(path_str).expanduser()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(
                f"{path_str} could not be read "
                f"({getattr(exc, 'strerror', None) or type(exc).__name__})"
            )
            continue
        for key in prov.host_url_keys:
            value = _value_from_text(text, key)
            if not value:
                continue
            host = _host_of_url(value)
            if host:
                hosts.add(host)
                found = True
    if found:
        result = (tuple(sorted(hosts)), "")
    elif problems:
        result = (tuple(sorted(hosts)), "; ".join(problems))
    else:
        result = (
            tuple(sorted(hosts)),
            "the deployment configuration names no Woodpecker address",
        )
    _HOST_CACHE[cache_key] = result
    return result


def _woodpecker_token(prov: CiProvenance) -> str:
    """The Woodpecker API token, or an empty string.

    The token is read from the environment, or from the file the policy names
    when the environment does not carry it. The launchd job that runs the queue
    carries only `HOME` and `PATH`, so on that host the file is the source.

    The answer is remembered for the run: the queue evaluates up to 200 pull
    requests per tick, and reading a file once per pull request is a queue that
    spends its tick on the file.
    """
    key = (prov.token_env, prov.token_file)
    if key in _TOKEN_CACHE:
        return _TOKEN_CACHE[key]
    token = str(os.environ.get(prov.token_env) or "").strip()
    if not token and prov.token_file:
        token = _token_from_file(prov.token_file, prov.token_env)
    _TOKEN_CACHE[key] = token
    return token


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse a redirect.

    `urllib` copies every request header to the redirect target except
    `content-length` and `content-type`, so a redirect would hand the
    Woodpecker token to a host the allow-list never approved, and the answer
    that comes back would be the answer of that host.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # The name is the one the base class uses.
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


_WOODPECKER_OPENER = urllib.request.build_opener(_NoRedirect)


def _woodpecker_read(
    url: str, token: str, timeout: float = PROVENANCE_READ_TIMEOUT
) -> tuple[int, Any]:
    """One read-only GET against the Woodpecker API, read again if it is dropped.

    Returns the HTTP status and the decoded body. A transport failure is
    reported as status 0, because "the API could not be read" and "the build is
    not there" are different answers and an operator needs to tell them apart.

    Nothing a posted status can put in the URL may kill the tick: the read
    catches everything, because a queue that dies on a crafted `target_url`
    stops merging for everybody.

    Three things are true of a read that could not be made, and each of them
    used to be false:

    - A dropped connection is not an answer about the build, so the read is
      tried again before it is believed.
    - A host that could not be read is remembered for a short while, so the
      queue does not ask a dead host three times per pull request of the tick.
      One dropped connection used to refuse every pull request of the tick,
      for a reason that had nothing to do with them.
    - A failed read is not cached as the answer for that URL, so the URL is
      read again once the memory of the failure has passed. The memory is of
      that host and not of the queue: it keeps that host unasked for a minute,
      and after that the host is asked again.

    An answer the API gave - any status code, and a refused redirect - is
    cached for the tick: the API answered, and its answer is the same until
    the next tick.
    """
    cached = _READ_CACHE.get(url)
    if cached is not None:
        return cached
    host = _read_host(url)
    remembered = _HOST_FAILURE.get(host)
    if remembered is not None:
        failed_at, answer = remembered
        if time.monotonic() - failed_at < PROVENANCE_HOST_COOLDOWN:
            # The host did not answer a moment ago. It is asked once more, and
            # briefly: a host that was asleep for a moment answers, and the
            # tick carries on with the build instead of with the memory of a
            # failure that is no longer true. One ask and not three, so a host
            # that is down costs the tick one short read per pull request.
            status, payload, dropped = _woodpecker_read_once(
                url, token, PROVENANCE_REPROBE_TIMEOUT
            )
            if not dropped:
                _HOST_FAILURE.pop(host, None)
                _READ_CACHE[url] = (status, payload)
                return (status, payload)
            return (
                0,
                f"{answer[1]} (the host was asked once more and did not answer)",
            )
        # The memory of the failure has run out: the host is read again with
        # the whole budget.
        _HOST_FAILURE.pop(host, None)
    status, payload, dropped = _woodpecker_read_attempts(url, token, timeout)
    if dropped:
        _HOST_FAILURE[host] = (time.monotonic(), (status, payload))
    else:
        _READ_CACHE[url] = (status, payload)
    return (status, payload)


def _read_host(url: str) -> str:
    """The scheme and the host of a URL, which is what a read of it shares.

    Two URLs on one host are one host for the queue: a host that could not be
    read could not be read for either of them. The key is normalised the way
    the allow-list is - the host in lower case, with its port - so that two
    spellings of one address do not each pay their own retry storm.
    """
    parts = urllib.parse.urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        port = None
    host = (parts.hostname or "").lower()
    if port:
        return f"{parts.scheme}://{host}:{port}"
    return f"{parts.scheme}://{host}"


def _woodpecker_read_attempts(
    url: str, token: str, timeout: float
) -> tuple[int, Any, bool]:
    """The read, tried again while the API cannot be reached.

    The third value says whether the API could not be reached at all, which is
    the only failure worth trying again: a server that answered 404 answered,
    and its answer is the same until the next tick.

    The budget bounds the attempts of one read, so one path costs the budget
    once and not once per attempt. It is a deadline and not a sum of timeouts:
    the deadline is handed to the attempt, so a server that answers the
    headers and then trickles the body cannot hold the read open past it.
    """
    deadline = time.monotonic() + PROVENANCE_READ_BUDGET
    reason = ""
    attempts = 0
    for attempt in range(1, PROVENANCE_READ_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(
                min(PROVENANCE_RETRY_BACKOFF, max(0.0, deadline - time.monotonic()))
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        attempts = attempt
        status, payload, dropped = _woodpecker_read_once(
            url, token, min(timeout, remaining), deadline
        )
        if not dropped:
            return (status, payload, False)
        reason = f"{payload} (tried {attempt} times)"
    return (0, reason, True) if attempts else (0, "the read was not attempted", True)


def _read_response_body(response: Any, deadline: float | None) -> bytes:
    """The whole body, given up on when the deadline has passed.

    The pieces have to be the size of one socket read, or the deadline between
    them is never reached. `read(n)` on an `http.client.HTTPResponse` returns
    only when it has `n` bytes or the body has ended, so a server that answers
    the headers at once and then trickles the body holds one `read(65536)` open
    for as long as it likes — the socket timeout bounds one operation on the
    socket, not the body (measured by the Code Reviewer on DIG-5573: a
    2 001-byte body in twenty pieces was read in a single call). `read1(n)`
    returns as soon as one underlying read has something to give, so the loop
    below is a loop the deadline can interrupt.

    `read1` is what `urlopen` and the Woodpecker opener return in production.
    The `read` fallback is for a response-shaped object that does not have it
    (a test double, or a file wrapper): those keep the loop but not the
    per-chunk guarantee.
    """
    read = getattr(response, "read1", None) or response.read
    chunks: list[bytes] = []
    while True:
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("the read exceeded its budget")
        chunk = read(65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _woodpecker_read_once(
    url: str, token: str, timeout: float, deadline: float | None = None
) -> tuple[int, Any, bool]:
    """One attempt at the read.

    The third value says whether the API could not be reached, so that the
    caller can tell a dropped connection from an answer the API gave.

    The body is read one socket read at a time and the deadline is checked
    between them. The timeout of a socket is the timeout of one operation on
    it, so a server that answers the headers and then trickles the body would
    hold the read open for as long as it liked unless the read gives up at the
    deadline.
    """
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    try:
        with _WOODPECKER_OPENER.open(request, timeout=timeout) as response:
            body = _read_response_body(response, deadline).decode("utf-8", "replace")
            status = int(response.status)
            final_url = response.geturl()
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
        if code in (301, 302, 303, 307, 308):
            # The redirect was refused: the answer of another host is not the
            # answer of ours, and the token would have gone with it. The answer
            # is the same every time, so the read is not tried again.
            return (0, "the request was redirected", False)
        return (code, None, False)
    except Exception as exc:  # a status must never kill a tick
        # The API could not be reached. This is the one failure that says
        # nothing about the build, so it is the one failure worth trying again.
        return (0, f"{type(exc).__name__}: {exc}", True)
    if final_url != url:
        return (0, "the request was redirected", False)
    try:
        return (status, json.loads(body or "null"), False)
    except json.JSONDecodeError:
        return (status, None, False)


def _build_steps(pipeline: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    """Every step of a build, by name, with the states it was seen in.

    A name with more than one state is ambiguous - two workflows can carry a
    step of the same name - and the gate refuses an ambiguous step rather than
    pick one.
    """
    steps: dict[str, set[str]] = {}
    for workflow in pipeline.get("workflows") or []:
        if not isinstance(workflow, Mapping):
            continue
        for child in workflow.get("children") or []:
            if not isinstance(child, Mapping):
                continue
            name = str(child.get("name") or "")
            if name:
                steps.setdefault(name, set()).add(str(child.get("state") or ""))
    return {name: frozenset(states) for name, states in steps.items()}


def _resolve_woodpecker_repo_id(
    name: str,
    static_id: str,
    base_url: str,
    token: str,
    timeout: float,
) -> tuple[str, str]:
    """The numeric id of a Woodpecker repository, and why it is not known.

    The name is the authority and it is resolved against the Woodpecker API on
    every check, because a repository that was recreated carries a new id: a
    number written down in the policy then points at a different repository, or
    at nothing, and the gate reads the wrong build.

    The number in the policy is used only when the policy names no repository
    by name, because then there is nothing to resolve. It is never a
    substitute for a name that could not be resolved. A number that cannot be
    confirmed names a repository the gate does not know, and the build of an
    unknown repository says nothing about this pull request - so the gate
    refuses instead of reading it. The lookup adds no new way for the tick to
    fail: the build behind the status is read from the same API, so an API
    that cannot answer the lookup cannot answer that either.

    The lookup is refused on a redirect for the same reason the build read is:
    the token must not travel to a host the allow-list never named.
    """
    if name:
        url = f"{base_url}/api/repos/lookup/{name}"
        status, payload = _woodpecker_read(url, token, timeout=timeout)
        if status == 200 and isinstance(payload, Mapping):
            resolved = str(payload.get("id") or "").strip()
            if resolved:
                return resolved, ""
        if status == 0:
            problem = "the Woodpecker API could not be read"
        else:
            problem = f"the Woodpecker API answered HTTP {status}"
        return "", f"the Woodpecker repository {name} could not be resolved ({problem})"
    if static_id:
        return static_id, ""
    return "", "the policy names no Woodpecker repository"


def verify_ci_provenance(
    pr: Mapping[str, Any],
    policy: Policy,
    repo: str | None,
    *,
    mode: str | None = None,
    context: str = "",
    commit_match: str | None = None,
) -> Provenance:
    """Check the pull request's status against the build it names.

    Every refusal names what is wrong, because the queue is the only gate and
    an unexplained refusal is a queue nobody trusts. The reason is written in
    words that stay the same from tick to tick; the volatile facts about the
    build are in `detail`, which goes to the log and never to the verdict.
    """
    prov = policy.ci_provenance
    active = mode or provenance_mode(policy)
    if active == PROVENANCE_OFF:
        return Provenance(True, "the CI provenance gate is off")

    ctx = context or prov.context
    entry = _newest_status(_rollup(dict(pr)), ctx)
    if entry is None:
        return Provenance(False, f"no '{ctx}' status is reported on the head commit")
    target = _status_target_url(entry)
    if not target:
        return Provenance(
            False, f"the '{ctx}' status carries no target_url, so it names no build"
        )
    match = commit_match or commit_match_mode(policy)
    return _verify_build(
        target,
        prov,
        repo,
        str(pr.get("headRefOid") or ""),
        active,
        match,
        subject="status",
    )


def _verify_build(
    target: str,
    prov: CiProvenance,
    repo: str | None,
    head: str,
    active: str,
    match: str,
    subject: str,
) -> Provenance:
    """Read the build a status names and say whether it answers for this head.

    `subject` is what named the build - a `status` or a `receipt` - so the
    reason says which of the two it was. The reason text is what the live
    driver keys its handback comment on, so it never carries the build number.
    """
    parsed = urllib.parse.urlparse(target)
    host = _host_of_url(target)
    if not parsed.scheme or not host:
        return Provenance(
            False, "the target_url is not an absolute URL", target_url=target
        )
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return Provenance(
            False,
            f"the target_url scheme {scheme!r} is not http or https",
            target_url=target,
        )

    allowed, config_problem = _allowed_hosts(prov)
    if prov.require_config and config_problem:
        return Provenance(
            False,
            "the deployment configuration could not be read, so the Woodpecker "
            f"hosts cannot be confirmed ({config_problem})",
            target_url=target,
        )
    if not allowed:
        return Provenance(
            False,
            "no Woodpecker host is configured, so no build can be checked",
            target_url=target,
        )
    if host not in allowed:
        return Provenance(
            False, f"the target_url host {host!r} is not a Woodpecker host", target_url=target
        )

    shape = _parse_pipeline_url(parsed.path)
    if shape is None:
        return Provenance(
            False, "the target_url does not name a Woodpecker pipeline", target_url=target
        )
    kind, named_repo, number = shape

    repo_key = repo or ""
    static_id = prov.woodpecker_repos.get(repo_key, "")
    expected_name = prov.woodpecker_repo_names.get(repo_key, "")
    if not expected_name and static_id:
        expected_name = prov.woodpecker_names.get(static_id, "")
    if not expected_name and not static_id:
        return Provenance(
            False,
            f"no Woodpecker repository is configured for {repo or 'this repository'}",
            target_url=target,
        )
    if kind == "name":
        if not expected_name:
            return Provenance(
                False,
                "the policy names no Woodpecker repository for "
                f"{repo or 'this repository'}, so the URL cannot be checked",
                target_url=target,
            )
        if named_repo != expected_name:
            return Provenance(
                False,
                f"the target_url names the Woodpecker repository {named_repo!r}, "
                f"not {expected_name!r}",
                target_url=target,
            )
    elif kind != "id":
        return Provenance(
            False,
            "the target_url names no Woodpecker repository, so it cannot be checked "
            "against this repository's build",
            target_url=target,
        )

    token = _woodpecker_token(prov)
    if not token:
        return Provenance(
            False,
            f"no Woodpecker token is available ({prov.token_env} is unset and no "
            "token file is configured), so the build cannot be read",
            target_url=target,
        )

    timeout = (
        PROVENANCE_READ_TIMEOUT_SHADOW
        if active == PROVENANCE_SHADOW
        else PROVENANCE_READ_TIMEOUT
    )
    base = f"{scheme}://{host}"
    expected_id, resolve_problem = _resolve_woodpecker_repo_id(
        expected_name,
        static_id,
        base,
        token,
        timeout,
    )
    if not expected_id:
        return Provenance(
            False,
            "the Woodpecker repository for "
            f"{repo or 'this repository'} could not be resolved: {resolve_problem}",
            target_url=target,
        )
    if kind == "id" and named_repo != expected_id:
        return Provenance(
            False,
            f"the target_url names the Woodpecker repository {named_repo!r}, "
            f"not {expected_id!r}",
            target_url=target,
        )

    api_url = f"{base}/api/repos/{expected_id}/pipelines/{number}"
    status, payload = _woodpecker_read(api_url, token, timeout=timeout)
    build = f"{expected_id}#{number}"
    detail = f"build {build} at {_redacted_url(target)}"
    if status == 0:
        return Provenance(
            False,
            "the Woodpecker API could not be read",
            detail=f"{detail}: {payload}",
            target_url=target,
        )
    if status == 404:
        return Provenance(
            False,
            f"the build named by the {subject} does not exist",
            detail=detail,
            target_url=target,
        )
    if status != 200:
        return Provenance(
            False,
            f"the Woodpecker API answered HTTP {status}",
            detail=detail,
            target_url=target,
        )
    if not isinstance(payload, Mapping):
        return Provenance(
            False,
            "the Woodpecker API answered with something that is not a build",
            detail=detail,
            target_url=target,
        )

    build_status = str(payload.get("status") or "").strip().lower()
    if not build_status or build_status in _PIPELINE_UNFINISHED_STATES:
        return Provenance(
            False,
            f"the build named by the {subject} has not finished",
            detail=f"{detail} (status {build_status or 'unknown'})",
            target_url=target,
        )

    step = prov.steps.get(repo or "")
    if not step:
        return Provenance(
            False,
            f"no check step is configured for {repo or 'this repository'}",
            detail=detail,
            target_url=target,
        )
    states = _build_steps(payload).get(step)
    if states is None:
        return Provenance(
            False,
            f"the build named by the {subject} has no '{step}' step, so it says nothing "
            f"about {repo or 'this repository'}",
            detail=detail,
            target_url=target,
        )
    if len(states) > 1:
        return Provenance(
            False,
            f"the build named by the {subject} has more than one '{step}' step, so it "
            f"says nothing about {repo or 'this repository'}",
            detail=detail,
            target_url=target,
        )
    state = next(iter(states))
    if state != "success":
        return Provenance(
            False,
            f"the '{step}' step of the build named by the {subject} is {state}",
            detail=detail,
            target_url=target,
        )

    label = repo or "this repository"
    ok_reason = f"the build named by the {subject} ran '{step}' for {label}"
    if match == COMMIT_MATCH_OFF:
        # The commit comparison is off: the build is read, and nothing is said about
        # which commit it ran. Only for a policy that has another way of tying a
        # status to the head - the trusted receipt.
        return Provenance(
            True,
            ok_reason,
            detail=f"{detail} (build status {build_status})",
            target_url=target,
        )

    commit = str(payload.get("commit") or "").strip().lower()
    head = str(head or "").strip().lower()
    mismatch = ""
    if not head:
        mismatch = "the pull request head sha is unknown, so no build can be matched to it"
    elif not commit:
        mismatch = (
            f"the build named by the {subject} reports no commit, so it cannot be "
            "matched to the head"
        )
    elif commit != head:
        mismatch = f"the build named by the {subject} ran another commit"
        detail = f"{detail} ran commit {commit[:12]}, not the head {head[:12]}"
    if mismatch and match == COMMIT_MATCH_ENFORCE:
        return Provenance(
            False,
            mismatch,
            detail=detail,
            target_url=target,
        )
    if mismatch:
        # The comparison is measured, not enforced: the build is reported as what it
        # is, and the reason it did not match the head is kept for the log.
        return Provenance(
            True,
            ok_reason,
            detail=detail,
            target_url=target,
            measured=mismatch,
        )

    return Provenance(
        True,
        f"the build named by the {subject} ran '{step}' for {label} at the head commit",
        detail=f"{detail} at commit {head[:12]} (build status {build_status})",
        target_url=target,
    )


def _status_writer(row: Mapping[str, Any]) -> str:
    """The login of the account that wrote a status row.

    The REST endpoint answers with a `creator` object; a row without one, or
    with one that is not an object, has no writer the queue can name.
    """
    creator = row.get("creator")
    if not isinstance(creator, Mapping):
        return ""
    return str(creator.get("login") or "").strip()


def _newest_receipt_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The newest of the rows, by the time GitHub stamped it.

    The REST endpoint spells the times `created_at` and `updated_at`; the
    GraphQL rollup spells them `startedAt` and `createdAt`. Both are read,
    because which one comes depends on the endpoint in front of us.
    """

    def stamp(row: Mapping[str, Any]) -> str:
        for key in (
            "created_at",
            "updated_at",
            "started_at",
            "startedAt",
            "createdAt",
            "completedAt",
        ):
            value = row.get(key)
            if value:
                return str(value)
        return ""

    return max(enumerate(rows), key=lambda pair: (stamp(pair[1]), pair[0]))[1]


def _commit_statuses(repo: str | None, sha: str) -> tuple[list[dict[str, Any]], str]:
    """The commit statuses on one commit, with the writer of each.

    The GraphQL rollup the queue already reads carries no creator: a status
    context says what the status was and which build it names, not who wrote
    it. That one fact is what a trusted receipt is made of, so the receipt is
    read from the REST endpoint, which does say it.

    A read that fails is a problem, not an absence: the queue cannot tell "no
    receipt" from "no way to read the receipts", so it says so and stops.
    """
    if not repo:
        return [], "the repository is unknown"
    try:
        rows = _gh_json(
            "api",
            f"repos/{repo}/commits/{sha}/statuses?per_page=100",
            timeout=PROVENANCE_STATUS_TIMEOUT,
        )
    except QueueError as exc:
        return [], str(exc)
    if not isinstance(rows, list):
        return [], "the API answered with something that is not a list of statuses"
    return [dict(row) for row in rows if isinstance(row, Mapping)], ""


def verify_trusted_receipt(
    pr: Mapping[str, Any],
    policy: Policy,
    repo: str | None,
    *,
    mode: str | None = None,
    commit_match: str | None = None,
) -> Provenance | None:
    """The receipt that a seat cannot write.

    `None` means the policy asks for no receipt, which is different from a
    receipt that is missing.

    A `local-ci` status is worth only its writer's worth: it is posted with a
    user token, so a seat that runs the check itself can post the same green
    row. The receipt is the same status posted by the CI's own GitHub App
    installation, so the writer is the CI and nobody else. It also answers the
    question the build's own commit cannot answer today: it sits on the head
    commit, so it binds the receipt to the head.

    A row that was written by somebody else does not cancel a receipt that was
    written by the app. The queue looks for a trusted receipt; a forged row
    beside a real one is the forged writer's business, not the pull request's.
    That way a seat cannot hold a pull request by writing a failing status
    next to the CI's own passing one.
    """
    prov = policy.ci_provenance
    receipt = prov.trusted_receipt
    if not receipt.context or not receipt.creators:
        return None
    if not receipt.required:
        # A receipt the policy does not require is not read. The queue looks at
        # every open pull request on every tick, and a status list it is not
        # going to obey buys nothing while the CI writes none. The chain is
        # switched on by the policy change that comes with the CI's own token.
        return None
    active = mode or provenance_mode(policy)
    if active == PROVENANCE_OFF:
        return None

    head = str(pr.get("headRefOid") or "").strip().lower()
    if not head:
        return Provenance(
            False,
            "the pull request head sha is unknown, so the trusted receipt cannot be read",
        )

    rows, problem = _commit_statuses(repo, head)
    if problem:
        return Provenance(
            False,
            "the commit statuses could not be read",
            detail=problem,
        )
    mine = [row for row in rows if str(row.get("context") or "") == receipt.context]
    if not mine:
        return Provenance(
            False, f"no '{receipt.context}' receipt is reported on the head commit"
        )

    trusted = [row for row in mine if _status_writer(row) in receipt.creators]
    if trusted:
        # The newest row the CI itself wrote is the CI's own verdict on the
        # head, and it is the only one that counts. An earlier green row does
        # not survive a later red one: the app is the CI, so its last word on
        # this head is the word. A row somebody else wrote is left out
        # entirely, which is what keeps a forged row from cancelling the
        # receipt.
        row = _newest_receipt_row(trusted)
        state = str(row.get("state") or "").strip().lower() or "unknown"
        if state != "success":
            return Provenance(False, f"the '{receipt.context}' receipt is {state}")
    else:
        successful = [
            row for row in mine if str(row.get("state") or "").strip().lower() == "success"
        ]
        if successful:
            newest = _newest_receipt_row(successful)
            writer = _status_writer(newest)
            return Provenance(
                False,
                f"the '{receipt.context}' receipt was written by "
                f"{writer or 'an unknown writer'}, which is not a trusted CI writer",
                detail=f"the trusted writers are {', '.join(receipt.creators)}",
            )
        newest = _newest_receipt_row(mine)
        state = str(newest.get("state") or "").strip().lower() or "unknown"
        return Provenance(False, f"the '{receipt.context}' receipt is {state}")

    row = _newest_receipt_row(trusted)
    target = _status_target_url(row)
    if not target:
        return Provenance(
            False,
            f"the '{receipt.context}' receipt carries no target_url, so it names no build",
        )
    match = commit_match or commit_match_mode(policy)
    return _verify_build(
        target,
        prov,
        repo,
        head,
        active,
        match,
        subject="receipt",
    )


def _provenance_index_path() -> Path:
    return Path(os.environ.get(PROVENANCE_INDEX_ENV) or PROVENANCE_INDEX_PATH)


def _provenance_index() -> dict[str, dict[str, Any]]:
    """What the log already holds, by the path it is written to.

    The index is a memory of the log, not a second log: it says which refusals
    the log already carries, so a refusal that repeats is counted instead of
    written again.
    """
    path = _provenance_index_path()
    key = str(path)
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    index: dict[str, dict[str, Any]] = {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = None
    if isinstance(raw, Mapping) and isinstance(raw.get("entries"), Mapping):
        for entry_key, entry in raw["entries"].items():
            if isinstance(entry, Mapping):
                index[str(entry_key)] = dict(entry)
    _INDEX_CACHE[key] = index
    return index


def _prune_index(index: dict[str, dict[str, Any]]) -> None:
    """Drop the entries the log no longer needs to remember.

    An entry that has not been seen for a fortnight is a window that ended, and
    the index is not a history. The cap is the same idea for a busy day: the
    index holds the recent refusals, not every refusal the queue ever made.
    """
    oldest_allowed = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=PROVENANCE_INDEX_MAX_AGE_DAYS
    )
    stale: list[str] = []
    for entry_key, entry in index.items():
        stamp = str(entry.get("last_seen") or entry.get("first_seen") or "")
        try:
            seen = datetime.datetime.fromisoformat(stamp)
        except ValueError:
            stale.append(entry_key)
            continue
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=datetime.timezone.utc)
        if seen < oldest_allowed:
            stale.append(entry_key)
    for entry_key in stale:
        index.pop(entry_key, None)
    if len(index) > PROVENANCE_INDEX_MAX_ENTRIES:
        ordered = sorted(
            index.items(), key=lambda item: str(item[1].get("last_seen") or "")
        )
        for entry_key, _ in ordered[: len(index) - PROVENANCE_INDEX_MAX_ENTRIES]:
            index.pop(entry_key, None)


def _flush_provenance_index() -> None:
    """Write the index out, so the next tick knows what the log already holds."""
    for path_str, index in list(_INDEX_CACHE.items()):
        path = Path(path_str)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            handle = os.fdopen(
                os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600),
                "w",
                encoding="utf-8",
            )
            with handle:
                json.dump({"entries": index}, handle, indent=2, sort_keys=True)
                handle.write("\n")
            tmp.replace(path)
            os.chmod(path, 0o600)
        except OSError:
            # The index is a convenience, never a gate: a queue that cannot
            # write it must still merge and still say why on stderr.
            pass


def _log_lines(path: Path) -> set[str]:
    """The lines the log holds, without their timestamps.

    The index says which refusals the log already carries, and that claim is
    only true while the log carries them: a log that was rotated away, or
    emptied, or edited, no longer holds what the index remembers. So the log
    is read once per run and a refusal is looked for in it, rather than
    trusting the index on its own.

    The lines are held without their timestamps. When the refusal was first
    seen is the index's business; the line itself is what has to be there.

    The file is only read again when its size says it changed, so an operator
    who empties the log between two ticks sees the refusals written again.
    """
    key = str(path)
    try:
        size = path.stat().st_size
    except OSError:
        size = -1
    cached = _LOG_CACHE.get(key)
    if cached is not None and cached[0] == size:
        return cached[1]
    lines: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        _, _, rest = raw.partition(" ")
        lines.add(rest if rest else raw)
    _LOG_CACHE[key] = (size, lines)
    return lines


def _index_count(entry: Mapping[str, Any]) -> int:
    """How often a refusal was seen.

    A count that is not a number is a count of one. The index is a convenience
    and a corrupted one must not stop the tick.
    """
    try:
        return int(entry.get("count") or 1)
    except (TypeError, ValueError):
        return 1


def _log_provenance(
    pr: Mapping[str, Any],
    repo: str | None,
    required: str,
    reason: str,
    detail: str,
    mode: str,
    verb: str = "",
) -> None:
    """Record what the gate found.

    DIG-4809 runs this in shadow mode and reads the log to see whether the gate
    would have refused a pull request that should have merged. The line goes to
    stderr, which the launchd job keeps, and to a file of its own, so the window
    is one file to read. The file is written for the owner of the queue alone
    and is capped, because a file nobody rotates is a file that eventually
    fills the disk the queue lives on.

    The file holds one line per refusal, not one per refusal per tick. The
    queue looks at every open pull request on every tick, so writing the line
    again each time is how the 48 hour window turns into tens of thousands of
    lines nobody reads. A refusal that repeats is counted in the index instead,
    and the count says how often the gate saw it.

    A measurement is written under its own verb, so a line that says what the
    gate would have said cannot be read as a verdict.
    """
    if not verb:
        verb = "would refuse" if mode == PROVENANCE_SHADOW else "refuses"
    line = (
        f"CI provenance ({mode}): PR #{pr.get('number', 0)} {repo or '?'} — "
        f"{verb} '{required}': {reason}"
    )
    if detail:
        line += f" — {detail}"
    print(line, file=sys.stderr)
    path = Path(os.environ.get(PROVENANCE_LOG_ENV) or PROVENANCE_LOG_PATH)
    # The mode is part of the key: a refusal in shadow mode and the same
    # refusal in enforce mode are two different lines, and the switch to
    # enforce is exactly the moment the log has to start carrying the new ones.
    key = f"{mode}|{repo or '?'}|{pr.get('number', 0)}|{required}|{reason}"
    index = _provenance_index()
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    entry = index.get(key)
    if entry is not None and line in _log_lines(path):
        entry["count"] = _index_count(entry) + 1
        entry["last_seen"] = stamp
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if _rotate_provenance_log(path):
            # The file was replaced, so what it held is in the rotated file now
            # and the lines this run read are no longer the ones in it.
            _LOG_CACHE.pop(str(path), None)
        handle = os.fdopen(
            os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a",
            encoding="utf-8",
        )
        with handle:
            handle.write(f"{stamp} {line}\n")
        os.chmod(path, 0o600)
    except OSError:
        # The log is a convenience, never a gate. A queue that cannot write it
        # must still refuse, and must still say why on stderr. The index must
        # not remember a line the log does not hold, so nothing is recorded.
        return
    _log_lines(path).add(line)
    index[key] = {"count": 1, "first_seen": stamp, "last_seen": stamp, "reason": reason}
    _prune_index(index)
    _flush_provenance_index()


def _rotate_provenance_log(path: Path) -> bool:
    """Keep the provenance log to one file of one size.

    The log grows by one line per pull request per tick, so an uncapped file
    grows without bound. The oldest file is dropped, not the newest: what the
    window needs is the recent lines.
    """
    try:
        if path.stat().st_size < PROVENANCE_LOG_MAX_BYTES:
            return False
    except OSError:
        return False
    try:
        path.replace(path.with_name(path.name + ".1"))
    except OSError:
        return False
    return True


def _gate_ci_provenance(
    pr: Mapping[str, Any], policy: Policy, repo: str | None, required: str
) -> list[str]:
    """The reasons a status is not evidence. Empty when it is.

    There are two chains and they answer different questions.

    The first chain asks whether the status names a build, and whether that
    build really ran this repository's check and passed. It is what DIG-4794
    shipped, and it is the chain that measured the wrong commit on a live pull
    request.

    The second chain asks who wrote the status. The `local-ci` row is posted
    with a user token, so the build it names can be copied from any recent
    build, and the writer of the row is the only thing that says whether the
    check ran on this head. The receipt is the same status posted by the CI's
    own GitHub App installation, and it sits on the head commit.

    The commit comparison is governed by its own switch, because it is the one
    check that cannot pass with the launcher as it is today: the pipeline the
    worker runs in is the launcher repository's own cron run, so the build's
    commit is never the pull request's head. Turning the comparison off without
    the receipt would leave nothing binding a status to a head, so the policy
    that asks for the softer comparison has to ask for the receipt too.
    """
    mode = provenance_mode(policy)
    if mode == PROVENANCE_OFF:
        return []
    reasons: list[str] = []
    match = commit_match_mode(policy)
    receipt = policy.ci_provenance.trusted_receipt
    if match != COMMIT_MATCH_ENFORCE and not receipt.required:
        # The environment can override the policy file, so the invariant the
        # policy loader checks is checked again here: without the receipt,
        # softening the comparison would let any green row through.
        _log_provenance(
            pr,
            repo,
            required,
            "the policy does not require a trusted CI receipt, so nothing binds a "
            "status to the head commit",
            f"the commit comparison is {match!r}",
            mode,
        )
        if mode != PROVENANCE_SHADOW:
            return [
                f"required check '{required}' has no trusted CI receipt: the policy "
                "does not require one, so nothing binds a status to the head commit"
            ]

    result = verify_ci_provenance(pr, policy, repo, mode=mode, context=required)
    if not result.ok:
        _log_provenance(pr, repo, required, result.reason, result.detail, mode)
        if mode != PROVENANCE_SHADOW:
            reasons.append(
                f"required check '{required}' has no verified Woodpecker provenance: "
                f"{result.reason}"
            )
    elif result.measured:
        _log_provenance(
            pr, repo, required, result.measured, result.detail, mode, "measured"
        )

    receipt_result = verify_trusted_receipt(pr, policy, repo, mode=mode)
    if receipt_result is None:
        return reasons
    context = receipt.context or "the trusted CI receipt"
    if not receipt_result.ok:
        _log_provenance(
            pr, repo, context, receipt_result.reason, receipt_result.detail, mode
        )
        # The receipt is required by the policy, so a missing or untrusted one
        # is a refusal - in shadow mode it is the refusal the gate would make.
        if mode != PROVENANCE_SHADOW and receipt.required:
            reasons.append(
                f"required check '{context}' is not accepted as a trusted CI "
                f"receipt: {receipt_result.reason}"
            )
    elif receipt_result.measured:
        _log_provenance(
            pr,
            repo,
            context,
            receipt_result.measured,
            receipt_result.detail,
            mode,
            "measured",
        )
    return reasons


def _governed_receipt_context(policy: Policy) -> str:
    """The receipt context, when the chain that reads it is the one in force.

    The receipt is the CI's own row, and the chain that reads it asks who
    wrote it. The generic scan in `_gate_checks` reads every status that is
    neither a required check nor an ignored one, so without this a seat's own
    failing `local-ci/app` row would hold a pull request next to the CI's own
    passing one - which is the one thing the receipt chain exists to prevent.

    The context is only left to the receipt chain while that chain reads it: a
    receipt the policy does not require, a gate that is off, and a policy with
    no required status check all mean nobody reads the row, so the scan keeps
    it and a red row still holds the pull request.
    """
    receipt = policy.ci_provenance.trusted_receipt
    context = str(receipt.context or "").strip()
    if not context or not receipt.required:
        return ""
    if provenance_mode(policy) == PROVENANCE_OFF:
        return ""
    if not any(
        check in policy.status_context_checks for check in policy.required_checks
    ):
        return ""
    return context


def _gate_checks(pr: dict[str, Any], policy: Policy, repo: str | None = None) -> list[str]:
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
            # A commit status is only as strong as whoever posted it, and a
            # StatusContext is the one report any writer can type. The provenance
            # gate asks the status to name the build that made it, and checks
            # that build (DIG-4794). In shadow mode it only records what it would
            # have refused.
            reasons.extend(_gate_ci_provenance(pr, policy, repo, required))
            continue
        if not any(_is_check_run(e) for e in entries):
            reasons.append(
                f"required check '{required}' only reported as a commit status, which any "
                "writer can set; the queue needs a workflow run"
            )

    # A non-required check that failed is still a red build. The base branch has a
    # CI contract whether or not GitHub enforces it.
    receipt_context = _governed_receipt_context(policy)
    for name, entries in by_name.items():
        if name in policy.required_checks or name in policy.ignored_checks:
            continue
        if name == receipt_context:
            # The receipt is the CI's own row, and the chain that reads it asks
            # who wrote it. A seat's failing row beside the CI's own passing
            # one is the seat's business, not a red build.
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
# Only the marker's `key=value` fields are read, and one line of prose beside it:
# `Review verdict: changes requested`. The prose is not a contract *about the
# findings* — a matcher on `## Verdict: changes requested (narrow)` would have to
# survive a reviewer reformatting a heading, and a heading someone forgets to
# update is indistinguishable from a verdict someone forgot to post. The review
# rule's own token is different: it is how a reviewer says which way the review
# went, and a queue that cannot read it cannot see the verdict at all (DIG-4878).

_MARKER_RE = re.compile(r"<!--\s*opencode-power-pack:code-review\b(?P<fields>[^>]*?)\s*-->")
_MARKER_FIELD_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)=(?P<value>\S+)")
_SCOPE_SHA_RE = re.compile(r"@(?P<sha>[0-9a-f]{7,40})\b")
# The `scope=` key itself, present or not, whatever its value looks like.
_SCOPE_KEY_RE = re.compile(r"(?:^|\s)scope\s*=", re.IGNORECASE)

# `changes_needed` is read alongside `changes_requested` because DIG-1021's interim
# discipline named the two verdicts "approve" and "changes needed"; a reviewer
# writing that spelling must not slip past the gate.
BLOCKING_VERDICTS = frozenset({"changes_requested", "changes_needed"})
APPROVE_VERDICTS = frozenset({"approved", "approve"})
READABLE_VERDICTS = BLOCKING_VERDICTS | APPROVE_VERDICTS


def _normalise_verdict(value: str) -> str:
    return value.strip().strip("'\";").lower().replace("-", "_")


def _marker_verdict(body: str) -> tuple[str, str, bool] | None:
    """`(verdict, scope_sha, names_scope)` from a review marker in `body`, or None.

    `names_scope` is True when the marker carries a `scope=` field at all, even
    one whose value is not a readable sha. The field's presence, not its parse,
    decides whether the marker names a head of its own.

    None means "this comment carries no marker verdict the queue can read" — a
    plain comment, or a marker whose `verdict=` is missing or misspelled. That
    is a missing signal, not a clearance, and it must not be treated as one.
    """
    for marker in _MARKER_RE.finditer(body):
        fields = {
            m.group("key").lower(): m.group("value")
            for m in _MARKER_FIELD_RE.finditer(marker.group("fields"))
        }
        verdict = _normalise_verdict(fields.get("verdict", ""))
        if verdict not in READABLE_VERDICTS:
            continue
        scope_sha = _SCOPE_SHA_RE.search(fields.get("scope", ""))
        names_scope = _SCOPE_KEY_RE.search(marker.group("fields")) is not None
        return verdict, (scope_sha.group("sha") if scope_sha else ""), names_scope
    return None


# The review rule's own format is a line carrying the token `Review verdict:`.
# The queue reads it as well as the marker: a reviewer who posts the line and no
# marker has still delivered a verdict, and reading only the marker leaves that
# verdict invisible — which is how a "changes requested" written in prose came
# to be read as no verdict at all (DIG-4878).
#
# The value list is explicit and longest-first. A loose `(?P<verdict>[\w -]+?)`
# reads one character and stops, which turns "changes requested" into "c" —
# unreadable, and the block goes with it. "no review owed" and "NO REVIEW —
# non-answer" are not on the list on purpose: they are the review rule's
# non-answers, and a non-answer is not a verdict.
_PROSE_VERDICT_RE = re.compile(
    r"review\s+verdict\s*:\s*[*_`\s]*"
    r"(?P<verdict>changes\s+requested|changes\s+needed|changes_requested|changes_needed"
    r"|approved|approve)\b",
    re.IGNORECASE,
)

# A sha written in prose, read as a prefix of the head at 7 characters or more —
# the same width the reviewer-independence gate reads. The token has to stand
# alone: a hex run inside a word is a word, not a commit, and a hex run joined
# to another by a dash is a uuid group, not a commit.
_PROSE_SHA_RE = re.compile(r"(?<![0-9a-zA-Z-])(?P<sha>[0-9a-f]{7,40})(?![0-9a-zA-Z-])")

# The line with which a seat says it withdraws the block it posted earlier. It
# is read beside the verdict, in the same comment, and only a line that opens
# with the token counts — a "withdraw" somewhere in prose is not a withdrawal
# (DIG-5246). The heads it names are read with `_PROSE_SHA_RE`; a line naming
# none is a withdrawal of the seat's blocks that name no head at all.
_WITHDRAWAL_LINE_RE = re.compile(
    r"^[ \t]*(?:[-*+>][ \t]*)?[*_`]*withdraws?[*_`]*[ \t]*:[ \t]*(?P<refs>[^\n]*)$",
    re.IGNORECASE | re.MULTILINE,
)

# The markers are read from the raw comment; the prose is what is left. A hex run
# inside a marker is not prose: `agent=54a431af-501a-47d9-...` is a seat uuid,
# and reading its first group as a commit would name a head nobody reviewed.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# The seat a verdict belongs to. Every seat on this org pushes under one GitHub
# login, so `author.login` cannot tell two reviewers apart — the seat id is the
# provenance marker's `agent=` field, and it is the only place it is written.
# A verdict whose seat cannot be read is judged by the newest-verdict rule
# instead of by seat (see `_standing_seat_blocks`).
_SEAT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{3,63}$")


def _comment_text(body: str) -> str:
    """The comment body with its HTML comments taken out."""
    return _HTML_COMMENT_RE.sub(" ", body)


def _line_at(body: str, index: int) -> str:
    """The line of `body` that contains `index`."""
    start = body.rfind("\n", 0, index) + 1
    end = body.find("\n", index)
    return body[start:] if end == -1 else body[start:end]


def _prose_verdict(body: str) -> tuple[str, str] | None:
    """`(verdict, the line it was read from)` from a `Review verdict:` line."""
    match = _PROSE_VERDICT_RE.search(body)
    if match is None:
        return None
    return match.group("verdict").lower().replace(" ", "_"), _line_at(body, match.start())


def _withdrawal(body: str) -> tuple[bool, tuple[str, ...]]:
    """`(declared, heads named)` from a `Withdraws:` line, or `(False, ())`.

    `declared` is True when the comment carries the line at all: it is what says
    the seat means to withdraw a block, and it is deliberately explicit, because
    the line lets a later approve clear a block the same seat posted on an
    unchanged head (DIG-5246). `heads` is every sha named on the line, oldest
    occurrence first, deduplicated. A line naming no sha withdraws only blocks
    that name no head, so it can never spend a block scoped to a commit the
    reviewer did not name.
    """
    declared = False
    heads: list[str] = []
    for match in _WITHDRAWAL_LINE_RE.finditer(body):
        declared = True
        for found in _PROSE_SHA_RE.finditer(match.group("refs")):
            sha = found.group("sha").lower()
            if sha not in heads:
                heads.append(sha)
    return declared, tuple(heads)


@dataclass(frozen=True)
class PostedVerdict:
    """The verdict the queue reads on a PR, and the head it names."""

    verdict: str
    source: str
    scope: str
    bindings: tuple[str, ...]
    comment_id: str
    author: str
    at: str
    # The seat that posted it, read from the provenance marker. Empty when the
    # comment carries no readable seat: every seat shares one GitHub login, so
    # there is nothing else to tell them apart by.
    seat: str = ""
    # A `Withdraws:` line in this comment, and the heads it names. Read only on
    # an approve, and only against the seat's own standing block (DIG-5246).
    withdrawal: bool = False
    withdrawn_heads: tuple[str, ...] = ()


def _comment_seat(provenance: Mapping[str, str]) -> str:
    """The seat that posted this comment, or "" when it cannot be read."""
    agent = str(provenance.get("agent") or "").strip()
    return agent if agent and _SEAT_ID_RE.match(agent) else ""


def _comment_verdict(comment: Mapping[str, Any]) -> PostedVerdict | None:
    """The verdict one comment carries, with the head it names, or None.

    The marker wins inside a comment: it is the contract, and the prose around
    it is what a reviewer reads. The prose line is read when the comment carries
    no marker verdict at all — a marker whose `verdict=` is missing or
    misspelled is skipped, and the line beside it still says what the reviewer
    decided.
    """
    body = str(comment.get("body") or "")
    text = _comment_text(body)
    marker = _marker_verdict(body)
    prose = _prose_verdict(text)
    if marker is None and prose is None:
        return None
    named_scope = False
    if marker is not None:
        verdict, scope, named_scope = marker
        source = "a `verdict=` marker"
        # The marker's `scope=` is the head the verdict is about. The prose around
        # it may name any number of commits, so it is not read as a binding.
        claims = [scope] if scope else []
    else:
        verdict, _line = prose
        source = "a `Review verdict:` line"
        scope = ""
        # A prose verdict names the head it covers somewhere in the comment — on
        # the verdict line, in the sentence after it, or in the scope line the
        # review opens with. The question this gate asks is "does this comment
        # name the head the PR stands at", so every sha in it is a candidate.
        claims = [found.group("sha") for found in _PROSE_SHA_RE.finditer(text)]
    provenance = _provenance_fields(body)
    provenance_head = str(provenance.get("head") or "")
    if provenance_head and not named_scope:
        # A marker verdict names the head it is about through its own `scope=`.
        # The provenance marker's `head=` is the fallback for a marker that names
        # no scope, and never a second binding for one that does: an approve
        # whose `scope=` names a stale head says nothing about the head the PR
        # stands at, and must not clear a block just because the provenance
        # marker names the newer head. "Names a scope" is the field's presence:
        # a `scope=` that does not parse as a sha (uppercase, short, no `@`)
        # binds nothing, and must not fall back to the provenance head. The
        # prose path has no `scope=`, so it keeps every sha in the comment as a
        # candidate, the provenance head included.
        claims.append(provenance_head)
    bindings: list[str] = []
    for binding in claims:
        if binding and binding not in bindings:
            bindings.append(binding)
    withdrawal, withdrawn_heads = _withdrawal(text)
    author = comment.get("author")
    login = "?"
    if isinstance(author, Mapping):
        login = str(author.get("login") or "?")
    return PostedVerdict(
        verdict=verdict,
        source=source,
        scope=scope,
        bindings=tuple(bindings),
        comment_id=str(comment.get("id") or ""),
        author=login,
        at=str(comment.get("createdAt") or ""),
        seat=_comment_seat(provenance),
        withdrawal=withdrawal,
        withdrawn_heads=withdrawn_heads,
    )


def _readable_verdicts(pr: dict[str, Any]) -> list[PostedVerdict]:
    """Every verdict the queue can read on this PR, oldest first.

    A verdict the queue cannot read is skipped rather than counted: a typo'd
    marker, a comment with no verdict, or a reviewer's non-answer is a missing
    signal, not a clearance, and letting it displace a real block would hand
    anyone who can comment a way to unlock the queue.
    """
    verdicts: list[PostedVerdict] = []
    for comment in pr.get("comments") or []:
        if not isinstance(comment, Mapping):
            continue
        parsed = _comment_verdict(comment)
        if parsed is None:
            continue
        verdicts.append(parsed)
    verdicts.sort(key=lambda verdict: verdict.at)
    return verdicts


def _binds_head(sha: str, head: str) -> bool:
    """True when `sha` names `head`, as a prefix of 7 characters or more.

    That is the width the reviewer-independence gate reads, and the width every
    verdict binding is judged at.
    """
    if not sha or not head:
        return False
    return len(sha) >= 7 and head.lower().startswith(sha.lower())


def _covers_head(verdict: PostedVerdict, head: str) -> bool:
    """True when the verdict names the head the PR stands at."""
    return any(_binds_head(binding, head) for binding in verdict.bindings)


def verdict_applies_to_head(verdict: PostedVerdict, head: str) -> bool:
    """True when a verdict is a statement about the head the PR stands at.

    A review verdict is a statement about one commit. A verdict naming another
    commit is a statement about code the PR has left: it must not hold this
    head, and it must not clear a block on it either. That is the #6263
    handback — approved at 01:01 on `177278b680f4`, handed back at 01:05
    because a `changes_requested` against `a87fc55760e9` still stood — and it
    is a staleness bug, not a reason to ask the same seat to review a head it
    never read.

    A verdict that names no head at all is not stale: there is nothing to be
    stale against, so it keeps the treatment it had before this rule and
    counts. Refusing to read it would be a review-softening change, not this
    one.
    """
    if not verdict.bindings:
        return True
    return _covers_head(verdict, head)


def _withdraws(approve: PostedVerdict, block: PostedVerdict | None) -> bool:
    """True when `approve` explicitly withdraws the block it would clear.

    DIG-5246. `#6280` merged at 12:08 on 2026-10-22 because the code reviewer's
    12:04 approve on the same head `b1c5fde73ef8` silently cleared its own
    10:21 `changes_requested`; the two blockers were still open and landed in
    `develop`. A later approve is a statement about the code, not about the
    finding, so clearing a block the same seat posted on the same, unchanged
    head needs the seat to say so on a `Withdraws:` line in that same comment.

    The line names the block by the head it names, or — for a block that names
    no head — by naming none itself. A line naming a head that is not the
    block's spends nothing. A block on a head the PR has left is already spent
    by the branch moving (`verdict_applies_to_head`), so "a new head and a fresh
    approve" needs no withdrawal.
    """
    if block is None:
        return True
    if not approve.withdrawal:
        return False
    if not approve.withdrawn_heads:
        # There is no head to name on the block, and a bare line must not spend
        # a block that names one.
        return not block.bindings
    return any(
        _binds_head(ref, binding) or _binds_head(binding, ref)
        for ref in approve.withdrawn_heads
        for binding in block.bindings
    )


def _standing_seat_blocks(pr: dict[str, Any], head: str) -> list[PostedVerdict]:
    """The blocks the seats who posted them have not cleared, oldest first.

    A blocking verdict belongs to the seat that posted it: that seat's own
    later approve naming the head the PR stands at clears it, and nothing else
    does. An approve by the same seat that names another head clears nothing —
    it says nothing about this head. Another seat's approve clears nothing
    either: `#6170` (DIG-4911) merged into `develop` on 2026-10-21 with the
    security desk's `changes requested` on the branch, because the code
    reviewer's later approve on the head was the newest readable verdict.

    An approve on the same, unchanged head as the seat's own block clears it
    only when the approve carries a `Withdraws:` line naming that block
    (`_withdraws`, DIG-5246). The head moving does the clearing on its own:
    every verdict is first scoped to the head it names
    (`verdict_applies_to_head`), and a seat that blocked a commit the PR has
    left has not asked for changes to the head it stands at now.

    A verdict whose seat cannot be read is not judged here: the seat is
    unknown, so the newest-verdict rule (`_latest_posted_verdict`) judges it.
    That is a known limitation, not a choice — 33 of the 40 readable verdicts
    on the open PRs carried no seat marker when this rule was measured.
    """
    by_seat: dict[str, list[PostedVerdict]] = {}
    for verdict in _readable_verdicts(pr):
        if verdict.seat:
            by_seat.setdefault(verdict.seat, []).append(verdict)
    standing: list[PostedVerdict] = []
    for verdicts in by_seat.values():
        block: PostedVerdict | None = None
        for verdict in verdicts:
            if verdict.verdict in APPROVE_VERDICTS:
                # Only an approve naming this head clears a block, and on an
                # unchanged head only one that withdraws it. An approve naming
                # another head says nothing about this one and leaves the block
                # alone.
                if _covers_head(verdict, head) and _withdraws(verdict, block):
                    block = None
            elif verdict_applies_to_head(verdict, head):
                block = verdict
        if block is not None:
            standing.append(block)
    standing.sort(key=lambda verdict: verdict.at)
    return standing


def _latest_posted_verdict(pr: dict[str, Any]) -> PostedVerdict | None:
    """The newest comment carrying a verdict the queue can read.

    Newest wins, so a reviewer who blocked and then came back and approved clears
    their own block. Comments the queue cannot read are skipped rather than
    counted as the newest: letting a typo'd marker displace a real block would
    hand anyone who can comment a way to unlock the queue.
    """
    verdicts = _readable_verdicts(pr)
    return verdicts[-1] if verdicts else None


def _sha_text(sha: str) -> str:
    """A sha as the queue names it in a refusal."""
    return f"`{sha[:12]}`" if sha else "no commit"


def _verdict_value_reason(pr: dict[str, Any]) -> list[str]:
    """A refusal when the newest readable verdict does not clear this PR.

    DIG-4878. A blocking verdict used to be spent the moment the commit it named
    left the branch: the gate asked `pr["commits"]` whether that commit was still
    there, and a new commit, a rebase or a merge from develop rewrites that list.
    The block was retired, the coverage gate then carried the merge on
    `reviewed:agent`, and a PR whose latest verdict was "changes requested" landed
    with no approve on the head it merged. Six digithings PRs did it between
    2026-10-20 and 2026-10-21 (#6115, #6074, #6071, #6019, #5968, #5761). The
    answer then was to count a block on any ancestor of the head; #6263 showed
    what that costs — a block on a head the PR has left holds it indefinitely,
    and only the posting seat can clear it, by re-reviewing code it never read.
    A verdict is now scoped to the head it names (`verdict_applies_to_head`), so
    the branch list still does not decide this gate and neither does an old
    verdict: a block on the current head stands, an old one does not hold it, and
    an old approve clears nothing.

    The rule reads the verdict now, not the branch, and it is one scoping step
    and two clauses, in this order. It is written down once, in
    `docs/MERGE_QUEUE.md` ("The verdict rule"), so no two seats read it
    differently:

    0. **Every verdict is scoped to the head it names.** A verdict naming another
       commit is about code the PR has left: it does not block the current head
       and it clears nothing on it. One that names no head at all cannot be
       stale, so it blocks as before.

    1. **A seat's own block stands until that seat clears it.** A blocking
       verdict belongs to the seat that posted it. That seat's later approve
       naming the head the PR stands at clears it; an approve naming another
       head does not, and no other seat's approve does either. When the approve
       names the same, unchanged head the block names, it clears the block only
       when it carries a `Withdraws:` line naming it (DIG-5246, `#6280`): an
       approve is a statement about the code, and the queue does not read it as
       a statement that the finding is withdrawn. `#6170` (DIG-4911) merged into
       `develop` on 2026-10-21 with the security desk's `changes requested` still
       on the branch, because the code reviewer's later approve on the head was
       the newest readable verdict — a second sign-off was never asked for, so
       the queue never held the PR for it.
    2. **Everything else is judged by the newest readable verdict.** The newest
       readable verdict is the one that counts: a blocking verdict blocks when
       it names the head the PR stands at (or names no head at all, which
       cannot be stale); an approve clears only when it names the head the PR
       stands at; a verdict the queue cannot read is skipped, not read as a
       clearance.

    Clause 1 needs the seat, and the seat is written only in the provenance
    marker (`agent=`): every seat pushes under one GitHub login, so a comment's
    author cannot say who wrote it. A verdict whose seat cannot be read is
    judged by clause 2 — the newest-verdict rule — because there is no seat to
    hold it to. That is a known limitation of what the marker carries, not a
    second policy.

    This is the value gate. Whether a review happened at all, and whether it came
    from another seat, is the coverage gate's question (`_review_coverage`), and
    the two stay apart on purpose (DIG-4795).
    """
    head = str(pr.get("headRefOid") or "")
    standing = _standing_seat_blocks(pr, head)
    if standing:
        return [_standing_seat_reason(pr, standing[-1], head)]
    latest = _latest_posted_verdict(pr)
    if latest is None:
        # No verdict the queue can read is not a verdict. The coverage gate
        # decides this PR, on its own evidence.
        return []
    head_text = f"`{head[:12]}`" if head else "an unknown head"
    where = f"comment {latest.comment_id}" if latest.comment_id else "a comment"
    if latest.verdict in BLOCKING_VERDICTS:
        if not verdict_applies_to_head(latest, head):
            # A block written against another head is not a statement about this
            # one (#6263): it neither holds this head nor asks for a fresh review
            # of it. The coverage gate still decides whether this PR has review
            # evidence on the head it stands at.
            return []
        if latest.scope:
            scope_text = f", scoped to `{latest.scope[:12]}`"
        elif latest.bindings:
            scope_text = f", naming `{latest.bindings[0][:12]}`"
        else:
            scope_text = ""
        return [
            f"PR #{pr.get('number')}: the latest review verdict is '{latest.verdict}' "
            f"({latest.source}, posted by {latest.author} in {where}){scope_text}; "
            f"the PR now stands at {head_text}, and a blocking "
            f"verdict stands until a later approve names the head it covers"
        ]
    if _covers_head(latest, head):
        return []
    return [
        f"PR #{pr.get('number')}: the latest review verdict is '{latest.verdict}' "
        f"({latest.source}, posted by {latest.author} in {where}) but it names "
        f"{_sha_text(latest.bindings[0] if latest.bindings else '')}, and the PR now "
        f"stands at {head_text}; an approve counts only when it names the head it covers"
    ]


def _standing_seat_reason(pr: dict[str, Any], block: PostedVerdict, head: str) -> str:
    """The refusal for a block the seat that posted it has not cleared."""
    head_text = f"`{head[:12]}`" if head else "an unknown head"
    where = f"comment {block.comment_id}" if block.comment_id else "a comment"
    if block.scope:
        scope_text = f", scoped to `{block.scope[:12]}`"
    elif block.bindings:
        scope_text = f", naming `{block.bindings[0][:12]}`"
    else:
        scope_text = ""
    later = [
        verdict
        for verdict in _readable_verdicts(pr)
        if verdict.seat == block.seat and verdict.at > block.at
    ]
    approve = later[-1] if later else None
    if (
        approve is not None
        and approve.verdict in APPROVE_VERDICTS
        and _covers_head(approve, head)
        and not _withdraws(approve, block)
    ):
        # DIG-5246: the handback for the #6280 timeline. The seat did come back
        # and approve the same head; what it did not do is say it withdraws the
        # finding, so the queue cannot read the approve as clearing it.
        if block.bindings:
            withdraw = f"`Withdraws:` line naming `{block.bindings[0][:12]}`"
        else:
            withdraw = "`Withdraws:` line"
        return (
            f"PR #{pr.get('number')}: seat {block.seat} posted '{block.verdict}' "
            f"({block.source}, in {where}){scope_text} and then approved the same "
            f"head {head_text} (comment {approve.comment_id or 'a comment'}); an "
            "approve on an unchanged head does not clear the block it left behind. "
            f"Add a {withdraw} to the approving comment, or move the PR to a new "
            "head and approve that head"
        )
    return (
        f"PR #{pr.get('number')}: seat {block.seat} posted '{block.verdict}' "
        f"({block.source}, in {where}){scope_text}, and the PR now stands at "
        f"{head_text}; a blocking verdict stands until that seat posts a later "
        f"approve naming the head it covers"
    )


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

    `_verdict_value_reason` reads `pr["comments"]`, and a PR can carry a
    `changes_requested` verdict with **no label at all** — so this is not the
    `reviewed:agent` lazy fetch's client, and it runs before both review gates rather
    than inside the coverage one.

    `#5903` merged on 2026-10-19T08:23:06Z with four review passes on it and the
    newest a `changes_requested` verdict. The gate was not wrong: run against the
    real payload it refuses. The *row* was wrong — the host tick fetched it with a
    field list that left `comments` out, so `_verdict_value_reason` read nothing,
    `_gate_review` stayed silent, and `_gate_review_coverage` authorised the merge on
    a label. The queue's own audit comment says which gate carried it:
    `review: review evidence via the coverage gate (_gate_review_coverage)`.

    An absent comment list is a missing signal, not a clearance — the sentence
    `_marker_verdict` already applies to a marker it cannot parse. So the row is
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


def _native_block_on_head(pr: dict[str, Any], head: str) -> bool:
    """True when a native `CHANGES_REQUESTED` review names the head, or no head.

    GitHub's `reviewDecision` is not scoped to a commit: it keeps saying
    `CHANGES_REQUESTED` after the branch moves, and every seat here pushes under
    one login, so the login that posted the block is also the only login that
    could approve — a stale native block is permanent. The review itself does
    name its head, in `commit.oid`, so the gate reads that.

    A review with no readable commit cannot be shown stale, and a payload with
    no review list at all is a missing signal, not a clearance: both keep the
    block, exactly as `reviewDecision` did before this rule.
    """
    reviews = pr.get("reviews")
    if not head or not isinstance(reviews, list):
        return True
    for review in reviews:
        if not isinstance(review, Mapping):
            continue
        if str(review.get("state") or "").upper() != "CHANGES_REQUESTED":
            continue
        commit = review.get("commit")
        oid = str(commit.get("oid") or "") if isinstance(commit, Mapping) else ""
        if not oid or _binds_head(oid, head):
            return True
    return False


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

    `_verdict_value_reason` is the value gate, and it runs here, before the
    coverage gate: a PR whose newest verdict blocks must not be carried to a
    merge by a `reviewed:agent` label (DIG-4878).

    Both arms are scoped to the head the PR stands at. `reviewDecision` is an
    aggregate GitHub keeps after the branch moves, and a posted verdict keeps
    its own scope; neither may hold a head it was not made against (#6263).
    """
    reasons: list[str] = []
    head = str(pr.get("headRefOid") or "")
    if str(pr.get("reviewDecision") or "").upper() == "CHANGES_REQUESTED":
        if _native_block_on_head(pr, head):
            reasons.append("review has outstanding change requests")
    # twelve-x PR #347 merged on an attestation 6m37s after a posted "changes
    # requested". A posted blocking verdict stays a block until a newer one clears it.
    reasons.extend(_verdict_value_reason(pr))
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
# Two rules keep the claim honest. The marker stands alone on its own line, so
# a sentence that quotes the marker is prose about it and not the claim. And a
# value that cannot be a record — a placeholder, a typo — is refused by name,
# never sent to the API: the API answers questions about records, and a value
# that is not one has no answer to give.
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

# The provenance marker is a claim, and a claim is a line of its own: nothing
# but the marker (and the in-session marker beside it) may share the line. A
# marker quoted inside a sentence is prose about the marker, not the claim.
# The queue used to read it as the claim — a review comment that explained the
# marker ("the gate wants a `<!-- digithings-review agent=… run=… head=… -->`
# marker") handed the queue placeholder values as if they were a seat and a
# run. The queue then asked the Paperclip API about `…`, the read failed on a
# healthy API, and the gate reported a transport failure instead of the fact
# about the marker it had in hand (DIG-4809, 21 Oct 2026).
#
# A blockquote is not a claim either: a quoted reply carries someone else's
# words, so a marker inside one says nothing about the seat that replied.
_PROVENANCE_RE = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?"
    r"(?:<!--[ \t]*in-session-review[ \t]*-->[ \t]*)?"
    r"<!--\s*digithings-review\b(?P<fields>[^>]*?)\s*-->"
    r"(?:[ \t]*<!--[ \t]*in-session-review[ \t]*-->)?[ \t\r]*$",
    re.MULTILINE,
)

#: A seat id and a run id are Paperclip uuids, and the Paperclip API accepts
#: only the RFC 4122 shapes it accepts: version 1 to 5, variant 8, 9, a or b.
#: A value outside that shape is refused by the server with a 400, and a 400
#: read as a failed read is a transport failure — so the queue checks the shape
#: itself and never sends a value the server would refuse (DIG-4809, 21 Oct
#: 2026, measured against the live API: `11111111-1111-1111-1111-…` answers
#: 400, `11111111-1111-4111-8111-…` answers 404 for a run nobody has).
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}"
    r"-[0-9a-fA-F]{12}$"
)

#: A head sha, at any length git accepts as an abbreviation.
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
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


class _AuthorUnidentified(RuntimeError):
    """A commit names a run the API would refuse, so its seat is unknown.

    A commit trailer that carries something which is not a run id cannot be
    resolved to the seat that wrote the commit. That seat is then an author
    the gate does not know about, and a seat it does not know about can post
    the review the gate is about to count as independent. The gate refuses
    rather than guesses: an author it cannot name is not an author it can
    clear.
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
    #: Whether that failure was the API not answering rather than a fact about
    #: the PR. The two are not the same: "the authoring seat could not be
    #: identified" is a statement about the commits on this branch and stays a
    #: gate; "Paperclip could not be read" says nothing about the branch and is
    #: skipped for the tick (DIG-5573).
    transient: bool = False


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
#: budget bounds the attempts of one read: the pause before the second attempt
#: and the attempt itself both happen inside it, so one path costs the budget
#: once and not once per attempt. It is a budget per path and not per tick:
#: the gate reads a ticket, a run and a pull request's runs, so a control plane
#: that does not answer costs that much again for each of them.
#:
#: The timeout is the socket timeout of one request. That is what covers the
#: case that was measured: a control plane that thinks for minutes before it
#: answers. A server that answers slowly instead of late is a different shape,
#: and a socket timeout does not bound it — the budget does, because the body
#: is read one socket read at a time (`read1`) and the deadline is checked
#: between the pieces.
#:
#: The budget was raised on 2026-10-26 (DIG-5573). The slowest answer measured
#: that day was `GET /api/issues/{id}/runs` at **119.9 s** — 41 296 bytes,
#: HTTP 200, same endpoint, same body — while the same read on two other
#: tickets in the same minute took 34.6 s and 38.9 s. The read is
#: load-dependent, not PR-dependent, and at 45 s / 60 s a 120-second answer
#: could never fit and a 35-second one left no room for the second attempt.
#:
#: The bounded window that 2026-10-26 also proposed is not available: the
#: server ignores `?limit=` on `/api/issues/{id}/runs` (identical payload at
#: `?limit=5`, measured twice), so there is no cheaper form of the same read to
#: switch to. Raising the numbers is the fix; the URL read and the facts it
#: feeds are unchanged, so the gate judges exactly what it judged before.
#:
#: A slow tick is the price. A false handback is not a neutral cost either: the
#: live driver keys its handback comment on the reasons it is given, so a
#: transient read failure that appears as a reason re-posts the comment every
#: other tick (42 handbacks on #6418 in 29 h), and the same transient can hold
#: a PR after its review has landed. A tick that waits minutes for a true
#: answer is cheaper than a tick that publishes a false one.
#:
#: The four numbers are the fix, and the suite pins them: a timeout below the
#: slowest answer measured turns a slow API back into a refusal, a budget
#: below two timeouts plus the backoff leaves no room for the second attempt
#: after a slow first one, and a backoff that hammers a struggling control
#: plane makes the second attempt likelier to fail than the first.
PAPERCLIP_READ_TIMEOUT = 150.0
PAPERCLIP_READ_BUDGET = 310.0
PAPERCLIP_READ_ATTEMPTS = 2
PAPERCLIP_RETRY_BACKOFF = 3.0

#: Where the answers are kept between ticks.
#:
#: The budget above was raised on 2026-10-26 because a slow answer read as a
#: refusal, and a refusal for a transport reason is a false handback. That fix
#: left the other half of the cost unaddressed: the reader lived for one tick,
#: so every tick asked for every fact again. The driver fires every 180 s and
#: reads every open pull request of both repos, which is ~25 tickets, ~25
#: ticket-run lists and one run per provenance trailer — at 12 s a ticket and
#: 28-144 s a ticket's run list, a tick that outran its own interval by an
#: order of magnitude. It also wrote nothing to its log until every pull
#: request had been judged, so the silence was indistinguishable from a dead
#: job (DIG-5632).
#:
#: The answers are facts about the control plane and almost all of them are
#: final. A run belongs to one seat forever. A ticket key names one id forever.
#: A ticket's run list only grows, and it grows at the end: a run that covered
#: a commit existed before that commit was written. So an answer may stand in
#: for a read for exactly the commits that were already written when the
#: answer was taken, and a commit written after it forces a fresh read. That
#: is the rule `issue_runs` applies, and it is why the cache cannot hide a run
#: that would make the reviewing seat the authoring seat.
PROVENANCE_CACHE_PATH_DEFAULT = "~/.config/digithings/merge-queue/provenance-cache.json"
#: Bumped when the shape below changes, so a cache written by an older queue is
#: read as no cache instead of as facts it does not hold.
PROVENANCE_CACHE_VERSION = 1
#: A cache is a faster queue, never an unbounded file. When it outgrows this,
#: the oldest answers go first: they are the ones the least has changed under.
PROVENANCE_CACHE_MAX_ENTRIES = 4096
#: How long "the API has no such record" is believed. A 404 is a fact about a
#: key or a run id, and a key can start existing (a ticket filed a minute ago)
#: and a run id can appear (a comment naming a run that starts after it was
#: posted), so this answer expires and the others do not.
PROVENANCE_CACHE_MISS_TTL = 60.0

#: The environment variable the driver sets to the epoch second this tick must
#: stop reading Paperclip by, and the clock reading that answers it.
#:
#: The cache above fixes the steady state; this bounds the worst one. A cold
#: cache, or a batch of branches that all moved at once, still asks for facts the
#: cache cannot answer, and one PR was measured at **313.6 s** of reads on
#: 2026-10-26 — longer than the whole 180 s interval. No budget *between* PRs can
#: bound that, because the cost is inside one PR. So the driver states a deadline
#: and the reader stops asking when it passes.
#:
#: A read past the deadline is `_PaperclipUnavailable`, which the gate already
#: treats as `transient`: nothing is concluded about the PR, nothing is published
#: as a gate, and the PR is judged again on a later tick (DIG-5573). That is the
#: same answer a slow API already gives — the difference is that it now arrives
#: before the tick has outlived its interval.
PAPERCLIP_DEADLINE_ENV = "MQ_PAPERCLIP_DEADLINE"


def _paperclip_tick_deadline() -> float | None:
    """The epoch second this tick must stop reading by, or None for no deadline.

    A value that cannot be read is no deadline: the queue must not stop answering
    because an environment value was malformed. An absent value is no deadline
    too, which is what an older driver gives a newer runner.
    """
    raw = str(os.environ.get(PAPERCLIP_DEADLINE_ENV) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


#: The stand-in for "the API answered that there is no such record". It is not
#: None, because None is a payload the JSON could hold.
_MISSING = object()

#: The fields of each answer the gate reads, and the only ones the cache keeps.
#: The answers carry more than the gate needs — a ticket body, every comment on
#: it — and this file sits beside the queue's log on this Mac, so an answer is
#: cut down to the facts before it is written down. A path that is not one of
#: the three the gate asks is not cached at all, so a future reader that wants
#: a whole answer gets the whole answer from the API.
_RUN_ANSWER_FIELDS = ("id", "agentId")
_TICKET_ANSWER_FIELDS = ("id", "identifier")
_ISSUE_RUNS_ANSWER_FIELDS = (
    "id",
    "runId",
    "agentId",
    "contextIssueId",
    "startedAt",
    "finishedAt",
)


def _answer_kind(path: str) -> str:
    """Which of the three questions `path` asks, or an empty string."""
    if path.startswith("/api/heartbeat-runs/"):
        return "run"
    if path.startswith("/api/issues/"):
        return "issue_runs" if path.endswith("/runs") else "ticket"
    return ""


def _trim_answer(path: str, payload: Any) -> Any:
    """The facts of one answer that the cache keeps, or None not to keep it."""
    kind = _answer_kind(path)
    if kind == "run" and isinstance(payload, Mapping):
        return {name: payload.get(name) for name in _RUN_ANSWER_FIELDS}
    if kind == "ticket" and isinstance(payload, Mapping):
        return {name: payload.get(name) for name in _TICKET_ANSWER_FIELDS}
    if kind == "issue_runs" and isinstance(payload, list):
        return [
            {name: run.get(name) for name in _ISSUE_RUNS_ANSWER_FIELDS}
            for run in payload
            if isinstance(run, Mapping)
        ]
    return None


class _ProvenanceCache:
    """The Paperclip answers that outlive one tick.

    The file is written on interpreter exit and only when it changed. A cache
    the queue cannot write is a slower queue, not a stopped one: every failure
    here is swallowed and the next read goes to the API.
    """

    def __init__(self, path: str, now: Any = None) -> None:
        self._path = path
        self._entries: dict[str, dict[str, Any]] = {}
        self._loaded = False
        self._dirty = False
        self._now = now or time.time

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            raw = json.loads(Path(self._path).expanduser().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict) or raw.get("version") != PROVENANCE_CACHE_VERSION:
            return
        entries = raw.get("entries")
        if not isinstance(entries, dict):
            return
        self._entries = {
            str(path): entry
            for path, entry in entries.items()
            if isinstance(entry, dict) and "at" in entry
        }

    def get(self, path: str, fresh_after: float) -> tuple[bool, float, Any]:
        """Whether `path` is known well enough, when it was taken, and the answer.

        The answer is `_MISSING` when the API said there is no such record. The
        moment is returned so a caller can keep it: an answer taken before a
        commit may not stand in for one taken after it.
        """
        self._load()
        entry = self._entries.get(path)
        if entry is None:
            return False, 0.0, None
        try:
            at = float(entry.get("at") or 0.0)
        except (TypeError, ValueError):
            return False, 0.0, None
        if at < fresh_after:
            return False, at, None
        if entry.get("missing"):
            if self._now() - at > PROVENANCE_CACHE_MISS_TTL:
                return False, at, None
            return True, at, _MISSING
        if "data" not in entry:
            return False, at, None
        return True, at, entry["data"]

    def put(self, path: str, payload: Any) -> None:
        self._load()
        self._entries[path] = {"at": self._now(), "data": payload}
        self._dirty = True
        self._prune()

    def put_missing(self, path: str) -> None:
        self._load()
        self._entries[path] = {"at": self._now(), "missing": True}
        self._dirty = True
        self._prune()

    def _prune(self) -> None:
        limit = PROVENANCE_CACHE_MAX_ENTRIES
        if len(self._entries) <= limit:
            return
        ordered = sorted(
            self._entries.items(), key=lambda item: float(item[1].get("at") or 0.0)
        )
        for path, _entry in ordered[: len(self._entries) - limit]:
            del self._entries[path]

    def flush(self) -> None:
        if not self._dirty:
            return
        self._dirty = False
        target = Path(self._path).expanduser()
        tmp = target.with_name(target.name + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps(
                    {"version": PROVENANCE_CACHE_VERSION, "entries": self._entries},
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            tmp.replace(target)
        except OSError:
            return


class ReviewerProvenance:
    """The Paperclip facts the reviewer gate needs: tickets, seats and runs.

    The queue runs from launchd with no Paperclip credential in its
    environment, so the key is read from the macOS keychain — the same
    credential `kit/bin/dt-paperclip-key` manages and the same one
    `com.digithings.decide-poll.plist` exports. The key is a header value and
    nothing else: it is never printed, logged or written anywhere.
    """

    def __init__(self, cfg: ReviewIndependence, now: Any = None) -> None:
        self._cfg = cfg
        self._token = ""
        self._now = now or time.time
        #: The answers this tick has already asked for, by path, with the moment
        #: each was taken: a later commit may need a fresher answer than an
        #: earlier one, so the moment is part of what is cached. `_MISSING` is
        #: the API's "there is no such record" and is cached like a payload.
        self._cache: dict[str, tuple[float, Any]] = {}
        self._store: _ProvenanceCache | None = (
            _ProvenanceCache(cfg.cache_path, self._now) if cfg.cache_path else None
        )
        if self._store is not None:
            atexit.register(self._store.flush)

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

    def _get(self, path: str, *, fresh_after: float = 0.0) -> Any:
        """One answer, from this tick, from the cache, or from the API.

        `fresh_after` is the latest moment the answer must be at least as new
        as to be usable: an answer taken before a commit was written may not
        name a run that covers that commit. Only `issue_runs` passes one.
        """
        cached = self._cache.get(path)
        if cached is not None:
            taken, kept = cached
            if taken >= fresh_after:
                if kept is _MISSING:
                    raise _PaperclipMissing(f"Paperclip has no {path}")
                return kept
        if self._store is not None:
            hit, taken, kept = self._store.get(path, fresh_after)
            if hit:
                if kept is _MISSING:
                    self._cache[path] = (taken, _MISSING)
                    raise _PaperclipMissing(f"Paperclip has no {path}")
                self._cache[path] = (taken, kept)
                return kept
        # The tick's budget for *asking* is spent: no read is started. Nothing is
        # concluded about the PR, so the gate defers it instead of refusing it
        # (DIG-5573). A read that has already started is left to finish on its own
        # budget — a read cut in half is a fact the cache never gets to keep, and
        # the PR then costs exactly the same on the next tick and every tick after
        # it, which is a queue that never converges.
        tick_deadline = _paperclip_tick_deadline()
        if tick_deadline is not None and time.time() >= tick_deadline:
            raise _PaperclipUnavailable(
                f"the tick's read budget is spent, so {path} was not read"
            )
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
                    # The socket timeout is the timeout of one operation on the
                    # socket, so a server that answers the headers and then
                    # trickles the body would hold the read open past the
                    # budget. `_read_response_body` reads one socket read at a
                    # time and checks the deadline between them, so the budget
                    # is the promise it says it is.
                    payload = json.loads(
                        _read_response_body(response, deadline).decode("utf-8")
                    )
            except urllib.error.HTTPError as exc:
                if exc.code in (400, 404):
                    # A fact, not a failure: the API answered, and the answer is
                    # "no such record". A ticket key that names no issue, or a run
                    # id nobody has ever heard of, is exactly what the gate has to
                    # judge — it must not be read as "the API is down".
                    #
                    # A 400 is the server refusing the address: an id that is not
                    # a shape it accepts. There is no record under that address
                    # either, so it is the same fact as the 404. Reading it as a
                    # failed read would turn a bad id in a comment into a
                    # transport failure, and a transport failure stops every
                    # merge in the queue on a healthy API (DIG-4809, 21 Oct 2026).
                    self._remember(path, _MISSING)
                    raise _PaperclipMissing(f"Paperclip has no {path}") from exc
                if exc.code < 500:
                    # 401 and 403 are the credential talking, not the record: the
                    # queue cannot read anything, so it says so.
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
                self._remember(path, payload)
                return payload
        if failure is None:
            raise _PaperclipUnavailable(
                f"Paperclip could not be read for {path}: the read budget was spent"
            )
        if isinstance(failure, urllib.error.HTTPError):
            detail = f"Paperclip answered {failure.code} for {path}"
        else:
            detail = f"Paperclip could not be read for {path}: {failure}"
        plural = "attempt" if attempts == 1 else "attempts"
        raise _PaperclipUnavailable(f"{detail} (after {attempts} {plural})") from failure

    def _remember(self, path: str, payload: Any) -> None:
        """Keep one answer for the rest of this tick, and for later ticks.

        The tick always keeps the whole answer. The file keeps only the facts
        the gate reads, and only for the three questions it asks.
        """
        self._cache[path] = (self._now(), payload)
        if self._store is None:
            return
        if payload is _MISSING:
            self._store.put_missing(path)
            return
        trimmed = _trim_answer(path, payload)
        if trimmed is not None:
            self._store.put(path, trimmed)

    def ticket(self, key: str) -> dict[str, Any] | None:
        """The Paperclip issue behind a ticket key, or None when there is none."""
        try:
            data = self._get(f"/api/issues/{key}")
        except _PaperclipMissing:
            return None
        return data if isinstance(data, dict) else None

    def issue_runs(
        self, issue_id: str, *, fresh_after: float = 0.0
    ) -> list[dict[str, Any]]:
        """Every run that happened on one issue.

        `fresh_after` is the moment the answer must be at least as new as: the
        newest commit on the pull request the answer is about to judge. A run
        list read at T holds every run that covered a commit written before T,
        because a run starts before the commit it covers, so the answer is
        exactly as good as a fresh read for those commits. A commit written
        after T is not covered by that promise and asks for a fresh read.
        """
        try:
            data = self._get(
                f"/api/issues/{issue_id}/runs", fresh_after=fresh_after
            )
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
                # A uuid is the same uuid whatever case it is written in, and
                # the API accepts either, so the gate compares one spelling.
                agent=str(fields.get("agent") or "").lower(),
                run=str(fields.get("run") or "").lower(),
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
            agent = match.group("agent")
            if not _UUID_RE.match(agent):
                # The trailer names something the API would refuse, so the seat
                # that wrote this commit is unknown. An unknown seat can be the
                # author of the very review the gate is about to count, so the
                # gate refuses instead of dropping the seat silently
                # (DIG-4809, 21 Oct 2026).
                raise _AuthorUnidentified("a commit names a seat id that is not one")
            authors.add(agent.lower())
        for match in _RUN_TRAILER_RE.finditer(body):
            run_id = match.group("run")
            if not _UUID_RE.match(run_id):
                raise _AuthorUnidentified("a commit names a run id that is not one")
            run = prov.run(run_id.lower())
            seat = str((run or {}).get("agentId") or "").lower()
            if seat:
                authors.add(seat)
    key = _ticket_key(pr)
    ticket = prov.ticket(key) if key else None
    if ticket:
        issue_id = str(ticket.get("id") or "")
        stamps = _author_dates(pr)
        # The run list may be taken from a cache only for the commits that were
        # already written when it was read. A run that covered such a commit
        # existed by then, so the answer names it; a run that started after the
        # answer was taken cannot have covered an older commit, and a commit
        # written after the answer forces the fresh read that sees it. Reads a
        # tick apart ask the same question, so this is the difference between
        # ~25 slow reads a tick and none (DIG-5632).
        known = max((_parse_ts(stamp) or 0.0) for stamp in stamps) if stamps else 0.0
        counts: dict[str, int] = {}
        for run in prov.issue_runs(issue_id, fresh_after=known):
            seat = str(run.get("agentId") or "").lower()
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

    A value that cannot be a record — a placeholder, a typo, a quoted example —
    is judged by name and never sent to the API. The API answers questions
    about records; a value that is not one has no answer, and asking turns the
    fact the gate holds into a failed read (DIG-4809, 21 Oct 2026).
    """
    problems: list[str] = []
    if not marker.head:
        problems.append(
            f"names no head SHA, so it says nothing about the head `{head[:12]}` "
            "this PR stands at"
        )
    elif not _SHA_RE.match(marker.head):
        problems.append(
            f"names head `{marker.head[:12]}`, which is not a commit SHA, "
            f"so it says nothing about the head `{head[:12]}` this PR stands at"
        )
    elif not _head_binds(marker.head, head):
        problems.append(
            f"names head `{marker.head[:12]}` while this PR stands at `{head[:12]}`"
        )
    reviewer = ""
    if marker.run:
        if not _UUID_RE.match(marker.run):
            # A value that is not a run id is not a record the API could ever
            # know, so it is never sent. Asking anyway turns a fact about the
            # marker into a failed read — and a failed read is a transport
            # failure, which stops every merge in the queue on a healthy API.
            problems.append(
                f"names run `{marker.run[:12]}`, which is not a run id, "
                "so no run was checked"
            )
        else:
            run = prov.run(marker.run)
            if run is None:
                problems.append(
                    f"names run `{marker.run[:8]}`, which the Paperclip API does not know"
                )
            else:
                reviewer = str(run.get("agentId") or "").lower()
                if not reviewer:
                    # The run is known, but it names no seat. The marker claims
                    # a seat and a run, and neither of them can be checked, so
                    # the gate cannot say who reviewed: that is a missing
                    # signal, not a clearance.
                    problems.append(
                        "names a run that carries no seat, so the queue cannot say "
                        "who reviewed"
                    )
                elif marker.agent and not _UUID_RE.match(marker.agent):
                    problems.append(
                        f"names seat `{marker.agent[:12]}`, which is not a seat id, "
                        f"so it cannot be checked against run `{marker.run[:8]}`"
                    )
                elif marker.agent and marker.agent != reviewer:
                    problems.append(
                        f"names seat `{marker.agent[:8]}` while run `{marker.run[:8]}` "
                        f"belongs to seat `{reviewer[:8]}`"
                    )
    elif marker.agent:
        if not _UUID_RE.match(marker.agent):
            problems.append(
                f"names seat `{marker.agent[:12]}`, which is not a seat id, "
                "so it names no seat the queue could check"
            )
        else:
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
            transient=True,
        )
    except _AuthorUnidentified as exc:
        # The commit names an author the gate cannot resolve. The seat that
        # wrote it may be the seat that posted the review, so the gate cannot
        # show the review to come from another seat and says so.
        return Independence(
            disqualified=every_marker,
            unverifiable=(
                f"the PR's authoring seat could not be identified: {exc}, so no "
                "review on it can be shown to come from a different seat"
            ),
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
            transient=True,
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
    """Write what the gate refused, and what the row would have merged on.

    A shadow log that cannot be written is a lost measurement, not a reason to
    change a verdict: the gate already decided, so it keeps its hands off the
    merge.
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
) -> tuple[list[str], str, str]:
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
      `--attest-review` is gone (2026-10-17), and no separate formal approval is
      demanded on top of the evidence (Chris's 2026-10-15 definition). But an
      in-session pass is only evidence when another seat wrote it: the reviewer
      independence gate (DIG-4795) drops a comment whose provenance marker names
      the PR's author seat or cannot be checked at all, and DIG-5220 shipped that
      gate in `enforce` mode after #6277 and #6197 merged on the authoring lane's
      own write-up.
    * The comments this gate scores are supplied by `fetch_queue` and, when the
      row arrives without them, completed by `_ensure_comments` — which runs
      before this function precisely because an unreadable review record must
      fail here rather than be read as "no verdict was posted". The lazy fetch
      below survives only as a defence for callers that hand in a raw row. An
      unreadable comments read fails closed, for the same reason an absent
      check fails closed: the alternative reads "no evidence" as "approved".

    Returns `(reasons, evidence, deferred)`. The third value is a fact the gate
    could not read — the Paperclip API did not answer — and it is kept apart
    from `reasons` on purpose: a reason is a statement about the branch and is
    published as a gate, while a failed read says nothing about the branch at
    all. The caller records it and skips the PR for this tick (DIG-5573).
    """
    crc = _coverage_module()
    labels = _label_names(pr)
    comments = pr.get("comments")
    if crc.AGENT_REVIEW_LABEL in labels and comments is None:
        if repo is None:
            return [
                "review coverage: `reviewed:agent` is set but the findings "
                "comment cannot be verified without a repo to read it from"
            ], "", ""
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
            ], "", ""
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

    # The gate always decides on the comments it accepted. Shadow mode keeps the
    # measurement — it records what the gate refused, and what the row would have
    # said with every comment counted — but it is no longer a licence to merge on
    # the marker the gate just refused. DIG-5220 made that change after #6277 and
    # #6197: in both, the authoring lane's own write-up was counted as the review
    # and the PR merged with no other seat's look at the final head.
    reviewed, why = crc.verdict_for(state_for(kept))
    if mode == "shadow":
        would_review, would_why = crc.verdict_for(state_for(counted))
        if independence.unverifiable:
            _log_shadow(
                cfg,
                pr,
                repo,
                [f"could not check the review seats: {independence.unverifiable}"],
            )
        elif independence.problems:
            lines = list(independence.problems)
            if would_review:
                # The measurement that matters: without this gate the row would
                # have merged on the evidence it just refused.
                lines.append(f"without this gate the row would have merged on {would_why}")
            _log_shadow(cfg, pr, repo, lines)

    if reviewed:
        evidence = why
        if independence.note:
            evidence = f"{evidence}; {independence.note}"
        elif independence.problems:
            evidence = (
                f"{evidence}; {len(independence.disqualified)} review marker(s) did "
                "not count"
            )
        return [], evidence, ""

    if independence.unverifiable:
        if independence.transient:
            # Not a reason: the queue could not read the facts, so it concluded
            # nothing about the review. It says so to the log and skips this PR
            # for the tick; publishing it would state a gate the branch never
            # failed (DIG-5573).
            return [], "", f"reviewer independence: {independence.unverifiable}"
        # A fact about this PR, not about the API: the commits do not name the
        # seat that wrote them, so no review can be shown to come from another
        # seat. The remedy is on the branch, so it is a gate.
        return [f"reviewer independence: {independence.unverifiable}"], "", ""
    if independence.problems:
        head = str(pr.get("headRefOid") or "")[:12]
        return [
            "reviewer independence: "
            + "; ".join(independence.problems[:3])
            + " — the queue needs a review from a different seat, on the head "
            f"this PR stands at (`{head}`)"
        ], "", ""
    return [
        f"review coverage: {why} — the queue needs a review pass that left its "
        "findings on the PR, the same evidence scripts/check_review_coverage.py "
        "enforces at promotion (completed Bot run, a reviewer bot such as "
        "CodeRabbit or Copilot, an in-session review with its findings comment, "
        "an approval, or reviewed:owner)"
    ], "", ""


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

    reasons.extend(_gate_checks(pr, policy, repo=repo))
    # The verdict gate reads the review record, so the row is completed before either
    # review gate runs. `_review_coverage`'s own lazy fetch is not enough on its own:
    # it runs *after* `_gate_review` and so cannot repair a row that `_gate_review`
    # has already read as verdict-free — which is how #5903 was authorised on a
    # label while a `changes_requested` verdict stood (#5903 post-mortem).
    unreadable = _ensure_comments(pr, repo)
    if unreadable:
        reasons.append(unreadable)
    reasons.extend(_gate_review(pr))
    coverage_reasons, review_evidence, deferred = _review_coverage(
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
    # how a queue burns its own capacity. A deferred fact is in the same class: the
    # queue could not judge that gate, so it must not spend a run as if the branch
    # were merely behind. Read off the finished `reasons` rather than re-testing each
    # gate, so a gate added later cannot silently become updatable.
    stale_base_only = state == "BEHIND" and reasons == [stale_reason] and not deferred

    rollup = _rollup(pr)
    return Verdict(
        number=int(pr.get("number", 0)),
        title=str(pr.get("title") or ""),
        head_ref=str(pr.get("headRefName") or ""),
        created_at=str(pr.get("createdAt") or ""),
        head_sha=str(pr.get("headRefOid") or ""),
        # An unread gate is not a cleared gate: a PR the queue could not judge is
        # never eligible, whether or not it also failed a gate it could judge.
        eligible=not reasons and not deferred,
        reasons=tuple(reasons),
        review_evidence=review_evidence,
        checks=tuple(
            f"{_check_name(e)}={e.get('conclusion') or e.get('state') or '?'}" for e in rollup
        ),
        stale_base_only=stale_base_only,
        deferred=deferred,
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
    deferred = [v for v in verdicts if v.deferred]
    # A row with a reason is published whatever else is wrong with the read: the
    # reason is a gate the branch failed, and only the read failure is held back.
    blocked = [v for v in verdicts if not v.eligible and v.reasons]
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
    # Deferred, not blocked: the queue could not read a fact it needs, so it
    # concluded nothing and nobody has to act. Kept out of `reasons` on purpose —
    # that list is what the handback comment publishes as gates, and a transport
    # failure is not a statement about the branch (DIG-5573).
    if deferred and not queued_only:
        print(
            f"\ndeferred ({len(deferred)}) — the queue could not read a fact it "
            "needs, which says nothing about these branches; nothing is published "
            "for them and the next tick asks again:"
        )
        for v in deferred:
            print(f"  #{v.number} {v.head_ref} — {v.title}")
            print(f"       · {v.deferred}")


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
            blocked = [v for v in verdicts if not v.eligible and v.reasons]
            deferred = [v for v in verdicts if v.deferred]
            if blocked:
                print(f"\nblocked ({len(blocked)}) — see `list` for reasons")
            if deferred:
                print(
                    f"\ndeferred ({len(deferred)}) — a fact the queue could not read; "
                    "not a gate, nothing published, retried next tick"
                )
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
    finally:
        # The tick is over: the counts the index holds are written out, so the
        # next tick knows what the log already says.
        _flush_provenance_index()


if __name__ == "__main__":
    raise SystemExit(main())

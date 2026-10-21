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
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
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

#: DIG-4809 names this switch: the environment wins over the policy file, so the
#: mode can be changed on the running host without a code change.
PROVENANCE_MODE_ENV = "MQ_CI_PROVENANCE"
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
#: The allowed hosts, read once per queue run from the deployment's own files.
_HOST_CACHE: dict[tuple[Any, ...], tuple[tuple[str, ...], str]] = {}
#: The log index, by the path it is written to.
_INDEX_CACHE: dict[str, dict[str, Any]] = {}

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
        ci_provenance=_load_ci_provenance(raw.get("ci_provenance"), path),
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


@dataclass(frozen=True)
class Provenance:
    """The outcome of reading one status as evidence of a build.

    `reason` says what is wrong in words that do not change from tick to tick.
    The live driver keys its handback comment on the reason text, so a reason
    that carried the build's number would post a fresh comment on the pull
    request every time the CI ran. `detail` holds the volatile part - the build
    number, the shas, the URL - and it goes to the log, never to the verdict.
    """

    ok: bool
    reason: str
    detail: str = ""
    target_url: str = ""


def provenance_mode(policy: Policy) -> str:
    """The mode in force. The environment wins over the policy file.

    An unreadable value is treated as `enforce`, not as `off`: a typo in the
    switch that decides whether the queue trusts a status must not silence the
    gate. `off` has to be spelled correctly to switch it off.
    """
    raw = str(os.environ.get(PROVENANCE_MODE_ENV) or "").strip().lower()
    if not raw:
        return policy.ci_provenance.mode
    if raw not in PROVENANCE_MODES:
        return PROVENANCE_ENFORCE
    return raw


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
        if name.strip() == key:
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
    except OSError:
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
        except OSError as exc:
            problems.append(
                f"{path_str} could not be read ({exc.strerror or type(exc).__name__})"
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
    """One read-only GET against the Woodpecker API.

    Returns the HTTP status and the decoded body. A transport failure is
    reported as status 0, because "the API could not be read" and "the build is
    not there" are different answers and an operator needs to tell them apart.

    Nothing a posted status can put in the URL may kill the tick: the read
    catches everything, because a queue that dies on a crafted `target_url`
    stops merging for everybody.
    """
    cached = _READ_CACHE.get(url)
    if cached is not None:
        return cached
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    try:
        with _WOODPECKER_OPENER.open(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            status = int(response.status)
            final_url = response.geturl()
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
        if code in (301, 302, 303, 307, 308):
            # The redirect was refused: the answer of another host is not the
            # answer of ours, and the token would have gone with it.
            result = (0, "the request was redirected")
        else:
            result = (code, None)
    except Exception as exc:  # a status must never kill a tick
        result = (0, f"{type(exc).__name__}: {exc}")
    else:
        if final_url != url:
            result = (0, "the request was redirected")
        else:
            try:
                result = (status, json.loads(body or "null"))
            except json.JSONDecodeError:
                result = (status, None)
    _READ_CACHE[url] = result
    return result


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

    The name is resolved against the Woodpecker API, because a repository that
    was recreated carries a new id: a number written down in the policy then
    points at a different repository, or at nothing, and the gate reads the
    wrong build. The number in the policy is the fallback for an API that
    cannot be read, which is the safe direction - a stale number refuses a
    pull request, it does not merge one.
    """
    if name:
        url = f"{base_url}/api/repos/lookup/{name}"
        status, payload = _woodpecker_read(url, token, timeout=timeout)
        if status == 200 and isinstance(payload, Mapping):
            resolved = str(payload.get("id") or "").strip()
            if resolved:
                return resolved, ""
    if static_id:
        return static_id, ""
    return "", f"the Woodpecker repository {name or 'named by the policy'} could not be resolved"


def verify_ci_provenance(
    pr: Mapping[str, Any],
    policy: Policy,
    repo: str | None,
    *,
    mode: str | None = None,
    context: str = "",
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
    expected_id = ""
    if kind == "id":
        expected_id, resolve_problem = _resolve_woodpecker_repo_id(
            expected_name,
            static_id,
            f"{scheme}://{parsed.netloc}",
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
        if named_repo != expected_id:
            return Provenance(
                False,
                f"the target_url names the Woodpecker repository {named_repo!r}, "
                f"not {expected_id!r}",
                target_url=target,
            )

    api_url = f"{scheme}://{parsed.netloc}/api/repos/{expected_id}/pipelines/{number}"
    status, payload = _woodpecker_read(api_url, token, timeout=timeout)
    build = f"{expected_id}#{number}"
    detail = f"build {build} at {target}"
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
            "the build named by the status does not exist",
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
            "the build named by the status has not finished",
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
            f"the build named by the status has no '{step}' step, so it says nothing "
            f"about {repo or 'this repository'}",
            detail=detail,
            target_url=target,
        )
    if len(states) > 1:
        return Provenance(
            False,
            f"the build named by the status has more than one '{step}' step, so it "
            f"says nothing about {repo or 'this repository'}",
            detail=detail,
            target_url=target,
        )
    state = next(iter(states))
    if state != "success":
        return Provenance(
            False,
            f"the '{step}' step of the build named by the status is {state}",
            detail=detail,
            target_url=target,
        )

    commit = str(payload.get("commit") or "").strip().lower()
    head = str(pr.get("headRefOid") or "").strip().lower()
    if not head:
        return Provenance(
            False,
            "the pull request head sha is unknown, so no build can be matched to it",
            detail=detail,
            target_url=target,
        )
    if not commit:
        return Provenance(
            False,
            "the build named by the status reports no commit, so it cannot be matched "
            "to the head",
            detail=detail,
            target_url=target,
        )
    if commit != head:
        return Provenance(
            False,
            "the build named by the status ran another commit",
            detail=f"{detail} ran commit {commit[:12]}, not the head {head[:12]}",
            target_url=target,
        )

    return Provenance(
        True,
        f"the build named by the status ran '{step}' for {repo or 'this repository'} "
        "at the head commit",
        detail=f"{detail} at commit {head[:12]} (build status {build_status})",
        target_url=target,
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
    oldest_allowed = datetime.now(timezone.utc) - timedelta(
        days=PROVENANCE_INDEX_MAX_AGE_DAYS
    )
    stale: list[str] = []
    for entry_key, entry in index.items():
        stamp = str(entry.get("last_seen") or entry.get("first_seen") or "")
        try:
            seen = datetime.fromisoformat(stamp)
        except ValueError:
            stale.append(entry_key)
            continue
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
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


def _log_has_lines(path: Path) -> bool:
    """Whether the log still holds lines.

    A log that was rotated away, or emptied, makes the index a memory of
    nothing: the refusals it remembers are not in the file any more, so they
    are written again.
    """
    try:
        return path.stat().st_size > 0
    except OSError:
        return False


def _log_provenance(
    pr: Mapping[str, Any],
    repo: str | None,
    required: str,
    reason: str,
    detail: str,
    mode: str,
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
    """
    verb = "would refuse" if mode == PROVENANCE_SHADOW else "refuses"
    line = (
        f"CI provenance ({mode}): PR #{pr.get('number', 0)} {repo or '?'} — "
        f"{verb} '{required}': {reason}"
    )
    if detail:
        line += f" — {detail}"
    print(line, file=sys.stderr)
    path = Path(os.environ.get(PROVENANCE_LOG_ENV) or PROVENANCE_LOG_PATH)
    key = f"{repo or '?'}|{pr.get('number', 0)}|{required}|{reason}"
    index = _provenance_index()
    stamp = datetime.now(timezone.utc).isoformat()
    entry = index.get(key)
    if entry is not None and _log_has_lines(path):
        entry["count"] = int(entry.get("count") or 1) + 1
        entry["last_seen"] = stamp
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_provenance_log(path)
        handle = os.fdopen(
            os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a",
            encoding="utf-8",
        )
        with handle:
            handle.write(f"{stamp} {line}\n")
        os.chmod(path, 0o600)
    except OSError:
        # The log is a convenience, never a gate. A queue that cannot write it
        # must still refuse, and must still say why on stderr.
        pass
    index[key] = {"count": 1, "first_seen": stamp, "last_seen": stamp, "reason": reason}
    _prune_index(index)
    _flush_provenance_index()


def _rotate_provenance_log(path: Path) -> None:
    """Keep the provenance log to one file of one size.

    The log grows by one line per pull request per tick, so an uncapped file
    grows without bound. The oldest file is dropped, not the newest: what the
    window needs is the recent lines.
    """
    try:
        if path.stat().st_size < PROVENANCE_LOG_MAX_BYTES:
            return
    except OSError:
        return
    try:
        path.replace(path.with_name(path.name + ".1"))
    except OSError:
        pass


def _gate_ci_provenance(
    pr: Mapping[str, Any], policy: Policy, repo: str | None, required: str
) -> list[str]:
    """The reasons a status is not evidence. Empty when it is."""
    mode = provenance_mode(policy)
    if mode == PROVENANCE_OFF:
        return []
    result = verify_ci_provenance(pr, policy, repo, mode=mode, context=required)
    if result.ok:
        return []
    _log_provenance(pr, repo, required, result.reason, result.detail, mode)
    if mode == PROVENANCE_SHADOW:
        return []
    return [
        f"required check '{required}' has no verified Woodpecker provenance: {result.reason}"
    ]


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
    crc._apply_reviews_checks_comments(
        state,
        reviews=_evidence_reviews(pr),
        checks=_rollup(pr),
        comments=comments if isinstance(comments, list) else [],
    )
    reviewed, why = crc.verdict_for(state)
    if reviewed:
        return [], why
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
    coverage_reasons, review_evidence = _review_coverage(pr, repo)
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
    finally:
        # The tick is over: the counts the index holds are written out, so the
        # next tick knows what the log already says.
        _flush_provenance_index()


if __name__ == "__main__":
    raise SystemExit(main())

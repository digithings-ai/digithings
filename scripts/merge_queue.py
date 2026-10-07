#!/usr/bin/env python3
"""Merge queue for develop branches that have no server-side merge queue.

GitHub's native merge queue is configured *through* branch protection, so it is
unavailable to any private repository on a Free plan. That is the situation in
``digithings-ai/twelve-x`` and in every other private repo we own; the survey and
the evidence are in ``docs/MERGE_QUEUE.md``. This script is the queue for those
branches: it reads the open PRs targeting a base, evaluates each against the
gates the absent server-side rules would have enforced, and merges the eligible
ones one at a time in creation order, re-reading the queue after every merge.

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
    review_path: tuple[str, ...]
    blocked_bases: tuple[str, ...]
    merge_method: str
    delete_branch: bool
    required_checks: tuple[str, ...]
    ignored_checks: frozenset[str] = frozenset()
    required_checks_by_repo: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

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
        review_path=tuple(raw.get("review_path", ())),
        blocked_bases=tuple(raw["blocked_bases"]),
        merge_method=defaults.get("merge_method", "squash"),
        delete_branch=bool(defaults.get("delete_branch", True)),
        required_checks=tuple(defaults.get("required_checks", ())),
        ignored_checks=frozenset(defaults.get("ignored_checks", ())),
        # Reject a non-string entry rather than coercing it: a typo'd check name is
        # the exact failure DIG-690 was, and `str(42)` would turn that into a gate
        # that silently matches nothing.
        required_checks_by_repo={
            str(repo): tuple(str(name) for name in names)
            for repo, names in (raw.get("required_checks_by_repo") or {}).items()
        },
    )


def _gh_json(*args: str) -> Any:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise QueueError(f"gh {' '.join(args[:2])} failed: {proc.stderr.strip() or proc.stdout}")
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
        "comments,commits",
    )
    if not isinstance(prs, list):
        raise QueueError(f"gh pr list did not return a list for {repo}:{base}")
    return sorted(prs, key=lambda p: (p.get("createdAt", ""), p.get("number", 0)))


def _check_name(entry: dict[str, Any]) -> str:
    # CheckRun carries `name`; StatusContext (external CI) carries `context`. gh
    # normalises most fields, but a third-party integration can post either.
    return str(entry.get("name") or entry.get("context") or "")


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
        for entry in pr.get("statusCheckRollup") or []:
            reported.add(_check_name(entry))
    if not reported:
        # Nothing ran anywhere. That is CI being absent, not a naming mistake, and
        # conflating the two would send the reader to the policy file.
        return (), ()
    return tuple(r for r in required if r not in reported), tuple(sorted(reported))


def _gate_checks(pr: dict[str, Any], policy: Policy) -> list[str]:
    """Required checks must have reported, and must have passed. No exceptions."""
    rollup = pr.get("statusCheckRollup") or []
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
        # not a passing build. Require the evidence to come from a workflow run.
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
    """A refusal when the newest readable posted verdict blocks this exact head."""
    latest = _latest_readable_verdict(pr)
    if latest is None:
        return []
    comment, verdict, scope_sha = latest
    if verdict not in BLOCKING_VERDICTS:
        return []
    if not _on_pr_history(pr, scope_sha):
        return []
    login = str((comment.get("author") or {}).get("login") or "?")
    where = (
        f"comment {comment.get('id') or '?'}" if comment.get("id") else f"a comment from {login}"
    )
    scope = scope_sha[:12] if scope_sha else "an unstated commit"
    return [
        f"a code-review verdict of '{verdict}' was posted on this PR by {login} "
        f"({where}) against {scope}, and that commit is still on this branch; "
        "a new review must clear it"
    ]


def _gate_review(pr: dict[str, Any], acting_role: str, attest_role: str | None) -> list[str]:
    """Satisfied by an approving review from someone else, or by another role's attestation."""
    reasons: list[str] = []
    if str(pr.get("reviewDecision") or "").upper() == "CHANGES_REQUESTED":
        reasons.append("review has outstanding change requests")

    # A blocking verdict is checked before the approval shortcut below. An approving
    # review is a way *past* this gate, not a waiver of it: twelve-x PR #347 carried
    # `--attest-review qa` and a posted "changes requested", and it merged.
    reasons.extend(_posted_verdict_reason(pr))

    author = str((pr.get("author") or {}).get("login") or "")
    reviews = pr.get("reviews") or []
    approved_by_other = any(
        str(r.get("state") or "").upper() == "APPROVED"
        and str((r.get("author") or {}).get("login") or "") != author
        # A bot's APPROVED is a linter saying it found no problems, not a person
        # taking responsibility for the change. GitHub's own review summary
        # ignores bot reviews for the same reason.
        and not str((r.get("author") or {}).get("login") or "").endswith("[bot]")
        for r in reviews
    )
    if approved_by_other:
        return reasons

    # No usable approval. Someone has to stand behind the review, and it cannot be
    # the role doing the merging: on this org every agent shares one GitHub login,
    # so a role that authored a PR is indistinguishable from one that did not. The
    # role is therefore asserted explicitly, and self-attestation is refused.
    if attest_role is None:
        reasons.append("no approving review from a non-author; needs --attest-review <role>")
    elif attest_role == acting_role:
        reasons.append(
            f"attested by '{acting_role}', which is also the merging role; "
            "attestation must come from a different role"
        )
    return reasons


def evaluate(
    pr: dict[str, Any],
    policy: Policy,
    *,
    base: str,
    acting_role: str,
    attest_role: str | None,
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
    if state in STALE_MERGE_STATES:
        reasons.append(f"mergeStateStatus={state} (base moved since the checks ran)")

    reasons.extend(_gate_checks(pr, policy))
    reasons.extend(_gate_review(pr, acting_role, attest_role))

    rollup = pr.get("statusCheckRollup") or []
    return Verdict(
        number=int(pr.get("number", 0)),
        title=str(pr.get("title") or ""),
        head_ref=str(pr.get("headRefName") or ""),
        created_at=str(pr.get("createdAt") or ""),
        head_sha=str(pr.get("headRefOid") or ""),
        eligible=not reasons,
        reasons=tuple(reasons),
        checks=tuple(
            f"{_check_name(e)}={e.get('conclusion') or e.get('state') or '?'}" for e in rollup
        ),
    )


def evaluate_all(
    prs: list[dict[str, Any]],
    policy: Policy,
    *,
    base: str,
    acting_role: str,
    attest_role: str | None,
) -> list[Verdict]:
    """Every PR, in queue order, with its verdict."""
    verdicts = [
        evaluate(pr, policy, base=base, acting_role=acting_role, attest_role=attest_role)
        for pr in prs
    ]
    verdicts.sort(key=Verdict.order_key)
    return verdicts


def _audit_body(
    verdict: Verdict, authority: Authority, policy: Policy, attest_role: str | None
) -> str:
    checks = "\n".join(f"- `{c}`" for c in verdict.checks) or "- (no checks reported)"
    review = f"attested by `{attest_role}`" if attest_role else "approving review from a non-author"
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
    parser.add_argument(
        "--attest-review",
        default=None,
        help="role standing behind the review when no non-author approval exists",
    )
    parser.add_argument("--limit", type=int, default=50, help="max PRs to inspect")
    parser.add_argument("--max-merges", type=int, default=1, help="max merges in run mode")
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

    if args.attest_review is not None and args.attest_review not in policy.review_path:
        print(
            f"merge_queue: '{args.attest_review}' is not in the review path "
            f"({', '.join(policy.review_path)}).",
            file=sys.stderr,
        )
        return EXIT_NOT_AUTHORISED

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
                attest_role=args.attest_review,
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
                _audit_body(head, authority, policy, args.attest_review),
            )
            merged.append(head)
            print(f"merged #{head.number} {head.head_ref} as {authority.role}")

        if not merged:
            print("nothing merged — no PR passed the queue gates")
        if len(merged) < args.max_merges:
            # The loop drained, so `verdicts` is the queue as it stands now and the
            # blocked list is worth showing. When --max-merges cut the run short,
            # `verdicts` still lists what we just merged, and printing it would
            # report a landed PR as queued.
            print_queue(verdicts, queued_only=False)
        else:
            print("`list` shows the current queue.")
        return EXIT_OK
    except QueueError as exc:
        print(f"merge_queue: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL


if __name__ == "__main__":
    raise SystemExit(main())

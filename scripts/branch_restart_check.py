#!/usr/bin/env python3
"""Refuse a new branch that rebuilds work already in flight on another branch.

DIG-1589, implementing the control designed in
``docs/ops/2026-10-06-d8c5-restart-root-cause.md`` § 7. The finding was that
branch-hygiene policy § 6.4 ("abandon the existing branch with a written reason
rather than forking again") had no lookup and no gate, so it shipped as a
reminder to be careful. This module is the lookup; ``scripts/hooks/pre-push.sh``
is the gate.

The lookup is git itself rather than a registry of in-flight branches: a registry
is a second source of truth that drifts and needs an owner, whereas patch-ids on
unmerged remote branches already answer "is this work in flight?" and the reason
travels with the commit.

Usage::

    python3 scripts/branch_restart_check.py <candidate-ref>

Exits 1 and prints the refusal — with each sibling branch, its tip and the
overlap count — to stderr when the candidate should not be pushed, and 0
otherwise. Anything it cannot decide fails *open* with a loud note; see
``_fail_open``.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# The base a candidate is measured against. Work already in develop is done, and
# only work that is not in develop can still be resumed.
BASE_REF = "origin/develop"

# Why the threshold is 3 and not 1. The d8c5 sibling branches shared a 40-commit
# unmerged base, so any two leaves cut in the same area share at least one
# patch-id — a threshold of 1 would refuse honest parallel work every time. A
# large shared *unmerged* stack is the signal that separates "I am about to redo
# work that is still in flight" from "I am working next to someone".
MIN_UNMERGED_PATCH_OVERLAP = 3

# Branches never treated as "work in flight that someone else is holding":
#   main, develop             — the integration branches themselves.
#   module/*                  — protected by the module-branch-protection
#                               ruleset and the accumulation point for a
#                               component's work, so overlapping one is the
#                               normal case rather than a restart.
#   release/*                 — release lines; work there is not resumed.
#   release-please--branches--  — accumulated release-please commits whose
#                               individual patch-ids are already in develop
#                               while the branch tip is not. Requiring these to
#                               be "reachable from develop" would not filter
#                               them, and a branch that holds nothing in flight
#                               must not appear as a sibling.
#   bot/*                     — pushed by project-stub-fields.yml and friends.
#                               Machine refs overlap constantly, and an
#                               operator cannot act on a refusal naming one.
PROTECTED_BRANCH_PREFIXES = (
    "main",
    "develop",
    "module/",
    "release/",
    "release-please--branches--",
    "bot/",
)

# Escape read from the push environment. A genuine resume names the branch it
# continues, so that branch must not also be the one it is compared against —
# otherwise resuming a resume re-imposes the refusal the escape exists to lift.
RESUME_FROM_ENV = "RESUME_FROM"

# Escape read from the tip commit message or the push environment. Also the key
# of the commit trailer the pre-push hook already reads via %(trailers:key=...).
RESTART_REASON_KEY = "RESTART_REASON"

_RESTART_REASON_RE = re.compile(rf"^\s*{RESTART_REASON_KEY}:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)

# Prefixes that are spellings of the same branch rather than part of its name.
_REF_PREFIXES = ("refs/remotes/", "refs/heads/", "refs/tags/")


@dataclass(frozen=True)
class Sibling:
    """An unmerged remote branch sharing patch-ids with the candidate."""

    branch: str
    tip: str
    overlap: int


@dataclass(frozen=True)
class Decision:
    """Outcome of one guard evaluation.

    ``reason`` is written for the session about to fork: it names what tripped
    the guard, the evidence, and both ways forward. ``notes`` carry the
    fail-open path and any applied escape; they are printed even when the push
    proceeds, so an allowed push still leaves a trace in the run log.
    """

    allowed: bool
    reason: str = ""
    siblings: tuple[Sibling, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)


class _Unknown(Exception):
    """The guard could not evaluate the candidate, so it must fail open."""


# ── pure helpers ─────────────────────────────────────────────────────────────


def normalize_branch_ref(name: str) -> str:
    """Reduce a branch name to the spelling ``for-each-ref`` reports for origin/*.

    ``RESUME_FROM`` arrives from a shell command line, where the same branch can
    be typed four ways. Every spelling has to compare equal or the escape fails
    to match and the refusal reads as "the guard is broken".
    """
    value = name.strip()
    for prefix in _REF_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix) :]
    if value.startswith("origin/"):
        value = value[len("origin/") :]
    return value.rstrip("/")


def is_protected_branch(name: str) -> bool:
    """True for branches that must never count as duplicate work in flight."""
    branch = normalize_branch_ref(name)
    return any(
        branch == prefix or branch.startswith(prefix) for prefix in PROTECTED_BRANCH_PREFIXES
    )


def parse_restart_reason(message: str) -> str | None:
    """Extract a ``RESTART_REASON`` value from a commit message, or ``None``.

    A trailer is the documented spelling; a body line is also accepted, because
    it is what an agent writes when it amends the tip mid-thought and it carries
    the same intent. Only a whole line counts, so prose that merely mentions the
    key ("add a line reading ``RESTART_REASON: <one line>``") does not clear the
    guard. A bare label with no value is rejected too — that records that a gate
    exists, not why this restart is legitimate, which is the same rule the hook
    applies to its ``Human-Approved-By`` trailer.
    """
    match = _RESTART_REASON_RE.search(message)
    return match.group(1).strip() if match else None


def format_refusal(
    branch: str,
    candidate_ids: int,
    siblings: Sequence[Sibling],
    resume_from: str | None,
) -> str:
    """Build the refusal text: the evidence, then the two ways forward."""
    lines = [
        f"pre-push: refusing to push '{branch}' — it rebuilds work that is still in flight.",
        f"         {siblings[0].overlap} of its {candidate_ids} unmerged patch-ids already exist"
        " on another unmerged branch:",
    ]
    for sibling in siblings:
        lines.append(
            f"           {sibling.branch} (tip {sibling.tip[:8]}) shares {sibling.overlap} of them"
        )
    lines.append("         Resume before you create — cut from the branch above and push with:")
    if resume_from:
        lines.append(f"           RESUME_FROM={resume_from}")
    elif siblings:
        lines.append(f"           RESUME_FROM={normalize_branch_ref(siblings[0].branch)}")
    lines.append("         Or, if this really is new work, record why and push again:")
    lines.append(f"           {RESTART_REASON_KEY}: <one line>")
    lines.append("         in the tip commit message, or in the push environment.")
    return "\n".join(lines)


# ── git plumbing ─────────────────────────────────────────────────────────────


def _run(repo: os.PathLike[str] | str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )


def _git(repo: os.PathLike[str] | str, *args: str) -> str:
    """Run git in ``repo`` and return stdout; raise ``_Unknown`` on failure."""
    proc = _run(repo, *args)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise _Unknown(
            f"`git {args[0]}` failed: {detail[-1] if detail else f'exit {proc.returncode}'}"
        )
    return proc.stdout


def _is_reachable_from_base(repo: os.PathLike[str] | str, tip: str) -> bool:
    """True when ``tip`` is already merged into ``origin/develop``.

    ``git merge-base --is-ancestor`` returns 0 (reachable), 1 (not reachable) and
    128 for an unknown ref. Only the last is an error, and it means we cannot
    tell a merged branch from an unmerged one — which must fail open rather than
    guess, because guessing "unmerged" manufactures siblings that do not exist.
    """
    proc = _run(repo, "merge-base", "--is-ancestor", tip, BASE_REF)
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    raise _Unknown(
        f"`git merge-base --is-ancestor` failed: {proc.stderr.strip() or proc.returncode}"
    )


def unmerged_patch_ids(repo: os.PathLike[str] | str, candidate: str) -> set[str]:
    """Patch-ids the candidate holds that ``origin/develop`` does not.

    ``git cherry origin/develop <candidate>`` is the cheap way to find which
    commits are still in flight, but it prints *commit shas*, and a rebuilt
    branch has different shas for the same diff — comparing them would find
    nothing and the guard would never fire. So the cherry-picked range is piped
    through ``git patch-id --stable``, which hashes the diff itself, and those
    hashes are what "same work" means here.

    ``--pretty=format:%H`` is load-bearing: it is the sha each patch-id line is
    attributed to, and without it ``patch-id`` attributes every patch to the
    zero sha. A merge commit in the range contributes no patch (git shows none
    by default), so it is counted as neither work in flight nor overlap.
    """
    patches = _run(repo, "log", "-p", "--pretty=format:%H", candidate, f"^{BASE_REF}")
    if patches.returncode != 0:
        detail = (patches.stderr or "").strip().splitlines()
        raise _Unknown(f"`git log -p` failed: {detail[-1] if detail else patches.returncode}")
    if not patches.stdout.strip():
        return set()
    ids = subprocess.run(
        ["git", "patch-id", "--stable"],
        cwd=str(repo),
        input=patches.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    if ids.returncode != 0:
        detail = (ids.stderr or "").strip().splitlines()
        raise _Unknown(f"`git patch-id` failed: {detail[-1] if detail else ids.returncode}")
    return {line.split()[0] for line in ids.stdout.splitlines() if line.split()}


def unmerged_remote_branches(repo: os.PathLike[str] | str) -> list[tuple[str, str]]:
    """Return ``(branch, tip)`` for every origin/* branch still holding work.

    Reachability comes from ``%(ahead-behind:origin/develop)``, which reports
    ahead/behind counts for every ref in a *single* ``for-each-ref``. Asking
    git one question per ref instead cost 19s on this repo's 478 remote refs —
    far too slow for a hook that runs on every push, and slow enough that people
    would reach for ``--no-verify``. Ahead == 0 means fully merged, which is the
    same test ``merge-base --is-ancestor`` answers, at a fraction of the cost.

    Branches with fewer unmerged commits than the threshold are skipped here: a
    branch holding 1 or 2 commits cannot overlap a candidate by 3, so computing
    its patch-ids would be work that cannot change the answer. That prunes 420
    unmerged refs to 179 on this repo today.
    """
    listing = _git(
        repo,
        "for-each-ref",
        "--format=%(refname:short) %(objectname) %(ahead-behind:origin/develop)",
        "refs/remotes/origin",
    )
    branches: list[tuple[str, str]] = []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        branch, tip, ahead_behind = parts[0], parts[1], parts[2]
        # origin/HEAD is a symbolic placeholder, not a branch.
        if branch in ("origin", "origin/HEAD") or is_protected_branch(branch):
            continue
        ahead = ahead_behind.split()[0] if ahead_behind else "0"
        if ahead.isdigit() and int(ahead) < MIN_UNMERGED_PATCH_OVERLAP:
            continue
        if _is_reachable_from_base(repo, tip):
            continue
        branches.append((branch, tip))
    return branches


def tip_commit_message(repo: os.PathLike[str] | str, candidate: str) -> str:
    return _git(repo, "log", "-1", "--format=%B", candidate)


# ── the guard ────────────────────────────────────────────────────────────────


def _fail_open(note: str) -> Decision:
    """Allow the push, loudly.

    This guard is a second line of defence, not the only one. Failing closed
    would turn every offline push, every clone that has not fetched
    ``origin/develop``, and every missing ``python3`` into a hard block on work
    that never had a duplicate to begin with. The hook's live-trading arm fails
    closed on an unresolvable diff base because that one stands between an edit
    and production money; nothing here is at stake at that level, so this fails
    open and says so.
    """
    return Decision(allowed=True, notes=(note,))


def check(
    repo: os.PathLike[str] | str,
    candidate: str,
    *,
    branch_name: str | None = None,
    env: Mapping[str, str] | None = None,
    base: str = BASE_REF,
    is_update: bool = False,
) -> Decision:
    """Decide whether ``candidate`` may be pushed.

    ``branch_name`` is the name the ref will have on the remote, when the caller
    knows it; it excludes the candidate from its own sibling set. ``env``
    supplies ``RESUME_FROM`` and ``RESTART_REASON``.

    ``is_update`` says the remote already holds this ref, which the caller reads
    from a non-zero remote sha. The guard is about *creation*: a second branch
    holding work already in flight. Once a branch exists, its unmerged stack
    keeps overlapping the same siblings at every later commit, so a sibling
    check on an update would refuse ordinary follow-up work. That is why this
    returns before the first git call and says nothing — there is no decision to
    report, and a note on every update push would bury the refusals that matter.
    """
    if is_update:
        return Decision(allowed=True)

    environ = os.environ if env is None else env
    try:
        tip = _git(repo, "rev-parse", "--verify", f"{candidate}^{{commit}}").strip()

        # Escape 1: a reason in the push environment.
        reason = (environ.get(RESTART_REASON_KEY) or "").strip()
        if reason:
            return Decision(
                allowed=True,
                notes=(
                    f"branch-restart-check: {RESTART_REASON_KEY} from the push environment: {reason}",
                ),
            )

        # Escape 2: a reason in the tip commit message, where it survives to the
        # next session reading the branch.
        reason = parse_restart_reason(tip_commit_message(repo, candidate))
        if reason:
            return Decision(
                allowed=True,
                notes=(
                    f"branch-restart-check: {RESTART_REASON_KEY} from the tip commit message: {reason}",
                ),
            )

        # A tip already merged into develop holds nothing in flight.
        if _is_reachable_from_base(repo, tip):
            return Decision(
                allowed=True,
                notes=(
                    f"branch-restart-check: {tip[:8]} is already in {base}; no duplicate work.",
                ),
            )

        candidate_ids = unmerged_patch_ids(repo, candidate)
        if not candidate_ids:
            return Decision(allowed=True)

        resume_from = (environ.get(RESUME_FROM_ENV) or "").strip()

        # Branches excluded from the sibling set: the candidate's own name, plus
        # any branch named by RESUME_FROM. Both are exclusions — neither replaces
        # the other, so this is a set rather than a single value. Omitting the
        # candidate's own name is the bug that made the guard refuse ordinary
        # follow-up commits: origin/<branch> already holds the shared stack, so
        # every branch under active development would overlap itself and become
        # unpushable.
        excluded = set()
        if branch_name:
            excluded.add(normalize_branch_ref(branch_name))
        if resume_from:
            excluded.add(normalize_branch_ref(resume_from))

        siblings: list[Sibling] = []
        for branch, sibling_tip in unmerged_remote_branches(repo):
            # The candidate against itself is not duplicate work. On a push to a
            # branch that already exists upstream, origin/<branch> holds the same
            # stack one commit behind; on a re-push at the same tip, the tips are
            # equal. Either way it is this branch, not someone else's work.
            if sibling_tip == tip or normalize_branch_ref(branch) in excluded:
                continue
            overlap = len(candidate_ids & unmerged_patch_ids(repo, branch))
            if overlap >= MIN_UNMERGED_PATCH_OVERLAP:
                siblings.append(Sibling(branch=branch, tip=sibling_tip, overlap=overlap))

        if not siblings:
            return Decision(allowed=True)

        siblings.sort(key=lambda s: (-s.overlap, s.branch))
        name = branch_name or candidate
        return Decision(
            allowed=False,
            reason=format_refusal(name, len(candidate_ids), siblings, resume_from or None),
            siblings=tuple(siblings),
        )
    except _Unknown as exc:
        return _fail_open(f"branch-restart-check: duplicate-work guard skipped — {exc}.")
    except Exception as exc:
        # The guard must never be the reason a push fails. `_Unknown` above is
        # the failure we expected; anything else is a bug in this file or an
        # unexpected shape from git, and the hook reads a non-zero exit as a
        # deliberate refusal. Failing open here costs a duplicate leaf once; a
        # traceback reaching the hook costs every agent a blocked push.
        return _fail_open(
            f"branch-restart-check: the duplicate-work guard could not decide, "
            f"so it did not block the push — {type(exc).__name__}: {exc}."
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="branch_restart_check.py",
        description=(
            "Refuse a new branch that rebuilds work already in flight on another "
            "unmerged branch. Exits 1 on refusal, 0 otherwise."
        ),
    )
    parser.add_argument("candidate", help="the branch ref (or any commit-ish) being pushed")
    parser.add_argument("--branch-name", default=None, help="name the ref will have on the remote")
    parser.add_argument("--repo", default=".", help="repository to inspect (default: cwd)")
    # Both spellings are accepted so the caller states which kind of push this
    # is. Leaving it implicit in the checker is what made the arm refuse every
    # update to an unmerged branch.
    push_kind = parser.add_mutually_exclusive_group()
    push_kind.add_argument(
        "--is-create",
        dest="is_update",
        action="store_false",
        default=False,
        help="the remote does not hold this ref yet, so this push creates it (default)",
    )
    push_kind.add_argument(
        "--is-update",
        dest="is_update",
        action="store_true",
        help="the remote already holds this ref, so this push updates it and is not refused",
    )
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        # argparse exits 2 on a usage error, and the hook reads any non-zero exit
        # as a deliberate refusal — so an argument it cannot parse would block the
        # push. The reachable case is a version skew: install-hooks.sh installs the
        # hook from origin/develop while this file is resolved from the working
        # tree, so a checkout that has not pulled yet pairs the new hook with a
        # checker that does not know --is-update. Fail open and say why; `git pull`
        # is the fix.
        if not exc.code:
            raise
        print(
            "branch-restart-check: the duplicate-work guard could not read its "
            f"arguments, so it did not block the push — run 'git pull' so the hook "
            f"and this checker are the same revision."
        )
        return 0

    decision = check(
        args.repo,
        args.candidate,
        branch_name=args.branch_name,
        is_update=args.is_update,
    )
    for note in decision.notes:
        print(note)
    if not decision.allowed:
        print(decision.reason, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

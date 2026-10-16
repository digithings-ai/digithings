#!/usr/bin/env python3
"""Tell the operator that the branch they are pushing has gone stale.

DIG-1579, implementing prevention step 3 of ``docs/ops/branch-hygiene-policy.md``
(§ 6, item 3). That section asks for "a non-blocking warning when a branch being
pushed is older than 10 days, so an agent gets told at push time instead of at
deletion time". § 6, item 1 measures the same problem from the other end: with
``delete_branch_on_merge`` off, 288 branches had accumulated by 2026-10-06 and
the disposal work is what this warning exists to make unnecessary.

This module is the lookup and ``scripts/hooks/pre-push.sh`` is the gate — the
same split ``scripts/branch_restart_check.py`` already uses for the DIG-1589
duplicate-work guard. Two properties are not negotiable, so they are stated here
rather than left to the caller:

1. **It never blocks.** Every path returns 0, including a traceback. The hook
   wires this arm to ``|| true`` so a crash in the warning cannot read as a
   refusal and strand a push.
2. **It never touches the network.** Both inputs — the tip's commit time and the
   unmerged patch count — are read from local git state. A pre-push hook that
   called the network is a hook operators disable with ``--no-verify``, which
   would take the live-trading co-sign gate down with it.

The tier it reports is the policy's own measure: **unmerged patches**, not commit
count. ``git rev-list --count origin/develop..<branch>`` counts commits whose
patch already reached develop by a squash, so § 2 rules it out by name; this
module uses ``git cherry`` so the number is patch-id based and invariant to
squash, rebase and reordering.

Usage::

    python3 scripts/branch_age_warning.py <candidate-ref> --branch-name <name>
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass

# The base a candidate is measured against. Work already in develop is done, and
# only work that is not in develop can still be resumed or disposed of.
BASE_REF = "origin/develop"

# § 6, item 3 names this threshold and § 6, item 2 uses the same 10 days for the CI guard, so
# the two agree by construction. Changing it here without changing the Worker
# would give an operator two different answers for one branch.
STALE_AFTER_DAYS = 10
STALE_AFTER_SECONDS = STALE_AFTER_DAYS * 24 * 60 * 60

# Policy § 5: "Never delete, never count as stranded". A stale-branch *warning*
# on one of these would contradict the policy that exempts it — `module/*` is an
# accumulation point whose age is normal, and a `release/v*` line staying quiet
# between patches is the only way it stays patchable for a pinned client. So
# they are silent rather than merely harmless.
#
# Split in two on purpose. `main` and `develop` are the only two names the policy
# lists as whole refs, and matching them with a prefix test would also silence
# `mainline-anything` / `develop-tools`, which are ordinary work branches. Every
# entry in the prefix tuple carries its own separator, so `startswith` cannot
# reach past the boundary it names.
EXCLUDED_BRANCH_EXACT = (
    "main",
    "develop",
)
EXCLUDED_BRANCH_PREFIXES = (
    "module/",
    "release/v",
    "chore/sync-module-",
)

POLICY_DOC = "docs/ops/branch-hygiene-policy.md"


@dataclass(frozen=True)
class Tier:
    """One row of the policy § 3 tier table."""

    label: str
    action: str
    owner: str


# § 3, transcribed. The upper bound is inclusive because the policy states the
# bands as ranges ("3-10", ">10"); the table is walked in order so a patch count
# lands in exactly one tier, which is what "lands in exactly one tier" in § 3
# requires.
TIERS: tuple[tuple[int, Tier], ...] = (
    (0, Tier("T0 - free", "delete, no approval", "anyone with write access")),
    (2, Tier("T1 - small", "delete after a snapshot check", "the agent that owns the branch")),
    (10, Tier("T2 - decide", "explicit PR-or-discard decision per branch", "EM")),
)


class _Unknown(Exception):
    """The warning could not be evaluated, so it says nothing and does not block."""


# ── pure helpers ─────────────────────────────────────────────────────────────


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def humanise_age(seconds: int) -> str:
    """Render an age in days, the unit the threshold and the policy both use.

    Days everywhere below 48h keeps the output aligned with ``STALE_AFTER_DAYS``:
    a reader comparing against the 10-day rule must not have to convert hours.
    """
    if seconds < 0:
        # A commit dated in the future means the clock or the commit metadata is
        # wrong. Report the raw value rather than "0 minutes", which would read
        # as a measurement.
        return f"{seconds}s (commit dated in the future)"
    if seconds < 60:
        return _plural(seconds, "second")
    minutes = seconds // 60
    if minutes < 60:
        return _plural(minutes, "minute")
    hours = minutes // 60
    if hours < 48:
        return _plural(hours, "hour")
    return _plural(hours // 24, "day")


def is_excluded_branch(name: str) -> bool:
    """True for the refs policy § 5 exempts from the stranded set."""
    value = (name or "").strip()
    if value in EXCLUDED_BRANCH_EXACT:
        return True
    return any(value.startswith(prefix) for prefix in EXCLUDED_BRANCH_PREFIXES)


def tier_for(patches: int) -> Tier:
    """The § 3 tier a branch carrying ``patches`` unmerged patches lands in."""
    for upper, tier in TIERS:
        if patches <= upper:
            return tier
    return Tier("T3 - escalate", "CTO decision per branch", "CTO")


def warning_lines(
    branch: str,
    age_seconds: int,
    patches: int | None,
    tier_note: str = "",
) -> list[str]:
    """The message, as the lines the hook prints.

    Kept pure and separate from ``main`` so the wording is pinned by a unit test
    instead of only by the shell suite. The three things the operator needs in
    order to act are always present: how old, which tier, where the rule lives.
    """
    if patches is None:
        tier_text = f"tier unknown ({tier_note or 'unmerged patch count unavailable'})"
    else:
        tier = tier_for(patches)
        tier_text = (
            f"{_plural(patches, 'unmerged patch')} -> tier {tier.label} "
            f"({tier.action}; owner: {tier.owner})"
        )

    return [
        f"pre-push: warning - branch '{branch}' last commit is {humanise_age(age_seconds)} old.",
        f"         {tier_text}.",
        f"         Policy: {POLICY_DOC} (section 3 for tiers, section 6, item 3 for this warning).",
        "         Non-blocking: the push proceeds. Nothing is refused by this warning.",
    ]


# ── git access ───────────────────────────────────────────────────────────────


def _run(repo: os.PathLike[str] | str, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        # ``--repo`` can name a directory that is not there, and a missing cwd
        # makes subprocess raise before git is ever started. Left as-is it
        # escapes the ``returncode`` check below and is reported as an
        # "unexpected failure", which reads like a bug in this module instead of
        # a wrong argument. Either way it stays non-blocking; this only makes
        # the one line it prints true.
        raise _Unknown(f"cannot run git in {repo!r}: {exc.strerror or exc}") from exc


def _git(repo: os.PathLike[str] | str, *args: str) -> str:
    """Run git in ``repo`` and return stdout; raise ``_Unknown`` on failure."""
    proc = _run(repo, *args)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise _Unknown(
            f"`git {args[0]}` failed: {detail[-1] if detail else f'exit {proc.returncode}'}"
        )
    return proc.stdout


def tip_commit_time(repo: os.PathLike[str] | str, candidate: str) -> int:
    """Epoch seconds of the tip commit — the branch's age, read locally.

    ``%ct`` is the committer date as an integer, so no timezone or locale can
    change the answer. The hook passes the sha it is about to publish, which is
    the tip of the branch the remote will end up holding; re-resolving a branch
    *name* would read whatever the local checkout happens to point at.
    """
    raw = _git(repo, "log", "-1", "--format=%ct", candidate).strip()
    if not raw.isdigit():
        raise _Unknown(f"`git log -1 --format=%ct` returned {raw!r}, not an epoch")
    return int(raw)


def unmerged_patch_count(repo: os.PathLike[str] | str, candidate: str) -> int:
    """``git cherry`` ``+`` count against develop — the policy § 2 measure.

    Counting in python rather than shelling to ``grep -c`` keeps the exit status
    honest: ``grep -c`` prints ``0`` and exits 1 on no match, which under
    ``set -o pipefail`` is indistinguishable from the command having failed.
    """
    out = _git(repo, "cherry", BASE_REF, candidate)
    return sum(1 for line in out.splitlines() if line.startswith("+"))


# ── entry point ──────────────────────────────────────────────────────────────


def _evaluate(repo: str, candidate: str, branch_name: str, now: float) -> list[str]:
    """The warning to print, or ``[]`` when there is nothing to say.

    Order matters. Age first, because it is the only thing the § 6, item 3 rule turns
    on and the only measurement that has no repository-wide dependency; the
    patch count is only spent once a branch is already known to be stale.
    """
    # ``int`` here, not at the formatting end: ``now`` is ``time.time()``'s float
    # while ``%ct`` is an integer, and their difference carries the fraction
    # through to the operator as "40.0 days". The measurement is in whole
    # seconds — that is what ``%ct`` gives — so the unit conversion belongs here
    # where the measurement is taken.
    age_seconds = int(now - tip_commit_time(repo, candidate))
    if age_seconds < STALE_AFTER_SECONDS:
        return []

    try:
        patches: int | None = unmerged_patch_count(repo, candidate)
        tier_note = ""
    except _Unknown as exc:
        # The age is still worth reporting. Silently dropping the whole message
        # would make a stale branch look fine whenever origin/develop is missing.
        patches = None
        tier_note = f"{exc}; run 'git fetch origin' and push again for the tier"

    return warning_lines(branch_name, age_seconds, patches, tier_note)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="branch_age_warning.py",
        description=(
            "Warn when the branch being pushed is older than 10 days. Never "
            "blocks: every path exits 0."
        ),
    )
    parser.add_argument("candidate", help="the branch ref (or any commit-ish) being pushed")
    parser.add_argument("--branch-name", default=None, help="name the ref will have on the remote")
    parser.add_argument("--repo", default=".", help="repository to inspect (default: cwd)")
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        # argparse exits 2 on a usage error. This module never blocks, so there is
        # nothing to translate here — but a traceback would print to stderr on a
        # path that runs on every push, so keep it to one line.
        if not exc.code:
            raise
        print("branch-age-warning: could not read its arguments; skipping the warning.")
        return 0

    branch_name = args.branch_name or args.candidate
    if is_excluded_branch(branch_name):
        return 0

    try:
        lines = _evaluate(args.repo, args.candidate, branch_name, time.time())
    except _Unknown as exc:
        # Unknown tip, or a repository git cannot answer for. A warning is not
        # worth a failed push, so say so once and let the push through.
        print(f"branch-age-warning: skipped — {exc}.")
        return 0
    except Exception as exc:  # pragma: no cover - defensive, and still non-blocking
        print(f"branch-age-warning: skipped — unexpected failure: {exc}.")
        return 0

    for line in lines:
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

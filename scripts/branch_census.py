#!/usr/bin/env python3
"""Census stale branches by unmerged patches, and tell landed work from live work.

`docs/ops/branch-hygiene-policy.md` § 2 measures a branch with ``git cherry``
(patch-id based, so a rebase or a reorder does not change the answer) and § 3
counts the tier populations from that measure. This module is the executable
form of both, so the numbers in the policy are reproducible instead of quoted.

Two things it does that ``git cherry`` on its own cannot do:

1. **It counts unresolvable branches as unresolvable.** A branch whose ref is
   gone from the remote cannot be measured. Reporting it as ``0`` patches would
   understate the population; reporting it as a patch count would invent one. It
   is counted in the census total and excluded from the patch total, and both
   numbers are always printed side by side.

2. **It separates "landed" from "recoverable".** ``git cherry`` is *patch-id*
   based, which is exactly why it is invariant to squash **as a patch identity**
   and exactly why it is *not* a proof of landing: a squash merge rewrites the
   patch (new parent context, new message) while keeping the diff, so a branch
   whose work shipped by squash can still report ``+`` for every commit it had.
   Measured on ``claude/digithings-web-ui-refactor`` (PR #4791, merged into
   develop): **144 patches** read as unmerged on a branch that had already
   merged. The landed signal is per-PR and squash-aware -- see
   :func:`pr_land_state`.

Usage::

    python3 scripts/branch_census.py --tsv docs/ops/2026-10-06-stranded-branch-triage.tsv
    python3 scripts/branch_census.py --markdown          # table for a doc or a comment
    python3 scripts/branch_census.py --no-gh             # git only; no landed column

Exit codes: 0 census ran, 2 usage/IO error. It never exits non-zero because a
branch is old -- a census reports, it does not enforce.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field

# The GitHub remote is named `github`; `origin` is a cursor mirror that carries
# none of the branches under census. Measured 2026-10-15: `github/develop`
# exists, `origin/develop` does not.
REMOTE = "github"

# The base unmerged patches are measured against. Section 2 of the policy says
# develop explicitly, and § 5 excludes `main` and `develop` themselves.
BASE = "develop"

# Tier thresholds from policy § 3, expressed on the *measured* patch count.
# The census re-derives the tier and reports drift against the recorded tier
# rather than trusting the recorded one: a tier recorded on 2026-10-06 is a
# claim about that day's tree, not about this one.
TIERS: tuple[tuple[str, int, int], ...] = (
    # (label, min_inclusive, max_inclusive) -- None max means unbounded
    ("T0", 0, 0),
    ("T1", 1, 2),
    ("T2", 3, 10),
    ("T3", 11, None),
)

# Section 5 exclusions. These are never counted as stranded, so their patches
# are reported separately rather than inside the recoverable total.
EXCLUSIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("main/develop", re.compile(r"^(main|develop)$")),
    ("module/**", re.compile(r"^module/")),
    ("chore/sync-module-*", re.compile(r"^chore/sync-module-")),
    ("release/v*", re.compile(r"^release/v\d")),
)

# `merge_commit_sha` is non-NULL on a closed-unmerged PR too: GitHub records the
# *test* merge commit it computed for the PR. Six of the 42 census PRs read
# `merged=false` with a non-NULL `merge_commit_sha`, and treating that field as
# the landed flag marks them landed. `merged` is the only landed flag.
_MERGED_TRUE = True


@dataclass
class BranchRow:
    """One census row, with every field that could have been wrong made explicit."""

    branch: str
    recorded_tier: str
    pr_number: str
    # The TSV column is `commits_not_in_develop` -- a COMMIT count, which is the
    # measure policy section 2 rejects. It is kept for provenance and named for
    # what it is; nothing derives a tier or a patch count from it.
    recorded_commits: int
    # None means "could not be measured" and is never rendered as 0.
    ref: str | None = None
    patches: int | None = None
    landed: str | None = None  # "landed" | "not-landed" | "no-pr" | "unresolved"
    pr_base: str | None = None
    exclusion: str | None = None
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# The measure. Both functions below are pure so the tests can pin them without
# a git repo or a network.
# --------------------------------------------------------------------------


def count_unmerged_patches(cherry_stdout: str) -> int:
    """Count the ``+`` lines of ``git cherry`` output.

    Line-anchored on purpose. The obvious spelling is
    ``stdout.count("\\n+")``, and it is wrong by exactly one on any branch whose
    FIRST output line is a ``+`` -- which is the common case, since the tip
    commit is usually the unmerged one. Measured on the 43 resolvable T2
    branches of the 2026-10-06 census: ``count("\\n+")`` returned 119 and the
    line-anchored count returned 162, a difference of exactly 43 -- one per
    branch, with the same refs and the same base both times. That uniform delta
    is the signature of a counting bug rather than of drift, and it is why this
    function splits lines instead of searching a substring.

    Matched on the sign **and its trailing space**, which is the whole grammar
    ``git cherry`` emits -- ``+ <sha>`` or ``- <sha>``, one line per commit, and
    nothing else. A bare ``startswith("+")`` also accepts ``+++ b/path``, the
    unified-diff line: text that ``git cherry`` cannot produce, so counting it
    would mean a caller had handed this function diff output and gotten a
    number instead of an error. Tightening the predicate is free -- the census
    total over the 71 resolvable branches of the 2026-10-06 census is 826
    patches under both spellings -- and it makes the counter unable to be fed
    the wrong format.

    ``-`` lines are patches already applied under a *different* sha; ``+`` lines
    are patches with no counterpart on the base.
    """
    return sum(1 for line in cherry_stdout.splitlines() if line.startswith("+ "))


def count_applied_patches(cherry_stdout: str) -> int:
    """Count the ``-`` lines: patches present on the base under another sha.

    Same sign-plus-space grammar as :func:`count_unmerged_patches`; the two
    together must account for every line git emits, which is what the live
    control test asserts.
    """
    return sum(1 for line in cherry_stdout.splitlines() if line.startswith("- "))


def classify_tier(patches: int | None) -> str | None:
    """Map a measured patch count onto the policy's tiers.

    Returns ``None`` for an unmeasurable branch. An unresolvable ref is not a
    T0: T0 means "measured, zero unmerged patches", and conflating the two is
    how a vanished branch ends up deleted as free.
    """
    if patches is None:
        return None
    for label, low, high in TIERS:
        if patches >= low and (high is None or patches <= high):
            return label
    raise AssertionError(f"patch count {patches} matched no tier")


def short_tier(recorded: str | None) -> str:
    """Reduce a census tier label to its bare name.

    The 2026-10-06 TSV writes ``T0-free`` / ``T1-small`` / ``T2-decide`` /
    ``T3-cto``. Grouping by those raw strings makes a reader count four tiers
    they cannot match against policy section 3's ``T0``..``T3`` table, so the
    label is reduced to its first token. An unknown or missing label is
    returned as ``?`` and never silently folded into a real tier: a row whose
    tier nobody can read is a gap in the census, not a T0.
    """
    token = (recorded or "").strip().split("-", 1)[0].strip().upper()
    if token in {label for label, _, _ in TIERS}:
        return token
    return "?"


def exclusion_for(branch: str) -> str | None:
    """Return the section-5 exclusion that covers ``branch``, else ``None``."""
    for label, pattern in EXCLUSIONS:
        if pattern.match(branch):
            return label
    return None


def pr_land_state(*, merged: object, merge_commit_sha: str | None, on_own_base: bool) -> str:
    """Decide whether a PR's work is on its base, without trusting one field.

    Three inputs and three traps:

    * ``merged`` -- not ``merge_commit_sha is not None``. GitHub publishes a
      test-merge sha on a closed-unmerged PR, so the latter marks shipped work
      that never shipped.
    * ``on_own_base`` -- ``merge-base --is-ancestor`` of the merge commit against
      the PR's *own* ``base.ref``. Nine of the 42 census PRs merged into
      ``main``, ``module/digiquant`` or ``module/digichat``, not develop;
      checking develop for those answers a question nobody asked.
    * A squash merge has no second parent, so ancestry of the *branch head* is
      the wrong question. The merge commit is the one object that exists on the
      base for either merge style.
    """
    if not merged:
        return "not-landed"
    if merge_commit_sha is None:
        # merged=true with no merge commit: recorded, never inferred either way.
        return "merged-no-merge-commit"
    return "landed" if on_own_base else "merged-not-on-base"


# --------------------------------------------------------------------------
# git / gh plumbing. Every subprocess failure degrades to "unmeasurable" and
# records why; nothing here invents a value.
# --------------------------------------------------------------------------


def _run(argv: Sequence[str], *, cwd: str | None = None) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            argv, capture_output=True, text=True, cwd=cwd, check=False
        )
    except OSError as exc:  # missing binary -- a 127 is not a result
        return 127, "", str(exc)
    return p.returncode, p.stdout, p.stderr


def remote_refs(cwd: str | None = None) -> set[str]:
    """Every remote-tracking ref name, live and archived, as git spells them."""
    rc, out, _ = _run(["git", "for-each-ref", "--format=%(refname:short)", "refs/remotes"], cwd=cwd)
    if rc != 0:
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def resolve_ref(branch: str, refs: Iterable[str], remote: str = REMOTE) -> str | None:
    """Resolve a census branch name to a local ref, live first then archived.

    Archive refs win nothing and lose nothing here -- the point is only that a
    branch whose head ref was deleted still resolves if § 4 clause 5 pushed it
    to ``refs/archive/<branch>`` before disposal. Order matters for reporting
    only: a branch present both ways is reported live.
    """
    refs = set(refs)
    for candidate in (f"{remote}/{branch}", f"{remote}/archive/{branch}"):
        if candidate in refs:
            return candidate
    return None


def measure_patches(ref: str, base: str = BASE, remote: str = REMOTE, cwd: str | None = None) -> tuple[int | None, str | None]:
    """Return ``(unmerged, applied)`` for ``ref``, or ``(None, None)`` on failure."""
    rc, out, err = _run(["git", "cherry", f"{remote}/{base}", ref], cwd=cwd)
    if rc != 0:
        return None, err.strip()[:200] or f"git cherry rc={rc}"
    return count_unmerged_patches(out), count_applied_patches(out)


def is_ancestor(sha: str, ref: str, cwd: str | None = None) -> bool | None:
    """``git merge-base --is-ancestor``; ``None`` when the sha is unresolvable.

    rc 0 -> True, rc 1 -> False. A third value (128, "not a valid object name")
    means the object was never fetched, which is a void measurement and must not
    be reported as a negative.
    """
    rc, _, _ = _run(["git", "merge-base", "--is-ancestor", sha, ref], cwd=cwd)
    if rc == 0:
        return True
    if rc == 1:
        return False
    return None


def fetch_pr(pr: int, repo: str) -> dict | None:
    """Fetch the PR fields the landed signal needs. ``None`` when unreachable."""
    gh = os.environ.get("GH_BIN") or "/opt/homebrew/bin/gh"
    rc, out, _ = _run([
        gh, "api", f"repos/{repo}/pulls/{pr}",
        "--jq", "{n:.number,merged:.merged,base:.base.ref,mcs:.merge_commit_sha}",
    ])
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------
# Census
# --------------------------------------------------------------------------


def read_tsv(path: str) -> list[dict[str, str]]:
    """Read the triage TSV by column NAME, never by position.

    The column that matters most is the patch column, and it is the one whose
    name this reads rather than whose index this assumes. On the 2026-10-06
    census the 4th column is ``commits_not_in_develop`` -- the measure section 2
    calls the wrong one. A positional read of "column 3 is patches" silently
    reads a commit count.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _int_or_zero(value: str | None) -> int:
    try:
        return int((value or "").strip())
    except ValueError:
        return 0


def census(
    rows: Sequence[dict[str, str]],
    *,
    refs: Iterable[str] | None = None,
    remote: str = REMOTE,
    base: str = BASE,
    repo: str | None = None,
    cwd: str | None = None,
) -> list[BranchRow]:
    """Measure every census row. ``repo=None`` skips the landed column entirely."""
    refset = remote_refs(cwd) if refs is None else set(refs)
    out: list[BranchRow] = []
    pr_cache: dict[str, dict | None] = {}

    for raw in rows:
        branch = (raw.get("branch") or "").strip()
        if not branch:
            continue
        row = BranchRow(
            branch=branch,
            recorded_tier=(raw.get("tier") or "").strip(),
            pr_number=(raw.get("pr_number") or "").strip(),
            recorded_commits=_int_or_zero(raw.get("commits_not_in_develop")),
            exclusion=exclusion_for(branch),
        )
        ref = resolve_ref(branch, refset, remote)
        if ref is None:
            row.landed = "unresolved"
            row.notes.append("no live or archive ref")
            out.append(row)
            continue
        row.ref = ref
        if "archive/" in ref:
            row.notes.append("archive ref only")
        patches, err = measure_patches(ref, base, remote, cwd)
        row.patches = patches
        if patches is None:
            row.landed = "unresolved"
            row.notes.append(err or "git cherry failed")
            out.append(row)
            continue
        if repo is None:
            row.landed = "not-measured"
            out.append(row)
            continue
        if not row.pr_number.isdigit():
            # A stack base: real work, but no PR of its own, so "landed" has no
            # answer and "recoverable" is the only honest description.
            row.landed = "no-pr"
            row.notes.append("stack base or unfiled branch")
        else:
            if row.pr_number not in pr_cache:
                pr_cache[row.pr_number] = fetch_pr(int(row.pr_number), repo)
            pr = pr_cache[row.pr_number]
            if pr is None:
                row.landed = "unresolved"
                row.notes.append("gh api unavailable")
            else:
                row.pr_base = pr.get("base")
                on_base = None
                if pr.get("mcs"):
                    on_base = is_ancestor(
                        pr["mcs"], f"{remote}/{pr.get('base') or base}", cwd
                    )
                    if on_base is None:
                        row.notes.append("merge commit not fetched")
                row.landed = pr_land_state(
                    merged=pr.get("merged") is _MERGED_TRUE,
                    merge_commit_sha=pr.get("mcs"),
                    on_own_base=bool(on_base),
                )
        out.append(row)
    return out


def summarise(rows: Sequence[BranchRow]) -> dict:
    """Aggregate a census into the two numbers a reader must not confuse.

    ``branches`` is every census row. ``measured`` is the subset whose patches
    could be counted. ``patches_measurable`` is the sum over that subset -- an
    UPPER bound on nothing and a LOWER bound on the true population, because
    the unmeasured branches are exactly the ones whose refs are gone and whose
    patch counts no longer exist anywhere. ``patches_unlanded`` is the number
    that matters for disposal: patches on branches whose PR never landed.
    """
    def by_tier(rows_: Sequence[BranchRow]) -> dict:
        acc: dict[str, dict] = {}
        for r in rows_:
            tier = classify_tier(r.patches) or "unmeasured"
            a = acc.setdefault(tier, {"branches": 0, "patches": 0, "unlanded_branches": 0, "unlanded_patches": 0})
            a["branches"] += 1
            if r.patches is not None:
                a["patches"] += r.patches
            if r.landed in ("not-landed", "no-pr", "unresolved", "merged-no-merge-commit", "merged-not-on-base"):
                a["unlanded_branches"] += 1
                a["unlanded_patches"] += r.patches or 0
        return dict(sorted(acc.items()))

    def by_recorded_tier(rows_: Sequence[BranchRow]) -> dict:
        """The same split, keyed on the tier the 2026-10-06 census recorded.

        Reported alongside :func:`by_tier` because the two answer different
        questions. ``by_tier`` is what the branches carry *now* and is what
        disposal acts on. This one is keyed on the recorded tier, so a reader
        can see which recorded population moved and how the previously
        published per-tier figures compare with what the same rows measure
        today. The two differ only where a branch has drifted, and the
        difference is reported as ``drift`` rather than absorbed.
        """
        acc: dict[str, dict] = {}
        for r in rows_:
            tier = short_tier(r.recorded_tier)
            a = acc.setdefault(
                tier,
                {
                    "census_rows": 0,
                    "measurable": 0,
                    "patches": 0,
                    "landed_branches": 0,
                    "landed_patches": 0,
                    "nopr_branches": 0,
                    "nopr_patches": 0,
                    "unlanded_branches": 0,
                    "unlanded_patches": 0,
                },
            )
            a["census_rows"] += 1
            if r.patches is None:
                continue
            a["measurable"] += 1
            a["patches"] += r.patches
            bucket = {
                "landed": ("landed_branches", "landed_patches"),
                "no-pr": ("nopr_branches", "nopr_patches"),
            }.get(r.landed, ("unlanded_branches", "unlanded_patches"))
            a[bucket[0]] += 1
            a[bucket[1]] += r.patches
        return dict(sorted(acc.items()))

    def drift(rows_: Sequence[BranchRow]) -> list[dict]:
        """Branches whose measured tier differs from the one recorded.

        Only measurable branches can drift: an unresolvable ref has no tier to
        re-derive, and a row whose recorded label is unreadable is reported
        separately by ``by_recorded_tier`` under ``?`` rather than counted as a
        movement between two real tiers.
        """
        out = []
        for r in rows_:
            if r.patches is None:
                continue
            recorded = short_tier(r.recorded_tier)
            measured = classify_tier(r.patches)
            if recorded == "?" or recorded == measured:
                continue
            out.append(
                {
                    "branch": r.branch,
                    "recorded_tier": recorded,
                    "measured_tier": measured,
                    "patches": r.patches,
                }
            )
        return sorted(out, key=lambda d: d["branch"])

    return {
        "branches": len(rows),
        "measured": sum(1 for r in rows if r.patches is not None),
        "unresolvable": sum(1 for r in rows if r.patches is None),
        "excluded_branches": sum(1 for r in rows if r.exclusion),
        "patches_measurable": sum(r.patches for r in rows if r.patches is not None),
        "patches_on_excluded": sum(r.patches for r in rows if r.exclusion and r.patches is not None),
        "patches_unlanded": sum(r.patches or 0 for r in rows if r.landed not in ("landed", "not-measured")),
        "by_tier": by_tier(rows),
        "by_recorded_tier": by_recorded_tier(rows),
        "drift": drift(rows),
        "landed": {k: sum(1 for r in rows if r.landed == k) for k in sorted({r.landed or "unknown" for r in rows})},
    }


def markdown(rows: Sequence[BranchRow], summary: dict) -> str:
    """Render the census as markdown, bounds included.

    Two tables, because two questions are asked of the same census. The
    recorded-tier table is keyed on the tier the 2026-10-06 census wrote down,
    so it can be laid next to the figures that census published and show what
    changed. The measured-tier table is keyed on what the branches carry today
    and is the one disposal acts on. A reader who needs only the current state
    wants the second; a reader checking a published number wants the first.
    """
    out = [
        "| Recorded tier | Census rows | Measurable | Measured `+` | Landed (br / p) "
        "| No PR (br / p) | PR never landed (br / p) |",
        "|---|---|---|---|---|---|---|",
    ]
    for tier, a in summary["by_recorded_tier"].items():
        out.append(
            f"| {tier} | {a['census_rows']} | {a['measurable']} | {a['patches']} "
            f"| {a['landed_branches']} / {a['landed_patches']} "
            f"| {a['nopr_branches']} / {a['nopr_patches']} "
            f"| {a['unlanded_branches']} / {a['unlanded_patches']} |"
        )
    recorded = summary["by_recorded_tier"]
    if recorded:
        # The totals row is generated rather than transcribed: these are the
        # numbers a reader quotes, so they must not be a human's addition.
        total = {
            key: sum(a[key] for a in recorded.values())
            for key in recorded[next(iter(recorded))]
        }
        out.append(
            f"| **Total** | **{total['census_rows']}** | **{total['measurable']}** "
            f"| **{total['patches']}** "
            f"| **{total['landed_branches']} / {total['landed_patches']}** "
            f"| **{total['nopr_branches']} / {total['nopr_patches']}** "
            f"| **{total['unlanded_branches']} / {total['unlanded_patches']}** |"
        )
    out += ["", "| Measured tier | Branches | Unmerged patches | Not landed (br / p) |", "|---|---|---|---|"]
    for tier, a in summary["by_tier"].items():
        out.append(
            f"| {tier} | {a['branches']} | {a['patches']} "
            f"| {a['unlanded_branches']} / {a['unlanded_patches']} |"
        )
    out += [
        "",
        f"- census rows: **{summary['branches']}**",
        f"- measured (ref resolved): **{summary['measured']}**",
        f"- unresolvable (ref gone, no patch count exists): **{summary['unresolvable']}**",
        f"- measurable patches: **{summary['patches_measurable']}** "
        f"(of which {summary['patches_on_excluded']} sit on section-5 exclusions)",
        f"- patches on branches whose PR never landed: **{summary['patches_unlanded']}**",
    ]
    drift = summary.get("drift") or []
    if drift:
        out += ["", "Tier drift since the recorded census:"]
        out += [
            f"- `{d['branch']}` {d['recorded_tier']} -> {d['measured_tier']} "
            f"({d['patches']} patches)"
            for d in drift
        ]
    out += [
        "",
        "Measurable patches are a **lower bound** on the census population: the",
        "unresolvable branches have no ref left to measure, so their patch count",
        "cannot be recovered by any tool, only re-derived from the archive.",
    ]
    return "\n".join(out)


# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--tsv",
        default="docs/ops/2026-10-06-stranded-branch-triage.tsv",
        help="census TSV to re-measure (default: the 2026-10-06 triage)",
    )
    ap.add_argument("--repo", default="digithings-ai/digithings", help="owner/name for the landed column")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--remote", default=REMOTE)
    ap.add_argument("--no-gh", action="store_true", help="skip the per-PR landed column")
    ap.add_argument("--markdown", action="store_true", help="emit markdown instead of JSON")
    ap.add_argument("--json", action="store_true", help="emit the per-branch rows as JSON")
    args = ap.parse_args(argv)

    if not os.path.exists(args.tsv):
        print(f"branch_census: no such census file: {args.tsv}", file=sys.stderr)
        return 2

    rows = census(
        read_tsv(args.tsv),
        remote=args.remote,
        base=args.base,
        repo=None if args.no_gh else args.repo,
    )
    summary = summarise(rows)

    if args.json:
        print(json.dumps([asdict(r) for r in rows], indent=1))
        return 0
    if args.markdown:
        print(markdown(rows, summary))
        return 0
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

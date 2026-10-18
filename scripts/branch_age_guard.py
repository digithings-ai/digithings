#!/usr/bin/env python3
"""branch_age_guard.py — DIG-1578. Warn about remote branches nobody is waiting on.

`docs/ops/branch-hygiene-policy.md` §6.2 item 2: a branch or PR whose head is
older than 10 days must not trigger a rebuild, and gets a labelled warning and a
stop. This script is the warning half. It warns and it reports; it never
deletes. Deletion belongs to the tiered run on DIG-1575, and keeping the two
apart is the point of this file's existence.

WHAT IT REPORTS

For every remote branch it sorts the branch into exactly one bucket:

* ``stale``   — head older than ``--max-age-days`` (default 10), no open PR.
* ``open_pr`` — stale-or-not but carries an open PR, so a human is watching it.
* ``fresh``   — head recent enough to be live work.
* ``excluded``— matched an exclusion from §6.2. The reason is named, never
  swallowed, because a silently-dropped branch reads exactly like a branch that
  aged out of the census.

WHY IT WARNS AND DOES NOT GATE CI

Measured 2026-10-15 across all 64 workflows on develop: **every** ``on: push``
trigger carries a ``branches:`` or ``tags:`` filter, and the single
``on: workflow_run`` trigger is filtered to ``main``. So no branch without an
open PR triggers a workflow run today, and the "stop" in §6.2 is already held
structurally rather than by any list this script publishes.

That structure is accidental and nothing pins it. The pin that makes it real
lives in ``tests/scripts/test_branch_age_guard.py``: a workflow that adds an
unfiltered ``push:`` fails CI. This script is therefore deliberately
report-only — it publishes no skip list, because a committed list that nothing
reads is a second source of truth that drifts, and the cost is paid on every
merge that touches it.

USAGE

    python3 scripts/branch_age_guard.py                 # report to stdout
    python3 scripts/branch_age_guard.py --json out.json # + machine-readable
    python3 scripts/branch_age_guard.py --max-age-days 3

Exit code is always 0. This is an informational tool, not a gate: a branch
aging past the threshold is a fact to publish, not a failure to fail CI over.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

# --- Policy constants (docs/ops/branch-hygiene-policy.md §6.2) ---------------

DEFAULT_MAX_AGE_DAYS = 10

#: Long-lived branches whose age is not a signal. Matched exactly.
EXCLUDED_BRANCHES: tuple[str, ...] = ("main", "develop")

#: Branch families that are supposed to be old. Matched as a path prefix, so
#: `module/digiquant` and `module/digiquant-work` are both covered.
EXCLUDED_PREFIXES: tuple[str, ...] = (
    "module/",
    "chore/sync-module-",
    "release/v",
)

#: Branches the harness reserves for work in flight. Same shape as
#: scripts/hooks/pre-push.sh enforces at push time; listed here so a branch
#: that is legitimately mid-attempt never shows up as an aged orphan.
RESERVED_PREFIXES: tuple[str, ...] = ("DIG-",)


def excluded_reason(branch: str) -> str | None:
    """Return why ``branch`` is excluded, or ``None`` when it is not excluded.

    Order is the order §6.2 lists them, so the reason a reader sees matches the
    policy's own order. Reserved ``DIG-`` branches are reported separately from
    policy exclusions so the two never get confused in the census.
    """
    if branch in EXCLUDED_BRANCHES:
        return f"long-lived branch ({branch})"
    for prefix in EXCLUDED_PREFIXES:
        if branch.startswith(prefix):
            return f"policy exclusion: {prefix}*"
    for prefix in RESERVED_PREFIXES:
        if branch.startswith(prefix):
            return f"reserved work branch: {prefix}*"
    return None


def parse_iso8601(value: str) -> datetime:
    """Parse a GitHub ISO-8601 timestamp into an aware UTC datetime.

    GitHub returns ``2026-10-15T09:12:33Z``. A ``Z`` suffix is accepted as UTC
    and offsets are honoured; a naive result is treated as UTC rather than
    local time, because the age comparison is only meaningful in one zone.
    """
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_stale(commit_iso: str, now: datetime, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> bool:
    """True when the head commit is strictly older than ``max_age_days``.

    Strictly older, not older-or-equal: a branch whose head is exactly at the
    boundary is live work until the next second, and a guard that fires on the
    boundary is a guard that fires a day early.
    """
    cutoff = now - timedelta(days=max_age_days)
    return parse_iso8601(commit_iso) < cutoff


def age_days(commit_iso: str, now: datetime) -> float:
    """Whole-and-fraction days between the head commit and ``now``."""
    return round((now - parse_iso8601(commit_iso)).total_seconds() / 86400.0, 2)


def select_stale(
    branches: Iterable[dict[str, Any]],
    open_pr_heads: Iterable[str],
    now: datetime,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> dict[str, Any]:
    """Bucket every branch. Pure: no I/O, no clock, no network.

    ``branches`` is the GitHub branches payload (``name``, ``commit.sha``, and a
    commit timestamp the caller resolved). ``open_pr_heads`` is the set of head
    refs that carry an open PR.

    The returned mapping carries every bucket plus the inputs the buckets were
    computed from, so a caller can print a census that reconciles.
    """
    open_prs = set(open_pr_heads)
    stale: list[dict[str, Any]] = []
    with_pr: list[dict[str, Any]] = []
    fresh: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    total = 0
    for raw in branches:
        name = raw.get("name")
        if not name:
            continue
        total += 1
        entry: dict[str, Any] = {"name": name}
        reason = excluded_reason(name)
        if reason is not None:
            entry["reason"] = reason
            excluded.append(entry)
            continue
        commit_iso = raw.get("committed_at")
        if not commit_iso:
            # An unresolvable commit date is not evidence the branch is fresh.
            # Report it rather than dropping it: a branch whose age cannot be
            # computed is a census gap, and a silent drop reads as "clean".
            entry["reason"] = "commit date unavailable"
            excluded.append(entry)
            continue
        entry["age_days"] = age_days(commit_iso, now)
        entry["head_sha"] = (raw.get("commit") or {}).get("sha", "")[:12]
        if name in open_prs:
            entry["reason"] = "open PR"
            with_pr.append(entry)
        elif is_stale(commit_iso, now, max_age_days):
            stale.append(entry)
        else:
            fresh.append(entry)

    for bucket in (stale, with_pr, fresh):
        bucket.sort(key=lambda e: -float(e.get("age_days", 0)))

    return {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "max_age_days": max_age_days,
        "total_branches": total,
        "stale": stale,
        "open_pr": with_pr,
        "fresh": fresh,
        "excluded": excluded,
    }


# --- Reporting ---------------------------------------------------------------


def render_report(census: dict[str, Any], repo: str) -> str:
    """Markdown report for the Actions job summary. Deterministic given a census."""
    stale = census["stale"]
    lines: list[str] = []
    lines.append(f"## Branch-age guard — `{repo}`")
    lines.append("")
    lines.append(
        f"Head older than **{census['max_age_days']} days** with no open PR: "
        f"**{len(stale)}** of {census['total_branches']} remote branches."
    )
    lines.append("")
    lines.append(
        "This is a warning only. No branch is deleted here, and no CI is skipped "
        "by this report — deletion is the tiered run on DIG-1575, and the "
        "rebuild stop is structural (see the note below)."
    )
    lines.append("")
    if stale:
        lines.append("| branch | age (days) | head |")
        lines.append("| --- | ---: | --- |")
        for entry in stale:
            lines.append(
                f"| `{entry['name']}` | {entry.get('age_days')} | `{entry.get('head_sha', '')}` |"
            )
    else:
        lines.append("No branch meets the stale definition. Nothing to warn about.")
    lines.append("")
    lines.append("### Census")
    lines.append("")
    lines.append("| bucket | count |")
    lines.append("| --- | ---: |")
    for key, label in (
        ("stale", "stale (no PR, over threshold)"),
        ("open_pr", "excluded: open PR"),
        ("fresh", "fresh"),
        ("excluded", "excluded: policy / reserved"),
    ):
        lines.append(f"| {label} | {len(census[key])} |")
    lines.append("")
    lines.append("### Exclusions honoured")
    lines.append("")
    for name in EXCLUDED_BRANCHES:
        lines.append(f"- `{name}` (exact)")
    for prefix in EXCLUDED_PREFIXES:
        lines.append(f"- `{prefix}*` (prefix)")
    for prefix in RESERVED_PREFIXES:
        lines.append(f"- `{prefix}*` (reserved harness work branches)")
    lines.append("- anything carrying an open PR")
    return "\n".join(lines)


def render_summary_line(census: dict[str, Any]) -> str:
    """One line for the cron dispatch log. Never raises, never prints a value."""
    return (
        f"branch-age-guard: {len(census['stale'])} stale of {census['total_branches']} "
        f"branches over {census['max_age_days']}d "
        f"({len(census['open_pr'])} with open PR, {len(census['excluded'])} excluded, "
        f"{len(census['fresh'])} fresh)"
    )


# --- I/O ---------------------------------------------------------------------


def _gh(args: Sequence[str]) -> Any:
    """Run ``gh api`` and return decoded JSON. Raises on any failure.

    On failure the exception carries gh's own stderr. Without it the only
    evidence is "returned non-zero exit status 1", which cannot tell a bad flag
    from an exhausted rate limit — and this guard runs unattended, so the reason
    has to survive into the report. stderr never carries the token: GH_TOKEN
    arrives by environment, never in argv.
    """
    proc = subprocess.run(
        ["gh", "api", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        # First lines only: gh prints a whole usage dump on a bad flag, and that
        # belongs in the operator's terminal, not in a one-screen report.
        reason = (proc.stderr.strip().splitlines() or ["<no stderr>"])[0]
        raise RuntimeError(f"gh api {args[0]}: {reason}")
    return json.loads(proc.stdout)


def _gh_rows(args: Sequence[str]) -> list[dict[str, Any]]:
    """Every object across every page of a paginated ``gh api`` listing.

    ``--paginate --slurp`` is the form that parses: ``--paginate`` alone emits
    several JSON documents back to back, and there is no ``--paginate-output``
    flag at all — ``gh api`` rejects it, so a caller reaching for it gets a
    non-zero exit and no rows rather than the listing it asked for.
    """
    rows = _gh([*args, "--paginate", "--slurp", "-H", "Accept: application/vnd.github+json"])
    out: list[dict[str, Any]] = []
    for page in rows if isinstance(rows, list) else []:
        if isinstance(page, list):
            out.extend(row for row in page if isinstance(row, dict))
        elif isinstance(page, dict):
            out.append(page)
    return out


def fetch_remote_branches(repo: str) -> list[dict[str, Any]]:
    """Every branch on ``repo``, with the head commit date resolved.

    The branches listing carries no commit date, so each head needs its own
    read. That is N+1 calls; the guard runs once a day, and a cache would be a
    second source of truth for a number nobody acts on between runs.
    """
    branches = _gh_rows([f"repos/{repo}/branches"])
    out: list[dict[str, Any]] = []
    for row in branches:
        name = row.get("name")
        sha = ((row.get("commit") or {}).get("sha")) or ""
        if not name or not sha:
            continue
        try:
            commit = _gh([f"repos/{repo}/commits/{sha}"])
        except Exception:  # a branch we cannot date is reported undated, never fatal
            commit = {}
        out.append(
            {
                "name": name,
                "commit": {"sha": sha},
                "committed_at": ((commit.get("commit") or {}).get("committer") or {}).get("date"),
            }
        )
    return out


def fetch_open_pr_heads(repo: str) -> set[str]:
    """Head ref names of every open PR. A branch with one is never stale."""
    pulls = _gh_rows([f"repos/{repo}/pulls", "-X", "GET", "-f", "state=open"])
    return {(p.get("head") or {}).get("ref") for p in pulls if (p.get("head") or {}).get("ref")}


def render_failure(repo: str, exc: BaseException) -> str:
    """A loud, non-empty report for a census that could not be taken.

    A guard that never read the branch list has NOT found zero stale branches.
    The report says so in words, keeps the reason, and names no credential.
    """
    return "\n".join(
        [
            f"# Branch-age guard: CENSUS FAILED for {repo}",
            "",
            "No census was taken. This is **not** a finding of zero stale branches.",
            f"Reason: {type(exc).__name__}: {exc}",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default="digithings-ai/digithings")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help=f"head older than this is stale (policy: {DEFAULT_MAX_AGE_DAYS})",
    )
    parser.add_argument("--json", dest="json_path", help="write the census as JSON")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    try:
        branches = fetch_remote_branches(args.repo)
        open_pr = fetch_open_pr_heads(args.repo)
    except Exception as exc:  # a census that could not be taken is reported, not guessed
        report = render_failure(args.repo, exc)
        print(report)
        if args.json_path:
            with open(args.json_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "repo": args.repo,
                        "error": f"{type(exc).__name__}: {exc}",
                        "stale": [],
                        "excluded": [],
                        "fresh": [],
                        "open_pr": [],
                        "total_branches": 0,
                        "max_age_days": args.max_age_days,
                    },
                    handle,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
        # Non-zero on purpose: the dispatch log must record a guard that did not
        # run. Returning 0 here would make a failed census read as a clean sweep.
        return 1

    census = select_stale(
        branches,
        open_pr,
        now,
        args.max_age_days,
    )
    print(render_report(census, args.repo))
    print()
    print(render_summary_line(census))
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(census, handle, indent=2, sort_keys=True)
            handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
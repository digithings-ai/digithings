#!/usr/bin/env python3
"""Fail loudly when an agent skills home holds a dangling or unresolvable skill link.

WHY THIS EXISTS. Agent seats load skills through a skills home that pairs a plain
slug with a content-hashed runtime alias:

    <slug>            -> <slug>--<10-hex>  ->  <materialised source dir>

The materialised directory is garbage-collected, but the two symlinks that point at
it are not. The seat then keeps a skill name that resolves to nothing, so the skill
silently stops loading — no error, no run failure, just a missing capability. On a
59-seat company with `paperclip` attached to every seat and `digithings-operating-rules`
to 54 of them, that is a large blast radius for a check nobody was running.

Deleting the broken symlink is the wrong repair. It hides the symptom and the seat
loses the skill permanently, so this script only ever *reads* and *reports*. Repair is
someone re-materialising the target (re-syncing the seat, or recreating the hashed
target from the managed source directory).

WHAT IT CHECKS, for every entry in the skills home:

* `dangling-link`      a symlink whose target does not exist (failure)
* `missing-manifest`   a skill directory with no `SKILL.md` (failure)
* `unresolvable`       a required skill name that does not resolve (failure, via `--expect`)
* `orphaned-alias`     a `<slug>--<hash>` entry with no `<slug>` sibling (warning; failure
                       under `--strict`, since it is the fingerprint of a half-finished relink)

EXIT CODES: `0` clean, `1` findings, `2` bad usage.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKILLS_HOME = REPO_ROOT / ".claude" / "skills"

# The manifest that makes a directory a loadable skill.
SKILL_MANIFEST = "SKILL.md"

# Runtime alias shape: `product-management--dce17287c0` (10 lowercase hex chars).
HASHED_ALIAS_RE = re.compile(r"^(?P<slug>.+)--(?P<hash>[0-9a-f]{10})$")

# Hidden entries are bookkeeping, not skills (`.staging`, `.DS_Store`, lock files).
SKIPPED_PREFIX = "."

# Findings that fail the gate on their own.
FAILURE_KINDS: frozenset[str] = frozenset({"dangling-link", "missing-manifest", "unresolvable"})

# Findings that only fail the gate under --strict.
WARNING_KINDS: frozenset[str] = frozenset({"orphaned-alias"})


@dataclass(frozen=True)
class Finding:
    """One defect in a skills home, with enough detail to repair it by hand."""

    name: str
    kind: str
    detail: str

    @property
    def is_failure(self) -> bool:
        return self.kind in FAILURE_KINDS

    def render(self) -> str:
        return f"{self.kind}: {self.name}: {self.detail}"


def hashed_alias_slug(name: str) -> str | None:
    """Return the slug a `<slug>--<10-hex>` alias belongs to, or None if `name` is not one."""
    match = HASHED_ALIAS_RE.match(name)
    return match.group("slug") if match else None


def _plausibly_a_skill(entry: Path) -> bool:
    """Is this plain, manifest-less directory meant to be a skill?

    A skills home can also hold bookkeeping containers — this host carries `synced/`,
    a directory of opaque sync-bucket directories, which has no manifest by design.
    Reporting those would make the gate cry wolf on every run, so a directory with no
    markdown at depth 1 and nothing but sub-directories is treated as a container.

    An *empty* directory still counts: a skill dir that lost its contents is a real
    failure, not a container.
    """
    children = list(entry.iterdir())
    if not children:
        return True
    if any(child.is_file() and child.suffix == ".md" for child in children):
        return True
    return not any(child.is_dir() for child in children)


def _check_entry(entry: Path) -> Finding | None:
    """Classify one entry of the skills home. Read-only; never repairs anything."""
    name = entry.name

    # `exists()` follows symlinks, so a link whose target is gone reports False here
    # and lands as `dangling-link` with the raw link target in the detail.
    if entry.is_symlink():
        raw_target = entry.readlink()
        resolved = raw_target if raw_target.is_absolute() else entry.parent / raw_target
        if not resolved.exists():
            return Finding(name, "dangling-link", f"target does not exist: {raw_target}")
        if not resolved.is_dir():
            return Finding(name, "dangling-link", f"target is not a directory: {raw_target}")
        return None

    if not entry.is_dir():
        return None

    alias_slug = hashed_alias_slug(name)
    if alias_slug is not None and not (entry.parent / alias_slug).exists():
        return Finding(
            name,
            "orphaned-alias",
            f"no sibling {alias_slug!r}; the alias a seat loads is missing",
        )

    if not (entry / SKILL_MANIFEST).is_file():
        if not _plausibly_a_skill(entry):
            return None
        return Finding(name, "missing-manifest", f"no {SKILL_MANIFEST} in {entry}")
    return None


def scan_skills_home(skills_home: Path) -> tuple[list[Finding], int]:
    """Scan every visible entry of `skills_home`. Returns (findings, entry count)."""
    findings: list[Finding] = []
    entries = [
        entry
        for entry in sorted(skills_home.iterdir())
        if not entry.name.startswith(SKIPPED_PREFIX)
    ]
    for entry in entries:
        finding = _check_entry(entry)
        if finding is not None:
            findings.append(finding)
    return findings, len(entries)


def check_expected(skills_home: Path, expected: Sequence[str]) -> list[Finding]:
    """Fail loudly when a required skill name does not resolve to a loadable skill."""
    findings: list[Finding] = []
    for name in expected:
        candidate = skills_home / name
        if not candidate.exists():
            findings.append(
                Finding(
                    name,
                    "unresolvable",
                    f"not present in {skills_home}; re-materialise the target or re-sync the seat",
                )
            )
        elif not (candidate / SKILL_MANIFEST).is_file():
            findings.append(
                Finding(name, "unresolvable", f"resolves but carries no {SKILL_MANIFEST}")
            )
    return findings


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only check that every agent skill link resolves.",
    )
    parser.add_argument(
        "--skills-home",
        type=Path,
        default=DEFAULT_SKILLS_HOME,
        help=f"skills directory to scan (default: {DEFAULT_SKILLS_HOME})",
    )
    parser.add_argument(
        "--expect",
        action="append",
        default=[],
        metavar="SKILL",
        help="require this skill name to resolve; repeat for more than one",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings (orphaned hashed aliases) as failures",
    )
    parser.add_argument(
        "--require-skills-home",
        action="store_true",
        help="fail when the skills home does not exist instead of reporting it absent",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns 0 when clean, 1 when there are findings, 2 on bad usage."""
    args = _parse_args(argv)
    skills_home: Path = args.skills_home

    if not skills_home.is_dir():
        if args.require_skills_home:
            print(f"check_agent_skills_links: skills home does not exist: {skills_home}")
            return 1
        # Absent is not broken: a CI checkout has no `.claude/skills` until
        # `make agents-init` runs. Failing here would make the gate meaningless.
        print(f"check_agent_skills_links: OK (skills home absent, nothing to check: {skills_home})")
        return 0

    try:
        findings, entry_count = scan_skills_home(skills_home)
    except OSError as exc:
        print(f"check_agent_skills_links: cannot scan {skills_home}: {exc}")
        return 2
    findings.extend(check_expected(skills_home, args.expect))

    def is_blocking(finding: Finding) -> bool:
        return finding.is_failure or (args.strict and finding.kind in WARNING_KINDS)

    failures = [f for f in findings if is_blocking(f)]
    warnings = [f for f in findings if not is_blocking(f)]

    if args.json:
        print(
            json.dumps(
                {
                    "skillsHome": str(skills_home),
                    "entries": entry_count,
                    "failures": [f.render() for f in failures],
                    "warnings": [f.render() for f in warnings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for finding in failures:
            print(f"check_agent_skills_links: FAIL {finding.render()}", file=sys.stderr)
        for finding in warnings:
            print(f"check_agent_skills_links: WARN {finding.render()}", file=sys.stderr)

    if failures:
        plural = "s" if len(failures) != 1 else ""
        print(
            f"check_agent_skills_links: {len(failures)} failure{plural} in {skills_home}",
            file=sys.stderr,
        )
        print(
            "check_agent_skills_links: this check never repairs anything. Re-materialise the "
            "hashed target or re-sync the seat; do not delete the link.",
            file=sys.stderr,
        )
        return 1

    suffix = f", {len(warnings)} warning{'' if len(warnings) == 1 else 's'}" if warnings else ""
    print(f"check_agent_skills_links: OK ({entry_count} entries scanned in {skills_home}{suffix})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

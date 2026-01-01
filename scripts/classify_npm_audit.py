"""Classify ``npm audit --json`` output for the dependency-audit CI lane (#3523).

Blocks on HIGH/CRITICAL advisories that are not accepted in
``npm-audit-ignore.txt`` and surfaces MODERATE/LOW as warnings, mirroring the
Python ``pip-audit`` sibling.

Two properties the lane's safety depends on, each pinned by
``tests/scripts/test_classify_npm_audit.py``:

* **Per-advisory, not per-package.** npm keys ``vulnerabilities`` by *package*
  and puts every advisory for that package in ``via`` — ``next@16.2.4`` alone
  carries two dozen. Matching the ignore set against the union of a package's
  ids accepts the package wholesale, so a brand-new advisory against an
  already-ignored package would be silently skipped. Each advisory is matched
  on its own ids instead, and a package blocks if *any* of its HIGH/CRITICAL
  advisories is unaccepted.
* **Fail closed.** When the registry is unreachable, rate-limited or 5xx, npm
  writes a valid JSON *error* object to stdout with no ``vulnerabilities`` key.
  Reading that as "no findings" would turn a network outage into a green
  security gate, so an error body or a missing ``vulnerabilities`` object is a
  failure rather than a pass.

Usage::

    python scripts/classify_npm_audit.py audit.json [npm-audit-ignore.txt]

Exit codes: ``0`` clean (warnings allowed), ``1`` blocking findings or an
unreadable/erroring audit.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — heterogeneous npm audit entries

GHSA_RE = re.compile(r"GHSA-[0-9a-z-]+", re.IGNORECASE)

#: Severities that fail the lane.
BLOCKING = frozenset({"high", "critical"})

#: Ordering for "worst open advisory decides the line"; unknown sorts lowest so
#: a missing severity never silently promotes an advisory into a blocker.
_RANK = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
_UNKNOWN_RANK = -1


class AuditError(RuntimeError):
    """The audit output could not be trusted — never read as clean."""


def _rank(severity: str) -> int:
    return _RANK.get(severity, _UNKNOWN_RANK)


def load_ignored(path: str | Path) -> set[str]:
    """Read the accepted-risk list, dropping blank lines and ``#`` comments."""
    ignored: set[str] = set()
    candidate = Path(path)
    if not candidate.is_file():
        return ignored
    for line in candidate.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            ignored.add(entry)
    return ignored


def advisory_ids(advisory: dict[str, Any]) -> set[str]:
    """Every identifier an advisory can be matched by.

    npm's ``url`` is the full advisory URL while the ignore file documents the
    bare GHSA id, so the id is surfaced as its own identifier — without that,
    none of the bare ids in ``npm-audit-ignore.txt`` would ever match.
    """
    ids: set[str] = set()
    for key in ("source", "url", "title"):
        value = str(advisory.get(key, "") or "")
        if value:
            ids.add(value)
    for key in ("url", "title"):
        match = GHSA_RE.search(str(advisory.get(key, "") or ""))
        if match:
            ids.add(match.group(0))
    return ids


def classify(data: dict[str, Any], ignored: set[str]) -> tuple[list[str], list[str], list[str]]:
    """Split findings into ``(blockers, warns, ignored_hits)``.

    Raises ``AuditError`` when the payload is not a trustworthy audit result.
    """
    if not isinstance(data, dict):
        raise AuditError("npm audit JSON is not an object")

    # Fail closed: npm reports registry/network failures as a JSON body with an
    # `error`/`message` and no `vulnerabilities`, which must not read as clean.
    if data.get("error"):
        raise AuditError(f"npm audit reported an error: {data['error']}")
    vulnerabilities = data.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        message = data.get("message") or "no `vulnerabilities` object in the payload"
        raise AuditError(
            f"npm audit did not return findings — refusing to report clean ({message})"
        )

    blockers: list[str] = []
    warns: list[str] = []
    ignored_hits: list[str] = []

    for name in sorted(vulnerabilities):
        entry = vulnerabilities[name] or {}
        # `via` mixes advisory objects with the names of the dependencies that
        # pull the package in; only the objects are advisories.
        advisories = [v for v in (entry.get("via") or []) if isinstance(v, dict)]
        if not advisories:
            # Listed only because a dependency is vulnerable — the leaf package
            # carries the advisory and is classified on its own. Reporting here
            # would double-count.
            continue

        open_advisories = [a for a in advisories if not (advisory_ids(a) & ignored)]
        if not open_advisories:
            ignored_hits.append(f"{name} (all {len(advisories)} advisories ignored)")
            continue

        package_fallback = str(entry.get("severity") or "unknown").lower()
        severities = [str(a.get("severity") or package_fallback).lower() for a in open_advisories]
        worst = max(severities, key=_rank)
        label = (
            f"{name} [{worst}] direct={bool(entry.get('isDirect'))} "
            f"({len(open_advisories)}/{len(advisories)} advisories open)"
        )
        if worst in BLOCKING:
            blockers.append(label)
        else:
            warns.append(label)

    return blockers, warns, ignored_hits


def main(argv: list[str]) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return 2

    audit_path = argv[1]
    ignore_path = argv[2] if len(argv) > 2 else "npm-audit-ignore.txt"

    try:
        data = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"::error::could not read npm audit JSON from {audit_path}: {exc}")
        return 1

    ignored = load_ignored(ignore_path)
    try:
        blockers, warns, ignored_hits = classify(data, ignored)
    except AuditError as exc:
        print(f"::error::{exc}")
        return 1

    for warn in warns:
        print(f"::warning::npm audit: {warn}")
    for hit in ignored_hits:
        print(f"::notice::npm audit (ignored): {hit}")
    for blocker in blockers:
        print(f"::error::npm audit blocker: {blocker}")

    totals = data.get("metadata", {}).get("vulnerabilities", {})
    if blockers:
        plural = "y" if len(blockers) == 1 else "ies"
        print(f"\nFAIL: {len(blockers)} HIGH/CRITICAL vulnerabilit{plural}.")
        print("Fix by bumping the affected package (or add the advisory id to")
        print(f"{ignore_path} with a justification comment).")
        return 1

    print(
        f"\nOK: 0 HIGH/CRITICAL vulnerabilities "
        f"({len(warns)} lower-severity, {len(ignored_hits)} ignored)."
    )
    print(f"Totals: {totals}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

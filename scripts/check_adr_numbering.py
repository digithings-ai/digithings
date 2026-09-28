#!/usr/bin/env python3
"""Audit ``docs/adr/`` numbering (#3524).

``docs/adr/`` holds immutable decisions named ``NNNN-short-title.md``. Nothing
checked that those numbers were zero-padded, unique, and gap-free, so a
mislabelled ADR (two files claiming the same number, or a jump with no recorded
reason) could sit unnoticed.

What it asserts
---------------
* every ADR file (except the ``0000-template.md`` scaffold and ``README.md``)
  starts with exactly four zero-padded digits;
* numbers are unique (the same number cannot be claimed twice);
* there are no gaps in ``1..max``, except for numbers listed with a reason in
  :data:`ALLOWED_GAPS`.

The template is ``0000`` by convention and is excluded, so the sequence is
expected to start at ``0001``.

Usage
-----
::

    python3 scripts/check_adr_numbering.py
    python3 scripts/check_adr_numbering.py --format json

Exit code is ``0`` when clean, ``1`` when a numbering problem is found.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = REPO_ROOT / "docs" / "adr"

# Files that are not numbered decisions.
IGNORED_NAMES: frozenset[str] = frozenset({"README.md", "0000-template.md"})

NAME_RE = re.compile(r"^(?P<num>\d+)-(?P<slug>.+)\.md$")

# Numbers deliberately never allocated, with the reason recorded here so a gap
# is a decision on the record rather than an oversight. Keep the reason short.
ALLOWED_GAPS: dict[int, str] = {}


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


def _collect() -> tuple[dict[int, list[str]], list[Finding]]:
    """Return number -> filenames, plus non-numbering findings."""
    by_number: dict[int, list[str]] = defaultdict(list)
    findings: list[Finding] = []
    if not ADR_DIR.is_dir():
        return by_number, [Finding("missing-dir", f"{ADR_DIR} does not exist")]

    for path in sorted(ADR_DIR.iterdir()):
        if not path.is_file() or path.name in IGNORED_NAMES:
            continue
        match = NAME_RE.match(path.name)
        if not match:
            findings.append(
                Finding(
                    "unpadded",
                    f"{path.name}: must be NNNN-slug.md with exactly four zero-padded digits",
                )
            )
            continue
        raw = match.group("num")
        if len(raw) != 4:
            findings.append(
                Finding(
                    "unpadded",
                    f"{path.name}: number {raw!r} is not exactly four zero-padded digits",
                )
            )
        by_number[int(raw)].append(path.name)
    return by_number, findings


def audit() -> list[Finding]:
    by_number, findings = _collect()

    for number in sorted(by_number):
        names = by_number[number]
        if len(names) > 1:
            findings.append(
                Finding(
                    "duplicate",
                    f"{number:04d}: claimed by {len(names)} files — {', '.join(names)}",
                )
            )

    if by_number:
        highest = max(by_number)
        for number in range(1, highest + 1):
            if number not in by_number and number not in ALLOWED_GAPS:
                findings.append(
                    Finding("gap", f"{number:04d}: missing with no recorded reason in ALLOWED_GAPS")
                )

    return findings


def render_text(findings: list[Finding]) -> str:
    if not findings:
        return "check_adr_numbering: OK — docs/adr numbering is sequential and unique"
    lines = ["check_adr_numbering: failures"]
    lines.extend(f"{f.code}: {f.message}" for f in findings)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    findings = audit()
    if args.format == "json":
        print(json.dumps({"findings": [asdict(f) for f in findings]}, indent=2))
    elif findings:
        print(render_text(findings), file=sys.stderr)
    else:
        print(render_text(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

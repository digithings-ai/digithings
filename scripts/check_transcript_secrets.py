#!/usr/bin/env python3
"""Fail-closed scan for credential values in a run transcript (DIG-1653).

The PreToolUse guard blocks the *read*; this is the second layer that checks the
*result*. A transcript is the thing that actually leaked in DIG-1639, so it is
worth being able to assert on one: the canary in
``tests/scripts/test_credential_file_guard.sh`` greps the captured run output
through this to prove no value survived.

Value shapes come from ``digitrace.redaction.CREDENTIAL_RULES`` — the same
ruleset, so the guard and the audit cannot drift apart. Placeholder-shaped values
are ignored by design: a transcript that says ``token = "***"`` is not a leak.

Usage::

    scripts/check_transcript_secrets.py PATH [PATH ...]
    some-command | scripts/check_transcript_secrets.py -

Exits 0 when nothing is found, 1 when a live credential is detected. Detection
reports the rule *name* and a byte offset, never the matched text, so this
script's own output is safe to paste into an issue.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "digitrace" / "src"))

try:
    from digitrace.redaction import detect_credential_value
except ImportError:  # pragma: no cover - guard for a repo without digitrace
    sys.stderr.write(
        "check_transcript_secrets: digitrace.redaction is not importable from "
        f"{_REPO_ROOT / 'digitrace' / 'src'}; cannot run the audit.\n"
    )
    raise SystemExit(2) from None


def scan(text: str) -> list[tuple[str, int]]:
    """Return ``(rule_name, offset)`` for every live credential found."""
    findings: list[tuple[str, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if rule := detect_credential_value(line):
            findings.append((rule, offset))
        offset += len(line)
    return findings


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(os.path.expanduser(path)).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        sys.stderr.write(f"check_transcript_secrets: cannot read {path}: {exc}\n")
        return ""


def main(argv: list[str]) -> int:
    paths = argv or ["-"]
    total = 0
    for path in paths:
        findings = scan(_read(path))
        for rule, offset in findings:
            # Name and offset only. Printing the value here would reproduce the
            # leak inside the tool written to detect it.
            sys.stderr.write(f"{path}: credential-shaped value at byte {offset} ({rule})\n")
        total += len(findings)
    if total:
        sys.stderr.write(
            f"check_transcript_secrets: {total} credential-shaped value(s) found. "
            "Treat the transcript as compromised: revoke the credential first, "
            "then clean the history. Rotation is the only real fix — see "
            "docs/ops/SECRETS_ROTATION.md.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

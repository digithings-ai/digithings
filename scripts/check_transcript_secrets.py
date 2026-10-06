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

Exits 0 when nothing is found, 1 when a live credential is detected, and 2 when
an input could not be read — an unscanned file is not a clean file. Detection
reports the rule *name* and a byte offset, never the matched text, so this
script's own output is safe to paste into an issue.
"""

from __future__ import annotations

import json
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


def _decoded_strings(line: str) -> list[str]:
    """Return every string carried by a JSON line, decoded.

    A real transcript is JSONL, so a leaked line reaches us as
    ``{"role":"tool","content":"refresh_token = \\"v1.0-...\\""}``. Matching the
    raw line misses it: the quote after ``=`` is escaped to ``\\"`` and the
    value rules all anchor on a real quote. Decoding first is what makes this
    script able to see a Paperclip transcript at all.
    """
    stripped = line.strip()
    if not stripped or stripped[0] not in "{[":
        return []
    try:
        decoded = json.loads(stripped)
    except ValueError:
        return []

    out: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for key, value in node.items():
                out.append(key)
                walk(value)
        elif isinstance(node, list):
            walk(node)

    walk(decoded)
    return out


def scan(text: str) -> list[tuple[str, int]]:
    """Return ``(rule_name, offset)`` for every live credential found."""
    findings: list[tuple[str, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        # The raw line covers plain logs and captured tool output; the decoded
        # strings cover JSONL. Both are checked so neither format is a blind spot.
        candidates = [line, *_decoded_strings(line)]
        for candidate in candidates:
            if rule := detect_credential_value(candidate):
                findings.append((rule, offset))
                break
        offset += len(line)
    return findings


def _read(path: str) -> str | None:
    """Return the file's text, or ``None`` when it cannot be read.

    ``None`` is not an empty transcript. An unreadable path used to return ``""``
    and exit 0, which reports "no secrets found" about a file nobody scanned.
    """
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(os.path.expanduser(path)).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        sys.stderr.write(f"check_transcript_secrets: cannot read {path}: {exc}\n")
        return None


def main(argv: list[str]) -> int:
    paths = argv or ["-"]
    total = 0
    unreadable = 0
    for path in paths:
        text = _read(path)
        if text is None:
            unreadable += 1
            continue
        findings = scan(text)
        for rule, offset in findings:
            # Name and offset only. Printing the value here would reproduce the
            # leak inside the tool written to detect it.
            sys.stderr.write(f"{path}: credential-shaped value at byte {offset} ({rule})\n")
        total += len(findings)
    if unreadable:
        # An unscanned file is not a clean file. Exit non-zero and non-1 so a
        # caller cannot read this as either a leak or a pass.
        sys.stderr.write(
            f"check_transcript_secrets: {unreadable} input(s) could not be read; "
            "the audit did not cover them.\n"
        )
        return 2
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

#!/usr/bin/env python3
"""Fail the build when customer PII is already tracked in git.

DIG-1498 R5, the third uncovered path for the same data as DIG-1210.
`scripts/index_occ_tickets.py` writes full non-anonymized Zammad ticket bodies
into the digisearch `occ_tickets` index: customer names, customer emails and
`[internal]` staff notes, unmasked, by design in demo mode. The retired
`seed_occ_tickets` supervisor program wrote the same shape and was removed for
exactly this reason.

Why a scanner and not only a `.gitignore` line: gitignore governs untracked
files. `git add -f`, an export committed from a machine whose root
`.gitignore` is missing, or the next artifact under the next name all reach the
index regardless. The ignore rules are the first wall; this is the second, and
it reads the index rather than the working tree.

The email shape is digitrace's, imported rather than re-invented -- a second
copy of the same regex drifts the day digitrace tightens its own. See
`digitrace/src/digitrace/redaction.py`.

Findings name a path, a line and a detector. They never carry the matched
value: this output lands in CI logs and workflow artifacts, which are not
places customer data should end up.

    python3 scripts/scan_customer_pii.py [--repo-root .] [--json report.json]

Exit 0 clean, 1 findings, 2 the scan could not run (never a silent pass).
"""

from __future__ import annotations

import argparse
import json
import re
from fnmatch import translate
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# digitrace is a src-layout package; CI has the whole repo, so a plain sys.path
# insert is the whole integration and keeps this script dependency-free.
sys.path.insert(0, str(_REPO_ROOT / "digitrace" / "src"))

from digitrace.redaction import EMAIL_PATTERN  # noqa: E402  (needs the path above)

__all__ = [
    "CUSTOMER_ARTIFACT_RULES",
    "DETECTOR_ALLOWLIST",
    "EMAIL_PATTERN",
    "Finding",
    "INTERNAL_MARKER_ALLOWLIST",
    "ScanError",
    "render",
    "scan_repo",
]

# The staff-internal note marker the helpdesk tags articles with. Bare, it is
# ambiguous -- the repo defines and asserts it in nine files -- so it is only a
# finding away from those, and only ever alongside a finding WITHIN them.
INTERNAL_MARKER_PATTERN = re.compile(r"\[internal\]")

# A client's own registry numbers are disclosure as much as an email is: they
# name the legal entity the whole helpdesk belongs to.
REGISTRATION_PATTERN = re.compile(r"HRB\s*\d{3,}|Amtsgericht")
VAT_ID_PATTERN = re.compile(r"\bDE\d{9}\b")

# Mirrors the customer-artifact block in `.gitignore`. `test_..._gitignore_...`
# and `test_the_customer_artifact_rules_match_the_scanner` pin the two to each
# other, because a rule the scanner does not know about is a rule nothing checks.
CUSTOMER_ARTIFACT_RULES = (
    "occ_tickets/",
    "occ_tickets*.json",
    "occ_tickets*.jsonl",
    "occ_tickets*.ndjson",
    "seed_occ_tickets*",
    "*_occ_tickets_snapshot*.json",
)

# Files that legitimately contain the bare `[internal]` marker, each measured:
# the convention's own definition, its documentation, and its assertions. None
# of them is customer data. The compound detector still applies to them --
# exempting a file that *defines* the marker must not exempt a file that
# *carries* a note.
INTERNAL_MARKER_ALLOWLIST = (
    # ADR 0031 quantifies the corpus ("372 notes, of which 188 also carry an
    # email"); the numbers are the finding, not the notes.
    "docs/adr/0031-occ-tickets-corpus-retrieval.md",
    # Digits' operating note naming the marker as the exposure.
    "docs/ops/OCC_INVITE_KEY.md",
    # Review notes quoting the behaviour under review.
    "review-4945.md",
    "review-4963.md",
    # Source of the convention: the backfill script and the formatter tag.
    "scripts/index_occ_tickets.py",
    "scripts/zammad_mcp/README.md",
    "scripts/zammad_mcp/formatting.py",
    # Assertions that the tagging happens.
    "tests/ds/test_multilingual_embedder.py",
    "tests/scripts/test_zammad_mcp.py",
    # This detector and its suite: a scanner that cannot name the marker cannot
    # detect it, so these two must be exempt from the bare-marker rule. Both are
    # still scanned by the compound detector and by every other one, and
    # test_the_allowlist_is_the_measured_one fails if an entry stops containing
    # the marker -- so an entry cannot quietly become a blanket exemption.
    "scripts/scan_customer_pii.py",
    "tests/scripts/test_scan_customer_pii.py",
)

# The registry shapes are the same story one level along: `REGISTRATION_PATTERN`
# above has to spell `HRB` and `Amtsgericht` out to find them, and this suite has
# to spell out the fixtures they must catch. Measured on the staged tree: those
# two files are the only tracked files carrying a registry shape or a VAT id,
# and every finding was one of these two detectors.
SELF_REFERENTIAL_FILES = (
    "scripts/scan_customer_pii.py",
    "tests/scripts/test_scan_customer_pii.py",
)

# Exemptions are keyed BY DETECTOR, never by file. A file named here is still
# scanned by every detector not listed against it -- which is what keeps
# `scripts/scan_customer_pii.py` and its suite inside the compound detector's
# reach, so an unmasked note added to either one is still found.
DETECTOR_ALLOWLIST = {
    "internal-marker": frozenset(INTERNAL_MARKER_ALLOWLIST),
    "company-registration": frozenset(SELF_REFERENTIAL_FILES),
    "vat-id": frozenset(SELF_REFERENTIAL_FILES),
}

# Artifacts are reads-once dumps; nothing legitimate in this repo is larger.
MAX_BYTES = 1_000_000
SNIFF_BYTES = 8192


class ScanError(RuntimeError):
    """The scan could not run. Never a pass."""


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    detector: str
    detail: str


def _git(repo_root: Path, *args: str, stdin: str | None = None, ok_codes: tuple[int, ...] = (0,)) -> str:
    """Run git and return stdout, treating `ok_codes` as success.

    `git check-ignore` exits 1 when no path matched, which for this scanner is
    the clean case and not a malfunction. Passing it through as a failure would
    turn a green repository into a hard error, and passing every non-zero
    through as success would hide a real one -- hence the explicit set.
    """
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in ok_codes:
        raise ScanError(f"git {' '.join(args)} failed in {repo_root}: {proc.stderr.strip()}")
    return proc.stdout


def _tracked_paths(repo_root: Path) -> list[str]:
    """Tracked files only -- the index is the question, the tree is not."""
    raw = _git(repo_root, "ls-files", "-z")
    return [p for p in raw.split("\0") if p]


def _read_text(path: Path) -> str | None:
    """File contents, or None when the file is binary or too big to scan."""
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        with path.open("rb") as handle:
            if b"\0" in handle.read(SNIFF_BYTES):
                return None
    except OSError:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _artifact_matchers() -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Compile `CUSTOMER_ARTIFACT_RULES` into path matchers.

    Not by asking git. `git check-ignore -v` reports only the rule that *wins*,
    and the pre-existing `/data/` rule at `.gitignore:94` shadows
    `occ_tickets*.json` for every path under `data/` -- so a forced-added
    `data/occ_tickets.json` reports `/data/` and reads as covered by something
    else. A missed artifact is exactly the failure this script exists to catch,
    so the patterns are matched directly and the two stay pinned together by
    test_the_customer_artifact_rules_match_the_scanner.

    Only the two forms these rules use are supported; anything else raises
    rather than being silently ignored.
    """
    matchers: list[tuple[str, re.Pattern[str]]] = []
    for rule in CUSTOMER_ARTIFACT_RULES:
        if rule.endswith("/"):
            # A directory of that name at any depth.
            name = rule[:-1]
            matchers.append((rule, re.compile(rf"(?:^|/){re.escape(name)}(?:/|$)")))
            continue
        if "/" in rule or "*" not in rule and "?" not in rule:
            raise ScanError(f"unsupported customer-artifact rule shape: {rule!r}")
        # A glob on the last path segment, at any depth.
        matchers.append((rule, re.compile(rf"(?:^|/){translate(rule)}$")))
    return tuple(matchers)


def _tracked_customer_artifacts(tracked: list[str]) -> list[Finding]:
    """Tracked files that are customer artifacts by name.

    `--no-index` is what makes the gitignore half of this checkable: without it
    git refuses to call a file ignored precisely because it is tracked, which is
    the one case being looked for. The scanner keys on the customer-artifact
    rules and not on "matched any rule" because 11 tracked files already match
    existing rules (`.env*`, `.vscode/`) and those are not findings.
    """
    matchers = _artifact_matchers()
    findings: list[Finding] = []
    for pathname in tracked:
        for rule, matcher in matchers:
            if matcher.search(pathname):
                findings.append(
                    Finding(pathname, 0, "tracked-customer-artifact",
                            f"tracked file matches the customer-artifact rule `{rule}`")
                )
                break
    return findings


def _content_findings(repo_root: Path, tracked: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for relative in tracked:
        text = _read_text(repo_root / relative)
        if text is None:
            continue
        marker_exempt = relative in DETECTOR_ALLOWLIST["internal-marker"]
        registry_exempt = (
            relative in DETECTOR_ALLOWLIST["company-registration"]
            and relative in DETECTOR_ALLOWLIST["vat-id"]
        )
        for number, line in enumerate(text.splitlines(), start=1):
            has_marker = INTERNAL_MARKER_PATTERN.search(line) is not None
            if has_marker and EMAIL_PATTERN.search(line):
                # Both halves are ordinary in this repo; on one line it is the
                # unmasked staff note with a person attached.
                findings.append(
                    Finding(relative, number, "internal-note-with-email",
                            "line carries an [internal] marker and an email address")
                )
                continue
            if has_marker and not marker_exempt:
                findings.append(
                    Finding(relative, number, "internal-marker",
                            "line carries an [internal] marker outside the allowlist")
                )
            if REGISTRATION_PATTERN.search(line) and not registry_exempt:
                findings.append(
                    Finding(relative, number, "company-registration",
                            "line carries a company registry reference")
                )
            if VAT_ID_PATTERN.search(line) and not registry_exempt:
                findings.append(
                    Finding(relative, number, "vat-id", "line carries a VAT id shape")
                )
    return findings


def scan_repo(repo_root: Path | str) -> list[Finding]:
    """Every customer-PII finding in the tracked tree of `repo_root`."""
    root = Path(repo_root).resolve()
    tracked = _tracked_paths(root)
    findings = _tracked_customer_artifacts(tracked)
    findings.extend(_content_findings(root, tracked))
    findings.sort(key=lambda f: (f.path, f.line, f.detector))
    return findings


def render(findings: list[Finding]) -> list[str]:
    """One locatable line per finding, and never the matched value."""
    return [f"{f.path}:{f.line}: {f.detector}: {f.detail}" for f in findings]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=".", help="repository to scan")
    parser.add_argument("--json", dest="report", help="write findings to this JSON file")
    args = parser.parse_args(argv)

    try:
        findings = scan_repo(args.repo_root)
    except ScanError as exc:
        print(f"scan could not run: {exc}", file=sys.stderr)
        return 2

    if args.report:
        Path(args.report).write_text(
            json.dumps(
                [
                    {"path": f.path, "line": f.line, "detector": f.detector, "detail": f.detail}
                    for f in findings
                ],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    for line in render(findings):
        print(line)
    if findings:
        print(f"\n{len(findings)} finding(s). Matched values are never printed; "
              "see the cited path and line.", file=sys.stderr)
        return 1
    print("no customer PII found in tracked files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Refuse a commit that adds a seed payload carrying unmasked customer PII.

The hole this fills: `scripts/secrets_audit.py` audits *secret names*, and
`scripts/check_example_credentials.py` catches credential-shaped values in
`.example`/`.template` files. Neither one looks at a data payload. On 2026-10-02
(#4987) `apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl`
landed on `main` carrying 791 rows that quote a customer email address, 86
distinct customer display names and 372 `[internal]` staff-only notes, in a
**public** repository. No check failed, because nothing was checking.

A payload that seeds a vector store is copied wholesale into a running Chroma
collection and served to whoever the tenant talks to. Reviewing it line by line
does not scale at 1.5 MB, and the reviewer's eye is the wrong instrument: the
defect is not one bad line, it is that a mask was missing from a generator.

So the invariant is mechanical and cheap: **a tracked payload may not contain
an email address that is not a reserved example domain.** Detection, not
judgement — this script does not know what a person is called and will not try.
A display name or an `[internal]` tag has no reliable shape, so it is out of
scope here; that residual is tracked as the free-text-name item on DIG-1230, and
masking it is a product decision, not a lint rule.

Three deliberate design points, each a trap this has already walked into:

* **Counts only, never values.** A finding prints the file, the line number and
  how many addresses are on it. It never echoes the address. A guard whose
  output can be pasted into a CI log is a second disclosure channel, and CI logs
  are readable by everyone who can read the repo — which, here, is everyone.
  The audit that established the numbers above worked the same way.
* **Reserved domains only.** `.test`, `.example`, `.invalid`, `.localhost` and
  friends are the domains reserved for exactly this (RFC 2606 / RFC 6761), so
  test fixtures stay writable without an allowlist that grows by exemption. A
  free-mail address is still a finding: `gmail.com` is not a reserved domain
  and `jane@gmail.test` is, which is what fixtures should use.
* **Diff-scoped, with an explicit whole-tree mode.** The default scans only the
  files a diff touches, so introducing the gate cannot retroactively fail on the
  payload that is already committed — the same reasoning as `BASELINE_SHA` in
  `check_review_coverage.py`. `--all` scans the tree and is what you want after
  containment lands. A gate that fires on the very commit that fixes the problem
  teaches people to reach for `--no-verify`.

Wired into `.github/workflows/security-gitleaks.yml` as a non-blocking-in-spirit
PR step, diff-scoped. It is deliberately **not** a required status check on
`main` or `develop` while the committed payload is still contained there: a
required check that is red on arrival gets suppressed rather than fixed. Making
it required is the last step of DIG-1230, once containment has landed.

Usage:
    scripts/check_pii_seed_payloads.py                        # uncommitted changes
    scripts/check_pii_seed_payloads.py --base origin/main     # a diff
    scripts/check_pii_seed_payloads.py --all                  # the whole tree
    scripts/check_pii_seed_payloads.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# An address, minus the domain. Deliberately loose on the local part: a miss
# here is a false negative on the exact rows this exists to catch, and the cost
# of a false positive is a fixture using `example.test` instead.
ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Top-level domains reserved for documentation and testing (RFC 2606 §2,
# RFC 6761). An address whose *last* label is one of these is an example by
# construction, not a disclosure: `corp.test`, `svc.invalid`, `localhost`.
RESERVED_TLDS: frozenset[str] = frozenset({"test", "example", "invalid", "localhost"})

# Second-level names reserved *under a real TLD* (RFC 2606 §2). These are the
# whole domain, not a suffix: `example.com` is reserved, `acme.example.com` is
# not (that is a real registrable domain shape and must be a finding).
RESERVED_DOMAINS: frozenset[str] = frozenset({"example.com", "example.net", "example.org"})

# Only data payloads are in scope. Source, docs and tests are covered by review
# and by the other guards; a payload is the one file class whose contents are
# copied verbatim into a running index.
PAYLOAD_SUFFIXES: tuple[str, ...] = (".jsonl", ".json")

# Paths never scanned. A committed payload is not the only way to seed an index,
# but it is the one that lands in git history, so it is the one this checks.
SKIP_PREFIXES: tuple[str, ...] = (
    "tests/",
    "docs/",
    "node_modules/",
    ".git/",
    "projects/",  # confidential local vaults, never pushed (see CLAUDE.md)
)


@dataclass(frozen=True)
class Finding:
    """One line carrying at least one non-reserved address.

    `count` is the number of such addresses on the line. No address is stored:
    see the module docstring.
    """

    path: str
    line: int
    count: int

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.count} unmasked address(es)"


def domain_of(address: str) -> str:
    """The domain of an address, lowercased.

    Split on the *last* `@` so a quoted `Name <addr>` header still resolves.
    """
    _, _, domain = address.rpartition("@")
    return domain.strip().strip(">,\"'").lower().rstrip(".")


def is_reserved(address: str) -> bool:
    """True when the address sits on a documentation/test domain.

    Two cases, and the distinction between them is the whole point:

    * a reserved **TLD** as the last label — `corp.test`, `acme.invalid`,
      `localhost`. Any subdomain of a reserved TLD is reserved too, because
      nothing can be registered under it.
    * a reserved **second-level name** as the entire domain — `example.com`,
      `example.net`, `example.org`. Exact match only. `acme.example.com` is a
      real registrable shape and must be reported.

    An earlier draft tested every label against the reserved set, which let
    `acme-corp.example.org` through on the strength of its middle label. The
    tests caught it; matching any label was never the rule.

    A trailing dot (the DNS root) is stripped first: `jane@example.test.` is
    still `example.test`.
    """
    domain = domain_of(address)
    if not domain:
        return False
    labels = domain.split(".")
    if not labels or not labels[-1]:
        return False
    if labels[-1] in RESERVED_TLDS:
        return True
    return domain in RESERVED_DOMAINS


def unmasked_addresses(text: str) -> int:
    """How many addresses in `text` are not on a reserved domain.

    Counts occurrences, not distinct addresses: the point is how much is in the
    file, and a repeated address is still a committed one.
    """
    return sum(1 for address in ADDRESS_RE.findall(text) if not is_reserved(address))


def scan_text(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        count = unmasked_addresses(line)
        if count:
            findings.append(Finding(path=path, line=number, count=count))
    return findings


def is_payload(relpath: str) -> bool:
    """Whether a repo-relative path is a tracked data payload in scope."""
    normalised = relpath.replace("\\", "/")
    if normalised.startswith(SKIP_PREFIXES):
        return False
    return normalised.endswith(PAYLOAD_SUFFIXES)


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def payload_paths_in_diff(base: str, head: str, root: Path = REPO_ROOT) -> list[str]:
    """Payload paths touched between two refs, added/modified only.

    Deletions are dropped on purpose: removing a payload is the fix, and failing
    the commit that removes one would make containment impossible to land.
    """
    raw = _git("diff", "--name-only", "--diff-filter=AM", f"{base}...{head}", cwd=root)
    return [line for line in raw.splitlines() if line and is_payload(line)]


def uncommitted_payload_paths(root: Path = REPO_ROOT) -> list[str]:
    """Payload paths staged, modified or new in the working tree.

    `-uall` is load-bearing. Without it `git status --porcelain` collapses an
    untracked *directory* to a single `?? dir/` entry, and `dir/` is not a
    payload suffix — so `seed/new_tickets.jsonl` dropped into a brand-new folder
    would be invisible to the default run. That is the exact shape of the commit
    this guard exists to stop.

    Renames are `R  old -> new`; the destination is the path in the tree, so
    that is the one to test. Testing the combined string would test neither.
    """
    raw = _git("status", "--porcelain", "-uall", cwd=root)
    paths: list[str] = []
    for line in raw.splitlines():
        if len(line) < 4:
            continue
        code, _, path = line[:2], line[2:3], line[3:]
        if "D" in code:
            continue
        if "->" in path:
            path = path.rsplit("->", 1)[1].strip()
        if path and is_payload(path):
            paths.append(path)
    return paths


def tracked_payload_paths(root: Path = REPO_ROOT) -> list[str]:
    """Every tracked payload in the tree."""
    raw = _git("ls-files", "--", "*.jsonl", "*.json", cwd=root)
    return [line for line in raw.splitlines() if line and is_payload(line)]


def select_paths(
    base: str | None, head: str, whole_tree: bool, root: Path = REPO_ROOT
) -> tuple[list[str], str]:
    """Which paths to scan, and a label naming the scope for the report."""
    if whole_tree:
        return tracked_payload_paths(root), "tracked tree"
    if base is None:
        return uncommitted_payload_paths(root), "uncommitted changes"
    return payload_paths_in_diff(base, head, root), f"{base}...{head}"


def read_blob(ref: str | None, relpath: str, root: Path = REPO_ROOT) -> str | None:
    """The contents of `relpath` at `ref`, or `None` if it cannot be read.

    With a `ref`, the blob is read from git rather than from the working tree.
    That distinction is load-bearing: a payload added by a commit under review is
    not checked out locally, so a working-tree read skips it entirely and the
    guard passes green on exactly the commit it exists to stop. An earlier draft
    had this bug and the falsification against #4987 caught it.
    """
    if ref is None:
        try:
            return (root / relpath).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    result = subprocess.run(
        ["git", "show", f"{ref}:{relpath}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def scan(
    paths: list[str],
    ref: str | None = None,
    root: Path = REPO_ROOT,
) -> list[Finding]:
    """Scan payloads, reading each from `ref` when given, else from disk."""
    findings: list[Finding] = []
    for relpath in sorted(set(paths)):
        text = read_blob(ref, relpath, root)
        if text is None:
            continue
        findings.extend(scan_text(relpath, text))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refuse a commit that adds a payload carrying unmasked customer PII."
    )
    parser.add_argument("--base", help="Base ref; scans payloads this diff touches.")
    parser.add_argument("--head", default="HEAD", help="Head ref (default: HEAD).")
    parser.add_argument(
        "--all",
        dest="whole_tree",
        action="store_true",
        help="Scan every tracked payload instead of a diff.",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = parser.parse_args(argv)

    paths, scope = select_paths(args.base, args.head, args.whole_tree, REPO_ROOT)
    # Uncommitted scope reads the working tree (that is what is being proposed);
    # a diff or the whole tree reads blobs from git, so a payload that is not
    # checked out locally is still scanned.
    ref = None if (args.whole_tree is False and args.base is None) else args.head
    findings = scan(paths, ref=ref)
    addresses = sum(finding.count for finding in findings)

    if args.json:
        print(
            json.dumps(
                {
                    "scope": scope,
                    "scanned": len(set(paths)),
                    "files_with_findings": len({finding.path for finding in findings}),
                    "addresses": addresses,
                    # Counts and locations only. No address value is ever emitted.
                    "findings": [
                        {
                            "path": finding.path,
                            "line": finding.line,
                            "count": finding.count,
                        }
                        for finding in findings
                    ],
                },
                indent=2,
            )
        )
        return 1 if findings else 0

    print(f"Scanned {len(set(paths))} payload(s) in {scope}.")
    if not findings:
        print("OK: no unmasked address in any payload in scope.")
        return 0

    print(f"FAIL: {addresses} unmasked address(es) across {len(findings)} line(s).")
    for finding in findings:
        print(f"  {finding.render()}")
    print(
        "\nAddresses are not printed. Use a reserved example domain "
        "(RFC 2606: .test / .example / .invalid / .localhost) in fixtures, and "
        "mask real data before it is committed. See DIG-1210."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

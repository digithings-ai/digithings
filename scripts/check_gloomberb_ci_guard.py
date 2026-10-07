#!/usr/bin/env python3
"""GLOOMBERB_ENABLED deployed-config guard (DIG-1322, sibling of DIG-1233).

``GLOOMBERB_ENABLED`` is the kill switch for the whole Gloomberb tool family.
DIG-1233 makes it default OFF; this guard makes that default enforceable, so the
other half of the switch -- an *explicit* opt-in -- cannot be committed into a
deployed config by accident.

Why the guard exists: flipping the default to OFF only helps while nobody writes
``GLOOMBERB_ENABLED = "1"`` into a file that ships. Cloudflare ``[vars]``,
Dockerfile ``ENV``, a workflow ``env:`` block and a compose ``environment:`` entry
all reach a deployed process without ever passing through review as "a credential
change", and an enabling value in any of them silently re-opens a path Counsel
ruled prohibited (browser-session-cookie replay against ``api.gloom.sh``).

What is checked:
  * Only **git-tracked** files are scanned. An untracked local ``.env`` is not a
    deploy artifact, and scanning it would make the guard fail on developer
    machines for something CI cannot control.
  * A line whose first non-space character is ``#`` is a comment and is skipped.
  * An inline comment is stripped before the value is judged, so
    ``GLOOMBERB_ENABLED = "0"  # was "1" in staging`` passes.
  * Only an **enabling** value fails. A disabled or empty value is defence in
    depth and is allowed to stay committed -- that is the point of it.

The enabling set is **read out of the client**, not hardcoded here:
``digiquant/src/digiquant/data/gloomberb/client.py`` owns
``_TRUTHY_ENV_VALUES``, and this guard parses that literal. A second copy of the
set in this file is a second thing to forget to update, and forgetting it is the
exact failure the guard exists to catch. If the client cannot be parsed the guard
FALLS BACK to the literal set and says so on stdout -- it does not silently scan
with a set it invented, and it does not pass by being unable to read anything.

Deployed surfaces (``DEPLOYED_PATTERNS``) — an enabling value fails the build:
  * ``apps/**/wrangler.toml|json|jsonc``  — Workers deployment config; ``[vars]``
    is shipped to the edge.
  * ``**/Dockerfile``                       — ``ENV`` is baked into the image.
  * ``.github/workflows/*.yml|yaml``         — ``env:`` runs in CI and in deploys.
  * ``docker-compose*.yml``                 — the shared integration stack.

Local / dev surfaces (``LOCAL_PATTERNS``) — an enabling value is ALLOWED, because
this is the stated exemption the issue asks for. Local development keeps the family
reachable; only deployed configs are policed:
  * ``.env``, ``.env.*`` (except ``.env.example``, which is documentation)
  * ``docker-compose.override.yml``, ``compose/**``, ``dev/**``, ``scripts/**``
  * ``tests/**`` and ``docs/**`` are never scanned at all -- they hold prose and
    fixtures, not deploy artifacts.

There is deliberately **no per-line escape token** (no ``gloomberb-allow``). An
escape hatch on a security guard is just a second way to fail the guard; the only
exemption is the LOCAL list above, which is stated here in code and pinned by the
tests.

Coverage self-check: ``DEPLOYED_PATTERNS`` is an allowlist, so a config family
added later could escape it. ``coverage_gaps()`` therefore fails the build if any
git-tracked ``wrangler.toml`` in the repo matches no deployed pattern -- today
there are seven, and a new Cloudflare app must not be able to land outside the
guard unnoticed.

Stdlib-only; no pip or npm install needed.

Usage: check_gloomberb_ci_guard.py [--warn] [--json]
  --warn  report findings but exit 0 (for a dry run against a known-bad tree)
  --json  emit the findings as JSON on stdout instead of text
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

FLAG = "GLOOMBERB_ENABLED"

REPO_ROOT = Path(__file__).resolve().parents[1]

# The client is the single source of truth for what counts as "on".
CLIENT_REL = Path("digiquant/src/digiquant/data/gloomberb/client.py")

# Fallback only, used when CLIENT_REL cannot be parsed. Mirrors the client's set
# at the time of writing; `enabling_values()` reports which source it used.
FALLBACK_ENABLING_VALUES = frozenset({"1", "true", "yes", "on"})

# Patterns that ship to a deployed process.
DEPLOYED_PATTERNS: tuple[str, ...] = (
    "apps/*/wrangler.toml",
    "apps/*/wrangler.json",
    "apps/*/wrangler.jsonc",
    "apps/*/*/wrangler.toml",
    "apps/*/*/wrangler.json",
    "apps/*/*/wrangler.jsonc",
    "*/Dockerfile",
    "*/*/Dockerfile",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "docker-compose*.yml",
    "docker-compose*.yaml",
)

# The stated local/dev exemption. Enabling values here are allowed.
LOCAL_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "docker-compose.override.yml",
    "docker-compose.override.yaml",
    "compose/*",
    "dev/*",
    "scripts/*",
)

# Never a deploy artifact.
IGNORED_PATTERNS: tuple[str, ...] = (
    ".env.example",
    "node_modules/*",
    ".worktrees/*",
    ".paperclip/*",
    "apps/*/reference/*",
    "apps/*/*/reference/*",
)

# Families that must never escape DEPLOYED_PATTERNS without a deliberate edit.
COVERAGE_FAMILIES: tuple[str, ...] = ("wrangler.toml", "wrangler.json", "wrangler.jsonc")

# name=value / name: value / "name": value, with an optional leading `export`,
# `ENV`, `-`, or `{` so compose and Dockerfile forms match too.
_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    ^[\s{>*-]*
    (?:export\s+|ENV\s+)?
    ["']?
    (?P<name>[A-Z][A-Z0-9_]*)
    ["']?
    \s*(?::|=)\s*
    (?P<value>.*)$
    """
)

# The braces are optional so that an emptied set (``frozenset()``) still parses and
# is reported as "empty" rather than as "the name moved" -- the two mean different
# things to whoever has to fix it.
_CLIENT_TRUTHY_RE = re.compile(
    r"""_TRUTHY_ENV_VALUES[^=]*=\s*frozenset\(\s*\{?(?P<body>[^})]*)\}?""",
    re.MULTILINE,
)

_CLIENT_STRING_RE = re.compile(r"""["'](?P<value>[^"']*)["']""")


@dataclass(frozen=True)
class Finding:
    """One enabling value found in one file."""

    path: str
    line_no: int
    line: str
    deployed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line_no,
            "text": self.line.strip(),
            "deployed": self.deployed,
        }


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def is_deployed(path: str) -> bool:
    """True when a committed file at ``path`` ships to a deployed process."""
    if _matches(path, IGNORED_PATTERNS):
        return False
    return _matches(path, DEPLOYED_PATTERNS) and not _matches(path, LOCAL_PATTERNS)


def is_local(path: str) -> bool:
    """True when a committed file at ``path`` is a local/dev config."""
    if _matches(path, IGNORED_PATTERNS):
        return False
    return _matches(path, LOCAL_PATTERNS)


def enabling_values(client_path: Path | None = None) -> tuple[frozenset[str], str]:
    """Return the enabling values and the source label used to obtain them.

    Reads ``_TRUTHY_ENV_VALUES`` out of the Gloomberb client so this guard and the
    runtime can never disagree about which value turns the family on.
    """
    path = client_path if client_path is not None else REPO_ROOT / CLIENT_REL
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return FALLBACK_ENABLING_VALUES, f"fallback (cannot read {CLIENT_REL})"

    match = _CLIENT_TRUTHY_RE.search(text)
    if match is None:
        return FALLBACK_ENABLING_VALUES, f"fallback (no _TRUTHY_ENV_VALUES in {CLIENT_REL})"

    values = frozenset(
        v.strip().lower() for v in _CLIENT_STRING_RE.findall(match.group("body")) if v.strip()
    )
    if not values:
        return FALLBACK_ENABLING_VALUES, f"fallback (empty _TRUTHY_ENV_VALUES in {CLIENT_REL})"
    return values, f"parsed from {CLIENT_REL}"


def strip_inline_comment(raw: str) -> str:
    """Drop a trailing ``# ...`` comment, then surrounding whitespace and quotes."""
    value = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.strip()


def scan_text(path: str, text: str, values: frozenset[str]) -> list[Finding]:
    """Return every enabling ``GLOOMBERB_ENABLED`` value in ``text``."""
    deployed = is_deployed(path)
    if not deployed and not is_local(path):
        return []

    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        match = _ASSIGNMENT_RE.match(line)
        if match is None or match.group("name") != FLAG:
            continue
        value = strip_inline_comment(match.group("value"))
        if value.lower() in values:
            findings.append(Finding(path=path, line_no=line_no, line=line, deployed=deployed))
    return findings


def tracked_files(repo_root: Path | None = None) -> list[str]:
    """Repo-relative paths of git-tracked files, or ``[]`` outside a checkout."""
    root = repo_root if repo_root is not None else REPO_ROOT
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def coverage_gaps(files: list[str]) -> list[str]:
    """Tracked config files that no deployed pattern claims.

    An empty return is the claim "every Cloudflare config in this repo is inside
    the guard". A non-empty return means a new app or config family landed
    outside DEPLOYED_PATTERNS and the allowlist needs a deliberate edit.
    """
    gaps = []
    for path in files:
        name = path.rsplit("/", 1)[-1]
        if name in COVERAGE_FAMILIES and not is_deployed(path):
            gaps.append(path)
    return sorted(gaps)


def scan(repo_root: Path | None = None) -> tuple[list[Finding], list[str], frozenset[str], str]:
    """Full scan: (findings, coverage gaps, enabling values, values source)."""
    root = repo_root if repo_root is not None else REPO_ROOT
    values, source = enabling_values(root / CLIENT_REL)
    files = tracked_files(root)

    findings: list[Finding] = []
    for path in files:
        if not (is_deployed(path) or is_local(path)):
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(scan_text(path, text, values))

    return findings, coverage_gaps(files), values, source


def render(findings: list[Finding], gaps: list[str], source: str, values: frozenset[str]) -> str:
    lines = [
        f"gloomberb-ci-guard: enabling values = {sorted(values)} ({source})",
    ]
    deployed = [f for f in findings if f.deployed]
    local = [f for f in findings if not f.deployed]

    for gap in gaps:
        lines.append(f"  COVERAGE GAP  {gap}: no DEPLOYED_PATTERNS entry claims this config")

    for finding in deployed:
        lines.append(
            f"  DEPLOYED      {finding.path}:{finding.line_no}: {finding.line.strip()}"
            + "  -- GLOOMBERB_ENABLED must never be enabled in a deployed config"
        )
    for finding in local:
        lines.append(f"  local-ok      {finding.path}:{finding.line_no}: {finding.line.strip()}")

    if not deployed and not gaps:
        lines.append(f"gloomberb-ci-guard: PASS ({len(local)} local exemption(s), 0 deployed)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--warn", action="store_true", help="report but exit 0")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON output")
    args = parser.parse_args(argv)

    findings, gaps, values, source = scan()

    if args.as_json:
        print(
            json.dumps(
                {
                    "ok": not gaps and not [f for f in findings if f.deployed],
                    "enablingValues": sorted(values),
                    "valuesSource": source,
                    "coverageGaps": gaps,
                    "findings": [f.as_dict() for f in findings],
                },
                indent=2,
            )
        )
    else:
        print(render(findings, gaps, source, values))

    blocking = gaps or [f for f in findings if f.deployed]
    if blocking and args.warn:
        return 0
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())

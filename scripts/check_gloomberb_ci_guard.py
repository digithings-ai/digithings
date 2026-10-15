#!/usr/bin/env python3
"""Gloomberb deployed-config guard (DIG-1322, sibling of DIG-1233, per DIG-2752).

**What this guard gates is the session cookie, not the flag.** Chris's decision
of 2026-10-10 (DIG-2752) is that gating is *per tool*: the public Gloomberb tools
stay on everywhere, and only the cookie-required tools are gated, on a
per-deployer ``GLOOMBERB_SESSION_COOKIE`` secret. A deployed
``GLOOMBERB_ENABLED = "1"`` is therefore an intended configuration -- the public
tools are supposed to be reachable -- and this guard must not block on it.

So ``GLOOMBERB_ENABLED`` is **reported** (``flag-on``) and never blocks, anywhere.
That supersedes DIG-1322's original "never set to an enabling value in a deployed
config" line, which was written against a family-wide default-off posture that no
longer holds. The reason it is still reported rather than dropped is that the flag
is the switch the cookie half is read next to, and a reviewer looking at a diff
that turns it on should be able to see the gate say so without stopping the build.

Why the cookie half exists: ``GLOOMBERB_SESSION_COOKIE`` is a real credential --
a browser session cookie replayed against ``api.gloom.sh``, the access method
Counsel ruled prohibited without an organisational licence. The flag decides
whether the family is reachable; the cookie decides whether it is *authenticated*.
Watching only the flag left the second half free to regress just as silently, and
DIG-2752 makes the cookie the one thing a deployer supplies out of band. Cloudflare
``[vars]``, Dockerfile ``ENV``, a workflow ``env:`` block and a compose
``environment:`` entry all reach a deployed process without ever passing through
review as "a credential change".

What is checked:
  * Only **git-tracked** files are scanned. An untracked local ``.env`` is not a
    deploy artifact, and scanning it would make the guard fail on developer
    machines for something CI cannot control.
  * A line whose first non-space character is ``#`` is a comment and is skipped.
  * An inline comment is stripped before the value is judged, so
    ``GLOOMBERB_SESSION_COOKIE = "abc"  # not a real one`` is still judged on
    ``"abc"`` and fails. A comment is never a way to talk the cookie half down.
  * For the cookie, a value that is not provably a placeholder or a secret
    reference **fails**, in every scanned file. For the flag, only the shape of
    the assignment is reported.

The cookie half (DIG-2752) -- the three checks that are the gate:

``GLOOMBERB_SESSION_COOKIE`` is the per-deployer credential the Gloomberb family
is now gated on. Per DIG-2752 it belongs to whoever deploys the stack, it is
supplied through that deployment's secret store, and it is never ours. The flag
above only decides whether the family is reachable; the cookie decides whether
it is *authenticated*. A guard that watched only the flag would let the second
half regress just as silently, so three checks were added:

  1. ``cookie_value`` -- a **committed cookie value** fails in EVERY scanned
     file, the local exemption included. The exemption exists because running the
     tools locally was authorised; it was never an authorisation to commit the
     credential that makes them authenticated. A *tracked* cookie is an exposure
     wherever it sits, so this rule has no local pass.
     Passes: an empty value, a visible placeholder (``<cookie-value>``,
     ``{paste-here}``, ``REDACTED``, ``CHANGEME``) and a secret reference.
  2. ``plaintext_cookie_slot`` -- a **deployed** file naming the cookie in a
     plaintext carrier (``[vars]``, a workflow ``env:``, a compose
     ``environment:``, a Dockerfile ``ENV``) fails unless the value is a secret
     reference -- **including at the empty value**, which rule 1 cannot catch.
     That is its whole job: ``GLOOMBERB_SESSION_COOKIE = ""`` in ``[vars]`` is a
     slot in git that invites the value, and a per-deployer secret belongs in
     ``wrangler secret put`` / ``secrets.*``, never in a file.
  3. ``advertised_without_secret`` -- a **deployed** file that points the cookie
     at an **indirection which is not a secret store** (``$VAR`` / ``${VAR}``,
     ``vars.X``, ``${{ vars.X }}``, ``process.env.X``, ``os.environ``,
     ``Deno.env``) also fails. This is Chris's "none advertised without a
     ``GLOOMBERB_SESSION_COOKIE`` secret" case: a repository variable is a
     settings field, and a shell passthrough baked into a Dockerfile ``ENV`` is a
     committed value wearing a disguise. The gate is on the *cookie*, not on the
     flag turning the family on -- so a deployed config that turns the family on
     for the public tools, and says nothing at all about the cookie, passes.

     ``env.X`` is deliberately **accepted** here. On a Cloudflare Worker
     ``env.GLOOMBERB_SESSION_COOKIE`` *is* the binding a ``wrangler secret put``
     produces, so it is the sanctioned path and it is the one a real deployment
     writes.

Bound of this cookie half, stated so it is not over-read: it covers **config
surfaces** -- the deployed and local file sets listed below -- because that is
where a *config* cookie lives. A cookie pasted into source or prose is a
different guard's job (``tests/scripts/test_gloomberb_session_cookie_runbook.py``
pins the runbook's placeholder discipline; ``security-gitleaks.yml`` scans the
repo for credential shapes), and ``tests/`` must stay out of this one because
its fixtures deliberately hold cookie-shaped strings to prove the gate works.

Fail-closed throughout: a cookie value the guard cannot classify as a placeholder
or a secret reference is treated as a value.

The enabling set is **read out of the client**, not hardcoded here:
``digiquant/src/digiquant/data/gloomberb/client.py`` owns
``_TRUTHY_ENV_VALUES``, and this guard parses that literal. A second copy of the
set in this file is a second thing to forget to update, and forgetting it is the
exact failure the guard exists to catch. If the client cannot be parsed the guard
FALLS BACK to the literal set and says so on stdout -- it does not silently scan
with a set it invented, and it does not pass by being unable to read anything.

Deployed surfaces — a cookie in a plaintext carrier, or a committed cookie value,
fails the build:
  * ``apps/**/wrangler.toml|json|jsonc``  — Workers deployment config; ``[vars]``
    is shipped to the edge.
  * ``**/Dockerfile*`` at any depth, by basename — ``ENV`` is baked into the image.
  * ``**/docker-compose*.yml``, ``**/compose*.yml`` — the shared integration stack
    plus the client release and self-host compose sets under ``infra/``.
  * ``.github/workflows/*.yml|yaml`` and ``.github/*.yml|yaml`` — ``env:`` runs in
    CI and in deploys. The second entry is deliberately broad: it is there for
    ``.github/digiquant-pipeline.yml``, whose ``env:`` block
    ``workflows/pipeline-digiquant.yml`` loads into ``$GITHUB_ENV`` from outside
    ``.github/workflows/``, which path filtering cannot see.

Local / dev surfaces (``LOCAL_PATTERNS``) — a cookie *value* still fails here,
because the exemption authorises a developer to RUN the tools with their own
cookie in an untracked ``.env``, not to commit it. Local development keeps the
family reachable; only deployed cookie *slots* are policed:
  * ``.env``, ``.env.*`` (except ``.env.example``, which is documentation)
  * ``docker-compose.override.yml``, ``compose/**``, ``dev/**``, ``scripts/**``
  * ``docker-compose.local.yml`` — the Langfuse bring-up compose, which its own
    header marks LOCAL DEV ONLY.
  * ``tests/**`` and ``docs/**`` are never scanned at all -- they hold prose and
    fixtures, not deploy artifacts.

One family is never local: a ``Dockerfile*`` basename (``NEVER_LOCAL_BASENAMES``).
``ENV`` is baked into whichever image the recipe builds, so the recipe ships from
``scripts/`` as much as from ``digiquant/`` -- ``scripts/zammad_mcp/Dockerfile.mcp``
builds the zammad MCP image and is covered by that rule, not by ``scripts/**``.

There is deliberately **no per-line escape token** (no ``gloomberb-allow``). An
escape hatch on a security guard is just a second way to fail the guard; the only
exemption is the LOCAL list above, which is stated here in code and pinned by the
tests.

Coverage self-check: ``DEPLOYED_PATTERNS`` is an allowlist, so a config family
added later could escape it. ``coverage_gaps()`` therefore fails the build if any
git-tracked file of a watched family -- ``wrangler.*``, ``Dockerfile*``, or a
compose basename -- is claimed by no rule at all: neither deployed, nor on the
local exemption list, nor ignored. A new Cloudflare app, a new
``Dockerfile.<target>``, or a new ``infra/`` release compose can therefore not land
outside the guard unnoticed, and a deliberate exemption has to be written down as
one of the three lists above.

Deliberately **not** a watched family: ``digiquant/supabase/config.toml``. It
configures the local Supabase CLI stack (ports, schemas, seed) and carries no
``env``/``environment`` surface through which the flag could reach a deployed
process; the containers it configures are described by compose files that are
watched. Adding it would be coverage of the file rather than of the vector.

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

# Patterns that ship to a deployed process, matched against the whole path.
DEPLOYED_PATTERNS: tuple[str, ...] = (
    "apps/*/wrangler.toml",
    "apps/*/wrangler.json",
    "apps/*/wrangler.jsonc",
    "apps/*/*/wrangler.toml",
    "apps/*/*/wrangler.json",
    "apps/*/*/wrangler.jsonc",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    # `.github/digiquant-pipeline.yml` holds `env:` tunables that
    # .github/workflows/pipeline-digiquant.yml loads into $GITHUB_ENV. It sits
    # outside .github/workflows/, so the entry above misses it. Deliberately
    # broad over the rest of `.github/`: over-covering costs nothing on the
    # deployed side, and the one real carrier there is invisible to path
    # filtering. (fnmatch `*` crosses `/`, so this also reaches workflows/.)
    ".github/*.yml",
    ".github/*.yaml",
)

# Families matched against the BASENAME at any depth, because the repo's own
# naming defeats path globs on both axes:
#
#   * depth — five root deploy images (`Dockerfile.digithings-stack-cloudflare`,
#     `Dockerfile.digitrace-langfuse-web`, ...) have no `/` for a path glob to
#     anchor on at all, and `*/*/Dockerfile` cannot reach three-deep recipes;
#   * name  — this repo does not call a build recipe `Dockerfile`. Of the 20
#     tracked Dockerfiles, 12 are `Dockerfile.<target>`.
#
# A glob like `*/Dockerfile` therefore matched 8 of the 20 tracked Dockerfiles and
# let the other 12 through, every root deploy image among them -- the exact vector
# the guard exists to catch. Basename matching makes depth irrelevant and follows
# the repo's real convention instead of an invented one.
DEPLOYED_BASENAMES: tuple[str, ...] = (
    "Dockerfile",
    "Dockerfile.*",
    "docker-compose.yml",
    "docker-compose.yaml",
    "docker-compose.*.yml",
    "docker-compose.*.yaml",
    "compose.yml",
    "compose.yaml",
    "compose.*.yml",
    "compose.*.yaml",
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

# Local exemptions keyed on basename, because the deployed compose globs above are
# now basename-matched and would otherwise claim these. `docker-compose.override.yml`
# wins over the deployed `docker-compose*.yml` glob: it is the root stack's local
# override, layered on the deployed file at run time.
LOCAL_BASENAMES: tuple[str, ...] = (
    "docker-compose.override.yml",
    "docker-compose.override.yaml",
    # apps/digitrace-langfuse/docker-compose.local.yml — its own header says
    # "LOCAL DEV ONLY ... NOT for production".
    "docker-compose.local.yml",
    "docker-compose.local.yaml",
)

# Never a deploy artifact.
IGNORED_PATTERNS: tuple[str, ...] = (
    ".env.example",
    "node_modules/*",
    ".worktrees/*",
    ".paperclip/*",
    "apps/*/reference/*",
    "apps/*/*/reference/*",
    # docs/ holds prose, examples and templates. docs/templates/project/
    # docker-compose.yml is a starting point for a client, not this repo's stack.
    # The module docstring promises docs/ is never scanned; basename matching
    # would otherwise reach it now that compose is matched by name at any depth.
    "docs/*",
    # GitHub issue/PR form templates: not workflows, no env: block.
    ".github/ISSUE_TEMPLATE/*",
)

# Families the local/dev exemption must not be able to claim. A build recipe is
# not a dev config: `ENV` is baked into whichever image it builds, so it ships
# from scripts/ as much as from digiquant/. scripts/zammad_mcp/Dockerfile.mcp
# builds the zammad MCP image and is deployed under that rule, not under scripts/**.
NEVER_LOCAL_BASENAMES: tuple[str, ...] = ("Dockerfile", "Dockerfile.*")

# Families that must never escape coverage without a deliberate edit. Each entry is
# (label, basename patterns); every tracked file matching one must be claimed by
# DEPLOYED, LOCAL or IGNORED, or coverage_gaps() fails the build.
COVERAGE_BASENAME_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("wrangler", ("wrangler.toml", "wrangler.json", "wrangler.jsonc")),
    ("dockerfile", ("Dockerfile", "Dockerfile.*")),
    (
        "compose",
        (
            "docker-compose.yml",
            "docker-compose.yaml",
            "docker-compose.*.yml",
            "docker-compose.*.yaml",
            "compose.yml",
            "compose.yaml",
            "compose.*.yml",
            "compose.*.yaml",
        ),
    ),
)

# Flattened view of the table above, kept for callers that just want the names.
COVERAGE_FAMILIES: tuple[str, ...] = tuple(
    pattern for _, patterns in COVERAGE_BASENAME_FAMILIES for pattern in patterns
)

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


# ── Cookie carriers (DIG-2752) ────────────────────────────────────────────────
#
# The names are written out rather than read out of the client on purpose. The
# enabling set is a *runtime semantic* and must agree with `_env_flag`; the cookie
# names are a *contract* between this guard and the deployer-facing runbook, and
# the runbook's own test (`tests/scripts/test_gloomberb_session_cookie_runbook.py`)
# pins the same names independently. Two constants answering to two different
# owners is fine; two copies of one that are free to drift is not.
COOKIE_VARS = ("GLOOMBERB_SESSION_COOKIE", "SUBSTACK_SESSION_COOKIE")

#: A value that is plainly a stand-in, not a credential. Deliberately narrow: a
#: value the guard cannot *prove* is a placeholder is treated as a real cookie.
PLACEHOLDER_TOKENS = frozenset(
    {
        "changeme",
        "change-me",
        "cookie",
        "example",
        "none",
        "placeholder",
        "redacted",
        "replace-me",
        "secret",
        "todo",
        "unset",
        "xxx",
        "your-cookie",
    }
)

#: A value that points at a secret store rather than carrying one. Every arm is a
#: shape a real deployment uses, and the list ends at a shell variable: a
#: per-deployer secret must arrive through a secret store, so `$NAME` is NOT
#: accepted here even though it is accepted by the indirection check — a shell
#: passthrough of a Dockerfile `ENV` is baked into the image.
SECRET_REFERENCE_RE = re.compile(
    r"""(?ix)
      \$\{\{\s*secrets\.                        # GitHub Actions  ${{ secrets.NAME }}
    | \bsecrets\.[A-Za-z_]                      # any holder's secrets.NAME
    | \bwrangler\s+secret\b                     # `wrangler secret put NAME`
    | \bprocess\.env\.[A-Za-z_]
    | \benv\.[A-Za-z_]                          # Cloudflare Worker env.NAME
    | \bos\.environ(?:\.get)?\s*[\[(]
    | \bDeno\.env(?:\.get)?\s*[\[(]
    | \bimport\.meta\.env\b
    | \bgetenv\s*\(
    """
)

#: A value that resolves at deploy time but is **not** a secret store -- the third
#: check's subject. Deliberately narrower than the arm it replaced: every other
#: indirection (``env.NAME``, ``secrets.NAME``, ``process.env.NAME``,
#: ``os.environ``, ``Deno.env``) genuinely reads a secret store and is the
#: sanctioned path, so it is accepted and never reaches this. What is left are the
#: two that resolve to somewhere real but readable: a repository variable, and a
#: shell variable, which a Dockerfile ``ENV`` bakes into the image.
NOT_A_SECRET_STORE_RE = re.compile(
    r"""(?ix)
      \$\{\{?\s*vars\.[A-Za-z_]               # ${{ vars.NAME }} / ${vars.NAME}
    | \bvars\.[A-Za-z_]                       # Cloudflare vars.NAME
    | \$\{?[A-Z][A-Z0-9_]*\}?$                # shell $NAME / ${NAME}
    """
)


@dataclass(frozen=True)
class Finding:
    """One guard finding in one file.

    ``kind`` is what makes a finding blocking, so the reason is a property of the
    row rather than of the caller that filters it:

    * ``flag-on`` -- an enabling ``GLOOMBERB_ENABLED`` value. **Never blocks**,
      deployed or local: per-tool gating means the public tools are meant to be
      on. Reported because a reviewer should see the flag being turned on
      alongside whatever the cookie half says about the same file.
    * ``cookie_value`` -- a committed cookie value. **Always blocks**, local files
      included: the exemption authorises running the tools, not committing the
      credential that authenticates them.
    * ``plaintext_cookie_slot`` -- the cookie named in a deployed plaintext
      carrier with no secret reference, empty value included.
    * ``advertised_without_secret`` -- a deployed file pointing the cookie at
      something that is not a secret store.
    """

    path: str
    line_no: int
    line: str
    deployed: bool
    kind: str = "flag-on"

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line_no,
            "text": self.line.strip(),
            "deployed": self.deployed,
            "kind": self.kind,
        }


#: Why each kind blocks, in one place, so `render` and `main` cannot disagree.
FINDING_REASONS: dict[str, str] = {
    "flag-on": (
        "GLOOMBERB_ENABLED is on, so the public Gloomberb tools are reachable; "
        "that is intended under DIG-2752 per-tool gating and does not fail the build"
    ),
    "cookie_value": (
        "a session cookie value must never be committed; the per-deployer cookie "
        "belongs in that deployment's secret store (DIG-2752)"
    ),
    "plaintext_cookie_slot": (
        "a deployed config may name the cookie only through a secret reference "
        "(${{ secrets.X }}, env.X, wrangler secret put); a [vars]/ENV/env: slot "
        "is a slot in git that invites the value"
    ),
    "advertised_without_secret": (
        "this deployed config points the cookie at something that is not a secret "
        "store, so the cookie-required tools would be advertised without a "
        "GLOOMBERB_SESSION_COOKIE secret"
    ),
}


@dataclass(frozen=True)
class Gap:
    """One tracked config file that no rule claims."""

    family: str
    path: str

    def as_dict(self) -> dict[str, object]:
        return {"family": self.family, "path": self.path}


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _matches_basename(path: str, patterns: tuple[str, ...]) -> bool:
    name = _basename(path)
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def is_ignored(path: str) -> bool:
    """True when a committed file at ``path`` is never a deploy artifact."""
    return _matches(path, IGNORED_PATTERNS) or _matches_basename(path, IGNORED_PATTERNS)


def _never_local(path: str) -> bool:
    """True for families the local/dev exemption is not allowed to claim."""
    return _matches_basename(path, NEVER_LOCAL_BASENAMES)


def is_deployed(path: str) -> bool:
    """True when a committed file at ``path`` ships to a deployed process."""
    if is_ignored(path):
        return False
    if _never_local(path):
        return True
    if _matches(path, LOCAL_PATTERNS) or _matches_basename(path, LOCAL_BASENAMES):
        return False
    return _matches(path, DEPLOYED_PATTERNS) or _matches_basename(path, DEPLOYED_BASENAMES)


def is_local(path: str) -> bool:
    """True when a committed file at ``path`` is a local/dev config."""
    if is_ignored(path) or _never_local(path):
        return False
    return _matches(path, LOCAL_PATTERNS) or _matches_basename(path, LOCAL_BASENAMES)


def is_claimed(path: str) -> bool:
    """True when some rule — deployed, local exemption or ignore — owns ``path``."""
    return is_deployed(path) or is_local(path) or is_ignored(path)


def gap_family(path: str) -> str | None:
    """Label of the watched family ``path`` belongs to, or ``None``."""
    for label, patterns in COVERAGE_BASENAME_FAMILIES:
        if _matches_basename(path, patterns):
            return label
    return None


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


def is_placeholder(value: str) -> bool:
    """True when ``value`` is visibly a stand-in rather than a credential."""
    text = value.strip()
    if not text:
        return True
    if (text[0], text[-1]) in {
        ("<", ">"),
        ("{", "}"),
        ("[", "]"),
        ("(", ")"),
    }:
        return True
    return text.lower() in PLACEHOLDER_TOKENS


def is_secret_reference(value: str) -> bool:
    """True when ``value`` points at a secret store instead of carrying one."""
    return bool(SECRET_REFERENCE_RE.search(value.strip()))


def is_not_a_secret_store(value: str) -> bool:
    """True when ``value`` resolves at deploy time but *not* through a secret store.

    The narrow arm of the indirection check it replaced: a shell variable and a
    repository variable. Both resolve somewhere real at deploy time, and neither
    of those places is a secret store -- a shell passthrough in a Dockerfile
    ``ENV`` is baked into the image, and ``vars.NAME`` is a settings field that
    anybody with repo settings can read. Split out from the arms that genuinely
    are secret stores (``env.NAME``, ``secrets.NAME``, ``process.env.NAME``,
    ``os.environ``, ``Deno.env``) because those are the sanctioned path and the
    caller has already accepted them by the time this is consulted.
    """
    return bool(NOT_A_SECRET_STORE_RE.search(value.strip()))


def scan_text(path: str, text: str, values: frozenset[str]) -> list[Finding]:
    """Every guard finding in ``text``.

    Two halves that answer different questions.

    The flag half is **report-only**. Since DIG-2752's per-tool gating decision
    (2026-10-10) the public Gloomberb tools are meant to be reachable everywhere,
    so an enabling ``GLOOMBERB_ENABLED`` value is emitted as ``flag-on`` and
    blocks nowhere -- not deployed, not local. It is still emitted because a
    reviewer turning the flag on in a diff should see the gate acknowledge it in
    the same run that judges the cookie next to it.

    The cookie half is the only gate, and it has three rules:
    ``cookie_value`` (a committed credential -- always blocking),
    ``plaintext_cookie_slot`` (a deployed plaintext carrier holding a literal or
    an empty value) and ``advertised_without_secret`` (a deployed cookie line
    pointing at ``$VAR`` / ``vars.X``, i.e. at anything that is not a secret
    store). Ordering matters: ``is_secret_reference`` runs first, so a line that
    *does* name a secret store is never re-litigated by the two rules below it.
    """
    deployed = is_deployed(path)
    if not deployed and not is_local(path):
        return []

    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        match = _ASSIGNMENT_RE.match(line)
        if match is None:
            continue
        name = match.group("name")
        value = strip_inline_comment(match.group("value"))

        if name == FLAG:
            if value.lower() in values:
                findings.append(Finding(path=path, line_no=line_no, line=line, deployed=deployed))
            continue

        if name in COOKIE_VARS:
            if is_secret_reference(value):
                continue
            if is_not_a_secret_store(value):
                # An indirection is neither a placeholder nor a literal, so it is
                # classified before the two rules below -- otherwise `$VAR` would
                # be reported as a committed credential, which is the wrong reason
                # for what is actually a config pointing at the wrong place.
                if deployed:
                    findings.append(
                        Finding(
                            path=path,
                            line_no=line_no,
                            line=line,
                            deployed=deployed,
                            kind="advertised_without_secret",
                        )
                    )
                # Local: nothing is committed and nothing is deployed, so there is
                # nothing to gate. The file is still read either way.
                continue
            if not is_placeholder(value):
                findings.append(
                    Finding(
                        path=path,
                        line_no=line_no,
                        line=line,
                        deployed=deployed,
                        kind="cookie_value",
                    )
                )
            elif deployed:
                findings.append(
                    Finding(
                        path=path,
                        line_no=line_no,
                        line=line,
                        deployed=deployed,
                        kind="plaintext_cookie_slot",
                    )
                )
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


def coverage_gaps(files: list[str]) -> list[Gap]:
    """Tracked config files that no deployed, local or ignore rule claims.

    An empty return is the claim "every watched config family in this repo is inside
    the guard". A non-empty return means a new app, a new ``Dockerfile.<target>`` or
    a new compose family landed where no rule reaches, and one of the three lists
    needs a deliberate edit — as a claim, not as an omission.
    """
    gaps: list[Gap] = []
    for path in files:
        family = gap_family(path)
        if family is not None and not is_claimed(path):
            gaps.append(Gap(family=family, path=path))
    return sorted(gaps, key=lambda gap: (gap.family, gap.path))


def scan(repo_root: Path | None = None) -> tuple[list[Finding], list[Gap], frozenset[str], str]:
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


def is_blocking(finding: Finding) -> bool:
    """True when a finding must fail the build.

    Two arms, both there for DIG-2752. A committed cookie value blocks wherever it
    is, local files included: the exemption exists so a developer can *run* the
    tools with their own cookie in an untracked ``.env``, not to commit it. And
    ``flag-on`` blocks nowhere -- since the per-tool gating decision the public
    tools are meant to be on, so the flag is reported and the cookie is the gate.
    """
    if finding.kind == "cookie_value":
        return True
    if finding.kind == "flag-on":
        return False
    return finding.deployed


def render(findings: list[Finding], gaps: list[Gap], source: str, values: frozenset[str]) -> str:
    lines = [
        f"gloomberb-ci-guard: enabling values = {sorted(values)} ({source})",
        f"gloomberb-ci-guard: cookie vars = {list(COOKIE_VARS)}"
        " (committed values fail everywhere; deployed slots need a secret reference)",
        "gloomberb-ci-guard: GLOOMBERB_ENABLED is reported, not gated (per-tool gating, DIG-2752)",
    ]
    blocking = [f for f in findings if is_blocking(f)]
    flag_on = [f for f in findings if f.kind == "flag-on"]
    local_ok = [f for f in findings if not is_blocking(f) and f.kind != "flag-on"]

    for gap in gaps:
        lines.append(
            f"  COVERAGE GAP  [{gap.family}] {gap.path}:"
            " no deployed, local or ignore rule claims this config"
        )

    for finding in blocking:
        label = "COOKIE" if finding.kind == "cookie_value" else "DEPLOYED"
        lines.append(
            f"  {label:<13} {finding.path}:{finding.line_no}: {finding.line.strip()}"
            f"  -- {FINDING_REASONS[finding.kind]}"
        )
    for finding in flag_on:
        lines.append(
            f"  flag-on       {finding.path}:{finding.line_no}: {finding.line.strip()}"
            f"  -- {FINDING_REASONS['flag-on']}"
        )
    for finding in local_ok:
        lines.append(f"  local-ok      {finding.path}:{finding.line_no}: {finding.line.strip()}")

    if not blocking and not gaps:
        lines.append(
            f"gloomberb-ci-guard: PASS ({len(local_ok)} local exemption(s),"
            f" {len(flag_on)} flag-on report(s), 0 blocking)"
        )
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
                    "ok": not gaps and not [f for f in findings if is_blocking(f)],
                    "enablingValues": sorted(values),
                    "valuesSource": source,
                    "cookieVars": list(COOKIE_VARS),
                    "coverageGaps": [g.as_dict() for g in gaps],
                    "findings": [f.as_dict() for f in findings],
                },
                indent=2,
            )
        )
    else:
        print(render(findings, gaps, source, values))

    blocking = gaps or [f for f in findings if is_blocking(f)]
    if blocking and args.warn:
        return 0
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())

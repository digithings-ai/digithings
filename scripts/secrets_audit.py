#!/usr/bin/env python3
"""Audit the secret surface: the names workflows read vs where they are defined.

A name is defined at some level in GitHub (repo secret, repo variable, org secret,
environment secret) and read in `.github/**/*.yml`; `docs/ops/SECRETS_INVENTORY.md`
is the hand-kept map of that same surface. The levels drift apart silently, so this
compares them in seconds:

    python scripts/secrets_audit.py            # asks `gh` for every level
    python scripts/secrets_audit.py --strict   # exit 1 when a repo secret is never read
    python scripts/secrets_audit.py --secrets-file names.txt --variables-file vars.txt

Five findings, in increasing order of how long they hide:

- `dead` — a repo secret nothing reads
- `not repo-level` — a read defined at another level (repo variable, org or
  environment secret), which is normal
- `unresolved` — a read no level defines; Actions substitutes an empty string, so
  a typo is invisible until a pipeline fails somewhere downstream
- `repo-over-org` — defined at both repo and org level, where the repo copy silently
  wins: two places to rotate and only one of them load-bearing
- `env-over-repo` — defined as both a repo secret and an environment secret: two live
  values, and a job that declares that environment reads the environment copy

THE MANIFEST, AND WHY CI NEEDS ONE

`unresolved` is the finding that breaks a deploy lane. A workflow read
`secrets.CLOUDFLARE_WORKERS_API_TOKEN`, that name existed nowhere, and Actions
substitutes an empty string for a secret it cannot find — so nothing failed at the
read. The deploy lane carried an empty token until wrangler refused, somewhere else,
later. This script finds that name, but only if it can be told where the secrets
live, and from a workflow it cannot: `GET repos/{owner}/{repo}/actions/secrets` and
the org and environment equivalents document that they need the `repo` scope, and a
workflow's GITHUB_TOKEN is a GitHub App installation token whose `permissions:`
vocabulary has no key for secrets. Run 37235973852 (#5063) granted `actions: read`
and all three listings still answered 403. No value of `permissions:` changes that,
and giving CI a token that could read them was rejected on purpose (Paperclip
DIG-477, option D).

So the levels come from a committed, names-only manifest of where the secrets live:

    python scripts/secrets_audit.py --write-manifest .github/secret-names.json
    python scripts/secrets_audit.py --manifest .github/secret-names.json --strict-unresolved

The manifest holds NAMES, never values, and `docs/ops/SECRETS_INVENTORY.md` already
publishes every one of those names, so it exposes nothing new. A level the writer
could not list is recorded as `read: false`, and the audit then refuses to claim it
checked everything: a level that could not be asked about is not a level with
nothing in it.

Two switches are offline, and both make `gh` never called: `--manifest` reads the
committed file, `--secrets-file` reads names from files on disk. `--strict`
(dead) and `--strict-unresolved` (a read nothing defines) are the two findings that
fail the run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent

EXPRESSION_RE = re.compile(r"\$\{\{(.*?)\}\}")

SECRET_READ_RE = re.compile(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)")

GITHUB_YAML_GLOBS: tuple[str, ...] = (".github/**/*.yml", ".github/**/*.yaml")

# Provided by Actions itself, not a secret anyone has to manage.
IMPLICIT_SECRETS: frozenset[str] = frozenset({"GITHUB_TOKEN"})

# The manifest's own schema version. A reader that does not recognise it refuses the
# file rather than guessing at a shape it does not know.
MANIFEST_SCHEMA_VERSION = 1

# A manifest older than this is stale: a secret deleted after it was written still
# reads as defined. The window is the 90-day rotation review's, so "as fresh as the
# last rotation review" is one rule and not two. Staleness is reported, not failed on
# — a stale manifest is the operator's to refresh, and failing an unrelated pull
# request over it would block every merge in the repo for something that has nothing
# to do with the change.
MANIFEST_STALE_DAYS = 90


def reads_in(text: str) -> set[str]:
    """Secret names one YAML file reads.

    Only names inside `${{ ... }}` count, and a trailing comment is removed first,
    so a commented-out read is not mistaken for a live one.
    """
    found: set[str] = set()
    for raw in text.splitlines():
        masked = list(raw)
        for match in EXPRESSION_RE.finditer(raw):
            for index in range(*match.span()):
                masked[index] = "\x00"
        comment = "".join(masked).find("#")
        line = raw if comment == -1 else raw[:comment]
        for expression in EXPRESSION_RE.findall(line):
            found.update(SECRET_READ_RE.findall(expression))
    return found


class Report(NamedTuple):
    """Reads seen in workflows, split against the repo-level secret list."""

    reads: set[str]
    dead: set[str]
    unmanaged: set[str]


def extract_secret_reads(root: Path) -> dict[str, set[str]]:
    """Map every `.github/**/*.yml` file to the secret names it reads."""
    by_file: dict[str, set[str]] = {}
    for pattern in GITHUB_YAML_GLOBS:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            by_file[path.relative_to(root).as_posix()] = reads_in(text)
    return by_file


def classify(by_file: dict[str, set[str]], repo_secrets: set[str]) -> Report:
    """`dead` = a repo secret nothing reads; `unmanaged` = a read with no repo secret."""
    reads: set[str] = set().union(*by_file.values()) if by_file else set()
    reads -= IMPLICIT_SECRETS
    return Report(
        reads=reads,
        dead=repo_secrets - reads,
        unmanaged=reads - repo_secrets,
    )


class Surface(NamedTuple):
    """Names defined per level; `None` where the level could not be read."""

    repo_secrets: set[str]
    repo_variables: set[str] | None = None
    org_secrets: set[str] | None = None
    environment_secrets: dict[str, set[str]] | None = None

    @property
    def complete(self) -> bool:
        """True when every level was read, so `unresolved` means something."""
        return (
            self.repo_variables is not None
            and self.org_secrets is not None
            and self.environment_secrets is not None
        )

    def levels_of(self, name: str) -> tuple[str, ...]:
        """Every level defining `name`, in report order."""
        found: list[str] = []
        if name in self.repo_secrets:
            found.append("repo secret")
        if self.repo_variables and name in self.repo_variables:
            found.append("repo variable")
        if self.org_secrets and name in self.org_secrets:
            found.append("org secret")
        for environment, names in (self.environment_secrets or {}).items():
            if name in names:
                found.append(f"{environment} env secret")
        return tuple(found)


class Levels(NamedTuple):
    """How the reads split once every level is known."""

    explained: set[str]
    unresolved: set[str]
    shadowed: set[str]
    env_over_repo: set[str]


def classify_levels(reads: set[str], surface: Surface) -> Levels:
    """Split reads into defined-at-another-level, defined-nowhere, and shadowing pairs."""
    levels = {name: surface.levels_of(name) for name in reads}
    return Levels(
        explained={name for name, where in levels.items() if where and "repo secret" not in where},
        unresolved={name for name, where in levels.items() if not where},
        shadowed={
            name
            for name, where in levels.items()
            if "repo secret" in where and "org secret" in where
        },
        env_over_repo={
            name
            for name, where in levels.items()
            if "repo secret" in where and any(level.endswith("env secret") for level in where)
        },
    )


def _gh_stdout(cmd: list[str], root: Path) -> str | None:
    """`gh` stdout, or None with a one-line reason on stderr."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=root)
    except FileNotFoundError:
        print("secrets_audit: `gh` not found on PATH", file=sys.stderr)
        return None

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        print(f"secrets_audit: `{' '.join(cmd)}` failed: {detail}", file=sys.stderr)
        return None
    return result.stdout


def _gh_json(cmd: list[str], root: Path) -> object | None:
    """Parsed `gh` JSON, or None with a one-line reason on stderr."""
    stdout = _gh_stdout(cmd, root)
    if stdout is None:
        return None
    try:
        return json.loads(stdout or "[]")
    except json.JSONDecodeError as exc:
        print(f"secrets_audit: could not parse `{' '.join(cmd)}` output: {exc}", file=sys.stderr)
        return None


def _gh_names(cmd: list[str], root: Path) -> set[str] | None:
    """Names from a `--jq` listing that prints one name per line, or None with a reason.

    Paginated object endpoints (`orgs/<org>/actions/secrets`, a repo's environments)
    concatenate one JSON object per page, which `json.loads` cannot read past page
    one — so those callers ask `gh` for the `name` fields directly instead.
    """
    stdout = _gh_stdout(cmd, root)
    if stdout is None:
        return None
    return {line.strip() for line in stdout.splitlines() if line.strip()}


def _names(payload: object) -> set[str] | None:
    """The `name` field of a `gh` list payload, or None when it is not that shape."""
    if not isinstance(payload, list):
        return None
    names: set[str] = set()
    for entry in payload:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            return None
        names.add(entry["name"])
    return names


def names_from_file(path: Path) -> set[str]:
    """Newline-separated names, `#` comments allowed."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def environments_from_file(path: Path) -> dict[str, set[str]]:
    """`environment:NAME` lines, one name each."""
    environments: dict[str, set[str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        environment, name = line.split(":", 1)
        environments.setdefault(environment.strip(), set()).add(name.strip())
    return environments


class ManifestError(Exception):
    """The manifest cannot be read, or is not the shape this script understands."""


class Acceptance(NamedTuple):
    """A named, owned, dated exemption for a read that resolves nowhere.

    An acceptance is a decision, not a fact: it says "this read is allowed to
    resolve to an empty string for now, somebody owns it, and it is looked at
    again on this date". It is scoped to the workflows that read the name, so
    the same name starting to be read somewhere else is no longer covered.
    """

    name: str
    workflows: tuple[str, ...]
    reason: str
    owner: str
    since: str
    review_by: str

    def covers(self, path: str) -> bool:
        """Whether this acceptance covers a read made by `path`."""
        return not self.workflows or path in self.workflows

    def as_payload(self) -> dict[str, object]:
        """The manifest body of this acceptance."""
        return {
            "workflows": list(self.workflows),
            "reason": self.reason,
            "owner": self.owner,
            "since": self.since,
            "review_by": self.review_by,
        }


class Manifest(NamedTuple):
    """The committed names-only manifest: the levels it names, and when it was written."""

    surface: Surface
    generated_at: str
    path: Path
    accepted: dict[str, Acceptance] = {}


def _level_names(entry: object, level: str) -> set[str] | None:
    """Names at one level, or None when the writer could not list that level.

    `read: false` means "not known", and it must not collapse into "none of them":
    a level that could not be asked about is not a level with nothing in it, and
    treating it as empty would turn a failed read into a clean bill of health.
    """
    if not isinstance(entry, dict):
        raise ManifestError(f"level {level!r} is missing or is not an object")
    read = entry.get("read")
    if read is False:
        return None
    if read is not True:
        raise ManifestError(f"level {level!r} has no `read` flag")
    names = entry.get("names")
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ManifestError(f"level {level!r} has no `names` list of strings")
    return set(names)


def _level_environments(entry: object) -> dict[str, set[str]] | None:
    """Environment name -> secret names, or None when the writer could not list them."""
    if not isinstance(entry, dict):
        raise ManifestError("level 'environments' is missing or is not an object")
    read = entry.get("read")
    if read is False:
        return None
    if read is not True:
        raise ManifestError("level 'environments' has no `read` flag")
    environments = entry.get("environments")
    if not isinstance(environments, dict):
        raise ManifestError("level 'environments' has no `environments` object")
    found: dict[str, set[str]] = {}
    for name, names in environments.items():
        if not isinstance(names, list) or not all(isinstance(item, str) for item in names):
            raise ManifestError(f"environment {name!r} has no `names` list of strings")
        found[str(name)] = set(names)
    return found


def _accepted_from_payload(payload: object) -> dict[str, Acceptance]:
    """The `accepted_missing` map, parsed into acceptances.

    A malformed entry is refused rather than dropped: an exemption that cannot
    be read must not quietly turn back into a failing check, and must not
    quietly turn into a passing one either.
    """
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ManifestError("`accepted_missing` is not an object")
    accepted: dict[str, Acceptance] = {}
    for name, entry in payload.items():
        if not isinstance(entry, dict):
            raise ManifestError(f"accepted_missing[{name!r}] is not an object")
        workflows = entry.get("workflows", [])
        if not isinstance(workflows, list) or not all(
            isinstance(item, str) for item in workflows
        ):
            raise ManifestError(
                f"accepted_missing[{name!r}] has no `workflows` list of strings"
            )
        fields: dict[str, str] = {}
        for field in ("reason", "owner", "since", "review_by"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ManifestError(f"accepted_missing[{name!r}] has no `{field}`")
            fields[field] = value
        accepted[str(name)] = Acceptance(
            name=str(name),
            workflows=tuple(workflows),
            reason=fields["reason"],
            owner=fields["owner"],
            since=fields["since"],
            review_by=fields["review_by"],
        )
    return accepted


def manifest_from_file(path: Path) -> Manifest:
    """Read the committed manifest.

    Every level comes from the file and `gh` is never called, which is the whole
    point: the live listings cannot be read from a workflow, and this is what runs
    in CI.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"could not read {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManifestError(f"{path} is not a JSON object")

    version = payload.get("schema_version")
    if version != MANIFEST_SCHEMA_VERSION:
        raise ManifestError(
            f"{path} has schema_version {version!r}, and this script reads "
            f"{MANIFEST_SCHEMA_VERSION}. Refusing to guess at a shape it does not know."
        )

    levels = payload.get("levels")
    if not isinstance(levels, dict):
        raise ManifestError(f"{path} has no `levels` object")

    repo_secrets = _level_names(levels.get("repo_secrets"), "repo_secrets")
    if repo_secrets is None:
        raise ManifestError(
            f"{path}: the repo secret level is marked unreadable, so no read can be "
            "resolved against it. Refresh the manifest."
        )

    return Manifest(
        surface=Surface(
            repo_secrets=repo_secrets,
            repo_variables=_level_names(levels.get("repo_variables"), "repo_variables"),
            org_secrets=_level_names(levels.get("org_secrets"), "org_secrets"),
            environment_secrets=_level_environments(levels.get("environments")),
        ),
        generated_at=str(payload.get("generated_at") or ""),
        path=path,
        accepted=_accepted_from_payload(payload.get("accepted_missing")),
    )


def manifest_payload(
    surface: Surface,
    *,
    generated_at: str,
    org: str,
    repo: str | None,
    accepted: dict[str, Acceptance] | None = None,
) -> dict[str, object]:
    """The manifest body: names only, one entry per level, each with a read flag."""

    def level(names: set[str] | None) -> dict[str, object]:
        if names is None:
            return {"read": False}
        return {"read": True, "names": sorted(names)}

    environments = surface.environment_secrets
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": generated_at,
        "generated_by": "scripts/secrets_audit.py --write-manifest",
        "org": org,
        "repo": repo,
        "note": (
            "Names only, never values. Refreshed from the live API by an operator whose "
            "token carries `repo` (and `admin:org` for the org level), because a workflow "
            "cannot read the Actions secret listings at all. `read: false` means the level "
            "could not be listed when this file was written, so the audit refuses to claim "
            "it checked every level."
        ),
        "accepted_missing": {
            name: entry.as_payload() for name, entry in sorted((accepted or {}).items())
        },
        "levels": {
            "repo_secrets": level(surface.repo_secrets),
            "repo_variables": level(surface.repo_variables),
            "org_secrets": level(surface.org_secrets),
            "environments": (
                {"read": False}
                if environments is None
                else {
                    "read": True,
                    "environments": {
                        name: sorted(names) for name, names in sorted(environments.items())
                    },
                }
            ),
        },
    }


def write_manifest(path: Path, payload: dict[str, object]) -> None:
    """Write the manifest as JSON: one level per key, names sorted, two-space indent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def manifest_age_days(manifest: Manifest, *, now: datetime | None = None) -> int | None:
    """Days since the manifest was written, or None when it carries no usable stamp."""
    stamp = manifest.generated_at.strip()
    if not stamp:
        return None
    try:
        written = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if written.tzinfo is None:
        written = written.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    return max(0, (reference - written).days)


def unread_levels(surface: Surface) -> list[str]:
    """The levels that could not be listed, named so the message can be acted on."""
    missing: list[str] = []
    if surface.repo_variables is None:
        missing.append("repo variables")
    if surface.org_secrets is None:
        missing.append("org secrets")
    if surface.environment_secrets is None:
        missing.append("environment secrets")
    return missing


def files_reading(by_file: dict[str, set[str]], names: set[str]) -> dict[str, list[str]]:
    """Which file reads each name, so a failure names the file to fix."""
    found: dict[str, list[str]] = {}
    for path, read in sorted(by_file.items()):
        for name in sorted(read & names):
            found.setdefault(name, []).append(path)
    return found


def split_accepted(
    unresolved: set[str],
    by_file: dict[str, set[str]],
    accepted: dict[str, Acceptance],
) -> tuple[set[str], dict[str, list[str]]]:
    """Split unresolved reads into the ones an acceptance covers and the ones it does not.

    A name is tolerated only when every workflow that reads it is covered by the
    acceptance, so a name that starts being read somewhere else stops being
    tolerated and the gate fails on it again.
    """
    tolerated: set[str] = set()
    readers: dict[str, list[str]] = {}
    for name in sorted(unresolved):
        entry = accepted.get(name)
        if entry is None:
            continue
        paths = sorted(path for path, read in by_file.items() if name in read)
        if not paths or any(not entry.covers(path) for path in paths):
            continue
        tolerated.add(name)
        readers[name] = paths
    return tolerated, readers


def accepted_from_manifest_file(path: Path) -> dict[str, Acceptance]:
    """The acceptances already written in a manifest, or none when there is none.

    A refresh replaces the facts, not the decisions: an acceptance is somebody's
    dated judgement, so rewriting the file must not silently drop it. A manifest
    that cannot be read yields no acceptances, and the caller says so loudly,
    because the gate then fails on names it used to tolerate.
    """
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    try:
        return _accepted_from_payload(payload.get("accepted_missing"))
    except ManifestError:
        return {}


def _utc_now() -> str:
    """Now, in UTC, as the manifest records it."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_secret_names(root: Path, secrets_file: Path | None) -> set[str] | None:
    """Repo-level secret names, or None when the list cannot be obtained."""
    if secrets_file is not None:
        return names_from_file(secrets_file)
    return _names(_gh_json(["gh", "secret", "list", "--json", "name"], root))


def repo_variable_names(root: Path) -> set[str] | None:
    """Repo-level variable names, or None when the list cannot be obtained."""
    return _names(_gh_json(["gh", "variable", "list", "--json", "name"], root))


def org_secret_names(org: str, root: Path) -> set[str] | None:
    """Org-level secret names, or None when the list cannot be obtained."""
    return _gh_names(
        ["gh", "api", "--paginate", "--jq", ".secrets[].name", f"orgs/{org}/actions/secrets"],
        root,
    )


def environment_secret_names(root: Path, repo: str) -> dict[str, set[str]] | None:
    """Environment name -> secret names, or None when the lists cannot be obtained."""
    environments = _gh_names(
        [
            "gh",
            "api",
            "--paginate",
            "--jq",
            ".environments[].name",
            f"repos/{repo}/environments",
        ],
        root,
    )
    if environments is None:
        return None

    found: dict[str, set[str]] = {}
    for name in sorted(environments):
        secrets = _gh_names(
            [
                "gh",
                "api",
                "--paginate",
                "--jq",
                ".secrets[].name",
                f"repos/{repo}/environments/{name}/secrets",
            ],
            root,
        )
        if secrets is None:
            return None
        found[name] = secrets
    return found


def repo_slug(root: Path) -> str | None:
    """`owner/name` for the repo at `root`, or None when it cannot be read."""
    payload = _gh_json(["gh", "repo", "view", "--json", "nameWithOwner"], root)
    if not isinstance(payload, dict):
        return None
    slug = payload.get("nameWithOwner")
    return slug if isinstance(slug, str) else None


def _fmt(names: set[str]) -> str:
    return ", ".join(sorted(names)) if names else "none"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repo root to scan")
    parser.add_argument(
        "--secrets-file",
        type=Path,
        default=None,
        help="newline-separated repo secret names; also switches the whole run offline",
    )
    parser.add_argument(
        "--variables-file",
        type=Path,
        default=None,
        help="newline-separated repo variable names (requires --secrets-file)",
    )
    parser.add_argument(
        "--org-secrets-file",
        type=Path,
        default=None,
        help="newline-separated org secret names (requires --secrets-file)",
    )
    parser.add_argument(
        "--env-secrets-file",
        type=Path,
        default=None,
        help="`environment:NAME` lines (requires --secrets-file)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="read every level from this committed manifest instead of asking `gh`",
    )
    parser.add_argument(
        "--write-manifest",
        type=Path,
        default=None,
        help=(
            "refresh this manifest from the live API; needs `repo`, and `admin:org` for "
            "the org level"
        ),
    )
    parser.add_argument("--org", default="digithings-ai", help="org to ask for org-level secrets")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when a repo secret is never read (dead)",
    )
    parser.add_argument(
        "--strict-unresolved",
        action="store_true",
        help="exit 1 when a read has no definition at any level (needs every level listed)",
    )
    parser.add_argument("--verbose", action="store_true", help="also list reads per file")
    args = parser.parse_args(argv)

    if args.manifest is not None and args.write_manifest is not None:
        print(
            "secrets_audit: --manifest reads a manifest and --write-manifest writes one. "
            "Pick one.",
            file=sys.stderr,
        )
        return 2
    if args.write_manifest is not None and args.secrets_file is not None:
        print(
            "secrets_audit: --write-manifest refreshes from the live API, so it cannot "
            "take the offline name files. Pick one.",
            file=sys.stderr,
        )
        return 2

    by_file = extract_secret_reads(args.root)
    if not by_file:
        print(f"secrets_audit: no .github YAML found under {args.root}", file=sys.stderr)
        return 1

    manifest: Manifest | None = None
    slug: str | None = None
    accepted: dict[str, Acceptance] = {}
    if args.manifest is not None:
        try:
            manifest = manifest_from_file(args.manifest)
        except ManifestError as exc:
            print(f"secrets_audit: {exc}", file=sys.stderr)
            return 1
        surface = manifest.surface
        accepted = manifest.accepted
        source = f"manifest {args.manifest}"
    elif args.secrets_file is not None:
        surface = Surface(
            repo_secrets=names_from_file(args.secrets_file),
            repo_variables=names_from_file(args.variables_file) if args.variables_file else None,
            org_secrets=names_from_file(args.org_secrets_file) if args.org_secrets_file else None,
            environment_secrets=(
                environments_from_file(args.env_secrets_file) if args.env_secrets_file else None
            ),
        )
        source = "the name files given on the command line"
    else:
        repo_secrets = repo_secret_names(args.root, None)
        if repo_secrets is None:
            reads = (set().union(*by_file.values()) if by_file else set()) - IMPLICIT_SECRETS
            print(f"secrets_audit: repo secret list unavailable, {len(reads)} referenced names")
            print(f"referenced: {_fmt(reads)}")
            if args.strict or args.strict_unresolved:
                print(
                    "secrets_audit: --strict and --strict-unresolved need the list of repo "
                    "secrets; `gh` could not provide it",
                    file=sys.stderr,
                )
                return 1
            return 0
        slug = repo_slug(args.root)
        surface = Surface(
            repo_secrets=repo_secrets,
            repo_variables=repo_variable_names(args.root),
            org_secrets=org_secret_names(args.org, args.root),
            environment_secrets=environment_secret_names(args.root, slug) if slug else None,
        )
        source = "the live GitHub API"

    if args.write_manifest is not None:
        existed = args.write_manifest.is_file()
        kept = accepted_from_manifest_file(args.write_manifest)
        write_manifest(
            args.write_manifest,
            manifest_payload(
                surface,
                generated_at=_utc_now(),
                org=args.org,
                repo=slug or repo_slug(args.root),
                accepted=kept,
            ),
        )
        print(f"secrets_audit: wrote {args.write_manifest} from {source}")
        if kept:
            print(
                f"secrets_audit: kept {len(kept)} accepted-missing entr(y/ies) from the "
                "previous manifest: " + _fmt(set(kept))
            )
        elif existed:
            print(
                "secrets_audit: warning: no accepted-missing entry could be read from the "
                "previous manifest, so the refreshed file carries none. If one was there, "
                "put it back by hand: a refresh replaces the facts, not the decisions.",
                file=sys.stderr,
            )
        missing = unread_levels(surface)
        if missing:
            print(
                f"secrets_audit: warning: could not list {', '.join(missing)}. The manifest "
                "records those levels as unreadable, so the audit refuses to claim it "
                "checked every level until it is refreshed.",
                file=sys.stderr,
            )

    report = classify(by_file, surface.repo_secrets)
    print(
        f"secrets_audit: {len(surface.repo_secrets)} repo secrets, "
        f"{len(report.reads)} referenced names, {len(by_file)} .github YAML files"
    )
    print(f"source: {source}")

    levels = classify_levels(report.reads, surface) if surface.complete else None
    if levels is None:
        missing = unread_levels(surface)
        detail = ", ".join(missing) if missing else "offline run"
        print(f"levels: not checked ({detail})")
    else:
        environment_count = len(surface.environment_secrets or {})
        print(
            f"levels: {len(surface.repo_variables or ())} repo variables, "
            f"{len(surface.org_secrets or ())} org secrets, {environment_count} environments"
        )
    print(f"dead: {_fmt(report.dead)}")
    tolerated: set[str] = set()
    accepted_readers: dict[str, list[str]] = {}
    blocking: set[str] = set()
    if levels is None:
        print(f"not repo-level: {_fmt(report.unmanaged)}")
    else:
        print(f"not repo-level: {_fmt(levels.explained)}")
        print(f"unresolved: {_fmt(levels.unresolved)}")
        print(f"repo-over-org: {_fmt(levels.shadowed)}")
        print(f"env-over-repo: {_fmt(levels.env_over_repo)}")
        for name, paths in files_reading(by_file, levels.unresolved).items():
            print(f"unresolved in: {name} -> {', '.join(paths)}")
        blocking = set(levels.unresolved)
        if accepted:
            tolerated, accepted_readers = split_accepted(levels.unresolved, by_file, accepted)
            blocking -= tolerated
            for name in sorted(tolerated):
                entry = accepted[name]
                print(
                    f"accepted-missing: {name} (owner {entry.owner}, since {entry.since}, "
                    f"review by {entry.review_by})"
                )
                print(
                    f"accepted-missing in: {name} -> "
                    f"{', '.join(accepted_readers.get(name, []))}"
                )

    if args.verbose:
        for rel, names in sorted(by_file.items()):
            print(f"  {rel}: {_fmt(names)}")

    drift = report.dead or report.unmanaged or (levels is not None and levels.unresolved)
    if drift:
        print(
            "hint: dead = delete the repo secret (or read it); "
            "unresolved = no level defines it, so Actions substitutes an empty string"
        )

    if manifest is not None:
        age = manifest_age_days(manifest)
        if age is None:
            print(f"manifest: {manifest.path} carries no usable timestamp")
        else:
            print(
                f"manifest: {manifest.path} written {age} day(s) ago "
                f"({manifest.generated_at})"
            )
            if age > MANIFEST_STALE_DAYS:
                print(
                    f"warning: the manifest is {age} days old, over the {MANIFEST_STALE_DAYS}-day "
                    "window. A secret deleted since it was written still reads as defined. "
                    "Refresh it with: make secrets-audit-refresh",
                    file=sys.stderr,
                )

    if args.strict and report.dead:
        print(
            f"secrets_audit: {len(report.dead)} dead repo secret(s): {_fmt(report.dead)}",
            file=sys.stderr,
        )
        return 1
    if args.strict_unresolved:
        if levels is None:
            unread = ", ".join(unread_levels(surface)) or "every level"
            print(
                "secrets_audit: --strict-unresolved needs every level listed; these could not "
                f"be: {unread}",
                file=sys.stderr,
            )
            return 1
        if blocking:
            print(
                f"secrets_audit: {len(blocking)} unresolved read(s): {_fmt(blocking)}",
                file=sys.stderr,
            )
            for name, paths in files_reading(by_file, blocking).items():
                print(f"secrets_audit: {name} is read by {', '.join(paths)}", file=sys.stderr)
            if tolerated:
                print(
                    f"secrets_audit: {len(tolerated)} other unresolved read(s) are tolerated "
                    f"by a dated entry in the manifest: {_fmt(tolerated)}",
                    file=sys.stderr,
                )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

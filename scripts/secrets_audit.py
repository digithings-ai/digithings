#!/usr/bin/env python3
"""Audit the secret surface: the names workflows read vs where they are defined.

A name is defined at some level in GitHub (repo secret, repo variable, org secret,
environment secret) and read in `.github/**/*.yml`; `docs/ops/SECRETS_INVENTORY.md`
is the hand-kept map of that same surface. The levels drift apart silently, so this
compares them in seconds:

    python scripts/secrets_audit.py            # asks `gh` for every level
    python scripts/secrets_audit.py --strict   # exit 1 when a repo secret is never read
    python scripts/secrets_audit.py --secrets-file names.txt --variables-file vars.txt

Four findings, in increasing order of how long they hide:

- `dead` — a repo secret nothing reads
- `not repo-level` — a read defined at another level (repo variable, org or
  environment secret), which is normal
- `unresolved` — a read no level defines; Actions substitutes an empty string, so
  a typo is invisible until a pipeline fails somewhere downstream
- `repo-over-org` — defined at both repo and org level, where the repo copy silently
  wins: two places to rotate and only one of them load-bearing

Deliberately not a CI gate: a read with no repo-level secret is normal here, so only
`--strict` (dead) and `--strict-unresolved` fail, and neither runs in CI. Passing
`--secrets-file` is the offline switch: every level comes from a file, `gh` is never
called, and `--strict-unresolved` refuses to pretend it checked.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent

EXPRESSION_RE = re.compile(r"\$\{\{(.*?)\}\}")

SECRET_READ_RE = re.compile(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)")

GITHUB_YAML_GLOBS: tuple[str, ...] = (".github/**/*.yml", ".github/**/*.yaml")

# Provided by Actions itself, not a secret anyone has to manage.
IMPLICIT_SECRETS: frozenset[str] = frozenset({"GITHUB_TOKEN"})


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


def classify_levels(reads: set[str], surface: Surface) -> Levels:
    """Split reads into defined-at-another-level, defined-nowhere, repo-shadows-org."""
    levels = {name: surface.levels_of(name) for name in reads}
    return Levels(
        explained={name for name, where in levels.items() if where and "repo secret" not in where},
        unresolved={name for name, where in levels.items() if not where},
        shadowed={
            name
            for name, where in levels.items()
            if "repo secret" in where and "org secret" in where
        },
    )


def _gh_json(cmd: list[str], root: Path) -> object | None:
    """Parsed `gh` JSON, or None with a one-line reason on stderr."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=root)
    except FileNotFoundError:
        print("secrets_audit: `gh` not found on PATH", file=sys.stderr)
        return None

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        print(f"secrets_audit: `{' '.join(cmd)}` failed: {detail}", file=sys.stderr)
        return None

    try:
        return json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        print(f"secrets_audit: could not parse `{' '.join(cmd)}` output: {exc}", file=sys.stderr)
        return None


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
    payload = _gh_json(["gh", "api", "--paginate", f"orgs/{org}/actions/secrets"], root)
    if not isinstance(payload, dict):
        return None
    return _names(payload.get("secrets"))


def environment_secret_names(root: Path, repo: str) -> dict[str, set[str]] | None:
    """Environment name -> secret names, or None when the lists cannot be obtained."""
    payload = _gh_json(["gh", "api", "--paginate", f"repos/{repo}/environments"], root)
    if not isinstance(payload, dict):
        return None

    environments: dict[str, set[str]] = {}
    for entry in payload.get("environments") or []:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not isinstance(name, str):
            return None
        secrets = _gh_json(
            ["gh", "api", "--paginate", f"repos/{repo}/environments/{name}/secrets"], root
        )
        if not isinstance(secrets, dict):
            return None
        found = _names(secrets.get("secrets"))
        if found is None:
            return None
        environments[name] = found
    return environments


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

    by_file = extract_secret_reads(args.root)
    if not by_file:
        print(f"secrets_audit: no .github YAML found under {args.root}", file=sys.stderr)
        return 1

    repo_secrets = repo_secret_names(args.root, args.secrets_file)
    if repo_secrets is None:
        reads = set().union(*by_file.values()) if by_file else set()
        print(f"secrets_audit: repo secret list unavailable, {len(reads)} referenced names")
        print(f"referenced: {_fmt(reads)}")
        return 1 if args.strict else 0

    if args.secrets_file is not None:
        surface = Surface(
            repo_secrets=repo_secrets,
            repo_variables=names_from_file(args.variables_file) if args.variables_file else None,
            org_secrets=names_from_file(args.org_secrets_file) if args.org_secrets_file else None,
            environment_secrets=(
                environments_from_file(args.env_secrets_file) if args.env_secrets_file else None
            ),
        )
    else:
        slug = repo_slug(args.root)
        surface = Surface(
            repo_secrets=repo_secrets,
            repo_variables=repo_variable_names(args.root),
            org_secrets=org_secret_names(args.org, args.root),
            environment_secrets=environment_secret_names(args.root, slug) if slug else None,
        )

    report = classify(by_file, repo_secrets)
    print(
        f"secrets_audit: {len(repo_secrets)} repo secrets, "
        f"{len(report.reads)} referenced names, {len(by_file)} .github YAML files"
    )

    levels = classify_levels(report.reads, surface) if surface.complete else None
    if levels is None:
        print("levels: not checked (offline run, or `gh` could not list every level)")
    else:
        environment_count = len(surface.environment_secrets or {})
        print(
            f"levels: {len(surface.repo_variables or ())} repo variables, "
            f"{len(surface.org_secrets or ())} org secrets, {environment_count} environments"
        )
    print(f"dead: {_fmt(report.dead)}")
    if levels is None:
        print(f"not repo-level: {_fmt(report.unmanaged)}")
    else:
        print(f"not repo-level: {_fmt(levels.explained)}")
        print(f"unresolved: {_fmt(levels.unresolved)}")
        print(f"repo-over-org: {_fmt(levels.shadowed)}")

    if args.verbose:
        for rel, names in sorted(by_file.items()):
            print(f"  {rel}: {_fmt(names)}")

    drift = report.dead or report.unmanaged or (levels is not None and levels.unresolved)
    if drift:
        print(
            "hint: dead = delete the repo secret (or read it); "
            "unresolved = no level defines it, so Actions substitutes an empty string"
        )

    if args.strict and report.dead:
        print(
            f"secrets_audit: {len(report.dead)} dead repo secret(s): {_fmt(report.dead)}",
            file=sys.stderr,
        )
        return 1
    if args.strict_unresolved:
        if levels is None:
            print(
                "secrets_audit: --strict-unresolved needs every level listed; "
                "`gh` could not list them",
                file=sys.stderr,
            )
            return 1
        if levels.unresolved:
            print(
                f"secrets_audit: {len(levels.unresolved)} unresolved read(s): "
                f"{_fmt(levels.unresolved)}",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

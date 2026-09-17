#!/usr/bin/env python3
"""Audit the repo secret surface: GitHub secrets vs the names workflows read.

A secret name lives in three places — GitHub (repo, org, or environment level),
the `.github/**/*.yml` files that read it, and `docs/ops/SECRETS_INVENTORY.md` —
and they drift apart silently. This reports that drift in seconds:

    python scripts/secrets_audit.py            # asks `gh secret list` for repo secrets
    python scripts/secrets_audit.py --strict   # exit 1 when a repo secret is never read
    python scripts/secrets_audit.py --secrets-file names.txt --root .

Deliberately not a CI gate: a workflow reading a name with no repo-level secret is
normal here (the name may live at the org or environment level), so only a
provably dead repo secret is a failure, and only under `--strict`.
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

SECRET_READ_RE = re.compile(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)")

GITHUB_YAML_GLOBS: tuple[str, ...] = (".github/**/*.yml", ".github/**/*.yaml")

# Provided by Actions itself, not a secret anyone has to manage.
IMPLICIT_SECRETS: frozenset[str] = frozenset({"GITHUB_TOKEN"})


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
            by_file[path.relative_to(root).as_posix()] = set(SECRET_READ_RE.findall(text))
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


def repo_secret_names(root: Path, secrets_file: Path | None) -> set[str] | None:
    """Repo-level secret names, or None when the list cannot be obtained."""
    if secrets_file is not None:
        lines = secrets_file.read_text(encoding="utf-8").splitlines()
        return {line.strip() for line in lines if line.strip() and not line.startswith("#")}

    try:
        result = subprocess.run(
            ["gh", "secret", "list", "--json", "name"],
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
        )
    except FileNotFoundError:
        print("secrets_audit: `gh` not found on PATH", file=sys.stderr)
        return None

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        print(
            f"secrets_audit: `gh secret list` failed ({result.returncode}): {detail}",
            file=sys.stderr,
        )
        return None

    try:
        return {entry["name"] for entry in json.loads(result.stdout or "[]")}
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"secrets_audit: could not parse `gh secret list` output: {exc}", file=sys.stderr)
        return None


def _fmt(names: set[str]) -> str:
    return ", ".join(sorted(names)) if names else "none"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repo root to scan")
    parser.add_argument(
        "--secrets-file",
        type=Path,
        default=None,
        help="newline-separated secret names instead of querying `gh secret list`",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when a repo secret is never read (dead)",
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
        return 0

    report = classify(by_file, repo_secrets)
    print(
        f"secrets_audit: {len(repo_secrets)} repo secrets, "
        f"{len(report.reads)} referenced names, {len(by_file)} .github YAML files"
    )
    print(f"dead: {_fmt(report.dead)}")
    print(f"not repo-level: {_fmt(report.unmanaged)}")

    if args.verbose:
        for rel, names in sorted(by_file.items()):
            print(f"  {rel}: {_fmt(names)}")

    if report.dead or report.unmanaged:
        print(
            "hint: dead = delete the repo secret (or read it); "
            "not repo-level = repo variable, org/environment secret, or a typo in the workflow"
        )

    if report.dead and args.strict:
        print(
            f"secrets_audit: {len(report.dead)} dead repo secret(s): {_fmt(report.dead)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

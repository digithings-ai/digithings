#!/usr/bin/env python3
"""Fail if any tracked file in this client repo is a byte-for-byte copy of a file in the pinned R0 tree.

Build-on rule: client repos consume digithings (R0) as pinned releases and never copy its code in.
Compares git blob ids, so it needs only `git` in both checkouts. Exact copies only: a copy with one
changed line passes, which review still has to catch.

Allowlist: `.r0-vendor-allow`, one repo-relative path per line, each with a reason after ' # '.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

MIN_BYTES = 64  # tiny files (empty, .gitkeep, one-line configs) collide by accident
IGNORED_NAMES = {".gitkeep", ".gitignore", "LICENSE", "VERSION"}
# R0 keeps the template itself as docs; client files that still match it are expected, not vendored.
R0_EXCLUDED_PREFIXES = ("docs/repo-split/client-template/",)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def r0_blobs(r0: Path) -> dict[str, str]:
    """Blob id -> one R0 path holding it."""
    out: dict[str, str] = {}
    for line in git(r0, "ls-tree", "-r", "--full-tree", "HEAD").splitlines():
        meta, path = line.split("\t", 1)
        mode, kind, blob = meta.split()
        if kind == "blob" and mode != "120000" and not path.startswith(R0_EXCLUDED_PREFIXES):
            out.setdefault(blob, path)
    return out


def client_files(client: Path) -> list[str]:
    return [p for p in git(client, "ls-files", "-z").split("\0") if p]


def allowlist(client: Path) -> set[str]:
    f = client / ".r0-vendor-allow"
    if not f.exists():
        return set()
    allowed = set()
    for raw in f.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        path, sep, reason = line.partition(" # ")
        if not sep or not reason.strip():
            sys.exit(f"{f.name}: '{line}' needs a reason after ' # '")
        allowed.add(path.strip())
    return allowed


def find_copies(client: Path, r0: Path) -> list[tuple[str, str]]:
    blobs = r0_blobs(r0)
    allowed = allowlist(client)
    hits = []
    for rel in client_files(client):
        p = client / rel
        if rel in allowed or p.name in IGNORED_NAMES or p.is_symlink() or not p.is_file():
            continue
        if p.stat().st_size < MIN_BYTES:
            continue
        blob = git(client, "hash-object", "--", rel).strip()
        if blob in blobs:
            hits.append((rel, blobs[blob]))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--client", type=Path, default=Path("."))
    ap.add_argument("--r0", type=Path, required=True)
    a = ap.parse_args()
    if not (a.r0 / ".git").exists():
        print(f"no R0 checkout at {a.r0}; the fetch-r0 step must run first", file=sys.stderr)
        return 2
    hits = find_copies(a.client.resolve(), a.r0.resolve())
    for rel, r0path in hits:
        print(f"vendored from R0: {rel} == {r0path}", file=sys.stderr)
    if hits:
        print(
            f"{len(hits)} file(s) copied from R0. Use the pinned package/image instead, or add the path "
            "to .r0-vendor-allow with a reason.",
            file=sys.stderr,
        )
        return 1
    print(f"no-vendored-r0 OK ({len(client_files(a.client))} files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

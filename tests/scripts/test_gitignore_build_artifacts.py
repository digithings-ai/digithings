"""Pin that Next build output and opencode session state are uncommittable.

`.next/` and `.opencode/` carried no root `.gitignore` entry, so coverage rested
entirely on each app shipping its own `.gitignore`. That failed in practice:
`0f193360` on feat/dig-183 committed `apps/digiquant-app/.next/dev/`, and DIG-183
then had to append the commit to `allowlist.commits` in `.gitleaks.toml` to keep
the scanner quiet about the Next-generated signing material in it. An allowlist
entry is the wrong instrument for build output.

These assertions run the real `git check-ignore`, so the pin fails if a root rule
is deleted, narrowed to an anchored path, or shadowed by a nearer one — not only
if the text is edited.

DIG-326.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]

# Probe paths with a comment on why each must be ignored. None are real files;
# `git check-ignore` resolves rules for paths that do not exist.
IGNORED = (
    # Next build output at the repo root.
    ".next/BUILD_ID",
    # Workspaces with no `.gitignore` of their own — the DIG-183 shape.
    "apps/digiquant-app/.next/dev/build-manifest.json",
    "packages/design/.next/static/chunks/main.js",
    # digichat's distDir is DIGICHAT_DIST_DIR, so it is not always `.next`.
    "apps/digichat/.next-cloudflare/BUILD_ID",
    # opencode session state, at the root and nested.
    ".opencode/session.db",
    "apps/digichat/.opencode/storage/message.json",
)

# Tracked source that must stay committable. Guards against a rule so broad it
# swallows real work.
TRACKED = (
    "AGENTS.md",
    "apps/digiquant-web/package.json",
    "apps/digichat/next.config.ts",
    "opencode.json",
    "packages/ui/src/index.ts",
)


def _check_ignore(paths: tuple[str, ...]) -> dict[str, str]:
    """Map each path to the rule that ignores it; absent paths are omitted."""
    out = subprocess.run(
        ["git", "check-ignore", "-v", "--no-index", *paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    hits: dict[str, str] = {}
    for line in out.stdout.splitlines():
        # <source>:<lineno>:<pattern>\t<pathname>
        source, pathname = line.split("\t", 1)
        # git prints the rule's own path relative to the repo root, so anchor it
        # for comparison against REPO_ROOT.
        hits[pathname] = str((REPO_ROOT / source.rsplit(":", 2)[0]).resolve())
    return hits


def test_build_and_session_artifacts_are_gitignored() -> None:
    hits = _check_ignore(IGNORED)
    missed = [p for p in IGNORED if p not in hits]
    assert not missed, f"not ignored by any rule: {missed}\nresolved: {hits}"


def test_no_tracked_source_is_shadowed() -> None:
    hits = _check_ignore(TRACKED)
    assert not hits, f"root rules now ignore tracked source: {hits}"


def test_the_rules_that_cover_a_naked_app_live_in_the_root_gitignore() -> None:
    """The root rule is the whole fix: no app-level edit can replace it.

    `apps/digiquant-app` exists only on feat/dig-183, so there is no app-level
    `.gitignore` to add it to on develop. A root rule also covers the next app
    that ships without one, which is the actual failure mode. These two probes
    have no nearer `.gitignore`, so they can only resolve through the root file.
    """
    hits = _check_ignore(
        (
            "apps/digiquant-app/.next/dev/build-manifest.json",
            "apps/digichat/.opencode/storage/message.json",
        )
    )
    root = str(REPO_ROOT / ".gitignore")
    assert hits == {
        "apps/digiquant-app/.next/dev/build-manifest.json": root,
        "apps/digichat/.opencode/storage/message.json": root,
    }

"""Unit tests for scripts/check_doc_links.py's gitignore awareness (#5001).

``make doc-check`` walks the repo with ``Path.rglob("*.md")`` and skipped only a
hardcoded prefix list. Anything git ignores but that list did not name was walked
anyway, so a build artifact produced its own failures: ``npm run build`` in
apps/digichat writes ``.next/standalone/``, which contains a copy of every
component's ``AGENTS.md``, and the relative links inside that copy do not resolve
from the copied location. Running ``make doc-check`` after ``npm run build``
therefore reported three broken links that exist nowhere in the tracked tree.

The fix asks git which paths are ignored rather than trying to re-implement
``.gitignore`` semantics (``!`` negations, anchored paths, per-directory
``.gitignore`` files). These tests pin that behaviour, including the fallback for
a tree that is not a git checkout at all.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_doc_links.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_doc_links", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_doc_links"] = module
    spec.loader.exec_module(module)
    return module


def test_gitignore_paths_returns_only_what_git_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    asked: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        asked.append(cmd[cmd.index("--stdin") + 1 :])
        return subprocess.CompletedProcess(
            cmd, 0, stdout="apps/digichat/.next/standalone/AGENTS.md\n", stderr=""
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = mod._gitignore_paths({"AGENTS.md", "apps/digichat/AGENTS.md", "apps/digichat/.next/x.md"})
    assert out == frozenset({"apps/digichat/.next/standalone/AGENTS.md"})


def test_gitignore_paths_returns_empty_when_nothing_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load()
    # git check-ignore exits 1 when no input path is ignored.
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr=""),
    )
    assert mod._gitignore_paths({"AGENTS.md"}) == frozenset()


def test_gitignore_paths_degrades_gracefully_outside_a_git_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tarball export has no .git. Reporting every link as broken would be a
    regression, so a git failure means "nothing is ignored" — the pre-#5001
    behaviour — rather than an exception out of main()."""

    def boom(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    mod = _load()
    monkeypatch.setattr(mod.subprocess, "run", boom)
    assert mod._gitignore_paths({"AGENTS.md"}) == frozenset()


def test_collect_skips_paths_git_ignores(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    monkeypatch.setattr(
        mod,
        "_gitignore_paths",
        lambda paths: frozenset({"apps/digichat/.next/standalone/AGENTS.md"}),
    )
    collected = {p.relative_to(mod.REPO_ROOT).as_posix() for p in mod._collect_markdown_files()}
    assert "apps/digichat/.next/standalone/AGENTS.md" not in collected


def test_collect_still_includes_tracked_component_docs() -> None:
    """The guard above must not become a way to skip real documentation: with
    no gitignore entries at all, the tracked AGENTS.md files are still scanned."""

    mod = _load()
    collected = {p.relative_to(mod.REPO_ROOT).as_posix() for p in mod._collect_markdown_files()}
    assert "apps/digichat/AGENTS.md" in collected
    assert "digigraph/AGENTS.md" in collected


def test_the_real_repo_scan_is_gitignore_clean() -> None:
    """Whatever git reports, the scan must agree — the two lists are computed
    independently and this is what catches a regression in either."""

    mod = _load()
    collected = {p.relative_to(mod.REPO_ROOT).as_posix() for p in mod._collect_markdown_files()}
    assert not (collected & mod._gitignore_paths(collected))

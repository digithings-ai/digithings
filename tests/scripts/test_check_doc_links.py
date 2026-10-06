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
    seen: list[bytes] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen.append(kwargs["input"])
        # `-z` makes git NUL-delimit its output, so the stub has to too — the
        # newline form is what an older version of this test asserted and it no
        # longer matches anything the production code can see.
        return subprocess.CompletedProcess(
            cmd, 0, stdout=b"apps/digichat/.next/standalone/AGENTS.md\x00", stderr=b""
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = mod._gitignore_paths({"AGENTS.md", "apps/digichat/AGENTS.md", "apps/digichat/.next/x.md"})
    assert out == frozenset({"apps/digichat/.next/standalone/AGENTS.md"})
    # On stdin, NUL-delimited too — 459 paths would blow the argv limit, and
    # a newline inside a filename would otherwise split into two paths.
    assert seen and set(seen[0].split(b"\x00")) == {
        b"AGENTS.md",
        b"apps/digichat/AGENTS.md",
        b"apps/digichat/.next/x.md",
    }


def test_gitignore_paths_returns_empty_when_nothing_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load()
    # git check-ignore exits 1 when no input path is ignored.
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b""),
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


def _git_repo(path: Path) -> None:
    """A real checkout, so `_gitignore_paths` reaches a real `git check-ignore`.

    Every other test here stubs the subprocess, so this is the only place the
    production code path is exercised end to end — which is exactly why the
    filter must not be stubbed in the test that claims to test it.
    """
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)


def test_collect_skips_paths_git_ignores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An ignored `AGENTS.md` is dropped, an untracked one is kept, and a `!`
    negation is honoured.

    Built on a throwaway repository rather than the digithings tree because the
    bug only exists where an ignored file actually sits on disk, and this repo
    has no such file in a clean checkout. The real subprocess runs here, so
    deleting the filter from the production code fails this test instead of
    passing it — which a monkeypatched `_gitignore_paths` could never do.
    """
    mod = _load()
    _git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text(
        "build/\ndocs/generated/*\n!docs/generated/kept.md\n", encoding="utf-8"
    )
    for rel in ("build/AGENTS.md", "docs/generated/drop.md", "docs/generated/kept.md", "docs/a.md"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# doc\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    collected = {p.relative_to(tmp_path).as_posix() for p in mod._collect_markdown_files()}

    # Ignored, and each one matches a collect rule, so only the gitignore
    # filter can keep them out.
    assert "build/AGENTS.md" not in collected
    assert "docs/generated/drop.md" not in collected
    # Never ignored, so they must survive.
    assert "docs/a.md" in collected
    # `!docs/generated/kept.md` re-includes a file git would otherwise have
    # ignored; re-implementing .gitignore by hand is what this change refused.
    assert "docs/generated/kept.md" in collected


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

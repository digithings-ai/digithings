"""Unit tests for scripts/verify_doc_only_pr.py (doc-only auto-merge path gate).

``agent-docs-automerge.yml`` enables squash auto-merge for PRs labeled
``automerge-docs`` only after this script exits 0. A typo that drops
``.github/workflows/`` from the deny list, or that treats ``SECURITY.md`` as
allowable docs, would silently auto-merge workflow or security-policy edits.
Conversely, rejecting root ``AGENTS.md`` / ``docs/**`` would block legitimate
doc automerges. These tests pin the allow/deny contract without hitting git.
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
SCRIPT = REPO_ROOT / "scripts" / "verify_doc_only_pr.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("verify_doc_only_pr", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_doc_only_pr"] = module
    spec.loader.exec_module(module)
    return module


vdo = _load()


@pytest.mark.parametrize(
    "path",
    [
        "docs/agents/AGENT_WORKFLOW.md",
        "docs/scoring/QUALITY.md",
        "website/index.md",
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "ARCHITECTURE.md",
        "digigraph/AGENTS.md",
        "digiquant/ARCHITECTURE.md",
        "frontend/digichat/CLAUDE.md",
    ],
)
def test_is_allowed_permits_doc_only_paths(path: str) -> None:
    assert vdo._is_allowed(path) is True


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        ".github/workflows/agent-docs-automerge.yml",
        "SECURITY.md",
        "docs/scoring/SECURITY.md",
        "frontend/digichat/SECURITY.md",
        "digigraph/src/digigraph/server.py",
        "scripts/verify_doc_only_pr.py",
        "website/app.js",
        "CONTRIBUTING.txt",  # not in root allowlist basename set
        r".github\workflows\ci.yml",  # Windows separators still deny
    ],
)
def test_is_allowed_denies_non_doc_or_protected_paths(path: str) -> None:
    assert vdo._is_allowed(path) is False


def test_deny_list_pins_workflow_and_security_substrings() -> None:
    assert ".github/workflows/" in vdo.DENY_PATH_SUBSTRINGS
    assert "SECURITY.md" in vdo.DENY_PATH_SUBSTRINGS
    assert "README.md" in vdo.ALLOW_ROOT_NAMES
    assert "AGENTS.md" in vdo.ALLOW_ROOT_NAMES


def test_main_ok_when_all_changed_paths_are_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vdo,
        "_changed_files",
        lambda _base: ["docs/a.md", "README.md", "digikey/ARCHITECTURE.md"],
    )
    monkeypatch.setattr(sys, "argv", ["verify_doc_only_pr.py", "origin/develop"])
    assert vdo.main() == 0


def test_main_rejects_when_any_path_is_disallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vdo,
        "_changed_files",
        lambda _base: ["docs/a.md", ".github/workflows/ci.yml"],
    )
    monkeypatch.setattr(sys, "argv", ["verify_doc_only_pr.py", "origin/develop"])
    assert vdo.main() == 1


def test_main_rejects_security_md_even_under_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    """SECURITY.md must never ride the doc automerge label."""
    monkeypatch.setattr(vdo, "_changed_files", lambda _base: ["docs/scoring/SECURITY.md"])
    monkeypatch.setattr(sys, "argv", ["verify_doc_only_pr.py"])
    assert vdo.main() == 1


def test_main_ok_with_empty_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vdo, "_changed_files", lambda _base: [])
    monkeypatch.setattr(sys, "argv", ["verify_doc_only_pr.py", "origin/develop"])
    assert vdo.main() == 0


def test_main_fails_closed_on_git_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_base: str) -> list[str]:
        raise subprocess.CalledProcessError(1, ["git", "merge-base"])

    monkeypatch.setattr(vdo, "_changed_files", _boom)
    monkeypatch.setattr(sys, "argv", ["verify_doc_only_pr.py", "origin/develop"])
    assert vdo.main() == 1

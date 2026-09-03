"""Unit tests for scripts/verify_agent_automerge_pr.py path + branch gates.

#2341 extended ALLOWED_BRANCH_PREFIXES with ``task/`` and ``claude/`` (the two
largest agent-PR sources) and kept the deny-substring list that blocks
automerge of workflows, digikey, live-trading, and scoring rubrics. Neither
list had a unit test — a typo in a deny substring or dropping ``task/`` from
the allowlist would silently widen or shrink automerge eligibility.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify_agent_automerge_pr.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("verify_agent_automerge_pr", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_agent_automerge_pr"] = module
    spec.loader.exec_module(module)
    return module


vap = _load()


@pytest.mark.parametrize(
    "path",
    [
        "digigraph/src/digigraph/server.py",
        "tests/dg/test_api.py",
        "frontend/digichat/src/app/page.tsx",
        "digiquant/src/digiquant/research/graph.py",
        "docs/agents/AGENT_WORKFLOW.md",
    ],
)
def test_is_allowed_permits_ordinary_agent_paths(path: str) -> None:
    assert vap._is_allowed(path) is True


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        ".github/workflows/agent-pr-automerge.yml",
        "docs/scoring/SECURITY.md",
        "digikey/src/digikey/server.py",
        "digikey/ARCHITECTURE.md",
        "digiquant/live/broker.py",
        "config/live.yaml",
        "config/live/trading.env",
        "frontend/digichat/SECURITY.md",
        r"digikey\src\digikey\keys.py",  # Windows separators still deny
    ],
)
def test_is_allowed_denies_protected_paths(path: str) -> None:
    assert vap._is_allowed(path) is False


@pytest.mark.parametrize(
    "branch",
    ["cursor/foo", "copilot/bar", "bot/baz", "task/123-slug", "claude/session"],
)
def test_main_accepts_agent_branch_prefixes(branch: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vap, "_changed_files", lambda _base: ["README.md"])
    monkeypatch.setattr(sys, "argv", ["verify_agent_automerge_pr.py", "origin/develop", branch])
    assert vap.main() == 0


@pytest.mark.parametrize(
    "branch",
    ["feat/not-agent", "develop", "module/digigraph", "hotfix/prod"],
)
def test_main_rejects_non_agent_branch_prefixes(
    branch: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vap, "_changed_files", lambda _base: ["README.md"])
    monkeypatch.setattr(sys, "argv", ["verify_agent_automerge_pr.py", "origin/develop", branch])
    assert vap.main() == 1


def test_main_rejects_when_changed_files_hit_deny_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vap,
        "_changed_files",
        lambda _base: ["digigraph/src/x.py", "digikey/src/digikey/server.py"],
    )
    monkeypatch.setattr(sys, "argv", ["verify_agent_automerge_pr.py", "origin/develop", "task/1"])
    assert vap.main() == 1


def test_main_ok_with_empty_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vap, "_changed_files", lambda _base: [])
    monkeypatch.setattr(sys, "argv", ["verify_agent_automerge_pr.py", "origin/develop", "cursor/x"])
    assert vap.main() == 0


def test_allowed_and_deny_lists_include_task_and_claude_prefixes() -> None:
    """Pin the #2341 expansion — task/ and claude/ must stay eligible for automerge."""
    assert "task/" in vap.ALLOWED_BRANCH_PREFIXES
    assert "claude/" in vap.ALLOWED_BRANCH_PREFIXES
    assert "digikey/" in vap.DENY_PATH_SUBSTRINGS
    assert "digiquant/live/" in vap.DENY_PATH_SUBSTRINGS
    assert ".github/workflows/" in vap.DENY_PATH_SUBSTRINGS

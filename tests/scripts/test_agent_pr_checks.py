"""Unit tests for scripts/agent_pr_checks.py CI gating used by agent auto-merge.

#2341 added ``task/`` and ``claude/`` to AGENT_BRANCH_PREFIXES so those PRs use
the agent check path instead of the stricter non-agent "every check SUCCESS"
gate. Without a test, dropping those prefixes would silently re-block the
majority of agent volume, and treating digikey-touching work as agent-green
on a partial check set would be the opposite failure mode.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "agent_pr_checks.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("agent_pr_checks", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_pr_checks"] = module
    spec.loader.exec_module(module)
    return module


apc = _load()


def test_agent_branch_prefixes_include_task_and_claude() -> None:
    assert "task/" in apc.AGENT_BRANCH_PREFIXES
    assert "claude/" in apc.AGENT_BRANCH_PREFIXES
    assert "cursor/" in apc.AGENT_BRANCH_PREFIXES


def test_non_agent_branch_requires_every_check_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        apc,
        "_gh_json",
        lambda *a: [
            {"name": "CI", "state": "SUCCESS"},
            {"name": "lint", "state": "FAILURE"},
        ],
    )
    ok, reason = apc.agent_checks_ok("org/repo", 1, "feat/human-pr", "abc")
    assert ok is False
    assert "not SUCCESS" in reason


def test_non_agent_branch_passes_when_all_checks_green(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        apc,
        "_gh_json",
        lambda *a: [
            {"name": "CI", "state": "SUCCESS"},
            {"name": "lint", "state": "SUCCESS"},
        ],
    )
    ok, reason = apc.agent_checks_ok("org/repo", 1, "feat/human-pr", "abc")
    assert ok is True
    assert "all checks SUCCESS" in reason


def test_score_check_is_ignored_for_agent_and_non_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``score / score`` is advisory (#3528) — must not block merge-when-ready."""
    assert "score / score" in apc.IGNORED_CHECK_NAMES
    monkeypatch.setattr(
        apc,
        "_gh_json",
        lambda *a: [
            {"name": "Required checks passed", "state": "SUCCESS"},
            {"name": "score / score", "state": "FAILURE"},
        ],
    )
    ok_agent, reason_agent = apc.agent_checks_ok("org/repo", 5, "task/3528-slug", "abc")
    assert ok_agent is True, reason_agent
    ok_human, reason_human = apc.agent_checks_ok("org/repo", 5, "chore/promote", "abc")
    assert ok_human is True, reason_human


@pytest.mark.parametrize("branch", ["task/99-slug", "claude/work", "cursor/x", "bot/y"])
def test_agent_branch_fails_on_any_non_success_check(
    branch: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        apc,
        "_gh_json",
        lambda *a: [
            {"name": "CI", "state": "SUCCESS"},
            {"name": "unit", "state": "PENDING"},
        ],
    )
    ok, reason = apc.agent_checks_ok("org/repo", 2, branch, "def")
    assert ok is False
    assert "non-ignored" in reason


@pytest.mark.parametrize("branch", ["task/99-slug", "claude/work"])
def test_task_and_claude_pass_when_checks_green(
    branch: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        apc,
        "_gh_json",
        lambda *a: [{"name": "CI", "state": "SUCCESS"}, {"name": "unit", "state": "SUCCESS"}],
    )
    ok, reason = apc.agent_checks_ok("org/repo", 3, branch, "ghi")
    assert ok is True
    assert "agent checks SUCCESS" in reason


def test_copilot_branch_requires_named_ci_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        apc,
        "_gh_json",
        lambda *a: [{"name": "lint", "state": "SUCCESS"}],
    )
    ok, reason = apc.agent_checks_ok("org/repo", 4, "copilot/thing", "jkl")
    assert ok is False
    assert "missing or failed main CI" in reason

    monkeypatch.setattr(
        apc,
        "_gh_json",
        lambda *a: [{"name": "CI", "state": "SUCCESS"}, {"name": "lint", "state": "FAILURE"}],
    )
    ok, reason = apc.agent_checks_ok("org/repo", 4, "copilot/thing", "jkl")
    assert ok is True
    assert "main CI success" in reason

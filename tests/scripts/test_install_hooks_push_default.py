"""Fail-closed on non-simple repo-local push.default (DIG-3774)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "scripts" / "install-hooks.sh"
HOOK_SRC = REPO_ROOT / "scripts" / "hooks" / "pre-push.sh"
_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _repo(tmp_path: Path, push_default: str | None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    hook_dir = repo / "scripts" / "hooks"
    hook_dir.mkdir(parents=True)
    shutil.copy(HOOK_SRC, hook_dir / "pre-push.sh")
    if push_default is not None:
        subprocess.run(
            ["git", "config", "--local", "push.default", push_default], cwd=repo, check=True
        )
    return repo


def _run(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALLER)],
        cwd=repo,
        capture_output=True,
        text=True,
        env=dict(os.environ, **_ENV, HOOKS_REF="WORKTREE"),
    )


@pytest.mark.unit
def test_non_simple_push_default_refuses_with_remedy(tmp_path: Path) -> None:
    result = _run(_repo(tmp_path, "upstream"))
    assert result.returncode != 0
    assert "git config --unset push.default" in result.stdout + result.stderr


@pytest.mark.unit
def test_simple_push_default_exits_zero(tmp_path: Path) -> None:
    assert _run(_repo(tmp_path, "simple")).returncode == 0


@pytest.mark.unit
def test_unset_push_default_exits_zero(tmp_path: Path) -> None:
    assert _run(_repo(tmp_path, None)).returncode == 0


@pytest.mark.unit
def test_agents_md_carries_no_track_rules() -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text()
    assert "--no-track" in text and "git push github" in text and "git ls-remote" in text

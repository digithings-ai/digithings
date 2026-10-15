"""Failing test for DIG-3774 (DIG-492 breach, layer 2).

``scripts/install-hooks.sh`` must fail loudly when the repo-local
``push.default`` is anything other than ``simple``, and exit 0 when it is
``simple`` or unset. The worker makes these pass and may not edit this file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "scripts" / "install-hooks.sh"
HOOK_SRC = REPO_ROOT / "scripts" / "hooks" / "pre-push.sh"


def _make_fixture(tmp: str, push_default: str | None):
    repo = Path(tmp) / "repo"
    repo.mkdir()
    env = dict(
        os.environ,
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
    )

    def git(*args: str):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )

    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "test")
    (repo / "scripts" / "hooks").mkdir(parents=True)
    shutil.copy(HOOK_SRC, repo / "scripts" / "hooks" / "pre-push.sh")
    git("add", "scripts/hooks/pre-push.sh")
    git("commit", "-q", "-m", "seed hook")
    git("branch", "-M", "develop")
    git("remote", "add", "origin", str(repo))
    git("update-ref", "refs/remotes/origin/develop", "refs/heads/develop")
    if push_default is not None:
        git("config", "push.default", push_default)
    return repo, env


def _run_installer(repo: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(INSTALLER)],
        capture_output=True,
        text=True,
        cwd=str(repo),
        env=env,
    )


def test_upstream_refuses_with_remedy() -> None:
    tmp = tempfile.mkdtemp(prefix="push-default-upstream-")
    try:
        repo, env = _make_fixture(tmp, "upstream")
        result = _run_installer(repo, env)
        assert result.returncode != 0, (
            "installer must refuse a repo-local push.default=upstream\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "git config --unset push.default" in (result.stdout + result.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_simple_exits_zero() -> None:
    tmp = tempfile.mkdtemp(prefix="push-default-simple-")
    try:
        repo, env = _make_fixture(tmp, "simple")
        result = _run_installer(repo, env)
        assert result.returncode == 0, (
            f"installer must accept push.default=simple\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_unset_exits_zero() -> None:
    tmp = tempfile.mkdtemp(prefix="push-default-unset-")
    try:
        repo, env = _make_fixture(tmp, None)
        result = _run_installer(repo, env)
        assert result.returncode == 0, (
            f"installer must accept an unset push.default\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

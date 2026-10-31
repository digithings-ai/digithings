"""`make bump` against a throwaway fake R0 git repo. Offline: no fetch, no network.

It must refuse a branch name, a short sha, and a full sha that is not on origin/develop,
leaving digithings.lock untouched, and accept a sha on origin/develop.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[2]
ZERO = "0" * 40

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture()
def fake_r0(tmp_path: Path) -> tuple[Path, str, str]:
    """A repo whose origin/develop holds one commit, plus one commit that is not on it."""
    r0 = tmp_path / "r0"
    r0.mkdir()
    git(r0, "init", "-q", "-b", "develop")
    (r0 / "README.md").write_text("fake r0\n")
    git(r0, "add", "-A")
    git(r0, "commit", "-qm", "on develop")
    on_develop = git(r0, "rev-parse", "HEAD")
    git(r0, "update-ref", "refs/remotes/origin/develop", on_develop)
    git(r0, "checkout", "-q", "-b", "feature")
    (r0 / "x.txt").write_text("off develop\n")
    git(r0, "add", "-A")
    git(r0, "commit", "-qm", "off develop")
    off_develop = git(r0, "rev-parse", "HEAD")
    return r0, on_develop, off_develop


@pytest.fixture()
def client(tmp_path: Path) -> Path:
    dst = tmp_path / "client"
    shutil.copytree(
        CLIENT, dst, symlinks=True, ignore=shutil.ignore_patterns(".git", ".link", "__pycache__")
    )
    lock = dst / "digithings.lock"
    lock.write_text(re.sub(r"(?m)^sha=.*$", f"sha={ZERO}", lock.read_text()))
    return dst


def bump(client: Path, r0: Path, sha: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "make",
            "-s",
            "-C",
            str(client),
            "bump",
            f"SHA={sha}",
            f"DIGITHINGS_DIR={r0}",
            "BUMP_TEST=scripts/check_lock.sh",
        ],
        capture_output=True,
        text=True,
    )


def pinned(client: Path) -> str:
    return re.search(r"(?m)^sha=(.*)$", (client / "digithings.lock").read_text()).group(1)


@pytest.mark.parametrize("kind", ["branch", "short", "off-develop"])
def test_bump_refuses(kind: str, client: Path, fake_r0: tuple[Path, str, str]) -> None:
    r0, on_develop, off_develop = fake_r0
    sha = {"branch": "develop", "short": on_develop[:12], "off-develop": off_develop}[kind]
    res = bump(client, r0, sha)
    assert res.returncode != 0, res.stdout + res.stderr
    assert pinned(client) == ZERO
    if kind == "off-develop":
        assert "not on origin/develop" in res.stdout + res.stderr


def test_bump_accepts_develop_sha(client: Path, fake_r0: tuple[Path, str, str]) -> None:
    r0, on_develop, _ = fake_r0
    res = bump(client, r0, on_develop)
    assert res.returncode == 0, res.stdout + res.stderr
    assert pinned(client) == on_develop
    assert "lock OK (git-sha)" in res.stdout + res.stderr

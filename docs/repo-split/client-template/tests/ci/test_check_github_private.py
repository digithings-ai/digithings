"""scripts/check_github_private.sh against a fake `gh` on a PATH shim. Offline.

`make release` must refuse unless the `github` backup remote is an existing private repo
under the owner the Makefile pins (`override GITHUB_OWNER := digithings-ai`) and passes as
the script's only argument; the environment never sets it. Only an exact `true` from `gh api repos/<owner>/<name> --jq .private`
passes; false, a 404 (gh exits non-zero), a missing remote, the wrong owner, garbage
output or a missing gh all refuse. PATH holds only the fake and basic tools, so no test
can reach the real gh or GitHub.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[2]
SCRIPT = CLIENT / "scripts" / "check_github_private.sh"
OWNER = "digithings-ai"
REMOTE = f"https://github.com/{OWNER}/example.git"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")


def fake_gh(tmp_path: Path, *, out: str = "true", rc: int = 0, stderr: str = "") -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$@" > "{tmp_path}/gh-args"\n'
        f"[ -z '{stderr}' ] || echo '{stderr}' >&2\n"
        f"[ {rc} = 0 ] || exit {rc}\n"
        f"cat <<'OUT'\n{out}\nOUT\n"
    )
    gh.chmod(0o755)
    return bin_dir


def run(
    tmp_path: Path,
    bin_dir: Path | None,
    remote: str | None = REMOTE,
    owner: str | None = OWNER,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    if remote:
        subprocess.run(["git", "-C", str(repo), "remote", "add", "github", remote], check=True)
    basics = tmp_path / "basics"
    basics.mkdir(exist_ok=True)
    for tool in ("git", "cat", "env", "bash", "printf"):
        found = shutil.which(tool)
        if found and not (basics / tool).exists():
            (basics / tool).symlink_to(found)
    path = f"{bin_dir}:{basics}" if bin_dir else str(basics)
    env = {"PATH": path, "HOME": str(tmp_path), **(extra_env or {})}
    args = ["bash", str(SCRIPT)] + ([] if owner is None else [owner])
    return subprocess.run(args, cwd=repo, env=env, capture_output=True, text=True)


@pytest.mark.parametrize(
    "remote",
    [
        f"https://github.com/{OWNER}/example.git",
        f"https://github.com/{OWNER}/example",
        f"git@github.com:{OWNER}/example.git",
        f"ssh://git@github.com/{OWNER}/example.git",
    ],
)
def test_private_true_passes(tmp_path: Path, remote: str) -> None:
    r = run(tmp_path, fake_gh(tmp_path, out="true"), remote=remote)
    assert r.returncode == 0, r.stderr
    assert "is private" in r.stdout
    args = (tmp_path / "gh-args").read_text().split("\n")
    assert args[:4] == ["api", f"repos/{OWNER}/example", "--jq", ".private"]


def test_private_false_refuses(tmp_path: Path) -> None:
    r = run(tmp_path, fake_gh(tmp_path, out="false"))
    assert r.returncode != 0 and "not private" in r.stderr


def test_404_refuses(tmp_path: Path) -> None:
    r = run(tmp_path, fake_gh(tmp_path, out="", rc=1, stderr="gh: Not Found (HTTP 404)"))
    assert r.returncode != 0 and "could not read" in r.stderr


def test_missing_remote_refuses(tmp_path: Path) -> None:
    r = run(tmp_path, fake_gh(tmp_path), remote=None)
    assert r.returncode != 0 and "no git remote 'github'" in r.stderr
    assert not (tmp_path / "gh-args").exists()


@pytest.mark.parametrize(
    "remote",
    ["https://github.com/someone-else/example.git", f"https://github.com/{OWNER}x/example.git"],
)
def test_wrong_owner_refuses(tmp_path: Path, remote: str) -> None:
    r = run(tmp_path, fake_gh(tmp_path), remote=remote)
    assert r.returncode != 0 and "is not the expected owner" in r.stderr
    assert not (tmp_path / "gh-args").exists()


@pytest.mark.parametrize(
    "out", ["TRUE", '"true"', "null", "", "true\ntrue", "<html>oops</html>", "1", " true"]
)
def test_garbage_output_refuses(tmp_path: Path, out: str) -> None:
    r = run(tmp_path, fake_gh(tmp_path, out=out))
    assert r.returncode != 0 and "refused" in r.stderr


@pytest.mark.parametrize(
    "remote",
    [
        f"http://192.168.1.35:3000/{OWNER}/example.git",
        f"https://github.com.evil.example/{OWNER}/example.git",
        f"https://github.com/{OWNER}/example/extra",
        f"https://github.com/{OWNER}/..",
    ],
)
def test_non_github_url_refuses(tmp_path: Path, remote: str) -> None:
    r = run(tmp_path, fake_gh(tmp_path), remote=remote)
    assert r.returncode != 0 and "refused" in r.stderr
    assert not (tmp_path / "gh-args").exists()


@pytest.mark.parametrize("owner", [None, "", "a/b", "$(id)"])
def test_owner_argument_missing_or_bad_refuses(tmp_path: Path, owner: str | None) -> None:
    r = run(tmp_path, fake_gh(tmp_path), owner=owner)
    assert r.returncode != 0 and "refused" in r.stderr
    assert not (tmp_path / "gh-args").exists()


def test_env_owner_alone_is_ignored(tmp_path: Path) -> None:
    # No argument: an exported GITHUB_OWNER must not stand in for it.
    r = run(tmp_path, fake_gh(tmp_path), owner=None, extra_env={"GITHUB_OWNER": OWNER})
    assert r.returncode != 0 and "usage" in r.stderr
    assert not (tmp_path / "gh-args").exists()


def test_env_owner_cannot_swap_the_argument(tmp_path: Path) -> None:
    evil = "https://github.com/evil/example.git"
    r = run(tmp_path, fake_gh(tmp_path), remote=evil, extra_env={"GITHUB_OWNER": "evil"})
    assert r.returncode != 0 and "is not the expected owner 'digithings-ai'" in r.stderr
    assert not (tmp_path / "gh-args").exists()


def test_no_gh_refuses(tmp_path: Path) -> None:
    r = run(tmp_path, None)
    assert r.returncode != 0 and "no 'gh'" in r.stderr


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
def test_release_runs_both_checks_deploy_only_forgejo() -> None:
    def plan(target: str, *extra: str) -> str:
        return subprocess.run(
            ["make", "-n", "-C", str(CLIENT), target, *extra], capture_output=True, text=True, check=True
        ).stdout

    release = plan("release", "V=1.0.0")
    assert "scripts/check_forgejo_private.sh" in release
    assert "scripts/check_github_private.sh 'digithings-ai'" in release
    for target in ("deploy-staging", "deploy-prod"):
        out = plan(target)
        assert "scripts/check_forgejo_private.sh" in out
        assert "check_github_private" not in out


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
@pytest.mark.parametrize("how", ["env", "cmdline", "both"])
def test_make_owner_is_pinned(how: str) -> None:
    env = dict(os.environ)
    args = ["make", "-n", "-C", str(CLIENT), "check-github-private"]
    if how in ("env", "both"):
        env["GITHUB_OWNER"] = "evil"
    if how in ("cmdline", "both"):
        args.append("GITHUB_OWNER=evil")
    out = subprocess.run(args, env=env, capture_output=True, text=True, check=True).stdout
    assert "scripts/check_github_private.sh 'digithings-ai'" in out
    assert "evil" not in out

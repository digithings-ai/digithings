"""scripts/check_forgejo_private.sh against fake `security` and `curl`. Offline.

The guard must pass only when the Forgejo API says the origin repo is private, and refuse
(fail closed) on a public repo, an unreadable flag, an API error, a missing keychain item,
a missing keychain tool, or an origin that is not on an allowed Forgejo host. The fake
curl also checks that the token reaches it on stdin, not in argv.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

CLIENT = Path(__file__).resolve().parents[2]
SCRIPT = CLIENT / "scripts" / "check_forgejo_private.sh"
ORIGIN = "http://192.168.1.35:3000/digithings-ai/example.git"
TOKEN = "fake-token-value"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")


def fake_bin(tmp_path: Path, *, body: str, curl_rc: int = 0, security: str | None = TOKEN) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if security is not None:
        sec = bin_dir / "security"
        sec.write_text(f"#!/usr/bin/env bash\nprintf '%s' '{security}'\n")
        sec.chmod(0o755)
    curl = bin_dir / "curl"
    curl.write_text(
        "#!/usr/bin/env bash\n"
        f'case "$*" in *{TOKEN}*) echo "token in argv" >&2; exit 99;; esac\n'
        f'grep -q "Authorization: token {TOKEN}" || {{ echo "no token on stdin" >&2; exit 98; }}\n'
        f'echo "$@" > "{tmp_path}/curl-args"\n'
        f"[ {curl_rc} = 0 ] || exit {curl_rc}\n"
        f"cat <<'JSON'\n{body}\nJSON\n"
    )
    curl.chmod(0o755)
    return bin_dir


def run(tmp_path: Path, bin_dir: Path, origin: str | None = ORIGIN) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    if origin:
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", origin], check=True)
    # Keep only the fakes plus the basics (git, python3, coreutils) on PATH.
    basics = tmp_path / "basics"
    basics.mkdir(exist_ok=True)
    for tool in ("git", "python3", "grep", "cat", "env", "bash", "printf"):
        found = shutil.which(tool)
        if found and not (basics / tool).exists():
            (basics / tool).symlink_to(found)
    env = {"PATH": f"{bin_dir}:{basics}", "HOME": str(tmp_path)}
    return subprocess.run(
        ["bash", str(SCRIPT)], cwd=repo, env=env, capture_output=True, text=True
    )


def test_private_repo_passes(tmp_path: Path) -> None:
    r = run(tmp_path, fake_bin(tmp_path, body='{"full_name":"digithings-ai/example","private":true}'))
    assert r.returncode == 0, r.stderr
    assert "is private" in r.stdout
    assert "/api/v1/repos/digithings-ai/example" in (tmp_path / "curl-args").read_text()
    assert TOKEN not in r.stdout + r.stderr


@pytest.mark.parametrize(
    "body",
    ['{"private":false}', '{"private":"true"}', '{"full_name":"x"}', "not json", "[]", ""],
)
def test_not_private_or_unreadable_refuses(tmp_path: Path, body: str) -> None:
    r = run(tmp_path, fake_bin(tmp_path, body=body))
    assert r.returncode != 0
    assert "refused" in r.stderr


def test_api_error_refuses(tmp_path: Path) -> None:
    r = run(tmp_path, fake_bin(tmp_path, body='{"private":true}', curl_rc=22))
    assert r.returncode != 0 and "could not read" in r.stderr


def test_missing_keychain_item_refuses(tmp_path: Path) -> None:
    r = run(tmp_path, fake_bin(tmp_path, body='{"private":true}', security=""))
    assert r.returncode != 0 and "refused" in r.stderr


def test_no_keychain_tool_refuses(tmp_path: Path) -> None:
    r = run(tmp_path, fake_bin(tmp_path, body='{"private":true}', security=None))
    assert r.returncode != 0 and "keychain" in r.stderr


@pytest.mark.parametrize(
    "origin",
    [None, "https://github.com/digithings-ai/example.git", "git@192.168.1.35:digithings-ai/example.git"],
)
def test_origin_not_on_forgejo_refuses(tmp_path: Path, origin: str | None) -> None:
    r = run(tmp_path, fake_bin(tmp_path, body='{"private":true}'), origin=origin)
    assert r.returncode != 0 and "refused" in r.stderr

"""Unit tests for scripts/fetch_task.sh.

Regression guard: issue bodies containing backticks, newlines inside JSON
strings, or embedded triple-quotes used to break the script when it
interpolated `gh issue view` output into a Python heredoc. The fix routes
JSON through an env var, so arbitrary control characters are safe.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "fetch_task.sh"


def _write_fake_gh(bin_dir: Path, payload: dict) -> None:
    """Install a stub `gh` on PATH that emits the given JSON for `issue view`."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "gh"
    # The stub ignores args and prints the payload. The script only uses
    # `gh issue view ... --json ...` and `gh auth status` (not invoked here).
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f"cat <<'__JSON__'\n{json.dumps(payload)}\n__JSON__\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run(bin_dir: Path, issue: str = "42") -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(SCRIPT), issue],
        env=env,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )


@pytest.mark.unit
def test_parses_body_with_adversarial_characters(tmp_path: Path) -> None:
    """Backticks, triple-quotes, and embedded newlines must not break parsing."""
    payload = {
        "number": 42,
        "title": "[agent] crash repro",
        "body": "Line 1\nLine 2 with `backticks`\nLine 3 with '''triple''' quotes\n",
        "url": "https://example.invalid/42",
        "state": "OPEN",
        "labels": [
            {"name": "component:digiquant"},
            {"name": "risk:med"},
        ],
    }
    bin_dir = tmp_path / "bin"
    _write_fake_gh(bin_dir, payload)

    result = _run(bin_dir)

    assert result.returncode == 0, result.stderr
    assert "=== Task #42: crash repro ===" in result.stdout
    assert "Component: digiquant" in result.stdout
    assert "Risk:      med" in result.stdout
    assert "`backticks`" in result.stdout
    assert "'''triple'''" in result.stdout


@pytest.mark.unit
def test_missing_issue_arg_exits_nonzero(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    _write_fake_gh(bin_dir, {})  # stub present but not invoked
    result = _run(bin_dir, issue="")
    assert result.returncode != 0
    assert "Usage" in result.stderr


@pytest.mark.unit
def test_requires_gh_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Script should exit with a clear error if `gh` is absent from PATH."""
    empty_bin = tmp_path / "empty"
    empty_bin.mkdir()
    # Minimal PATH without gh — but keep essentials bash needs.
    env = {"PATH": str(empty_bin)}
    # Include system dirs for bash itself but strip any gh in them.
    for d in ("/usr/bin", "/bin"):
        if Path(d).exists():
            env["PATH"] += f":{d}"
    # If the host has gh installed in /usr/bin or /bin, skip — we can't easily hide it.
    if shutil.which("gh", path=env["PATH"]):
        pytest.skip("cannot hide gh from PATH on this host")

    result = subprocess.run(
        ["bash", str(SCRIPT), "1"],
        env=env,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode != 0
    assert "gh CLI not found" in result.stderr

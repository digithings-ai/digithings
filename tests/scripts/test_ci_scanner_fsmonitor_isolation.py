"""Unit tests for the CI scanners' git access and the runner's stall verdict.

DIG-5318. On 2026-10-22 the post-merge run on develop 8cfd404816a6 turned
three scanners red while the tree was clean:

    scripts/check_gloomberb_ci_guard.py    TIMEOUT 600s [rc=124]
    scripts/check_plaintext_credentials.py TIMEOUT 600s [rc=124]
    scripts/check_vendor_content.py        TIMEOUT 600s [rc=124]

The tree was not the cause. The scanners read the tree through git, and git
read it through the fsmonitor daemon: in the post-merge worktree (4.3 GB,
node_modules + .venv) ``git ls-files`` spent 5.2 s of wall clock on 0.01 s of
CPU inside the daemon, and then failed outright with "could not read IPC
response". The plaintext guard then fell back to its full-tree walk, which
read 146k installed files instead of the 7,314 tracked ones, and the 600 s
budget turned a wedged cache into a red check that blamed the merge.

So three properties are pinned here:

* every scanner asks git for the file list with the fsmonitor daemon off,
* the fallback walk of the plaintext guard is bounded and skips the dependency
  trees, so a broken git can never turn into a crawl,
* the runner tells a scanner that did not answer apart from a scanner that
  found something: the first is a stall, the second is a finding.
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # A module with a dataclass has to be in sys.modules before it runs:
    # dataclasses looks its own module up there while it builds the class.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def plaintext():
    return _load("check_plaintext_credentials", "scripts/check_plaintext_credentials.py")


@pytest.fixture(scope="module")
def example():
    return _load("check_example_credentials", "scripts/check_example_credentials.py")


@pytest.fixture(scope="module")
def vendor():
    return _load("check_vendor_content", "scripts/check_vendor_content.py")


@pytest.fixture(scope="module")
def gloomberb():
    return _load("check_gloomberb_ci_guard", "scripts/check_gloomberb_ci_guard.py")


@pytest.fixture(scope="module")
def runner():
    return _load("local_ci", "scripts/local-ci/local_ci.py")


def _recording_run(calls, *, stdout="", toplevel="", fail_on=()):
    """A ``subprocess.run`` stand-in that records the argv it was handed.

    ``fail_on`` names a subcommand that must fail the way a wedged fsmonitor
    daemon fails: exit 1 with "could not read IPC response" on stderr.
    """

    def run(cmd, **kwargs):
        calls.append(list(cmd))
        for token in fail_on:
            if token in cmd:
                raise subprocess.CalledProcessError(
                    1, cmd, output="", stderr="fatal: could not read IPC response"
                )
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=toplevel, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    return run


# ── the scanners ask git without the fsmonitor daemon ───────────────────────


def test_the_plaintext_guard_asks_git_without_the_fsmonitor(plaintext, tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(
        plaintext.subprocess,
        "run",
        _recording_run(calls, stdout="app.py\0", toplevel=str(tmp_path)),
    )
    plaintext.tracked_files(tmp_path)
    assert calls, "the guard never asked git for the file list"
    for call in calls:
        assert "core.fsmonitor=false" in call, call


def test_the_example_guard_asks_git_without_the_fsmonitor(example, tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(example.subprocess, "run", _recording_run(calls, stdout=""))
    assert example.main() == 0
    assert calls, "the guard never asked git for the file list"
    for call in calls:
        assert "core.fsmonitor=false" in call, call


def test_the_vendor_guard_asks_git_without_the_fsmonitor(vendor, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(vendor.subprocess, "run", _recording_run(calls, stdout=""))
    vendor.git("ls-files", "-z")
    assert calls, "the guard never asked git for the file list"
    for call in calls:
        assert "core.fsmonitor=false" in call, call


def test_the_gloomberb_guard_asks_git_without_the_fsmonitor(gloomberb, tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(
        gloomberb.subprocess, "run", _recording_run(calls, stdout=b"app.py\0")
    )
    gloomberb.tracked_files(tmp_path)
    assert calls, "the guard never asked git for the file list"
    for call in calls:
        assert "core.fsmonitor=false" in call, call


# ── a broken git can no longer become a crawl ───────────────────────────────


def test_a_broken_git_is_not_a_crawl(plaintext, tmp_path, monkeypatch):
    """Git is there but cannot list the files: the guard must say so.

    The old code fell through to the full-tree walk here, and that walk is
    what turned a wedged daemon into a 600 s timeout on a checkout with
    node_modules and .venv (DIG-5318).
    """
    calls: list[list[str]] = []
    monkeypatch.setattr(
        plaintext.subprocess,
        "run",
        _recording_run(calls, toplevel=str(tmp_path), fail_on=("ls-files",)),
    )
    with pytest.raises(plaintext.ScanUnavailable) as caught:
        plaintext.tracked_files(tmp_path)
    assert "could not list" in str(caught.value)


def test_the_guard_reports_that_it_could_not_answer(plaintext, tmp_path, monkeypatch):
    def boom(root):
        raise plaintext.ScanUnavailable("git could not list the tracked files")

    monkeypatch.setattr(plaintext, "tracked_files", boom)
    # 3, not 1: the guard did not find a credential, it could not look.
    assert plaintext.main(["--root", str(tmp_path)]) == 3


def test_the_fallback_walk_skips_the_dependency_trees(plaintext, tmp_path):
    pkg = tmp_path / "node_modules" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "readme.md").write_text("installed code\n")
    (tmp_path / "app.py").write_text("print('hi')\n")
    found = plaintext.walk_files(tmp_path)
    names = {p.name for p in found}
    assert "app.py" in names
    assert "readme.md" not in names, "the dependency tree was scanned"


def test_the_fallback_walk_refuses_to_crawl(plaintext, tmp_path, monkeypatch):
    for i in range(5):
        (tmp_path / f"f{i}.txt").write_text("x\n")
    monkeypatch.setattr(plaintext, "MAX_WALK_FILES", 2)
    with pytest.raises(plaintext.ScanUnavailable):
        plaintext.walk_files(tmp_path)


def test_the_example_guard_walk_skips_the_dependency_trees(example, tmp_path):
    pkg = tmp_path / "node_modules" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "a.example").write_text("X=1\n")
    (tmp_path / "b.example").write_text("X=1\n")
    found = example._walk_source_files(tmp_path)
    names = {p.name for p in found}
    assert "b.example" in names
    assert "a.example" not in names, "the dependency tree was scanned"


def test_the_example_guard_reports_that_it_could_not_answer(example, tmp_path, monkeypatch):
    """A walk that cannot finish is a stall, not a finding (DIG-5318)."""
    monkeypatch.setattr(example, "MAX_WALK_FILES", 0)
    monkeypatch.setattr(
        example.subprocess,
        "run",
        _recording_run([], fail_on=("ls-files",)),
    )
    monkeypatch.chdir(tmp_path)
    assert example.main() == 3


def test_the_walk_says_why_it_is_walking(plaintext, tmp_path, monkeypatch, capsys):
    """The CI log must say the list came from a walk, not from git."""
    monkeypatch.setattr(
        plaintext.subprocess,
        "run",
        _recording_run([], fail_on=("rev-parse",)),
    )
    plaintext.tracked_files(tmp_path)
    assert "not a git checkout" in capsys.readouterr().err


# ── the runner tells a stall apart from a finding ───────────────────────────


def test_a_scanner_that_times_out_is_a_stall(runner, monkeypatch):
    calls: list[str] = []

    def fake_sh(cmd, **kwargs):
        calls.append(cmd)
        return 124, ""

    monkeypatch.setattr(runner, "sh", fake_sh)
    fails: list[str] = []
    out = io.StringIO()
    ok = runner.scan_step(
        "check_plaintext_credentials.py", "python3 x", out=out, fails=fails
    )
    assert ok is False
    assert fails == ["check_plaintext_credentials.py:stall"]
    assert len(calls) == 2, "a stalled scanner is retried once"
    assert "STALL" in out.getvalue()


def test_a_scanner_that_finds_something_is_a_finding(runner, monkeypatch):
    calls: list[str] = []

    def fake_sh(cmd, **kwargs):
        calls.append(cmd)
        return 1, ""

    monkeypatch.setattr(runner, "sh", fake_sh)
    fails: list[str] = []
    ok = runner.scan_step(
        "check_plaintext_credentials.py", "python3 x", out=io.StringIO(), fails=fails
    )
    assert ok is False
    assert fails == ["check_plaintext_credentials.py"]
    assert len(calls) == 1, "a finding is not retried"


def test_a_clean_scanner_passes(runner, monkeypatch):
    monkeypatch.setattr(runner, "sh", lambda cmd, **kwargs: (0, ""))
    fails: list[str] = []
    ok = runner.scan_step(
        "check_plaintext_credentials.py", "python3 x", out=io.StringIO(), fails=fails
    )
    assert ok is True
    assert fails == []


def test_a_scanner_that_could_not_look_is_a_stall(runner, monkeypatch):
    """Exit 3 is the guard's "I could not list the files", not a finding."""
    monkeypatch.setattr(runner, "sh", lambda cmd, **kwargs: (3, ""))
    fails: list[str] = []
    ok = runner.scan_step(
        "check_plaintext_credentials.py", "python3 x", out=io.StringIO(), fails=fails
    )
    assert ok is False
    assert fails == ["check_plaintext_credentials.py:stall"]


def test_the_scan_env_switches_the_fsmonitor_off(runner):
    env = runner.no_fsmonitor_env({"PATH": "/x"})
    assert env["PATH"] == "/x"
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "core.fsmonitor"
    assert env["GIT_CONFIG_VALUE_0"] == "false"


def test_an_existing_git_override_is_kept(runner):
    env = runner.no_fsmonitor_env(
        {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.something",
            "GIT_CONFIG_VALUE_0": "1",
        }
    )
    assert env["GIT_CONFIG_COUNT"] == "2"
    assert env["GIT_CONFIG_KEY_1"] == "core.fsmonitor"
    assert env["GIT_CONFIG_VALUE_1"] == "false"

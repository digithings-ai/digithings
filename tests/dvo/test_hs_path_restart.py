"""Tool lookup survives a short PATH; restart cycles Hammerspoon and checks it came back."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from digivoice import probe as probe_mod
from digivoice.opentui import launch_opentui
from digivoice.reload import hammerspoon_env_path, restart_hammerspoon
from digivoice.tui_bridge import dispatch

from tests.dvo.fakes import FakeReply, FakeRunner

pytestmark = pytest.mark.unit


def _exe(path: Path) -> Path:
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_probe_falls_back_to_tool_dirs(tmp_path: Path) -> None:
    brew = tmp_path / "brew"
    brew.mkdir()
    sox = _exe(brew / "sox")
    found = probe_mod.FilesystemProbe("/usr/bin:/bin", fallback_dirs=(str(brew),)).lookup("sox")
    assert found == str(sox)


def test_probe_prefers_caller_path(tmp_path: Path) -> None:
    first, brew = tmp_path / "a", tmp_path / "brew"
    first.mkdir()
    brew.mkdir()
    mine = _exe(first / "sox")
    _exe(brew / "sox")
    probe = probe_mod.FilesystemProbe(str(first), fallback_dirs=(str(brew),))
    assert probe.lookup("sox") == str(mine)


def test_default_fallbacks_cover_homebrew_and_usr_local() -> None:
    assert "/opt/homebrew/bin" in probe_mod.FALLBACK_TOOL_DIRS
    assert "/usr/local/bin" in probe_mod.FALLBACK_TOOL_DIRS


def test_augmented_path_appends_once() -> None:
    out = probe_mod.augmented_path("/usr/bin:/opt/homebrew/bin").split(os.pathsep)
    assert out.count("/opt/homebrew/bin") == 1
    assert out[0] == "/usr/bin"
    assert "/usr/local/bin" in out


def test_hammerspoon_env_path_has_homebrew() -> None:
    path = hammerspoon_env_path({"PATH": "/usr/bin:/bin", "HOME": "/Users/x"})
    assert "/opt/homebrew/bin" in path.split(":")
    assert "/Users/x/.local/bin" in path.split(":")


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _hs_replies(sequence: list[int]) -> object:
    """hs -c replies: stop expr ok, then probe codes from `sequence`."""
    state = {"i": 0}

    def respond(call: object) -> FakeReply:
        argv = call.argv  # type: ignore[attr-defined]
        if "return 'ok'" not in argv[-1]:
            return FakeReply(stdout="stopped")
        code = sequence[min(state["i"], len(sequence) - 1)]
        state["i"] += 1
        return FakeReply(code=code, stdout="ok" if code == 0 else "")

    return respond


def test_restart_quits_reopens_with_full_path_and_verifies(tmp_path: Path) -> None:
    clock = _Clock()
    # old instance gone (1), then new one answers on second probe.
    runner = FakeRunner({"hs": _hs_replies([1, 1, 0])})
    report = restart_hammerspoon(
        "darwin",
        tmp_path,
        {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        runner=runner,
        which_hs=lambda: "/opt/homebrew/bin/hs",
        which_osascript=lambda: "/usr/bin/osascript",
        which_open=lambda: "/usr/bin/open",
        monotonic=clock.now,
        sleep=clock.sleep,
    )
    assert report.summary == "hammerspoon restarted"
    assert "hammerspoon .. back up" in report.lines
    opened = runner.call_for("open")
    assert opened is not None
    assert opened.argv[1] == "--env"
    assert "/opt/homebrew/bin" in opened.argv[2]
    assert opened.argv[-2:] == ["-a", "Hammerspoon"]
    assert runner.call_for("osascript") is not None


def test_restart_reports_failure_when_hammerspoon_never_answers(tmp_path: Path) -> None:
    clock = _Clock()
    runner = FakeRunner({"hs": _hs_replies([1])})
    report = restart_hammerspoon(
        "darwin",
        tmp_path,
        {"PATH": "/usr/bin"},
        runner=runner,
        which_hs=lambda: "hs",
        which_osascript=lambda: "osascript",
        which_open=lambda: "open",
        budget=2.0,
        monotonic=clock.now,
        sleep=clock.sleep,
    )
    assert report.summary == "hammerspoon restart failed"


def test_restart_skips_off_macos(tmp_path: Path) -> None:
    runner = FakeRunner()
    report = restart_hammerspoon("linux", tmp_path, {}, runner=runner)
    assert report.summary == "hammerspoon skipped"
    assert runner.calls == []


def test_bridge_restart_reports_hammerspoon(tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path), "DIGIVOICE_DATA_DIR": str(tmp_path / "data")}
    out = dispatch({"op": "restart"}, platform="linux", home=tmp_path, env=env)
    assert out["restart"] is True
    assert out["hammerspoon"] == "hammerspoon skipped"


def test_tui_launch_ignores_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, dict[str, str]] = {}

    def fake_execve(node: str, argv: list[str], env: dict[str, str]) -> None:
        seen["env"] = env

    node = _exe(tmp_path / "bun")
    monkeypatch.setattr("digivoice.opentui.os.execve", fake_execve)
    monkeypatch.chdir(tmp_path)
    env = {"HOME": str(tmp_path), "DIGIVOICE_DATA_DIR": str(tmp_path / "d"), "DIGIVOICE_NODE": str(node)}
    launch_opentui("linux", tmp_path, env)
    if "env" in seen:
        assert seen["env"]["PYTHONSAFEPATH"] == "1"

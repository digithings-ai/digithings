"""Bare `digivoice` starts Hammerspoon and the banner without hanging."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from digivoice.cli import Runtime, run
from digivoice.paths import resolve_paths
from digivoice.reload import ensure_home_control, stop_home_control
from digivoice.settings import VoiceSettings, save_settings
from digivoice.status import StatusReporter, status_path

from tests.dvo.fakes import FakeCall, FakeProbe, FakeReply, FakeRunner

pytestmark = pytest.mark.unit


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _env(tmp_path: Path) -> dict[str, str]:
    return {"DIGIVOICE_DATA_DIR": str(tmp_path), "PATH": "/usr/bin"}


def _install_adapter(home: Path) -> None:
    adapter = home / ".hammerspoon" / "digivoice"
    adapter.mkdir(parents=True)
    (adapter / "init.lua").write_text("-- adapter\n", encoding="utf-8")
    (adapter / "banner_core.lua").write_text("-- core\n", encoding="utf-8")


def test_linux_home_skips_hammerspoon_without_calling_out(tmp_path: Path) -> None:
    def boom(_call: FakeCall) -> FakeReply:
        raise AssertionError("linux home launch must not spawn Hammerspoon")

    started = time.monotonic()
    report = ensure_home_control(
        "linux",
        tmp_path,
        _env(tmp_path),
        runner=FakeRunner({"hs": boom, "open": boom}),
        which_hs=lambda: "/usr/bin/hs",
        which_open=lambda: "/usr/bin/open",
    )
    assert time.monotonic() - started < 1
    assert report.summary == "hammerspoon skipped · banner skipped"
    result = run(
        [], Runtime(platform="linux", home=tmp_path, env=_env(tmp_path), probe=FakeProbe())
    )
    assert result.code == 0
    assert "▤" in result.stdout
    assert "hammerspoon skipped · banner skipped" in result.stdout


def test_armed_banner_is_hidden_until_a_take(tmp_path: Path) -> None:
    def reply(call: FakeCall) -> FakeReply:
        expr = call.argv[-1]
        if "ensure_banner" in expr:
            return FakeReply(code=0, stdout="armed\n")
        return FakeReply(code=0, stdout="ok\n")

    report = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=FakeRunner({"hs": reply}),
        which_hs=lambda: "hs",
        which_open=lambda: "open",
    )
    assert report.summary == "hammerspoon up · banner armed"
    assert "hidden until a take" in "\n".join(report.lines)


def test_running_hammerspoon_shows_banner_without_open(tmp_path: Path) -> None:
    def reply(call: FakeCall) -> FakeReply:
        expr = call.argv[-1]
        if expr == "return 'ok'":
            return FakeReply(code=0, stdout="ok\n")
        if "ensure_banner" in expr:
            return FakeReply(code=0, stdout="shown\n")
        return FakeReply(code=0, stdout="")

    clock = _Clock()
    runner = FakeRunner({"hs": reply, "open": reply})
    report = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=runner,
        which_hs=lambda: "/usr/local/bin/hs",
        which_open=lambda: "/usr/bin/open",
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    assert report.summary == "hammerspoon up · banner shown"
    assert all(call.program != "open" for call in runner.calls)
    assert any("ensure_banner" in call.argv[-1] for call in runner.calls)
    assert all(call.timeout is not None and call.timeout <= 4 for call in runner.calls)


def test_opens_hammerspoon_then_shows_banner(tmp_path: Path) -> None:
    clock = _Clock()
    probes = {"n": 0}

    def reply(call: FakeCall) -> FakeReply:
        if call.program == "open":
            return FakeReply(code=0, stdout="")
        expr = call.argv[-1]
        if expr == "return 'ok'":
            probes["n"] += 1
            if probes["n"] == 1:
                return FakeReply(code=1, stderr="connection refused")
            return FakeReply(code=0, stdout="ok\n")
        if "ensure_banner" in expr:
            return FakeReply(code=0, stdout="visible\n")
        return FakeReply(code=0, stdout="")

    runner = FakeRunner({"hs": reply, "open": reply})
    report = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=runner,
        which_hs=lambda: "hs",
        which_open=lambda: "open",
        budget=4,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    assert report.summary == "hammerspoon up · banner visible"
    assert any(
        call.program == "open"
        and call.argv[1] == "--env"
        and "/opt/homebrew/bin" in call.argv[2]
        and call.argv[-2:] == ["-a", "Hammerspoon"]
        for call in runner.calls
    )
    assert clock.t < 4
    assert all(call.timeout is not None for call in runner.calls)


def test_down_hammerspoon_returns_inside_budget(tmp_path: Path) -> None:
    clock = _Clock()
    runner = FakeRunner(
        {
            "hs": FakeReply(code=1, stderr="connection refused"),
            "open": FakeReply(code=1, stderr="unable to find application"),
        }
    )
    report = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=runner,
        which_hs=lambda: "hs",
        which_open=lambda: "open",
        budget=1.0,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    assert "banner hidden" in report.summary
    assert clock.t <= 1.2
    assert runner.calls


def test_live_banner_false_does_not_ask_to_show(tmp_path: Path) -> None:
    paths = resolve_paths("darwin", tmp_path, _env(tmp_path))
    save_settings(paths, VoiceSettings(live_banner=False))

    def reply(call: FakeCall) -> FakeReply:
        if "ensure_banner" in call.argv[-1]:
            raise AssertionError("banner ipc while live_banner is false")
        return FakeReply(code=0, stdout="ok\n")

    report = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=FakeRunner({"hs": reply}),
        which_hs=lambda: "hs",
        which_open=lambda: "open",
    )
    assert report.summary == "hammerspoon up · banner off"


def test_active_take_is_left_alone(tmp_path: Path) -> None:
    paths = resolve_paths("darwin", tmp_path, _env(tmp_path))
    StatusReporter(status_path(paths), "dict").update("recording", text="hello")

    def reply(call: FakeCall) -> FakeReply:
        if "ensure_banner" in call.argv[-1]:
            raise AssertionError("must not repaint over a live take")
        return FakeReply(code=0, stdout="ok\n")

    report = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=FakeRunner({"hs": reply}),
        which_hs=lambda: "hs",
        which_open=lambda: "open",
    )
    assert "banner busy" in report.summary


def test_require_line_is_added_then_reloaded(tmp_path: Path) -> None:
    _install_adapter(tmp_path)
    init = tmp_path / ".hammerspoon" / "init.lua"
    init.write_text("hs.logger.default = 1\n", encoding="utf-8")

    def reply(call: FakeCall) -> FakeReply:
        expr = call.argv[-1]
        if "hs.reload" in expr:
            return FakeReply(code=0, stdout="")
        if "ensure_banner" in expr:
            return FakeReply(code=0, stdout="shown\n")
        return FakeReply(code=0, stdout="ok\n")

    clock = _Clock()
    runner = FakeRunner({"hs": reply})
    report = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=runner,
        which_hs=lambda: "hs",
        which_open=lambda: "open",
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    assert 'require("digivoice")' in init.read_text(encoding="utf-8")
    assert any("hs.reload()" in call.argv for call in runner.calls)
    assert report.summary == "hammerspoon up · banner shown"
    again = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=FakeRunner({"hs": reply}),
        which_hs=lambda: "hs",
        which_open=lambda: "open",
    )
    text = init.read_text(encoding="utf-8")
    assert text.count('require("digivoice")') == 1
    assert again.summary == "hammerspoon up · banner shown"


def test_take_in_progress_is_not_reloaded(tmp_path: Path) -> None:
    _install_adapter(tmp_path)
    init = tmp_path / ".hammerspoon" / "init.lua"
    init.write_text("hs.logger.default = 1\n", encoding="utf-8")
    paths = resolve_paths("darwin", tmp_path, _env(tmp_path))
    StatusReporter(status_path(paths), "dict").update("recording", text="hello")

    def reply(call: FakeCall) -> FakeReply:
        if "hs.reload" in call.argv[-1] or "ensure_banner" in call.argv[-1]:
            raise AssertionError(call.argv[-1])
        return FakeReply(code=0, stdout="ok\n")

    report = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=FakeRunner({"hs": reply}),
        which_hs=lambda: "hs",
        which_open=lambda: "open",
    )
    assert report.summary == "hammerspoon up · banner busy"
    assert 'require("digivoice")' in init.read_text(encoding="utf-8")


def test_missing_banner_without_adapter_does_not_reload(tmp_path: Path) -> None:
    def reply(call: FakeCall) -> FakeReply:
        if "hs.reload" in call.argv[-1]:
            raise AssertionError("must not reload Hammerspoon when the adapter is absent")
        if "ensure_banner" in call.argv[-1]:
            return FakeReply(code=0, stdout="missing\n")
        return FakeReply(code=0, stdout="ok\n")

    report = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=FakeRunner({"hs": reply}),
        which_hs=lambda: "hs",
        which_open=lambda: "open",
    )
    assert report.summary == "hammerspoon up · banner hidden"


def test_missing_banner_reloads_once_then_shows(tmp_path: Path) -> None:
    _install_adapter(tmp_path)
    init = tmp_path / ".hammerspoon" / "init.lua"
    init.write_text('require("digivoice")\n', encoding="utf-8")
    reloaded = {"n": 0}

    def reply(call: FakeCall) -> FakeReply:
        expr = call.argv[-1]
        if "hs.reload" in expr:
            reloaded["n"] += 1
            return FakeReply(code=0, stdout="")
        if "ensure_banner" in expr:
            token = "shown" if reloaded["n"] else "missing"
            return FakeReply(code=0, stdout=token + "\n")
        return FakeReply(code=0, stdout="ok\n")

    clock = _Clock()
    runner = FakeRunner({"hs": reply})
    report = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=runner,
        which_hs=lambda: "hs",
        which_open=lambda: "open",
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    assert report.summary == "hammerspoon up · banner shown"
    assert reloaded["n"] == 1
    assert clock.t < 4


def test_up_but_out_of_budget_stays_up(tmp_path: Path) -> None:
    clock = _Clock()

    def reply(call: FakeCall) -> FakeReply:
        clock.t += 4
        return FakeReply(code=0, stdout="ok\n")

    report = ensure_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=FakeRunner({"hs": reply}),
        which_hs=lambda: "hs",
        which_open=lambda: "open",
        budget=4,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    assert report.summary == "hammerspoon up · banner hidden"


def test_stop_home_control_quits_hammerspoon(tmp_path: Path) -> None:
    seen: list[str] = []

    def reply(call: FakeCall) -> FakeReply:
        seen.append(" ".join(call.argv))
        name = Path(call.argv[0]).name
        if name == "hs" and "m.stop" in call.argv[-1]:
            return FakeReply(code=0, stdout="stopped\n")
        if name == "osascript":
            return FakeReply(code=0, stdout="")
        return FakeReply(code=1, stdout="unexpected")

    report = stop_home_control(
        "darwin",
        tmp_path,
        _env(tmp_path),
        runner=FakeRunner({"hs": reply, "osascript": reply}),
        which_hs=lambda: "/usr/local/bin/hs",
        which_osascript=lambda: "/usr/bin/osascript",
    )
    assert report.summary == "hammerspoon quit"
    assert any("m.stop" in line for line in seen)
    assert any("osascript" in line for line in seen)


def test_stop_home_control_skips_on_linux(tmp_path: Path) -> None:
    def boom(_call: FakeCall) -> FakeReply:
        raise AssertionError("linux quit must not spawn Hammerspoon")

    report = stop_home_control(
        "linux",
        tmp_path,
        _env(tmp_path),
        runner=FakeRunner({"hs": boom, "osascript": boom}),
        which_hs=lambda: "/usr/bin/hs",
        which_osascript=lambda: "/usr/bin/osascript",
    )
    assert report.summary == "hammerspoon skipped"


def test_home_quit_tears_down_hammerspoon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Quit is the OpenTUI action that stops Hammerspoon."""
    from digivoice.reload import LaunchReport
    from digivoice.tui_bridge import dispatch

    calls: list[str] = []

    def fake_stop(*_a, **_k) -> LaunchReport:
        calls.append("stop")
        return LaunchReport(summary="hammerspoon quit", lines=["hammerspoon .. quit"])

    monkeypatch.setattr("digivoice.tui_bridge.stop_home_control", fake_stop)
    result = dispatch({"op": "quit"}, platform="darwin", home=tmp_path, env=_env(tmp_path))
    assert result["exit"] == 0
    assert result["stopped"] is True
    assert calls == ["stop"]


def test_home_escape_leaves_hammerspoon_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A TTY launches OpenTUI. Esc is a close, not a Hammerspoon stop."""
    from digivoice.reload import LaunchReport
    from digivoice.tui_bridge import dispatch

    from digivoice import home as home_mod

    launched: list[str] = []

    def fake_launch(*_a, **kwargs) -> int:
        launched.append(kwargs.get("start", "/"))
        return 0

    monkeypatch.setattr(
        home_mod, "ensure_home_control", lambda *_a, **_k: LaunchReport(summary="up", lines=[])
    )
    monkeypatch.setattr(home_mod, "launch_opentui", fake_launch)
    monkeypatch.setattr(home_mod, "_is_tty", lambda _s: True)

    code = home_mod.run_home(
        "darwin",
        tmp_path,
        _env(tmp_path),
        stdin=__import__("io").StringIO(""),
        stdout=__import__("io").StringIO(),
        launch=LaunchReport(summary="up", lines=[]),
    )
    assert code == 0
    assert launched == ["/"]
    closed = dispatch({"op": "close"}, platform="darwin", home=tmp_path, env=_env(tmp_path))
    assert closed["stopped"] is False

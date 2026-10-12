"""Bare-`digivoice` home shell and the `reload` subcommand."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest
from digivoice.cli import Runtime, run
from digivoice.home import (
    HOME_BLOCKS,
    HOME_MENU,
    format_status_line,
    home_menu_tree,
    render_home_overview,
    run_home,
)

from tests.dvo.fakes import FakeProbe, FakeReply, FakeRunner

pytestmark = pytest.mark.unit


def _runtime(tmp_path: Path, **env: str) -> Runtime:
    merged = {"DIGIVOICE_DATA_DIR": str(tmp_path), **env}
    return Runtime(platform="linux", home=tmp_path, env=merged, probe=FakeProbe())


def test_status_line_names_the_model_and_settings_that_are_on() -> None:
    line = format_status_line(
        "ggml-base.en",
        paste=True,
        rewrite=False,
        banner=True,
        pin=False,
        summary="ok (4/4 ready)",
    )
    assert line == "ggml-base.en · paste · banner · ok (4/4 ready)"
    assert "\n" not in line


def test_bare_non_tty_prints_home_overview(tmp_path: Path) -> None:
    result = run([], _runtime(tmp_path))
    assert result.code == 0
    assert "DIGIVOICE" in result.stdout
    assert "— Context —" in result.stdout
    assert "— Actions —" in result.stdout
    assert "▦" in result.stdout
    assert "banner" in result.stdout
    assert "■" in result.stdout or "□" in result.stdout
    for item in HOME_MENU:
        assert item.split(" (")[0] in result.stdout
    assert "System" in result.stdout
    assert "reload" in result.stdout
    assert "dict --toggle" in result.stdout


def test_bare_help_still_shows_argparse_help(tmp_path: Path) -> None:
    for argv in (["--help"], ["-h"], ["help"]):
        result = run(argv, _runtime(tmp_path))
        assert result.code == 0
        assert "Local speech" in result.stdout


def test_home_menu_tree_matches_rendered_overview(tmp_path: Path) -> None:
    assert home_menu_tree() == list(HOME_MENU)
    text = render_home_overview("settings-body")
    assert "settings-body" in text
    assert "Quit" in text


def test_home_is_app_actions_with_settings_path() -> None:
    assert [m.split(" (")[0] for m in HOME_MENU] == [
        "History",
        "Settings",
        "System",
        "Quit",
    ]
    assert not any(m.startswith("Status") for m in HOME_MENU)
    assert not any(m.startswith("Doctor") for m in HOME_MENU)
    assert not any(m.startswith("Reload") for m in HOME_MENU)
    settings_at = next(i for i, m in enumerate(HOME_MENU) if m.startswith("Settings"))
    system_at = next(i for i, m in enumerate(HOME_MENU) if m.startswith("System"))
    assert settings_at < system_at
    assert HOME_BLOCKS[settings_at].path == "/settings"
    assert HOME_BLOCKS[system_at].path == "/system"
    assert [block.path for block in HOME_BLOCKS] == ["/history", "/settings", "/system", "/quit"]


def test_home_overview_mentions_settings_path(tmp_path: Path) -> None:
    result = run([], _runtime(tmp_path))
    assert result.code == 0
    assert "/settings" in result.stdout
    assert "Esc goes up" in result.stdout


def test_run_home_non_tty_never_hangs(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    buf = io.StringIO()
    code = run_home(
        runtime.platform, runtime.home, dict(runtime.env), stdin=io.StringIO(""), stdout=buf
    )
    assert code == 0
    assert "DIGIVOICE" in buf.getvalue()


def test_reload_skips_hammerspoon_when_hs_missing(tmp_path: Path) -> None:
    result = run(["reload"], _runtime(tmp_path))
    assert result.code == 0
    assert "cli " in result.stdout
    assert "settings" in result.stdout
    assert "adapter" in result.stdout
    assert "skipped (hs not on PATH" in result.stdout


def test_reload_json_shape(tmp_path: Path) -> None:
    result = run(["reload", "--json"], _runtime(tmp_path))
    assert result.code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["hammerspoon"]["ok"] is True
    assert "cli" in payload


def test_reload_hs_timeout_clears_stale_status(tmp_path: Path) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    hs = bindir / "hs"
    hs.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hs.chmod(0o755)
    stale = tmp_path / "status.json"
    stale.write_text('{"stale": true}', encoding="utf-8")
    runner = FakeRunner({"hs": FakeReply(code=124, stderr="timed out after 8s")})
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path), "PATH": str(bindir)},
        probe=FakeProbe(),
        runner=runner,
    )
    result = run(["reload"], runtime)
    assert result.code == 1
    assert "timed out" in result.stdout
    assert "cleared stale status" in result.stdout
    assert not stale.exists()
    call = runner.call_for("hs")
    assert call is not None
    assert call.argv == ["hs", "-c", "hs.reload()"]
    assert call.timeout == 8.0


def test_quit_and_slash_paths_map_without_a_tty(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    quit_result = run(["quit"], runtime)
    assert quit_result.code == 0
    assert "skipped" in quit_result.stdout
    doctor = run(["/doctor"], runtime)
    assert "Whisper" in doctor.stdout or "whisper" in doctor.stdout
    pin = run(["/settings/banner/pin"], runtime)
    assert pin.code == 0
    assert "on  /settings/banner/pin/on" in pin.stdout
    assert "off  /settings/banner/pin/off" in pin.stdout
    system = run(["system"], runtime)
    assert "/doctor" in system.stdout
    assert "/reload" in system.stdout
    assert "/system/logs" in system.stdout
    (tmp_path / "system.log").write_text("1000 error boom\n", encoding="utf-8")
    logs = run(["/system/logs"], runtime)
    assert logs.code == 0
    assert "boom" in logs.stdout
    reset = run(["reset"], runtime)
    assert reset.stdout == "settings reset\n"
    missing = run(["/history/delete"], runtime)
    assert missing.code == 2


def test_reload_reports_live_tip_through_symlink(tmp_path: Path) -> None:
    real = tmp_path / "checkout" / "digivoice" / "hammerspoon"
    real.mkdir(parents=True)
    (real / "init.lua").write_text("-- tip\n", encoding="utf-8")
    (real / "banner_core.lua").write_text("-- tip\n", encoding="utf-8")
    link_parent = tmp_path / ".hammerspoon"
    link_parent.mkdir()
    os.symlink(real, link_parent / "digivoice", target_is_directory=True)
    result = run(["reload"], _runtime(tmp_path))
    assert result.code == 0
    assert "live tip" in result.stdout
    assert str(real) in result.stdout

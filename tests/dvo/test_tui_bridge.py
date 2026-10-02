"""OpenTUI launch argv and the local screen bridge."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.history import append_entry, dict_entry
from digivoice.opentui import opentui_argv
from digivoice.paths import resolve_paths
from digivoice.settings import load_settings
from digivoice.status import system_log_path
from digivoice.tui_bridge import dispatch

from tests.dvo.fakes import FakeProbe, FakeRunner

pytestmark = pytest.mark.unit


def _env(tmp_path: Path) -> dict[str, str]:
    return {"DIGIVOICE_DATA_DIR": str(tmp_path), "PATH": ""}


def test_opentui_argv_points_at_the_node_app() -> None:
    argv = opentui_argv({"DIGIVOICE_NODE": "node"})
    assert argv[0] == "node"
    assert argv[1].endswith("digivoice/tui/src/main.js")
    assert Path(argv[1]).is_file()


def test_bridge_boot_lists_home_and_model_language_once(tmp_path: Path) -> None:
    env = _env(tmp_path)
    boot = dispatch({"op": "boot", "start": "/"}, platform="linux", home=tmp_path, env=env)
    actions = [row["action"] for row in boot["home"]]
    assert actions == ["History", "Settings", "System", "Quit"]
    rows = dispatch(
        {"op": "rows", "path": "/settings/speech/model"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    assert any("ggml-medium.en" in row["path"] for row in rows)
    assert any("ggml-large-v3" in row["path"] for row in rows)
    for row in rows:
        visible = f"{row['action']}\n{row['meta']}"
        language = "English" if "English" in visible else "multilingual"
        assert visible.count(language) == 1


def test_bridge_apply_confirms_before_a_missing_download(tmp_path: Path) -> None:
    env = _env(tmp_path)
    rows = dispatch(
        {"op": "rows", "path": "/settings/speech/model"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    index = next(i for i, row in enumerate(rows) if row["path"].endswith("ggml-tiny.en"))
    pending = dispatch(
        {"op": "apply", "path": "/settings/speech/model", "index": index},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert pending["confirm"] is True
    paths = resolve_paths("linux", tmp_path, env)
    assert load_settings(paths).stt_model == "ggml-base.en"
    assert "Download" in pending["rows"][0]["action"]


def test_bridge_restart_does_not_stop_and_update_stays_a_note(tmp_path: Path) -> None:
    env = _env(tmp_path)
    restart = dispatch({"op": "restart"}, platform="linux", home=tmp_path, env=env)
    assert restart["restart"] is True
    assert "stopped" not in restart
    source = tmp_path / "lua"
    source.mkdir()
    (source / "init.lua").write_text("-- status icon only\n", encoding="utf-8")
    tui = tmp_path / "tui"
    tui.mkdir()
    (tui / "package.json").write_text('{"name":"digivoice-tui"}\n', encoding="utf-8")

    def fetch(url: str, dest: Path) -> None:
        raise OSError(f"offline {url}")

    update = dispatch(
        {"op": "update"},
        platform="linux",
        home=tmp_path,
        env=env,
        probe=FakeProbe(commands={"sox": "/usr/bin/sox"}),
        runner=FakeRunner(),
        fetch=fetch,
        machine="aarch64",
        adapter_source=source,
        tui_root=tui,
    )
    assert "digivoice update" in update["note"]
    assert "failed" in update["note"]
    assert "not wired yet" not in update["note"]
    assert "stopped" not in update
    assert "exit" not in update
    assert (tmp_path / ".hammerspoon" / "digivoice" / "init.lua").is_file()


def test_bridge_boot_status_is_one_line(tmp_path: Path) -> None:
    boot = dispatch(
        {"op": "boot", "start": "/"}, platform="linux", home=tmp_path, env=_env(tmp_path)
    )
    status = boot["status"]
    assert "\n" not in status
    assert "ggml-base.en" in status
    assert "paste" in status
    assert "banner" in status
    assert "rewrite" not in status
    assert "pin" not in status.split(" · ")


def test_bridge_save_writes_settings_json(tmp_path: Path) -> None:
    env = _env(tmp_path)
    saved = dispatch({"op": "save"}, platform="linux", home=tmp_path, env=env)
    assert saved["saved"] is True
    text = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "paste_on_stop" in text
    rows = dispatch(
        {"op": "rows", "path": "/settings/speech/paste"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    off = next(index for index, row in enumerate(rows) if row["name"] == "off")
    dispatch(
        {"op": "apply", "path": "/settings/speech/paste", "index": off},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    dispatch({"op": "save"}, platform="linux", home=tmp_path, env=env)
    paths = resolve_paths("linux", tmp_path, env)
    assert load_settings(paths).paste_on_stop is False


def test_bridge_hotkey_apply_writes_the_binding(tmp_path: Path) -> None:
    env = _env(tmp_path)
    rows = dispatch(
        {"op": "rows", "path": "/settings/hotkeys"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    index = next(i for i, row in enumerate(rows) if row["name"] == "dictation")
    dispatch({"op": "save"}, platform="linux", home=tmp_path, env=env)
    before = (tmp_path / "settings.json").read_text(encoding="utf-8")
    refused = dispatch(
        {
            "op": "apply",
            "path": "/settings/hotkeys",
            "index": index,
            "text": "not-a-key",
        },
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert refused["saved"] is False
    assert "not a key" in refused["note"]
    assert (tmp_path / "settings.json").read_text(encoding="utf-8") == before
    dispatch(
        {
            "op": "apply",
            "path": "/settings/hotkeys",
            "index": index,
            "text": "ctrl+shift+space",
        },
        platform="linux",
        home=tmp_path,
        env=env,
    )
    paths = resolve_paths("linux", tmp_path, env)
    assert load_settings(paths).hotkey_bindings.dictation == "ctrl+shift+space"


def test_option_lock_in_reloads_hammerspoon(tmp_path: Path) -> None:
    """A bare Option name is Right Option, and Enter asks Hammerspoon to reload."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    hs = bindir / "hs"
    hs.write_text("#!/bin/sh\n", encoding="utf-8")
    hs.chmod(0o755)
    env = {"DIGIVOICE_DATA_DIR": str(tmp_path), "PATH": str(bindir)}
    runner = FakeRunner()
    rows = dispatch(
        {"op": "rows", "path": "/settings/hotkeys"},
        platform="linux",
        home=tmp_path,
        env=env,
        runner=runner,
    )["rows"]
    index = next(i for i, row in enumerate(rows) if row["name"] == "dictation")
    refused = dispatch(
        {"op": "apply", "path": "/settings/hotkeys", "index": index, "text": "not-a-key"},
        platform="linux",
        home=tmp_path,
        env=env,
        runner=runner,
    )
    assert refused["saved"] is False
    assert runner.calls == []
    saved = dispatch(
        {"op": "apply", "path": "/settings/hotkeys", "index": index, "text": "option"},
        platform="linux",
        home=tmp_path,
        env=env,
        runner=runner,
    )
    assert saved["saved"] is True
    paths = resolve_paths("linux", tmp_path, env)
    assert load_settings(paths).hotkey_bindings.dictation == "option"
    assert [call.argv for call in runner.calls] == [["hs", "-c", "hs.reload()"]]


def test_bridge_history_row_is_the_timestamp(tmp_path: Path) -> None:
    env = _env(tmp_path)
    paths = resolve_paths("linux", tmp_path, env)
    append_entry(paths.history_file, dict_entry("ship it", None))
    page = dispatch({"op": "history"}, platform="linux", home=tmp_path, env=env)
    row = page["rows"][0]
    assert row["kind"] == "take"
    assert row["action"].endswith("Z")
    assert row["text"] == "ship it"
    assert "ship it" not in row["action"]
    assert page["path"] == "/history"


def test_bridge_doctor_rows_are_short_checks(tmp_path: Path) -> None:
    page = dispatch({"op": "doctor"}, platform="linux", home=tmp_path, env=_env(tmp_path))
    assert page["title"] == "doctor"
    ids = [row["action"] for row in page["rows"]]
    assert "whisper-cli" in ids
    for skipped in ("tcc", "interrupt", "paths", "detection", "history"):
        assert skipped not in ids
    for row in page["rows"]:
        assert row["kind"] == "check"
        assert row["path"] == ""
        assert len(row["detail"]) <= 60
        assert row["meta"] in {"ok", "missing", "info"}


def test_bridge_empty_log_is_not_a_choice(tmp_path: Path) -> None:
    env = _env(tmp_path)
    empty = dispatch({"op": "logs"}, platform="linux", home=tmp_path, env=env)
    assert empty["rows"] == [{"action": "No log yet", "path": "", "meta": "", "kind": "note"}]
    paths = resolve_paths("linux", tmp_path, env)
    system_log_path(paths).write_text("ready now\n", encoding="utf-8")
    page = dispatch({"op": "logs"}, platform="linux", home=tmp_path, env=env)
    row = page["rows"][0]
    assert row["kind"] == "log"
    assert row["text"] == "ready now"
    assert row["meta"] == "system.log"


def test_bridge_update_exception_is_a_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**_kwargs: object) -> None:
        raise RuntimeError("update broke")

    monkeypatch.setattr("digivoice.tui_bridge.run_install", boom)
    update = dispatch({"op": "update"}, platform="linux", home=tmp_path, env=_env(tmp_path))
    assert update["note"] == "update broke"
    assert "exit" not in update
    assert "stopped" not in update

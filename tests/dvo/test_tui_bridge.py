"""OpenTUI launch argv and the local screen bridge."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.history import append_entry, dict_entry
from digivoice.opentui import opentui_argv
from digivoice.paths import resolve_paths
from digivoice.settings import load_settings, save_settings
from digivoice.status import system_log_path
from digivoice.tui_bridge import cancel_download, dispatch, run_download

from tests.dvo.fakes import FakeProbe, FakeReply, FakeRunner

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


def test_bridge_rows_mark_downloaded_models(tmp_path: Path) -> None:
    env = _env(tmp_path)
    paths = resolve_paths("linux", tmp_path, env)
    models = Path(paths.models_dir)
    models.mkdir()
    (models / "ggml-base.en.bin").write_bytes(b"base")
    rows = dispatch(
        {"op": "rows", "path": "/settings/speech/model"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    base = next(row for row in rows if row["path"].endswith("ggml-base.en"))
    tiny = next(row for row in rows if row["path"].endswith("ggml-tiny.en"))
    assert base["downloaded"] is True
    assert tiny["downloaded"] is False


def test_bridge_apply_opens_a_download_for_a_missing_model(tmp_path: Path) -> None:
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
    assert pending["download"] is True
    assert pending["filename"] == "ggml-tiny.en.bin"
    assert pending["index"] == index
    paths = resolve_paths("linux", tmp_path, env)
    assert load_settings(paths).stt_model == "ggml-base.en"
    assert not (Path(paths.models_dir) / "ggml-tiny.en.bin").exists()


def test_bridge_apply_selects_a_downloaded_model_without_fetching(tmp_path: Path) -> None:
    env = _env(tmp_path)
    paths = resolve_paths("linux", tmp_path, env)
    models = Path(paths.models_dir)
    models.mkdir()
    (models / "ggml-tiny.en.bin").write_bytes(b"tiny")
    (models / "ggml-base.en.bin").write_bytes(b"base")
    rows = dispatch(
        {"op": "rows", "path": "/settings/speech/model"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    index = next(i for i, row in enumerate(rows) if row["path"].endswith("ggml-tiny.en"))
    saved = dispatch(
        {"op": "apply", "path": "/settings/speech/model", "index": index},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert saved["stay"] is True
    assert saved["path"] == "/settings/speech/model"
    assert saved["index"] == index
    assert load_settings(paths).stt_model == "ggml-tiny.en"
    assert (models / "ggml-base.en.bin").read_bytes() == b"base"
    chosen = saved["rows"][index]
    assert chosen["downloaded"] is True


def test_download_streams_progress_and_keeps_other_models(tmp_path: Path) -> None:
    env = _env(tmp_path)
    paths = resolve_paths("linux", tmp_path, env)
    models = Path(paths.models_dir)
    models.mkdir()
    (models / "ggml-base.en.bin").write_bytes(b"base")
    rows = dispatch(
        {"op": "rows", "path": "/settings/speech/model"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    index = next(i for i, row in enumerate(rows) if row["path"].endswith("ggml-small.en"))

    def fetch(url: str, dest: Path, progress=None) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"small")
        if progress is not None:
            progress(2, 8)
            progress(8, 8)

    events: list[dict] = []
    run_download(
        paths,
        {"path": "/settings/speech/model", "index": index, "filename": "ggml-small.en.bin"},
        emit=events.append,
        fetch=fetch,
        home=tmp_path,
        env=env,
    )
    assert events[0] == {"got": 2, "total": 8}
    assert events[1] == {"got": 8, "total": 8}
    assert events[-1]["ok"] is True
    assert events[-1]["index"] == index
    assert (models / "ggml-base.en.bin").read_bytes() == b"base"
    assert (models / "ggml-small.en.bin").read_bytes() == b"small"
    assert not (models / "ggml-small.en.bin.partial").exists()
    assert load_settings(paths).stt_model == "ggml-small.en"
    marked = events[-1]["rows"][index]
    assert marked["downloaded"] is True


def test_download_failure_stays_unmarked(tmp_path: Path) -> None:
    env = _env(tmp_path)
    paths = resolve_paths("linux", tmp_path, env)
    models = Path(paths.models_dir)
    models.mkdir()
    (models / "ggml-base.en.bin").write_bytes(b"base")
    rows = dispatch(
        {"op": "rows", "path": "/settings/rewrite/model"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    index = next(i for i, row in enumerate(rows) if not row["downloaded"])

    def fetch(url: str, dest: Path, progress=None) -> None:
        dest.write_bytes(b"nope")
        if progress is not None:
            progress(1, 4)
        raise OSError("disk full")

    before = load_settings(paths).rewrite_model
    events: list[dict] = []
    run_download(
        paths,
        {"path": "/settings/rewrite/model", "index": index, "filename": rows[index]["choice"]},
        emit=events.append,
        fetch=fetch,
        home=tmp_path,
        env=env,
    )
    assert events[0]["got"] == 1
    assert "disk full" in events[-1]["error"]
    assert "ok" not in events[-1]
    assert (models / "ggml-base.en.bin").read_bytes() == b"base"
    assert not any(path.name.endswith(".partial") for path in models.iterdir())
    assert load_settings(paths).stt_model == "ggml-base.en"
    assert load_settings(paths).rewrite_model == before


def test_cancel_download_removes_only_the_partial(tmp_path: Path) -> None:
    env = _env(tmp_path)
    paths = resolve_paths("linux", tmp_path, env)
    models = Path(paths.models_dir)
    models.mkdir()
    (models / "ggml-base.en.bin").write_bytes(b"base")
    (models / "ggml-tiny.en.bin.partial").write_bytes(b"half")
    result = cancel_download(paths, "ggml-tiny.en.bin")
    assert result["cancelled"] is True
    assert (models / "ggml-base.en.bin").read_bytes() == b"base"
    assert not (models / "ggml-tiny.en.bin.partial").exists()
    assert not (models / "ggml-tiny.en.bin").exists()


def test_voice_missing_opens_a_download_and_a_file_selects(tmp_path: Path) -> None:
    env = _env(tmp_path)
    paths = resolve_paths("linux", tmp_path, env)
    rows = dispatch(
        {"op": "rows", "path": "/settings/speech/voice"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    auto = next(i for i, row in enumerate(rows) if row["choice"] == "auto")
    assert rows[auto]["downloaded"] is False
    picked = dispatch(
        {"op": "apply", "path": "/settings/speech/voice", "index": auto},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert "download" not in picked
    assert picked["stay"] is True
    assert load_settings(paths).tts_voice is None
    amy = next(i for i, row in enumerate(rows) if row["choice"] == "en_US-amy-medium.onnx")
    assert rows[amy]["downloaded"] is False
    opened = dispatch(
        {"op": "apply", "path": "/settings/speech/voice", "index": amy},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert opened["download"] is True
    assert opened["filename"] == "en_US-amy-medium.onnx"
    models = Path(paths.models_dir)
    models.mkdir()
    (models / "en_US-amy-medium.onnx").write_bytes(b"voice")
    rows = dispatch(
        {"op": "rows", "path": "/settings/speech/voice"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    amy = next(i for i, row in enumerate(rows) if row["choice"] == "en_US-amy-medium.onnx")
    assert rows[amy]["downloaded"] is True
    saved = dispatch(
        {"op": "apply", "path": "/settings/speech/voice", "index": amy},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert saved["stay"] is True
    assert load_settings(paths).tts_voice == "en_US-amy-medium.onnx"


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
    assert update["ok"] is False
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


def test_duplicate_hotkey_is_refused_and_does_not_reload(tmp_path: Path) -> None:
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
    before = load_settings(resolve_paths("linux", tmp_path, env)).hotkey_bindings.dictation
    refused = dispatch(
        {"op": "apply", "path": "/settings/hotkeys", "index": index, "text": "Esc"},
        platform="linux",
        home=tmp_path,
        env=env,
        runner=runner,
    )
    assert refused["saved"] is False
    assert "already cancel" in refused["note"]
    paths = resolve_paths("linux", tmp_path, env)
    assert load_settings(paths).hotkey_bindings.dictation == before
    assert runner.calls == []
    kept = dispatch(
        {"op": "apply", "path": "/settings/hotkeys", "index": index, "text": "Right Option"},
        platform="linux",
        home=tmp_path,
        env=env,
        runner=runner,
    )
    assert kept["saved"] is True
    assert [call.argv for call in runner.calls] == [["hs", "-c", "hs.reload()"]]


def test_hotkey_capture_flag_tracks_the_field(tmp_path: Path) -> None:
    env = _env(tmp_path)
    opened = dispatch(
        {"op": "hotkey-capture", "active": True},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert opened["active"] is True
    flag = tmp_path / "hotkey.capture"
    assert flag.read_text(encoding="utf-8") == "1\n"
    closed = dispatch(
        {"op": "hotkey-capture", "active": False},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert closed["active"] is False
    assert not flag.exists()
    dispatch({"op": "boot"}, platform="linux", home=tmp_path, env=env)
    flag.write_text("1\n", encoding="utf-8")
    dispatch({"op": "close"}, platform="linux", home=tmp_path, env=env)
    assert not flag.exists()


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
    assert update["ok"] is False
    assert "exit" not in update
    assert "stopped" not in update


def test_chooser_opens_on_the_saved_row(tmp_path: Path) -> None:
    env = _env(tmp_path)
    paths = resolve_paths("linux", tmp_path, env)
    current = load_settings(paths)
    save_settings(
        paths,
        current.model_copy(update={"paste_on_stop": False, "banner_position": "center"}),
    )
    model = dispatch(
        {"op": "rows", "path": "/settings/speech/model"},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert model["rows"][model["selected"]]["choice"] == "ggml-base.en"
    paste = dispatch(
        {"op": "rows", "path": "/settings/speech/paste"},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert paste["rows"][paste["selected"]]["choice"] == "off"
    position = dispatch(
        {"op": "rows", "path": "/settings/banner/position"},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert position["rows"][position["selected"]]["choice"] == "center"


def test_catalog_copy_under_mlx_is_selected_not_downloaded(tmp_path: Path) -> None:
    env = _env(tmp_path)
    weight = tmp_path / ".mlxstudio" / "models" / "whisper" / "GGML-tiny.en.bin"
    weight.parent.mkdir(parents=True)
    weight.write_bytes(b"tiny")
    voice = tmp_path / ".lmstudio" / "models" / "en_US-amy-medium.onnx"
    voice.parent.mkdir(parents=True)
    voice.write_bytes(b"amy")
    rows = dispatch(
        {"op": "rows", "path": "/settings/speech/model"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    index = next(i for i, row in enumerate(rows) if row["path"].endswith("ggml-tiny.en"))
    assert rows[index]["downloaded"] is True
    saved = dispatch(
        {"op": "apply", "path": "/settings/speech/model", "index": index},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert saved.get("download") is not True
    assert saved["stay"] is True
    paths = resolve_paths("linux", tmp_path, env)
    assert load_settings(paths).stt_model == "ggml-tiny.en"
    assert weight.read_bytes() == b"tiny"
    voices = dispatch(
        {"op": "rows", "path": "/settings/speech/voice"},
        platform="linux",
        home=tmp_path,
        env=env,
    )["rows"]
    amy = next(i for i, row in enumerate(voices) if row["choice"] == "en_US-amy-medium.onnx")
    assert voices[amy]["downloaded"] is True
    picked = dispatch(
        {"op": "apply", "path": "/settings/speech/voice", "index": amy},
        platform="linux",
        home=tmp_path,
        env=env,
    )
    assert picked.get("download") is not True
    assert picked["stay"] is True
    assert load_settings(paths).tts_voice == "en_US-amy-medium.onnx"


def test_reload_failure_is_not_reported_as_success(tmp_path: Path) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    hs = bindir / "hs"
    hs.write_text("#!/bin/sh\n", encoding="utf-8")
    hs.chmod(0o755)
    env = {"DIGIVOICE_DATA_DIR": str(tmp_path), "PATH": str(bindir)}
    result = dispatch(
        {"op": "reload"},
        platform="linux",
        home=tmp_path,
        env=env,
        runner=FakeRunner(responses={"hs": FakeReply(code=1, stderr="nope")}),
    )
    assert result["ok"] is False
    assert "reload failed" in result["note"]
    assert "reloaded" not in result["note"]

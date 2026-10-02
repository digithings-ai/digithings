"""Settings path: folders, toggles, cycles, and a line of explanation on each row."""

from __future__ import annotations

import io
import os
import pty
import threading
import time
from pathlib import Path

import pytest
from digivoice.catalog import REWRITE_CATALOG, STT_CATALOG
from digivoice.menu_tree import browse_settings, rows_at
from digivoice.paths import resolve_paths
from digivoice.settings import VoiceSettings, load_settings
from digivoice.tui import choose, render_screen, row_hits

pytestmark = pytest.mark.unit


def _paths(tmp_path: Path):
    return resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})


def _walk(settings: VoiceSettings, path: str = "/settings") -> list:
    rows = rows_at(settings, path)
    found = list(rows)
    for row in rows:
        if row.kind in {"dir", "pick"}:
            found.extend(_walk(settings, f"{path}/{row.name}"))
    return found


def test_settings_root_is_four_folders() -> None:
    rows = rows_at(VoiceSettings(), "/settings")
    assert [row.name for row in rows] == ["speech", "rewrite", "banner", "hotkeys"]
    assert all(row.kind == "dir" for row in rows)


def test_every_row_explains_itself() -> None:
    rows = _walk(VoiceSettings())
    assert rows
    for row in rows:
        assert row.explain
        assert "(" not in row.explain
        assert row.explain in row.label()
        if row.value:
            assert f"[{row.value}]" in row.label()


def test_browse_toggles_paste(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    browse_settings(paths, io.StringIO("1\n3\n\n\n"), io.StringIO())
    assert load_settings(paths).paste_on_stop is False


def test_browse_cycles_banner_density(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    browse_settings(paths, io.StringIO("3\n4\n\n\n"), io.StringIO())
    assert load_settings(paths).banner_density == "full"


def test_rewrite_is_enabled_style_and_model() -> None:
    rows = rows_at(VoiceSettings(), "/settings/rewrite")
    assert [row.name for row in rows] == ["enabled", "style", "model"]
    assert rows[1].kind == "pick"
    styles = rows_at(VoiceSettings(), "/settings/rewrite/style")
    assert [row.choice for row in styles] == [
        "email",
        "sms",
        "professional",
        "coding",
        "blog",
        "none",
    ]
    names = [row.name for row in _walk(VoiceSettings())]
    assert "runner" not in names
    assert "timeout" not in names
    assert "apps" not in names


def test_banner_pin_is_a_toggle() -> None:
    rows = rows_at(VoiceSettings(), "/settings/banner")
    assert [row.name for row in rows][:2] == ["show", "pin"]
    assert rows[1].field == "banner_pinned"
    assert rows[1].value == "off"


def test_speech_lists_model_voice_and_paste_only() -> None:
    rows = rows_at(VoiceSettings(), "/settings/speech")
    assert [row.name for row in rows] == ["model", "voice", "paste"]
    assert rows[0].kind == "pick"
    names = [row.name for row in _walk(VoiceSettings())]
    assert "words" not in names
    assert "spelling" not in names


def test_model_list_shows_size_and_recommended() -> None:
    rows = rows_at(VoiceSettings(), "/settings/speech/model")
    assert rows
    assert all(row.kind == "choice" for row in rows)
    recommended = [row for row in rows if "recommended" in row.value]
    assert len(recommended) == 1
    assert recommended[0].choice == "ggml-base.en"
    assert "~142 MB" in recommended[0].value
    assert all("(" not in row.explain for row in rows)


def test_opening_the_model_list_does_not_download(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []

    def install(paths, entry, stdout):
        calls.append(entry.id)
        return entry.filename

    browse_settings(paths, io.StringIO("1\n1\n\n\n"), io.StringIO(), install=install)
    assert calls == []
    assert load_settings(paths).stt_model == "ggml-base.en"


def test_missing_model_downloads_only_after_confirm(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []

    def install(paths, entry, stdout):
        calls.append(entry.id)
        target = Path(paths.models_dir) / entry.filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        return str(target)

    browse_settings(paths, io.StringIO("1\n1\n1\n2\n\n\n"), io.StringIO(), install=install)
    assert calls == []
    assert load_settings(paths).stt_model == "ggml-base.en"
    browse_settings(paths, io.StringIO("1\n1\n1\n1\n\n\n"), io.StringIO(), install=install)
    assert calls == ["ggml-tiny.en"]
    assert load_settings(paths).stt_model == "ggml-tiny.en"


def test_installed_model_is_selected_without_a_download(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    dest = tmp_path / "models"
    dest.mkdir()
    (dest / "ggml-tiny.en.bin").write_bytes(b"x")
    calls: list[str] = []

    def install(paths, entry, stdout):
        calls.append(entry.id)
        return entry.filename

    browse_settings(paths, io.StringIO("1\n1\n1\n\n\n"), io.StringIO(), install=install)
    assert calls == []
    assert load_settings(paths).stt_model == "ggml-tiny.en"


def test_browse_esc_at_the_root_changes_nothing(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    browse_settings(paths, io.StringIO("\n"), io.StringIO())
    assert load_settings(paths).paste_on_stop is True
    assert load_settings(paths).banner_density == "retract"


def test_hotkey_capture_persists_and_blank_cancels(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    browse_settings(paths, io.StringIO("4\n1\nctrl+space\n\n\n"), io.StringIO())
    saved = load_settings(paths)
    assert saved.hotkey_bindings.dictation == "ctrl+space"
    assert saved.hotkey_bindings.speak == "Double-tap Left Option"
    assert saved.hotkey_bindings.cancel == "Esc"
    browse_settings(paths, io.StringIO("4\n2\n\n\n\n"), io.StringIO())
    again = load_settings(paths)
    assert again.hotkey_bindings.speak == "Double-tap Left Option"
    assert again.hotkey_bindings.dictation == "ctrl+space"


def test_voice_pane_opens_selects_and_returns(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    speech = rows_at(VoiceSettings(), "/settings/speech")
    assert speech[1].name == "voice"
    assert speech[1].kind == "pick"
    voices = rows_at(VoiceSettings(), "/settings/speech/voice", Path(paths.models_dir))
    assert voices
    assert voices[0].choice == "auto"
    names = [row.choice for row in voices]
    assert len(names) == len(set(names))
    browse_settings(paths, io.StringIO("1\n2\n2\n\n\n"), io.StringIO())
    assert load_settings(paths).tts_voice == "en_US-lessac-medium.onnx"
    browse_settings(paths, io.StringIO("1\n2\n1\n\n\n"), io.StringIO())
    assert load_settings(paths).tts_voice is None


def test_model_rows_show_language_and_a_unique_name() -> None:
    for path, catalog, field in (
        ("/settings/speech/model", STT_CATALOG, "stt_model"),
        ("/settings/rewrite/model", REWRITE_CATALOG, "rewrite_model"),
    ):
        rows = rows_at(VoiceSettings(), path)
        assert len(rows) == len(catalog)
        choices = [row.choice for row in rows]
        assert len(choices) == len(set(choices))
        for row in rows:
            block = row.as_block(path)
            visible = f"{block.action}\n{block.meta}\n{block.path}"
            assert row.choice in block.path
            assert visible.count(row.choice) == 1
            assert "English" in visible or "multilingual" in visible
            assert row.field == field


def test_settings_rows_do_not_trap_on_a_note_or_a_line_prompt() -> None:
    rows = _walk(VoiceSettings())
    assert rows
    assert all(row.kind != "note" for row in rows)
    assert all(row.kind != "text" for row in rows)


def test_click_on_the_voice_row_selects_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The click that used to fall into a line prompt returns the voice row."""
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.setattr("digivoice.tui._term_size", lambda: (80, 24))
    rows = rows_at(VoiceSettings(), "/settings/speech")
    blocks = [row.as_block("/settings/speech") for row in rows]
    voice_index = next(index for index, row in enumerate(rows) if row.name == "voice")
    render_screen(
        "speech",
        [block.action for block in blocks],
        0,
        subtitle="/settings/speech",
        cols=80,
        rows=24,
        use_ansi=True,
        use_screen=True,
        clear=True,
        blocks=blocks,
        truecolor=False,
    )
    voice_row = next(index for index, hit in enumerate(row_hits()) if hit == voice_index)
    sequence = f"\x1b[<0;2;{voice_row + 1}M".encode()
    master, slave = pty.openpty()

    def feed() -> None:
        time.sleep(0.15)
        os.write(master, sequence)
        time.sleep(0.4)
        os.write(master, b"\x1b")

    threading.Thread(target=feed, daemon=True).start()
    raw = os.fdopen(slave, "rb+", buffering=0)
    tty = io.TextIOWrapper(raw, encoding="utf-8", newline="\n", write_through=True)
    try:
        picked = choose(
            "speech",
            stdin=tty,
            stdout=tty,
            subtitle="/settings/speech",
            blocks=blocks,
        )
    finally:
        tty.close()
        os.close(master)
    assert picked == voice_index

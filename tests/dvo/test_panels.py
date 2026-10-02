"""Doctor colors, history paging, and the system pane."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from digivoice.history import append_entry, dict_entry, read_history
from digivoice.models import DoctorCheck
from digivoice.panels import browse_history, browse_system, present_doctor
from digivoice.paths import resolve_paths
from digivoice.settings import VoiceSettings, load_settings, save_settings
from digivoice.status import StatusReporter, system_log_path

from tests.dvo.fakes import FakeProbe, FakeReply, FakeRunner

pytestmark = pytest.mark.unit


def _paths(tmp_path: Path):
    return resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})


def _required(status: str = "ok") -> list[DoctorCheck]:
    return [
        DoctorCheck(id="whisper-cli", status=status, detail="whisper"),
        DoctorCheck(id="piper", status="ok", detail="piper"),
        DoctorCheck(id="capture", status="ok", detail="sox"),
        DoctorCheck(id="models", status="ok", detail="models"),
        DoctorCheck(id="tcc", status="info", detail="not probed"),
    ]


def test_doctor_paints_ok_green_and_failure_red() -> None:
    checks = _required("missing")
    frame = present_doctor(checks, io.StringIO(), color=True, pause=0)
    assert "\x1b[32m" in frame
    assert "\x1b[31m" in frame
    assert "not ok" in frame
    assert "Whisper is not installed" in frame
    assert "Not ready" in frame
    assert "All set" not in frame


def test_doctor_keeps_long_paths_out_of_the_panel() -> None:
    path = "/Users/someone/" + ("Library/Application Support/" * 8) + "models/ggml-base.en.bin"
    checks = [
        DoctorCheck(id="models", status="missing", detail=path),
        *_required("ok")[1:],
    ]
    frame = present_doctor(checks, io.StringIO(), color=True, pause=0)
    assert path not in frame
    assert "Speech model is missing" in frame
    assert "ok" in frame
    for line in frame.splitlines():
        visible = line
        while "\x1b" in visible:
            start = visible.find("\x1b")
            end = visible.find("m", start)
            visible = visible[:start] + (visible[end + 1 :] if end >= 0 else "")
        assert len(visible) <= 100


def test_doctor_plain_status_column_keeps_its_gap() -> None:
    """Color off must not collapse the status column into the summary."""
    checks = [
        DoctorCheck(id="whisper-cli", status="ok", detail="/usr/local/bin/whisper-cli"),
        DoctorCheck(id="piper", status="missing", detail="/opt/homebrew/bin/piper"),
        DoctorCheck(id="history", status="info", detail="absent"),
    ]
    frame = present_doctor(checks, io.StringIO(), color=False, pause=0)
    assert "ok      Whisper is installed" in frame
    assert "not ok  Piper is not installed" in frame
    assert "info    No history yet" in frame
    assert "/usr/local" not in frame
    assert "/opt/homebrew" not in frame


def test_doctor_says_ready_when_required_checks_pass() -> None:
    frame = present_doctor(_required("ok"), io.StringIO(), color=True, pause=0)
    assert "All set. Local speech is ready." in frame
    assert "\x1b[32m" in frame


def test_esc_backs_out_of_history_system_and_logs(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    browse_history(paths, "linux", FakeProbe(), FakeRunner({}), io.StringIO("\n"), io.StringIO())
    browse_system(
        paths,
        "linux",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(tmp_path)},
        io.StringIO("\n"),
        io.StringIO(),
    )
    browse_system(
        paths,
        "linux",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(tmp_path)},
        io.StringIO("6\n\n"),
        io.StringIO(),
    )


def test_empty_history_stays_on_a_menu(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    out = io.StringIO()
    browse_history(paths, "linux", FakeProbe(), FakeRunner({}), io.StringIO("\n"), out)
    assert "No takes yet" in out.getvalue()
    assert "/history" in out.getvalue()


def test_history_pages_and_copies(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    for index in range(10):
        append_entry(paths.history_file, dict_entry(f"take-{index:02d}", None))
    probe = FakeProbe(commands={"wl-copy": "/bin/wl-copy"})
    runner = FakeRunner({"wl-copy": FakeReply()})
    listed = io.StringIO()
    browse_history(paths, "linux", probe, runner, io.StringIO("next\n\n"), listed)
    assert "take-00" in listed.getvalue()
    shown = io.StringIO()
    long = ("alpha " * 30) + "UNIQUE-END"
    append_entry(paths.history_file, dict_entry(long, None))
    browse_history(paths, "linux", probe, runner, io.StringIO("1\n\n"), shown)
    head = shown.getvalue().split("Take")[0]
    assert "UNIQUE-END" in head
    assert "\n" in head
    assert long not in head
    copied = io.StringIO()
    browse_history(paths, "linux", probe, runner, io.StringIO("1\n1\n\n"), copied)
    assert runner.calls[-1].stdin == long
    assert "put this take" not in copied.getvalue()
    assert "/history/copy" in copied.getvalue()
    assert "\n     c\n" in copied.getvalue()


def test_history_delete_removes_one_take(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    append_entry(paths.history_file, dict_entry("keep-me", None))
    append_entry(paths.history_file, dict_entry("drop-me", None))
    probe = FakeProbe(commands={"wl-copy": "/bin/wl-copy"})
    browse_history(
        paths,
        "linux",
        probe,
        FakeRunner({}),
        io.StringIO("1\n2\n\n"),
        io.StringIO(),
    )
    left = [entry.text for entry in read_history(paths.history_file).entries]
    assert left == ["keep-me"]


def test_system_reset_restores_defaults(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    save_settings(paths, VoiceSettings(paste_on_stop=False, stt_model="ggml-tiny.en"))
    out = io.StringIO()
    browse_system(
        paths,
        "linux",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(tmp_path)},
        io.StringIO("3\n1\n\n"),
        out,
    )
    saved = load_settings(paths)
    assert saved.paste_on_stop is True
    assert saved.stt_model == "ggml-base.en"
    assert "settings reset" in out.getvalue()


def test_system_logs_shows_the_whole_file(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    system_log_path(paths).write_text(
        "1000 error whisper failed\n1001 empty nothing heard\n",
        encoding="utf-8",
    )
    out = io.StringIO()
    browse_system(
        paths,
        "linux",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(tmp_path)},
        io.StringIO("6\n\n"),
        out,
    )
    text = out.getvalue()
    assert "whisper failed" in text
    assert "nothing heard" in text
    assert "/system/logs" in text


def test_system_logs_empty_stays_on_the_page(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    out = io.StringIO()
    browse_system(
        paths,
        "linux",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(tmp_path)},
        io.StringIO("6\n\n"),
        out,
    )
    assert "No log yet" in out.getvalue()
    assert "/system/logs" in out.getvalue()


def test_error_status_appends_a_system_log_line(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    StatusReporter(paths.data_dir + "/status.json", "dict", clock_ms=lambda: 1000).update(
        "error", detail="boom"
    )
    StatusReporter(paths.data_dir + "/status.json", "dict", clock_ms=lambda: 1001).update(
        "recording", text="still talking"
    )
    assert system_log_path(paths).read_text(encoding="utf-8") == "1000 error boom\n"


def test_system_update_stays_a_hint(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    out = io.StringIO()
    browse_system(
        paths,
        "linux",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(tmp_path)},
        io.StringIO("5\n\n"),
        out,
    )
    assert "not wired yet" in out.getvalue()

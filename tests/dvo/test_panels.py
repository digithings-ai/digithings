"""Doctor colors, history paging, and the system pane."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from digivoice.history import append_entry, dict_entry
from digivoice.models import DoctorCheck
from digivoice.panels import browse_history, browse_system, present_doctor
from digivoice.paths import resolve_paths
from digivoice.settings import VoiceSettings, load_settings, save_settings

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
    assert "Not ready" in frame
    assert "All set" not in frame


def test_doctor_says_ready_when_required_checks_pass() -> None:
    frame = present_doctor(_required("ok"), io.StringIO(), color=True, pause=0)
    assert "All set. Local speech is ready." in frame
    assert "\x1b[32m" in frame


def test_history_loads_older_takes_and_copies(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    for index in range(10):
        append_entry(paths.history_file, dict_entry(f"take-{index:02d}", None))
    probe = FakeProbe(commands={"wl-copy": "/bin/wl-copy"})
    runner = FakeRunner({"wl-copy": FakeReply()})
    listed = io.StringIO()
    browse_history(paths, "linux", probe, runner, io.StringIO("9\n\n"), listed)
    assert "take-00" in listed.getvalue()
    browse_history(paths, "linux", probe, runner, io.StringIO("1\n1\n\n"), io.StringIO())
    assert runner.calls[-1].stdin == "take-09"


def test_system_reset_restores_defaults(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    save_settings(paths, VoiceSettings(paste_on_stop=False, stt_model="ggml-tiny.en"))
    out = io.StringIO()
    browse_system(
        paths,
        "linux",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(tmp_path)},
        io.StringIO("2\n1\n\n"),
        out,
    )
    saved = load_settings(paths)
    assert saved.paste_on_stop is True
    assert saved.stt_model == "ggml-base.en"
    assert "settings reset" in out.getvalue()


def test_system_update_stays_a_hint(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    out = io.StringIO()
    browse_system(
        paths,
        "linux",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(tmp_path)},
        io.StringIO("4\n\n"),
        out,
    )
    assert "not wired yet" in out.getvalue()

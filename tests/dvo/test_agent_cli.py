"""Agent commands stay on stdout and never open the TUI, even when stdin is a TTY."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from digivoice.cli import Runtime, run
from digivoice.history import append_entry, dict_entry
from digivoice.models import InstallReport, InstallStep

from tests.dvo.fakes import FakeProbe, FakeRunner

pytestmark = pytest.mark.unit


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def _runtime(tmp_path: Path) -> Runtime:
    return Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(),
        runner=FakeRunner(),
    )


def _tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("digivoice.cli.sys.stdin", _Tty(""))


def _refuse_tui(monkeypatch: pytest.MonkeyPatch) -> None:
    def opened(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("opened the TUI")

    monkeypatch.setattr("digivoice.cli.launch_opentui", opened)


def test_logs_prints_the_file_on_a_tty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _tty(monkeypatch)
    _refuse_tui(monkeypatch)
    (tmp_path / "system.log").write_text(
        "1000 error whisper failed\n1001 empty nothing heard\n",
        encoding="utf-8",
    )
    result = run(["logs"], _runtime(tmp_path))
    assert result.code == 0
    assert result.stdout == "1000 error whisper failed\n1001 empty nothing heard\n"
    assert result.stderr == ""


def test_logs_missing_or_blank_says_no_log_yet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _tty(monkeypatch)
    _refuse_tui(monkeypatch)
    missing = run(["logs"], _runtime(tmp_path))
    assert missing.code == 0
    assert missing.stdout == "No log yet\n"
    (tmp_path / "system.log").write_text(" \n\t\n", encoding="utf-8")
    blank = run(["logs"], _runtime(tmp_path))
    assert blank.code == 0
    assert blank.stdout == "No log yet\n"


def test_slash_logs_on_a_tty_still_opens_the_screen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    opened: list[str] = []

    def fake_launch(*_args: object, **kwargs: object) -> int:
        opened.append(str(kwargs.get("start")))
        return 0

    _tty(monkeypatch)
    monkeypatch.setattr("digivoice.cli.launch_opentui", fake_launch)
    (tmp_path / "system.log").write_text("1000 error boom\n", encoding="utf-8")
    result = run(["/system/logs"], _runtime(tmp_path))
    assert result.code == 0
    assert result.stdout == ""
    assert opened == ["/system/logs"]


def test_settings_get_and_set_on_a_tty_do_not_open_the_tui(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _tty(monkeypatch)
    _refuse_tui(monkeypatch)
    runtime = _runtime(tmp_path)
    saved = run(["settings", "set", "paste_on_stop", "false"], runtime)
    assert saved.code == 0
    got = run(["settings", "get", "paste_on_stop"], runtime)
    assert got.code == 0
    assert got.stdout == "false\n"
    before = (tmp_path / "settings.json").read_text(encoding="utf-8")
    unknown = run(["settings", "set", "not_a_key", "1"], runtime)
    assert unknown.code != 0
    assert (tmp_path / "settings.json").read_text(encoding="utf-8") == before
    assert "not_a_key" not in before
    missing = run(["settings", "get", "not_a_key"], runtime)
    assert missing.code != 0
    assert (tmp_path / "settings.json").read_text(encoding="utf-8") == before


def test_history_json_on_a_tty_does_not_open_the_tui(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _tty(monkeypatch)
    _refuse_tui(monkeypatch)
    append_entry(tmp_path / "history.jsonl", dict_entry("ship the notes", None))
    result = run(["history", "--json"], _runtime(tmp_path))
    assert result.code == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["entries"][0]["text"] == "ship the notes"
    assert payload["entries"][0]["kind"] == "dict"


def test_install_auto_on_a_tty_stays_noninteractive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, object] = {}

    def fake_run_install(**kwargs: object) -> InstallReport:
        seen.update(kwargs)
        return InstallReport(steps=[InstallStep(id="stt", status="present", detail="ok")])

    def wizard(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("install wizard")

    _tty(monkeypatch)
    _refuse_tui(monkeypatch)
    monkeypatch.setattr("digivoice.cli.sys.stdin", _Tty("pick\n1\n1\n1\n"))
    monkeypatch.setattr("digivoice.cli.run_install", fake_run_install)
    monkeypatch.setattr("digivoice.cli.run_install_wizard", wizard)
    result = run(["install", "--auto"], _runtime(tmp_path))
    assert result.code == 0
    assert seen["selection"] is None
    assert "cancelled" not in result.stdout

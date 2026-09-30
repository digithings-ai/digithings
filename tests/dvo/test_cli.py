"""CLI stubs and the doctor entrypoint."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from digivoice.cli import Runtime, main, run

from tests.dvo.fakes import FakeProbe

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
RUNTIME = Runtime(
    platform="linux",
    home=Path("/home/chris"),
    env={},
    probe=FakeProbe(),
)
HISTORY = "/home/chris/.local/share/digivoice/history.jsonl"


def test_help_lists_commands() -> None:
    result = run([], RUNTIME)
    assert result.code == 0
    assert "digivoice dict" in result.stdout or "dict" in result.stdout
    assert "speak" in result.stdout
    assert "history" in result.stdout
    assert "doctor" in result.stdout


def test_dict_and_speak_are_stubs() -> None:
    dictate = run(["dict", "--hold"], RUNTIME)
    assert dictate.code == 2
    assert "not implemented yet" in dictate.stderr
    assert "mode: hold" in dictate.stderr
    assert "No audio was captured." in dictate.stderr

    speak = run(["speak", "--clipboard"], RUNTIME)
    assert speak.code == 2
    assert "source: clipboard" in speak.stderr
    assert "No audio was played." in speak.stderr


def test_rejects_bad_args() -> None:
    assert run(["dict", "--hold", "--toggle"], RUNTIME).code == 2
    assert "speak needs text" in run(["speak"], RUNTIME).stderr
    assert run(["history", "--last", "0"], RUNTIME).code == 2
    unknown = run(["nope"], RUNTIME)
    assert unknown.code == 2
    assert "invalid choice" in unknown.stderr or "unknown" in unknown.stderr


def test_history_prints_jsonl_path() -> None:
    result = run(["history", "--last", "20", "--grep", "hello"], RUNTIME)
    assert result.code == 0
    assert f"file: {HISTORY}" in result.stdout
    assert "--last 20" in result.stdout
    assert "--grep hello" in result.stdout


def test_module_doctor_runs(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["DIGIVOICE_DATA_DIR"] = str(tmp_path)
    env["PYTHONPATH"] = str(REPO / "digivoice" / "src")
    proc = subprocess.run(
        [sys.executable, "-m", "digivoice", "doctor"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "digivoice doctor" in proc.stdout
    assert "ggml-base.en" in proc.stdout
    assert "whisper-cli" in proc.stdout
    assert "result: not ready" in proc.stdout


def test_main_returns_doctor_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DIGIVOICE_DATA_DIR", str(tmp_path))
    code = main(["doctor"])
    captured = capsys.readouterr()
    assert code == 1
    assert "digivoice doctor" in captured.out

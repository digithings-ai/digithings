"""CLI: doctor, the live dict pipeline, speak, and history."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from digivoice.cli import Runtime, main, run
from digivoice.history import append_entry, dict_entry
from digivoice.probe import real_probe

from tests.dvo.fakes import FakeProbe, FakeReply, FakeRunner, writes_wav

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
RUNTIME = Runtime(
    platform="linux",
    home=Path("/home/chris"),
    env={},
    probe=FakeProbe(),
)
HISTORY = "/home/chris/.local/share/digivoice/history.jsonl"
TRANSCRIPT = "ship it."

# Two small fake binaries. Neither opens a device or loads a model.
FAKE_SOX = """#!/bin/sh
for arg in "$@"; do
  case "$arg" in
    *.wav) out="$arg"; break ;;
  esac
done
[ -n "$out" ] || exit 2
printf 'RIFF0000WAVEfmt ' > "$out"
exit 0
"""

FAKE_WHISPER = """#!/bin/sh
printf '[00:00:00.000 --> 00:00:01.200]   ship it.\\n'
"""


def _fake_bin(tmp_path: Path, name: str, script: str) -> str:
    binary = tmp_path / name
    binary.write_text(script, encoding="utf-8")
    binary.chmod(0o755)
    return str(binary)


def _dict_runtime(
    tmp_path: Path,
    *,
    platform: str = "linux",
    runner: FakeRunner | None = None,
    commands: dict[str, str] | None = None,
) -> Runtime:
    models = tmp_path / "models"
    models.mkdir(parents=True, exist_ok=True)
    (models / "ggml-base.en.bin").write_bytes(b"fake weights")
    resolved = {"sox": _fake_bin(tmp_path, "sox", FAKE_SOX)}
    resolved["whisper-cli"] = _fake_bin(tmp_path, "whisper-cli", FAKE_WHISPER)
    if commands:
        resolved.update(commands)
    return Runtime(
        platform=platform,
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(commands=resolved),
        runner=runner
        or FakeRunner({"sox": writes_wav(), "whisper-cli": FakeReply(stdout=TRANSCRIPT)}),
    )


def test_help_lists_commands() -> None:
    result = run([], RUNTIME)
    assert result.code == 0
    assert "dict" in result.stdout
    assert "speak" in result.stdout
    assert "history" in result.stdout
    assert "doctor" in result.stdout


def test_rejects_bad_args() -> None:
    assert run(["dict", "--hold", "--toggle"], RUNTIME).code == 2
    assert "speak needs text" in run(["speak"], RUNTIME).stderr
    assert run(["speak", "--clipboard", "--selection"], RUNTIME).code == 2
    assert run(["history", "--last", "0"], RUNTIME).code == 2
    assert "--grep expects a pattern" in run(["history", "--grep", ""], RUNTIME).stderr
    assert "--seconds expects a positive integer" in run(["dict", "--seconds", "0"], RUNTIME).stderr
    unknown = run(["nope"], RUNTIME)
    assert unknown.code == 2
    assert "invalid choice" in unknown.stderr or "unknown" in unknown.stderr


def test_dict_records_transcribes_and_appends(tmp_path: Path) -> None:
    runtime = _dict_runtime(tmp_path)
    result = run(["dict", "--hold"], runtime)
    assert result.code == 0
    # stdout is the transcript alone so it can be piped.
    assert result.stdout == f"{TRANSCRIPT}\n"
    assert "sox" in result.stderr
    assert "ggml-base.en" in result.stderr
    assert "macOS only" in result.stderr

    lines = (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["kind"] == "dict"
    assert entry["text"] == TRANSCRIPT
    assert entry["ts"].endswith("Z")
    wav = Path(entry["wav"])
    assert wav.is_file()
    assert wav.parent == tmp_path / "recordings"


def test_dict_keeps_stdout_clean_when_paste_is_denied(tmp_path: Path) -> None:
    denied = FakeReply(code=1, stderr="Not allowed assistive access. (-25211)")
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": FakeReply(stdout=TRANSCRIPT),
            "pbcopy": FakeReply(),
            "osascript": denied,
        }
    )
    runtime = _dict_runtime(
        tmp_path,
        platform="darwin",
        runner=runner,
        commands={"pbcopy": "/usr/bin/pbcopy", "osascript": "/usr/bin/osascript"},
    )
    result = run(["dict"], runtime)
    assert result.code == 0
    assert result.stdout == f"{TRANSCRIPT}\n"
    assert "Accessibility" in result.stderr
    # Dictation still recorded its history entry.
    assert len((tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_dict_no_paste_skips_the_clipboard(tmp_path: Path) -> None:
    runner = FakeRunner({"sox": writes_wav(), "whisper-cli": FakeReply(stdout=TRANSCRIPT)})
    runtime = _dict_runtime(
        tmp_path,
        platform="darwin",
        runner=runner,
        commands={"pbcopy": "/usr/bin/pbcopy", "osascript": "/usr/bin/osascript"},
    )
    result = run(["dict", "--no-paste"], runtime)
    assert result.code == 0
    assert "--no-paste" in result.stderr
    assert runner.programs == ["sox", "whisper-cli"]


def test_dict_without_capture_tools_fails_soft(tmp_path: Path) -> None:
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(commands={"whisper-cli": "/usr/bin/whisper-cli"}),
        runner=FakeRunner(),
    )
    result = run(["dict"], runtime)
    assert result.code == 1
    assert "digivoice dict:" in result.stderr
    assert "sox or ffmpeg" in result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "history.jsonl").exists()


def test_dict_keeps_the_wav_when_whisper_fails(tmp_path: Path) -> None:
    runner = FakeRunner(
        {"sox": writes_wav(), "whisper-cli": FakeReply(code=1, stderr="failed to open wav")}
    )
    runtime = _dict_runtime(tmp_path, runner=runner)
    result = run(["dict"], runtime)
    assert result.code == 1
    assert "failed to open wav" in result.stderr
    assert "audio kept at" in result.stderr
    assert not (tmp_path / "history.jsonl").exists()


def test_dict_end_to_end_through_real_subprocesses(tmp_path: Path) -> None:
    """Fake sox and whisper-cli on a PATH dir, executed for real, no injection."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_bin(bin_dir, "sox", FAKE_SOX)
    _fake_bin(bin_dir, "whisper-cli", FAKE_WHISPER)
    models = tmp_path / "models"
    models.mkdir()
    (models / "ggml-base.en.bin").write_bytes(b"fake weights")
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=real_probe(str(bin_dir)),
    )
    result = run(["dict", "--toggle", "--seconds", "5"], runtime)
    assert result.code == 0
    assert result.stdout == f"{TRANSCRIPT}\n"
    entry = json.loads((tmp_path / "history.jsonl").read_text(encoding="utf-8"))
    assert entry["text"] == TRANSCRIPT
    assert Path(entry["wav"]).is_file()


def test_history_without_a_file_exits_zero() -> None:
    result = run(["history"], RUNTIME)
    assert result.code == 0
    assert f"file: {HISTORY}" in result.stdout
    assert "no history file yet" in result.stdout


def test_history_lists_appended_entries(tmp_path: Path) -> None:
    history_file = tmp_path / "history.jsonl"
    append_entry(history_file, dict_entry("ship it", str(tmp_path / "a.wav")))
    append_entry(history_file, dict_entry("hold on", None))
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(),
    )
    result = run(["history"], runtime)
    assert result.code == 0
    assert "2 of 2 entries" in result.stdout
    assert "dict  ship it" in result.stdout
    assert "dict  hold on" in result.stdout

    last = run(["history", "--last", "1"], runtime)
    assert "1 of 2 entries" in last.stdout
    assert "ship it" not in last.stdout
    assert "hold on" in last.stdout

    grep = run(["history", "--grep", "SHIP"], runtime)
    assert "1 of 2 entries" in grep.stdout
    assert "ship it" in grep.stdout
    assert "hold on" not in grep.stdout

    empty = run(["history", "--grep", "absent"], runtime)
    assert empty.code == 0
    assert "no matching entries" in empty.stdout


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

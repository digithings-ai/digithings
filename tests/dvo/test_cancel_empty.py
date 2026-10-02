"""Esc cancel (cancel-file) and empty-take discard: nothing saved, nothing pasted."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from digivoice.cli import Runtime, run
from digivoice.paths import resolve_paths
from digivoice.probe import real_probe
from digivoice.runner import CANCELLED_CODE, cancellable_runner, run_command
from digivoice.settings import VoiceSettings, save_settings
from digivoice.status import CANCELLED_EXIT, StatusReporter, read_status

from tests.dvo.fakes import FakeCall, FakeProbe, FakeReply, FakeRunner, writes_wav

pytestmark = pytest.mark.unit

TRANSCRIPT = "ship it."
DARWIN_TOOLS = {"pbcopy": "/usr/bin/pbcopy", "osascript": "/usr/bin/osascript"}
PASTE_PROGRAMS = {"pbcopy", "osascript"}

# Open-ended recorder: writes the wav header, then records until SIGINT.
LONG_SOX = """#!/bin/sh
for arg in "$@"; do
  case "$arg" in
    *.wav) out="$arg"; break ;;
  esac
done
[ -n "$out" ] || exit 2
printf 'RIFF0000WAVEfmt ' > "$out"
exec sleep 30
"""
SLOW_WHISPER = """#!/bin/sh
exec sleep 30
"""
INSTANT_SOX = """#!/bin/sh
for arg in "$@"; do
  case "$arg" in
    *.wav) out="$arg"; break ;;
  esac
done
printf 'RIFF0000WAVEfmt ' > "$out"
"""
SPEECH_WHISPER = """#!/bin/sh
printf '[00:00:00.000 --> 00:00:01.200]   ship it.\\n'
"""


def _fake_bin(directory: Path, name: str, script: str) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory / name
    binary.write_text(script, encoding="utf-8")
    binary.chmod(0o755)
    return str(binary)


def _runtime(
    tmp_path: Path,
    runner: FakeRunner,
    *,
    platform: str = "darwin",
    rewrite_runner: object | None = None,
) -> Runtime:
    models = tmp_path / "models"
    models.mkdir(parents=True, exist_ok=True)
    (models / "ggml-base.en.bin").write_bytes(b"fake weights")
    commands = {
        "sox": _fake_bin(tmp_path / "bin", "sox", INSTANT_SOX),
        "whisper-cli": _fake_bin(tmp_path / "bin", "whisper-cli", SPEECH_WHISPER),
        **DARWIN_TOOLS,
    }
    return Runtime(
        platform=platform,
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(commands=commands),
        runner=runner,
        rewrite_runner=rewrite_runner,
    )


def _request_cancel_when(tmp_path: Path, reply: FakeReply):
    """A responder that behaves like the real tool, then 'presses Esc'."""

    def _respond(call: FakeCall) -> FakeReply:
        (tmp_path / "dict.cancel").write_text("cancel\n", encoding="utf-8")
        return reply

    return _respond


def _recorded_wavs(tmp_path: Path) -> list[Path]:
    return list((tmp_path / "recordings").glob("*.wav"))


def _assert_nothing_left(tmp_path: Path, runner: FakeRunner) -> None:
    assert not (tmp_path / "history.jsonl").exists()
    assert _recorded_wavs(tmp_path) == []
    assert not PASTE_PROGRAMS & set(runner.programs)
    assert not (tmp_path / "dict.cancel").exists()


def test_cancel_during_recording_discards_the_take(tmp_path: Path) -> None:
    def sox(call: FakeCall) -> FakeReply:
        writes_wav()(call)
        (tmp_path / "dict.cancel").write_text("cancel\n", encoding="utf-8")
        return FakeReply()

    runner = FakeRunner({"sox": sox, "whisper-cli": FakeReply(stdout=TRANSCRIPT)})
    result = run(["dict", "--hold"], _runtime(tmp_path, runner))
    assert result.code == CANCELLED_EXIT
    assert result.stdout == ""
    assert "cancelled" in result.stderr
    assert "whisper-cli" not in runner.programs
    _assert_nothing_left(tmp_path, runner)
    snapshot = read_status(tmp_path / "status.json")
    assert snapshot is not None and snapshot.state == "cancelled"


def test_cancel_during_transcribe_discards_the_take(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": _request_cancel_when(tmp_path, FakeReply(stdout=TRANSCRIPT)),
        }
    )
    result = run(["dict", "--hold"], _runtime(tmp_path, runner))
    assert result.code == CANCELLED_EXIT
    assert result.stdout == ""
    _assert_nothing_left(tmp_path, runner)


def test_cancel_during_transcribe_failure_is_still_a_cancel(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": _request_cancel_when(tmp_path, FakeReply(code=130, stderr="cancelled")),
        }
    )
    result = run(["dict", "--hold"], _runtime(tmp_path, runner))
    assert result.code == CANCELLED_EXIT
    assert "audio kept" not in result.stderr
    _assert_nothing_left(tmp_path, runner)


class CancellingRewrite:
    name = "fake"

    def __init__(self, tmp_path: Path) -> None:
        self._tmp_path = tmp_path

    def available(self) -> bool:
        return True

    def rewrite(self, system: str, user: str, *, timeout: float) -> str:
        (self._tmp_path / "dict.cancel").write_text("cancel\n", encoding="utf-8")
        return "REWRITTEN"


def test_cancel_during_rewrite_discards_the_take(tmp_path: Path) -> None:
    paths = resolve_paths("darwin", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    save_settings(paths, VoiceSettings(rewrite_enabled=True, rewrite_preset="email"))
    runner = FakeRunner({"sox": writes_wav(), "whisper-cli": FakeReply(stdout=TRANSCRIPT)})
    runtime = _runtime(tmp_path, runner, rewrite_runner=CancellingRewrite(tmp_path))
    result = run(["dict", "--hold"], runtime)
    assert result.code == CANCELLED_EXIT
    assert result.stdout == ""
    _assert_nothing_left(tmp_path, runner)


def test_cancel_arriving_just_before_the_history_append_still_discards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_update = StatusReporter.update

    def update(self: StatusReporter, state: str, **kwargs: str) -> None:
        real_update(self, state, **kwargs)  # type: ignore[arg-type]
        if state == "pasting":
            (tmp_path / "dict.cancel").write_text("cancel\n", encoding="utf-8")

    monkeypatch.setattr(StatusReporter, "update", update)
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": FakeReply(stdout=TRANSCRIPT),
            "pbcopy": FakeReply(),
            "osascript": FakeReply(),
        }
    )
    result = run(["dict", "--hold"], _runtime(tmp_path, runner))
    assert result.code == CANCELLED_EXIT
    _assert_nothing_left(tmp_path, runner)


def test_stale_cancel_file_does_not_cancel_the_next_take(tmp_path: Path) -> None:
    (tmp_path / "dict.cancel").write_text("cancel\n", encoding="utf-8")
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": FakeReply(stdout=TRANSCRIPT),
            "pbcopy": FakeReply(),
            "osascript": FakeReply(),
        }
    )
    result = run(["dict", "--hold"], _runtime(tmp_path, runner))
    assert result.code == 0
    assert result.stdout == f"{TRANSCRIPT}\n"
    assert len((tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_custom_cancel_file_flag(tmp_path: Path) -> None:
    custom = tmp_path / "elsewhere" / "stop-now"

    def sox(call: FakeCall) -> FakeReply:
        writes_wav()(call)
        custom.parent.mkdir(parents=True, exist_ok=True)
        custom.write_text("cancel\n", encoding="utf-8")
        return FakeReply()

    runner = FakeRunner({"sox": sox})
    result = run(["dict", "--hold", "--cancel-file", str(custom)], _runtime(tmp_path, runner))
    assert result.code == CANCELLED_EXIT
    assert not custom.exists()


@pytest.mark.parametrize("whisper_out", ["[BLANK_AUDIO]", "", "  \n", "[ Silence ]", "(silence)"])
def test_empty_stt_never_pastes_or_logs_a_blank(tmp_path: Path, whisper_out: str) -> None:
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": FakeReply(stdout=whisper_out),
            "pbcopy": FakeReply(),
            "osascript": FakeReply(),
        }
    )
    result = run(["dict", "--hold"], _runtime(tmp_path, runner))
    assert result.code == 1
    assert result.stdout == ""
    assert "take discarded" in result.stderr
    assert "no paste, no history entry" in result.stderr
    _assert_nothing_left(tmp_path, runner)
    snapshot = read_status(tmp_path / "status.json")
    assert snapshot is not None and snapshot.state == "empty"


def test_blank_rewrite_output_falls_back_to_the_raw_transcript(tmp_path: Path) -> None:
    class BlankRewrite:
        name = "fake"

        def available(self) -> bool:
            return True

        def rewrite(self, system: str, user: str, *, timeout: float) -> str:
            return "   "

    paths = resolve_paths("darwin", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    save_settings(paths, VoiceSettings(rewrite_enabled=True))
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": FakeReply(stdout=TRANSCRIPT),
            "pbcopy": FakeReply(),
            "osascript": FakeReply(),
        }
    )
    result = run(["dict", "--hold"], _runtime(tmp_path, runner, rewrite_runner=BlankRewrite()))
    assert result.code == 0
    assert result.stdout == f"{TRANSCRIPT}\n"


def test_status_tracks_a_successful_take(tmp_path: Path) -> None:
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": FakeReply(stdout=TRANSCRIPT),
            "pbcopy": FakeReply(),
            "osascript": FakeReply(),
        }
    )
    result = run(["dict", "--hold"], _runtime(tmp_path, runner))
    assert result.code == 0
    snapshot = read_status(tmp_path / "status.json")
    assert snapshot is not None
    assert (snapshot.kind, snapshot.state, snapshot.text) == ("dict", "done", TRANSCRIPT)
    assert "pasted" in snapshot.detail


def test_live_banner_off_writes_no_status_file(tmp_path: Path) -> None:
    paths = resolve_paths("darwin", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})
    save_settings(paths, VoiceSettings(live_banner=False))
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": FakeReply(stdout=TRANSCRIPT),
            "pbcopy": FakeReply(),
            "osascript": FakeReply(),
        }
    )
    assert run(["dict", "--hold"], _runtime(tmp_path, runner)).code == 0
    assert not (tmp_path / "status.json").exists()


def test_unwritable_status_never_fails_the_take(tmp_path: Path) -> None:
    (tmp_path / "status.json").mkdir()  # a directory where the file should go
    runner = FakeRunner(
        {
            "sox": writes_wav(),
            "whisper-cli": FakeReply(stdout=TRANSCRIPT),
            "pbcopy": FakeReply(),
            "osascript": FakeReply(),
        }
    )
    result = run(["dict", "--hold"], _runtime(tmp_path, runner))
    assert result.code == 0
    assert result.stdout == f"{TRANSCRIPT}\n"


def test_cancel_command_creates_the_cancel_file(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, FakeRunner())
    result = run(["cancel"], runtime)
    assert result.code == 0
    assert (tmp_path / "dict.cancel").is_file()
    assert result.stdout.strip() == str(tmp_path / "dict.cancel")


def test_status_command(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, FakeRunner())
    assert run(["status"], runtime).code == 1
    runner = FakeRunner({"sox": writes_wav(), "whisper-cli": FakeReply(stdout=TRANSCRIPT)})
    run(["dict", "--hold", "--no-paste"], _runtime(tmp_path, runner))
    shown = run(["status"], runtime)
    assert shown.code == 0
    assert json.loads(shown.stdout)["state"] == "done"


def test_speak_reports_the_selected_text(tmp_path: Path) -> None:
    models = tmp_path / "models"
    models.mkdir()
    (models / "voice.onnx").write_bytes(b"onnx")
    seen: list[str] = []

    def piper(call: FakeCall) -> FakeReply:
        snapshot = read_status(tmp_path / "status.json")
        assert snapshot is not None
        seen.append(f"{snapshot.kind}:{snapshot.state}:{snapshot.text}")
        wav = next(Path(part) for part in call.argv if part.endswith(".wav"))
        wav.write_bytes(b"RIFF")
        return FakeReply()

    runner = FakeRunner({"piper": piper})
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(
            commands={"piper": "/usr/bin/piper", "aplay": "/usr/bin/aplay"},
            directories={str(models)},
        ),
        runner=runner,
    )
    result = run(["speak", "read", "me"], runtime)
    assert result.code == 0
    assert seen == ["speak:speaking:read me"]
    final = read_status(tmp_path / "status.json")
    assert final is not None and (final.state, final.text) == ("done", "read me")


def test_speak_failure_reaches_the_banner(tmp_path: Path) -> None:
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(),
        runner=FakeRunner(),
    )
    result = run(["speak", "--selection"], runtime)
    assert result.code == 1
    snapshot = read_status(tmp_path / "status.json")
    assert snapshot is not None and snapshot.state == "error"
    assert snapshot.detail


# --- real subprocesses -------------------------------------------------------


def _cancel_after(path: Path, delay: float) -> threading.Thread:
    def _go() -> None:
        time.sleep(delay)
        path.write_text("cancel\n", encoding="utf-8")

    thread = threading.Thread(target=_go)
    thread.start()
    return thread


def _real_runtime(tmp_path: Path, sox: str, whisper: str) -> Runtime:
    bin_dir = tmp_path / "bin"
    _fake_bin(bin_dir, "sox", sox)
    _fake_bin(bin_dir, "whisper-cli", whisper)
    models = tmp_path / "models"
    models.mkdir()
    (models / "ggml-base.en.bin").write_bytes(b"fake weights")
    return Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=real_probe(str(bin_dir)),
        runner=run_command,
    )


def test_real_recorder_is_stopped_and_its_wav_deleted_on_cancel(tmp_path: Path) -> None:
    runtime = _real_runtime(tmp_path, LONG_SOX, SPEECH_WHISPER)
    thread = _cancel_after(tmp_path / "dict.cancel", 0.4)
    started = time.monotonic()
    result = run(["dict", "--toggle", "--seconds", "20"], runtime)
    thread.join()
    assert time.monotonic() - started < 10
    assert result.code == CANCELLED_EXIT
    assert _recorded_wavs(tmp_path) == []
    assert not (tmp_path / "history.jsonl").exists()


def test_real_whisper_is_killed_and_nothing_saved_on_cancel(tmp_path: Path) -> None:
    runtime = _real_runtime(tmp_path, INSTANT_SOX, SLOW_WHISPER)
    thread = _cancel_after(tmp_path / "dict.cancel", 0.6)
    started = time.monotonic()
    result = run(["dict", "--toggle", "--seconds", "5"], runtime)
    thread.join()
    assert time.monotonic() - started < 10
    assert result.code == CANCELLED_EXIT
    assert _recorded_wavs(tmp_path) == []
    assert not (tmp_path / "history.jsonl").exists()


def test_cancellable_runner_kills_the_child_and_reports_cancelled(tmp_path: Path) -> None:
    flag = tmp_path / "flag"
    thread = _cancel_after(flag, 0.3)
    runner = cancellable_runner(run_command, flag.exists)
    started = time.monotonic()
    result = runner(["sleep", "20"], timeout=30)
    thread.join()
    assert result.code == CANCELLED_CODE
    assert time.monotonic() - started < 5


def test_cancellable_runner_passes_stdin_and_output_through(tmp_path: Path) -> None:
    runner = cancellable_runner(run_command, lambda: False)
    result = runner(["cat"], stdin="hello there", timeout=5)
    assert (result.code, result.stdout) == (0, "hello there")
    missing = runner(["definitely-not-a-binary-xyz"], timeout=5)
    assert missing.code == 127
    slow = runner(["sleep", "5"], timeout=0.3)
    assert slow.code == 124


def test_cancellable_runner_leaves_injected_runners_alone() -> None:
    fake = FakeRunner()
    assert cancellable_runner(fake, lambda: True) is fake

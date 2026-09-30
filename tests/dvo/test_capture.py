"""Microphone capture: tool preference, argv shape, and failing soft."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from digivoice.capture import (
    BITS,
    CHANNELS,
    DEFAULT_HOLD_SECONDS,
    DEFAULT_TOGGLE_SECONDS,
    SAMPLE_RATE,
    capture_argv,
    mode_seconds,
    record,
    recording_path,
    select_tool,
)
from digivoice.errors import CaptureError
from digivoice.models import VoicePaths
from digivoice.paths import resolve_paths

from tests.dvo.fakes import FakeProbe, FakeReply, FakeRunner, writes_wav

pytestmark = pytest.mark.unit


@pytest.fixture
def paths(tmp_path: Path) -> VoicePaths:
    return resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})


def test_mode_seconds_cap_each_mode() -> None:
    assert mode_seconds("hold") == DEFAULT_HOLD_SECONDS
    assert mode_seconds("toggle") == DEFAULT_TOGGLE_SECONDS
    assert mode_seconds("default") > DEFAULT_HOLD_SECONDS


def test_sox_preferred_over_ffmpeg() -> None:
    probe = FakeProbe(commands={"sox": "/usr/bin/sox", "ffmpeg": "/usr/bin/ffmpeg"})
    assert select_tool(probe) == ("sox", "/usr/bin/sox")


def test_ffmpeg_covers_for_sox() -> None:
    assert select_tool(FakeProbe(commands={"ffmpeg": "/usr/bin/ffmpeg"})) == (
        "ffmpeg",
        "/usr/bin/ffmpeg",
    )


def test_no_capture_tool_when_neither_is_on_path() -> None:
    assert select_tool(FakeProbe(commands={"whisper-cli": "/usr/bin/whisper-cli"})) is None


def test_sox_argv_is_16k_mono_and_self_bounding() -> None:
    argv = capture_argv("sox", "/usr/bin/sox", Path("/tmp/a.wav"), 15, "darwin")
    assert argv[0] == "/usr/bin/sox"
    assert str(SAMPLE_RATE) in argv
    assert str(CHANNELS) in argv
    assert str(BITS) in argv
    assert "/tmp/a.wav" in argv
    # `rec … trim 0 N` closes the file at N seconds instead of being killed.
    assert argv[argv.index("rec") :] == ["rec", "trim", "0", "15"]


def test_ffmpeg_argv_bounds_the_clip_and_targets_the_mac_mic() -> None:
    argv = capture_argv("ffmpeg", "/usr/bin/ffmpeg", Path("/tmp/b.wav"), 30, "darwin")
    assert argv[0] == "/usr/bin/ffmpeg"
    assert "avfoundation" in argv
    assert argv[argv.index("-t") + 1] == "30"
    assert argv[-1] == "/tmp/b.wav"


def test_ffmpeg_on_linux_uses_alsa() -> None:
    argv = capture_argv("ffmpeg", "/usr/bin/ffmpeg", Path("/tmp/b.wav"), 30, "linux")
    assert "alsa" in argv


def test_unknown_capture_tool_is_rejected() -> None:
    with pytest.raises(CaptureError):
        capture_argv("rec", "/usr/bin/rec", Path("/tmp/c.wav"), 5, "darwin")


def test_recording_path_is_timestamped_under_the_data_dir(paths: VoicePaths) -> None:
    wav = recording_path(paths, datetime(2026, 9, 30, 12, 0, tzinfo=UTC))
    assert wav.parent == Path(paths.recordings_dir)
    assert wav.parent == Path(paths.data_dir) / "recordings"
    assert wav.name.startswith("dict-20260930T120000Z-")
    assert wav.suffix == ".wav"


def test_record_writes_a_wav_and_returns_the_path(paths: VoicePaths) -> None:
    runner = FakeRunner({"sox": writes_wav()})
    result = record(paths, FakeProbe(commands={"sox": "/usr/bin/sox"}), runner, mode="hold")
    assert result.tool == "sox"
    assert result.seconds == DEFAULT_HOLD_SECONDS
    assert Path(result.wav_path).is_file()
    assert runner.call_for("sox") is not None
    assert result.argv[0] == "/usr/bin/sox"


def test_record_honors_an_explicit_second_cap(paths: VoicePaths) -> None:
    result = record(
        paths,
        FakeProbe(commands={"sox": "/usr/bin/sox"}),
        FakeRunner({"sox": writes_wav()}),
        seconds=3,
    )
    assert result.seconds == 3
    assert result.argv[-1] == "3"


def test_record_falls_back_to_ffmpeg(paths: VoicePaths) -> None:
    result = record(
        paths,
        FakeProbe(commands={"ffmpeg": "/usr/bin/ffmpeg"}),
        FakeRunner({"ffmpeg": writes_wav()}),
    )
    assert result.tool == "ffmpeg"


def test_record_without_a_capture_tool_fails_soft(paths: VoicePaths) -> None:
    with pytest.raises(CaptureError) as excinfo:
        record(paths, FakeProbe(), FakeRunner(), platform="linux")
    assert "sox or ffmpeg" in str(excinfo.value)


def test_record_reports_the_recorder_stderr(paths: VoicePaths) -> None:
    runner = FakeRunner({"sox": FakeReply(code=1, stderr="sox FAIL formats: can't open input")})
    with pytest.raises(CaptureError) as excinfo:
        record(paths, FakeProbe(commands={"sox": "/usr/bin/sox"}), runner, platform="linux")
    assert "can't open input" in str(excinfo.value)


def test_record_rejects_a_recorder_that_wrote_nothing(paths: VoicePaths) -> None:
    runner = FakeRunner({"sox": FakeReply()})
    with pytest.raises(CaptureError) as excinfo:
        record(paths, FakeProbe(commands={"sox": "/usr/bin/sox"}), runner, platform="linux")
    assert "wrote no audio" in str(excinfo.value)


def test_record_bounds_the_recorder_with_a_timeout(paths: VoicePaths) -> None:
    runner = FakeRunner({"sox": writes_wav()})
    record(paths, FakeProbe(commands={"sox": "/usr/bin/sox"}), runner, seconds=15)
    assert runner.calls[0].timeout is not None

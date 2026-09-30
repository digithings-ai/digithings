"""Microphone to wav. sox first, then ffmpeg. No shell, no hang.

whisper.cpp wants 16 kHz mono 16-bit, so capture there once and let the recorder
bound itself: `sox … rec trim 0 N` and `ffmpeg … -t N` both close the file
normally at N seconds, which keeps the wav header valid instead of leaving a
truncated file behind when a cap is hit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from digivoice.errors import CaptureError
from digivoice.models import CaptureResult, VoicePaths
from digivoice.probe import CommandProbe
from digivoice.runner import CommandRunner, error_tail

SAMPLE_RATE = 16000
CHANNELS = 1
BITS = 16
# Caps keep a stuck microphone from hanging the CLI. The hold cap is the
# push-to-talk length; toggle gets room for a full sentence.
DEFAULT_HOLD_SECONDS = 15
DEFAULT_TOGGLE_SECONDS = 60
DEFAULT_SECONDS = 30
# Slack past the cap so the recorder can close the file before we call it hung.
_TIMEOUT_SLACK = 10.0
CAPTURE_TOOLS = ("sox", "ffmpeg")


def mode_seconds(mode: str) -> int:
    if mode == "hold":
        return DEFAULT_HOLD_SECONDS
    if mode == "toggle":
        return DEFAULT_TOGGLE_SECONDS
    return DEFAULT_SECONDS


def default_input(platform: str) -> list[str]:
    if platform == "darwin":
        return ["-f", "avfoundation", "-i", ":0"]
    return ["-f", "alsa", "-i", "default"]


def capture_argv(tool: str, binary: str, wav: Path, seconds: int, platform: str) -> list[str]:
    if tool == "sox":
        return [
            binary,
            "-q",
            "-d",
            "-r",
            str(SAMPLE_RATE),
            "-c",
            str(CHANNELS),
            "-b",
            str(BITS),
            str(wav),
            "rec",
            "trim",
            "0",
            str(seconds),
        ]
    if tool == "ffmpeg":
        return [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            *default_input(platform),
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            str(CHANNELS),
            "-t",
            str(seconds),
            "-y",
            str(wav),
        ]
    raise CaptureError(f"unknown capture tool: {tool}")


def select_tool(probe: CommandProbe) -> tuple[str, str] | None:
    """sox wins over ffmpeg; both are what `doctor` calls capture."""
    for tool in CAPTURE_TOOLS:
        found = probe.lookup(tool)
        if found:
            return tool, found
    return None


def recording_path(paths: VoicePaths, now: datetime) -> Path:
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path(paths.recordings_dir) / f"dict-{stamp}-{uuid4().hex[:8]}.wav"


def record(
    paths: VoicePaths,
    probe: CommandProbe,
    runner: CommandRunner,
    *,
    mode: str = "default",
    seconds: int | None = None,
    platform: str = "darwin",
) -> CaptureResult:
    """Record `seconds` of microphone audio to a wav under the data directory."""
    selected = select_tool(probe)
    if selected is None:
        raise CaptureError("no capture tool on PATH: need sox or ffmpeg to record the microphone")
    tool, binary = selected
    limit = mode_seconds(mode) if seconds is None else seconds
    wav = recording_path(paths, datetime.now(tz=UTC))
    wav.parent.mkdir(parents=True, exist_ok=True)
    argv = capture_argv(tool, binary, wav, limit, platform)
    result = runner(argv, timeout=limit + _TIMEOUT_SLACK)
    if result.code != 0:
        reason = error_tail(result.stderr) or f"exit {result.code}"
        raise CaptureError(f"{tool} could not record the microphone ({reason})")
    if not wav.is_file():
        raise CaptureError(f"{tool} exited 0 but wrote no audio: {wav}")
    return CaptureResult(wav_path=str(wav), tool=tool, seconds=limit, argv=list(argv))

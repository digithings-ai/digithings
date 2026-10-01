"""Microphone to wav. sox first, then ffmpeg. No shell, no hang.

whisper.cpp wants 16 kHz mono 16-bit, so capture there once. Hold / default
modes bound themselves with `sox … rec trim 0 N` and `ffmpeg … -t N`. Toggle
mode can stop early on SIGINT/SIGTERM or a stop-file so a hotkey adapter
(Hammerspoon) can press-to-start / press-to-stop without waiting out the cap.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from digivoice.errors import CaptureError
from digivoice.models import CaptureResult, VoicePaths
from digivoice.probe import CommandProbe
from digivoice.runner import CommandRunner, error_tail, run_command

SAMPLE_RATE = 16000
CHANNELS = 1
BITS = 16
# Caps keep a stuck microphone from hanging the CLI. The hold cap is the
# push-to-talk length; toggle gets room for a full sentence (or until stop).
DEFAULT_HOLD_SECONDS = 15
DEFAULT_TOGGLE_SECONDS = 60
DEFAULT_SECONDS = 30
# Slack past the cap so the recorder can close the file before we call it hung.
_TIMEOUT_SLACK = 10.0
# How often to poll the stop-file / child exit while recording.
_POLL_INTERVAL = 0.05
# Grace after SIGINT before escalating to SIGTERM / SIGKILL.
_SIGINT_GRACE = 1.5
_SIGTERM_GRACE = 1.0
CAPTURE_TOOLS = ("sox", "ffmpeg")
# Default stop-file name under the digivoice data directory (toggle mode).
DEFAULT_STOP_FILE_NAME = "dict.stop"


def mode_seconds(mode: str) -> int:
    if mode == "hold":
        return DEFAULT_HOLD_SECONDS
    if mode == "toggle":
        return DEFAULT_TOGGLE_SECONDS
    return DEFAULT_SECONDS


def default_stop_file(paths: VoicePaths) -> Path:
    return Path(paths.data_dir) / DEFAULT_STOP_FILE_NAME


def default_input(platform: str) -> list[str]:
    if platform == "darwin":
        return ["-f", "avfoundation", "-i", ":0"]
    return ["-f", "alsa", "-i", "default"]


def capture_argv(
    tool: str,
    binary: str,
    wav: Path,
    seconds: int,
    platform: str,
    *,
    unbounded: bool = False,
) -> list[str]:
    """Build recorder argv. `unbounded` omits the time cap for early-stop toggle."""
    if tool == "sox":
        argv = [
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
        ]
        if not unbounded:
            argv.extend(["rec", "trim", "0", str(seconds)])
        return argv
    if tool == "ffmpeg":
        argv = [
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
        ]
        if not unbounded:
            argv.extend(["-t", str(seconds)])
        argv.extend(["-y", str(wav)])
        return argv
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


def _clear_stop_file(stop_file: Path) -> None:
    try:
        stop_file.unlink(missing_ok=True)
    except OSError:
        pass


def _stop_requested(stop_file: Path | None, flag: list[bool]) -> bool:
    if flag and flag[0]:
        return True
    if stop_file is not None and stop_file.exists():
        return True
    return False


def _terminate_recorder(proc: subprocess.Popen[str]) -> None:
    """Ask the recorder process group to finish the wav, then escalate."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGINT)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.send_signal(signal.SIGINT)
        except (ProcessLookupError, OSError):
            return
    deadline = time.monotonic() + _SIGINT_GRACE
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL)
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.terminate()
        except (ProcessLookupError, OSError):
            return
    deadline = time.monotonic() + _SIGTERM_GRACE
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass
        proc.wait(timeout=2.0)


def _record_early_stop(
    tool: str,
    binary: str,
    wav: Path,
    limit: int,
    platform: str,
    stop_file: Path | None,
) -> CaptureResult:
    """Record until stop-file / SIGINT / SIGTERM, or the safety cap."""
    argv = capture_argv(tool, binary, wav, limit, platform, unbounded=True)
    if stop_file is not None:
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        _clear_stop_file(stop_file)

    stop_flag: list[bool] = [False]
    previous_int = signal.getsignal(signal.SIGINT)
    previous_term = signal.getsignal(signal.SIGTERM)

    def _on_signal(signum: int, frame: object) -> None:
        stop_flag[0] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)
    started = time.monotonic()
    stopped_early = False
    stderr_chunks: list[str] = []
    try:
        proc = subprocess.Popen(
            [str(part) for part in argv],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)
        raise CaptureError(f"{tool} not found: {binary}") from exc

    try:
        deadline = started + limit + _TIMEOUT_SLACK
        while True:
            code = proc.poll()
            if code is not None:
                break
            if _stop_requested(stop_file, stop_flag):
                stopped_early = True
                _terminate_recorder(proc)
                break
            if time.monotonic() >= deadline:
                _terminate_recorder(proc)
                signal.signal(signal.SIGINT, previous_int)
                signal.signal(signal.SIGTERM, previous_term)
                raise CaptureError(f"{tool} timed out after {limit}s safety cap")
            time.sleep(_POLL_INTERVAL)
        if proc.stderr is not None:
            try:
                err = proc.stderr.read()
            except OSError:
                err = ""
            if err:
                stderr_chunks.append(err)
        code = proc.wait(timeout=2.0)
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)
        if stop_file is not None:
            _clear_stop_file(stop_file)

    # sox/ffmpeg often exit 0 or 255/130 after SIGINT once the wav is closed.
    if not wav.is_file():
        reason = error_tail("".join(stderr_chunks)) or f"exit {code}"
        raise CaptureError(f"{tool} could not record the microphone ({reason})")
    # A non-zero exit with a wav on disk after an intentional early stop is OK.
    if code not in (0, None) and not stopped_early:
        # Some recorders exit non-zero when killed at the safety cap edge too.
        if code in (130, 143, 255, -2, -15):
            stopped_early = True
        else:
            reason = error_tail("".join(stderr_chunks)) or f"exit {code}"
            raise CaptureError(f"{tool} could not record the microphone ({reason})")
    elapsed = max(1, int(round(time.monotonic() - started)))
    return CaptureResult(
        wav_path=str(wav),
        tool=tool,
        seconds=min(elapsed, limit),
        argv=list(argv),
        stopped_early=stopped_early,
    )


def record(
    paths: VoicePaths,
    probe: CommandProbe,
    runner: CommandRunner,
    *,
    mode: str = "default",
    seconds: int | None = None,
    platform: str = "darwin",
    stop_file: str | Path | None = None,
    early_stop: bool = False,
) -> CaptureResult:
    """Record microphone audio to a wav under the data directory.

    When `early_stop` is true (toggle + real subprocess runner), recording runs
    until a stop-file appears, SIGINT/SIGTERM arrives, or the safety cap hits.
    Injected fake runners keep the bounded path so unit tests need no signals.
    """
    selected = select_tool(probe)
    if selected is None:
        raise CaptureError("no capture tool on PATH: need sox or ffmpeg to record the microphone")
    tool, binary = selected
    limit = mode_seconds(mode) if seconds is None else seconds
    wav = recording_path(paths, datetime.now(tz=UTC))
    wav.parent.mkdir(parents=True, exist_ok=True)

    use_early = early_stop and runner is run_command
    if use_early:
        stop_path = Path(stop_file) if stop_file is not None else default_stop_file(paths)
        return _record_early_stop(tool, binary, wav, limit, platform, stop_path)

    argv = capture_argv(tool, binary, wav, limit, platform, unbounded=False)
    result = runner(argv, timeout=limit + _TIMEOUT_SLACK)
    if result.code != 0:
        reason = error_tail(result.stderr) or f"exit {result.code}"
        raise CaptureError(f"{tool} could not record the microphone ({reason})")
    if not wav.is_file():
        raise CaptureError(f"{tool} exited 0 but wrote no audio: {wav}")
    return CaptureResult(wav_path=str(wav), tool=tool, seconds=limit, argv=list(argv))

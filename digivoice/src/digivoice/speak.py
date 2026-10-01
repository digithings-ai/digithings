"""Speak text with Piper and a local audio player. No cloud TTS.

Text is piped to Piper over stdin (never interpolated into a shell string).
Piper writes a wav; then afplay (macOS) or aplay/ffplay (Linux) plays it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from digivoice.errors import SpeakError
from digivoice.models import SpeakResult, VoicePaths
from digivoice.paths import piper_fallback
from digivoice.probe import CommandProbe
from digivoice.runner import CommandRunner, error_tail

PIPER_VOICE_ENV = "DIGIVOICE_PIPER_VOICE"
PIPER_TIMEOUT = 120.0
PLAY_TIMEOUT = 300.0
COPY_SELECTION_SCRIPT = 'tell application "System Events" to keystroke "c" using command down'
READ_SOURCE_TIMEOUT = 5.0


def select_piper(probe: CommandProbe, home: Path) -> str | None:
    found = probe.lookup("piper")
    if found:
        return found
    fallback = str(piper_fallback(home))
    if probe.executable(fallback):
        return fallback
    return None


def resolve_voice(paths: VoicePaths, env: Mapping[str, str], probe: CommandProbe) -> Path:
    """Prefer DIGIVOICE_PIPER_VOICE; else the first *.onnx under models_dir."""
    override = (env.get(PIPER_VOICE_ENV) or "").strip()
    if override:
        voice = Path(override).expanduser()
        if not probe.is_file(str(voice)):
            raise SpeakError(
                f"Piper voice missing: {voice} (set {PIPER_VOICE_ENV} to a .onnx path)"
            )
        return voice
    models = Path(paths.models_dir)
    if probe.is_dir(str(models)):
        onnx_files = sorted(p for p in models.glob("*.onnx") if p.is_file())
        if onnx_files:
            return onnx_files[0]
    raise SpeakError(
        f"no Piper voice found: set {PIPER_VOICE_ENV} to a .onnx file, "
        f"or place one under {paths.models_dir}"
    )


def speak_wav_path(paths: VoicePaths, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now(tz=UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path(paths.recordings_dir) / f"speak-{stamp}-{uuid4().hex[:8]}.wav"


def piper_argv(binary: str, voice: Path, wav: Path) -> list[str]:
    return [binary, "--model", str(voice), "--output_file", str(wav)]


def select_player(platform: str, probe: CommandProbe) -> tuple[str, str] | None:
    """Return (player_name, binary_path). afplay on darwin; aplay then ffplay on Linux."""
    if platform == "darwin":
        found = probe.lookup("afplay")
        return ("afplay", found) if found else None
    for name in ("aplay", "ffplay"):
        found = probe.lookup(name)
        if found:
            return name, found
    return None


def play_argv(player: str, binary: str, wav: Path) -> list[str]:
    if player == "afplay":
        return [binary, str(wav)]
    if player == "aplay":
        return [binary, "-q", str(wav)]
    if player == "ffplay":
        return [binary, "-nodisp", "-autoexit", "-loglevel", "error", str(wav)]
    raise SpeakError(f"unknown player: {player}")


def read_clipboard(platform: str, probe: CommandProbe, runner: CommandRunner) -> str:
    if platform == "darwin":
        binary = probe.lookup("pbpaste")
        if not binary:
            raise SpeakError("pbpaste not on PATH; cannot read the clipboard")
        result = runner([binary], timeout=READ_SOURCE_TIMEOUT)
    else:
        for name, argv_extra in (
            ("wl-paste", []),
            ("xclip", ["-o", "-selection", "clipboard"]),
            ("xsel", ["--clipboard", "--output"]),
        ):
            binary = probe.lookup(name)
            if binary:
                result = runner([binary, *argv_extra], timeout=READ_SOURCE_TIMEOUT)
                break
        else:
            raise SpeakError("no clipboard tool on PATH (need wl-paste, xclip, or xsel)")
    if result.code != 0:
        reason = error_tail(result.stderr) or f"exit {result.code}"
        raise SpeakError(f"clipboard read failed ({reason})")
    text = result.stdout.strip()
    if not text:
        raise SpeakError("clipboard is empty")
    return text


def read_selection(platform: str, probe: CommandProbe, runner: CommandRunner) -> str:
    if platform == "darwin":
        osascript = probe.lookup("osascript")
        if not osascript:
            raise SpeakError("osascript not on PATH; cannot read the selection")
        typed = runner([osascript, "-e", COPY_SELECTION_SCRIPT], timeout=READ_SOURCE_TIMEOUT)
        if typed.code != 0:
            reason = error_tail(typed.stderr) or f"exit {typed.code}"
            raise SpeakError(f"could not copy selection ({reason})")
        return read_clipboard(platform, probe, runner)
    for name, argv_extra in (
        ("xclip", ["-o", "-selection", "primary"]),
        ("xsel", ["--primary", "--output"]),
    ):
        binary = probe.lookup(name)
        if binary:
            result = runner([binary, *argv_extra], timeout=READ_SOURCE_TIMEOUT)
            if result.code != 0:
                reason = error_tail(result.stderr) or f"exit {result.code}"
                raise SpeakError(f"selection read failed ({reason})")
            text = result.stdout.strip()
            if not text:
                raise SpeakError("primary selection is empty")
            return text
    raise SpeakError("no selection tool on PATH (need xclip or xsel)")


def speak(
    paths: VoicePaths,
    probe: CommandProbe,
    runner: CommandRunner,
    text: str,
    *,
    platform: str,
    home: Path,
    env: Mapping[str, str],
) -> SpeakResult:
    """Synthesize `text` with Piper and play it. Returns paths used."""
    cleaned = " ".join(text.split())
    if not cleaned:
        raise SpeakError("nothing to speak")
    binary = select_piper(probe, home)
    if binary is None:
        raise SpeakError(f"piper not on PATH and not executable at {piper_fallback(home)}")
    voice = resolve_voice(paths, env, probe)
    player_sel = select_player(platform, probe)
    if player_sel is None:
        needed = "afplay" if platform == "darwin" else "aplay or ffplay"
        raise SpeakError(f"no audio player on PATH (need {needed})")
    player, player_bin = player_sel
    wav = speak_wav_path(paths)
    wav.parent.mkdir(parents=True, exist_ok=True)
    piper_cmd = piper_argv(binary, voice, wav)
    synthesized = runner(piper_cmd, stdin=cleaned + "\n", timeout=PIPER_TIMEOUT)
    if synthesized.code != 0:
        reason = error_tail(synthesized.stderr) or f"exit {synthesized.code}"
        raise SpeakError(f"piper failed ({reason})")
    if not wav.is_file():
        raise SpeakError(f"piper exited 0 but wrote no audio: {wav}")
    play_cmd = play_argv(player, player_bin, wav)
    played = runner(play_cmd, timeout=PLAY_TIMEOUT)
    if played.code != 0:
        reason = error_tail(played.stderr) or f"exit {played.code}"
        raise SpeakError(f"{player} failed ({reason})")
    return SpeakResult(
        text=cleaned,
        voice_path=str(voice),
        wav_path=str(wav),
        player=player,
        argv_piper=list(piper_cmd),
        argv_play=list(play_cmd),
    )

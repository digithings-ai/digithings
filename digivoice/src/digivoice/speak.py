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
from digivoice.focus import FocusTarget
from digivoice.models import SpeakResult, VoicePaths
from digivoice.paths import piper_fallback
from digivoice.probe import CommandProbe
from digivoice.runner import CommandRunner, error_tail
from digivoice.settings import load_settings

PIPER_VOICE_ENV = "DIGIVOICE_PIPER_VOICE"
PIPER_TIMEOUT = 120.0
PLAY_TIMEOUT = 300.0
COPY_SELECTION_SCRIPT = 'tell application "System Events" to keystroke "c" using command down'
READ_SOURCE_TIMEOUT = 5.0
# Accessibility query for the focused element's selected text. Static script, no
# user text interpolated: every external binary goes through CommandRunner argv.
AX_SELECTED_TEXT_ARGS: list[str] = [
    "-e",
    'tell application "System Events"',
    "-e",
    "tell (first process whose frontmost is true)",
    "-e",
    "set allElems to entire contents of window 1",
    "-e",
    "repeat with e in allElems",
    "-e",
    "if focused of e is true then",
    "-e",
    'set sel to value of attribute "AXSelectedText" of e',
    "-e",
    "if sel is not missing value then return sel",
    "-e",
    "end if",
    "-e",
    "end repeat",
    "-e",
    "end tell",
    "-e",
    "end tell",
]
FRONTMOST_APP_SCRIPT = (
    'tell application "System Events" to get name of first process whose frontmost is true'
)
GHOSTTY_BUNDLE = "com.mitchellh.ghostty"
AX_TARGET_SCRIPT = """on run argv
  set targetId to item 1 of argv
  set targetName to item 2 of argv
  tell application "System Events"
    if targetId is not "" then
      set proc to first process whose bundle identifier is targetId
    else if targetName is not "" then
      set proc to first process whose name is targetName
    else
      set proc to first process whose frontmost is true
    end if
    tell proc
      set allElems to entire contents of window 1
      repeat with e in allElems
        try
          if focused of e is true then
            set sel to value of attribute "AXSelectedText" of e
            if sel is not missing value then return sel
          end if
        end try
      end repeat
    end tell
  end tell
end run"""
GHOSTTY_APP_NAME = "Ghostty"
GHOSTTY_SELECTION_PBOARD = "com.mitchellh.ghostty.selection"


def select_piper(probe: CommandProbe, home: Path) -> str | None:
    found = probe.lookup("piper")
    if found:
        return found
    fallback = str(piper_fallback(home))
    if probe.executable(fallback):
        return fallback
    return None


def _settings_voice(paths: VoicePaths) -> Path | None:
    """Saved TUI voice, as a file under models_dir. None when unset or auto."""
    chosen = (load_settings(paths).tts_voice or "").strip()
    if not chosen or chosen.casefold() in {"auto", "none", "null"}:
        return None
    voice = Path(chosen).expanduser()
    if voice.is_absolute():
        return voice
    name = voice.name
    if not name.endswith(".onnx"):
        name = f"{name}.onnx"
    return Path(paths.models_dir) / name


def resolve_voice(paths: VoicePaths, env: Mapping[str, str], probe: CommandProbe) -> Path:
    """Prefer DIGIVOICE_PIPER_VOICE, then the saved voice, else the first *.onnx."""
    override = (env.get(PIPER_VOICE_ENV) or "").strip()
    if override:
        voice = Path(override).expanduser()
        if not probe.is_file(str(voice)):
            raise SpeakError(
                f"Piper voice missing: {voice} (set {PIPER_VOICE_ENV} to a .onnx path)"
            )
        return voice
    saved = _settings_voice(paths)
    if saved is not None and probe.is_file(str(saved)):
        return saved
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


def _ax_selected_text(osascript: str, runner: CommandRunner) -> str | None:
    """Focused element's AX selected text, or None when unavailable or empty.

    osascript renders a missing AppleScript value as the literal string
    "missing value" with exit 0, so that output must not count as a selection.
    """
    result = runner([osascript, *AX_SELECTED_TEXT_ARGS], timeout=READ_SOURCE_TIMEOUT)
    if result.code != 0:
        return None
    cleaned = result.stdout.strip()
    if not cleaned or cleaned.casefold() == "missing value":
        return None
    return cleaned


def _ax_in_target(osascript: str, runner: CommandRunner, focus: FocusTarget) -> str | None:
    """Selected text in the captured app, or None when that app has none."""
    # Same argv rule as paste: `-` after `-e` is the bundle id, not end of options.
    result = runner(
        [osascript, "-e", AX_TARGET_SCRIPT, focus.bundle_id, focus.name],
        timeout=READ_SOURCE_TIMEOUT,
    )
    if result.code != 0:
        return None
    cleaned = result.stdout.strip()
    if not cleaned or cleaned.casefold() == "missing value":
        return None
    return cleaned


def _target_is_ghostty(focus: FocusTarget) -> bool:
    if focus.bundle_id == GHOSTTY_BUNDLE:
        return True
    return focus.name.casefold() == GHOSTTY_APP_NAME.casefold()


def _frontmost_is_ghostty(osascript: str, runner: CommandRunner) -> bool:
    """True when the frontmost process is Ghostty. Never raises: unknown means no."""
    result = runner([osascript, "-e", FRONTMOST_APP_SCRIPT], timeout=READ_SOURCE_TIMEOUT)
    if result.code != 0:
        return False
    return result.stdout.strip().casefold() == GHOSTTY_APP_NAME.casefold()


def _named_pasteboard(pbpaste: str, runner: CommandRunner, name: str) -> str | None:
    """Text from a named pasteboard, or None when missing, unreadable, or empty."""
    result = runner([pbpaste, "-pboard", name], timeout=READ_SOURCE_TIMEOUT)
    if result.code != 0:
        return None
    return result.stdout.strip() or None


def read_selection(
    platform: str,
    probe: CommandProbe,
    runner: CommandRunner,
    focus: FocusTarget | None = None,
) -> str:
    """Read the current text selection. Soft-fails when nothing is selected.

    On darwin, in order:

    1. the focused element's Accessibility selected text (no clipboard touched);
    2. Ghostty's selection pasteboard, when Ghostty is frontmost (Ghostty's
       copy-on-select writes the highlight there instead of the general clipboard);
    3. Cmd+C via osascript, which only counts as a selection when the clipboard
       *changes*.

    An unchanged clipboard (including leftover dictation paste) is treated as
    empty selection — never as coding-reply readout.
    """
    if platform == "darwin":
        osascript = probe.lookup("osascript")
        if not osascript:
            raise SpeakError("osascript not on PATH; cannot read the selection")
        known = focus is not None and focus.known
        selected = (
            _ax_in_target(osascript, runner, focus)
            if known and focus is not None
            else _ax_selected_text(osascript, runner)
        )
        if selected:
            return selected
        pbpaste = probe.lookup("pbpaste")
        ghostty = _target_is_ghostty(focus) if known and focus is not None else False
        if pbpaste and not ghostty and not known:
            ghostty = _frontmost_is_ghostty(osascript, runner)
        if pbpaste and ghostty:
            ghostty = _named_pasteboard(pbpaste, runner, GHOSTTY_SELECTION_PBOARD)
            if ghostty:
                return ghostty
        try:
            before: str | None = read_clipboard(platform, probe, runner)
        except SpeakError:
            before = None
        typed = runner([osascript, "-e", COPY_SELECTION_SCRIPT], timeout=READ_SOURCE_TIMEOUT)
        if typed.code != 0:
            reason = error_tail(typed.stderr) or f"exit {typed.code}"
            raise SpeakError(f"could not copy selection ({reason})")
        try:
            after = read_clipboard(platform, probe, runner)
        except SpeakError:
            after = None
        if after and after != before:
            return after
        raise SpeakError(
            "nothing selected: select text then run speak --selection (clipboard alone is not used)"
        )
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
                raise SpeakError(
                    "nothing selected: select text then run speak --selection "
                    "(clipboard alone is not used)"
                )
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

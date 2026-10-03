"""Speak text with Piper and a local audio player. No cloud TTS.

Text is piped to Piper over stdin (never interpolated into a shell string).
Piper writes a wav; then afplay (macOS) or aplay/ffplay (Linux) plays it.
On macOS, Piper is linked to libespeak-ng.1.dylib. speak points dyld at a
same-architecture copy already on the machine and passes that tree's
espeak-ng-data. A library built for a different architecture is ignored.
"""

from __future__ import annotations

import os
import shutil
import struct
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from digivoice.errors import CancelledError, SpeakError
from digivoice.focus import FocusTarget
from digivoice.models import SpeakResult, VoicePaths
from digivoice.paths import piper_fallback, vendor_dir
from digivoice.probe import CommandProbe
from digivoice.runner import (
    CANCELLED_CODE,
    CommandResult,
    CommandRunner,
    error_tail,
    run_command,
    run_command_cancellable,
)
from digivoice.settings import load_settings

_ESPEAK_LIBRARY = "libespeak-ng.1.dylib"
_ESPEAK_TERMINATOR = b"espeak_TextToPhonemesWithTerminator"
_ESPEAK_DATA = "espeak-ng-data"
_ESPEAK_PHON = "phontab"
_MH_MAGIC_64 = 0xFEEDFACF
_CPU_ARM64 = 0x0100000C
_CPU_X86_64 = 0x01000007

PIPER_VOICE_ENV = "DIGIVOICE_PIPER_VOICE"
PIPER_TIMEOUT = 120.0
PLAY_TIMEOUT = 300.0
SPEAK_STOP_FILE_NAME = "speak.stop"
# The speak hotkey is Left Option. Release it, pause so that release lands,
# then send a plain Command-C. The clipboard read retries after that.
COPY_SELECTION_SCRIPT = """tell application "System Events"
  key up option
  delay 0.1
  keystroke "c" using command down
end tell"""
# Same argv rule as paste: bundle id and name follow `-e`, with no leading dash.
# Option is released, then Command-C is sent to the captured process.
ACTIVATE_AND_COPY_SCRIPT = """on run argv
  set targetId to item 1 of argv
  set targetName to item 2 of argv
  tell application "System Events"
    if targetId is not "" then
      set proc to first process whose bundle identifier is targetId
    else
      set proc to first process whose name is targetName
    end if
    set frontmost of proc to true
    delay 0.2
    key up option
    delay 0.1
    tell proc
      keystroke "c" using command down
    end tell
  end tell
end run"""
READ_SOURCE_TIMEOUT = 5.0
_NOTHING_SELECTED = (
    "nothing selected: select text then run speak --selection (clipboard alone is not used)"
)
# Planted before Command-C so a selection that matches the clipboard still changes it.
# The marker itself is never spoken. Nothing selected restores the previous clipboard.
_CLIPBOARD_MARKER = "digivoice-selection-"
# Command-C returns before the app writes the pasteboard. Read again briefly.
_COPY_READ_ATTEMPTS = 5
_COPY_READ_PAUSE = 0.1
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


def _voice_present(probe: CommandProbe, voice: Path) -> bool:
    return probe.is_file(str(voice)) or voice.is_file()


def resolve_voice(paths: VoicePaths, env: Mapping[str, str], probe: CommandProbe) -> Path:
    """Saved voice on disk, then DIGIVOICE_PIPER_VOICE when that file exists, else first *.onnx.

    A stale env path must not fail the take while another installed voice is on disk.
    """
    saved = _settings_voice(paths)
    if saved is not None and _voice_present(probe, saved):
        return saved
    override = (env.get(PIPER_VOICE_ENV) or "").strip()
    if override:
        voice = Path(override).expanduser()
        if _voice_present(probe, voice):
            return voice
    models = Path(paths.models_dir)
    if probe.is_dir(str(models)) or models.is_dir():
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


def espeak_library_dirs() -> tuple[Path, ...]:
    """Homebrew and /usr/local library directories. Tests replace this."""
    return (
        Path("/opt/homebrew/lib"),
        Path("/opt/homebrew/opt/espeak-ng/lib"),
        Path("/usr/local/lib"),
        Path("/usr/local/opt/espeak-ng/lib"),
    )


def espeak_data_dirs() -> tuple[Path, ...]:
    """Homebrew espeak-ng-data directories. Tests replace this."""
    return (
        Path("/opt/homebrew/share/espeak-ng-data"),
        Path("/usr/local/share/espeak-ng-data"),
    )


def macho_cpu(path: Path) -> str | None:
    """Thin Mach-O cpu, `arm64` or `x86_64`. None for any other file."""
    try:
        with path.open("rb") as handle:
            header = handle.read(8)
    except OSError:
        return None
    if len(header) < 8:
        return None
    magic, cputype = struct.unpack("<II", header)
    if magic != _MH_MAGIC_64:
        return None
    if cputype == _CPU_ARM64:
        return "arm64"
    if cputype == _CPU_X86_64:
        return "x86_64"
    return None


def library_matches_binary(binary: str, library: Path) -> bool:
    """True when both files share a Mach-O cpu, or neither is Mach-O."""
    binary_path = Path(binary)
    target = binary_path.resolve() if binary_path.exists() else binary_path
    binary_cpu = macho_cpu(target) if target.is_file() else None
    library_cpu = macho_cpu(library)
    if binary_cpu is None and library_cpu is None:
        return True
    return binary_cpu is not None and binary_cpu == library_cpu


def place_macho_library(binary: str, library: Path, name: str) -> Path | None:
    """Copy a same-arch Mach-O library next to the real Piper binary.

    `~/.local/bin/piper` is a symlink, so a library next to that link is not
    the directory dyld searches for the real binary. A matching library already
    beside the binary is left in place. A different architecture is not copied.
    """
    if not library_matches_binary(binary, library):
        return None
    binary_path = Path(binary)
    if not binary_path.exists():
        return None
    real = binary_path.resolve()
    cpu = macho_cpu(real)
    if cpu is None or macho_cpu(library) != cpu:
        return None
    dest = real.parent / name
    if dest.is_file() and macho_cpu(dest) == cpu:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(library, dest, follow_symlinks=True)
    return dest


def espeak_exports_terminator(path: Path) -> bool:
    """True when this espeak-ng exports the phonemize entry point.

    piper-jni's arm64 phonemize calls `espeak_TextToPhonemesWithTerminator`.
    Homebrew espeak-ng 1.52 does not provide that symbol.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return _ESPEAK_TERMINATOR in data


def place_espeak_beside(binary: str, library: Path) -> Path | None:
    """Copy a same-arch Mach-O espeak library next to the real Piper binary."""
    return place_macho_library(binary, library, _ESPEAK_LIBRARY)


def find_espeak_library(home: Path, binary: str, *, platform: str) -> Path | None:
    """A same-arch libespeak-ng already on disk. This does not download one."""
    invoked = Path(binary)
    for directory in (invoked.resolve().parent, invoked.parent):
        found = _matching_library(binary, directory / _ESPEAK_LIBRARY)
        if found is not None:
            return found
    vendor = vendor_dir(home) / "piper"
    if vendor.is_dir():
        for path in vendor.rglob(_ESPEAK_LIBRARY):
            if (
                path.is_file()
                and path.name == _ESPEAK_LIBRARY
                and library_matches_binary(binary, path)
            ):
                return path
    if platform != "darwin":
        return None
    for directory in espeak_library_dirs():
        found = _matching_library(binary, directory / _ESPEAK_LIBRARY)
        if found is not None:
            return found
    return None


def find_espeak_data(home: Path, binary: str, *, platform: str) -> Path | None:
    """An espeak-ng-data directory that contains phontab. No download."""
    invoked = Path(binary)
    for directory in (invoked.resolve().parent, invoked.parent):
        found = _phon_dir(directory / _ESPEAK_DATA)
        if found is not None:
            return found
    vendor = vendor_dir(home) / "piper"
    if vendor.is_dir():
        tabs = [
            path
            for path in vendor.rglob(_ESPEAK_PHON)
            if path.is_file() and path.name == _ESPEAK_PHON and path.parent.name == _ESPEAK_DATA
        ]
        if tabs:
            return tabs[0].parent
    if platform != "darwin":
        return None
    for directory in espeak_data_dirs():
        found = _phon_dir(directory)
        if found is not None:
            return found
    return None


def piper_library_env(platform: str, binary: str, library: Path | None) -> dict[str, str] | None:
    """DYLD path for a same-arch espeak-ng. Linux uses $ORIGIN."""
    if platform != "darwin" or library is None:
        return None
    if not library_matches_binary(binary, library):
        return None
    dirs = [str(library.parent)]
    previous = os.environ.get("DYLD_LIBRARY_PATH", "")
    for part in previous.split(os.pathsep):
        if part and part not in dirs:
            dirs.append(part)
    return {"DYLD_LIBRARY_PATH": os.pathsep.join(dirs)}


def speak_stop_path(paths: VoicePaths) -> Path:
    """File the speak hotkey writes to stop the player. Playback polls this."""
    return Path(paths.data_dir) / SPEAK_STOP_FILE_NAME


def length_scale_for_speed(speed: float) -> float:
    """Piper phoneme length. 1 is normal pace; smaller is faster, larger is slower.

    Playback speed 2 (twice as fast) is length scale 0.5. Speed 0.5 is length scale 2.
    """
    return 1.0 / speed


def format_length_scale(scale: float) -> str:
    return f"{scale:.6g}"


def piper_argv(
    binary: str,
    voice: Path,
    wav: Path,
    *,
    espeak_data: Path | None = None,
    length_scale: float | None = None,
) -> list[str]:
    argv = [binary, "--model", str(voice), "--output_file", str(wav)]
    if espeak_data is not None:
        argv.extend(["--espeak_data", str(espeak_data)])
    # Piper's default length scale is 1 (normal pace). Omit the flag at 1x.
    if length_scale is not None and abs(length_scale - 1.0) > 1e-6:
        argv.extend(["--length_scale", format_length_scale(length_scale)])
    return argv


def _matching_library(binary: str, path: Path) -> Path | None:
    found = _existing_file(path)
    if found is None or not library_matches_binary(binary, found):
        return None
    return found


def _existing_file(path: Path) -> Path | None:
    if path.is_file():
        return path
    return None


def _named_under(root: Path, name: str) -> Path | None:
    if not root.is_dir():
        return None
    matches = [path for path in root.rglob(name) if path.is_file() and path.name == name]
    return matches[0] if matches else None


def _phon_dir(path: Path) -> Path | None:
    if (path / _ESPEAK_PHON).is_file():
        return path
    return None


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


def _clipboard_text(platform: str, probe: CommandProbe, runner: CommandRunner) -> str | None:
    """Clipboard text, or None when it cannot be read. An empty clipboard is ``""``."""
    if platform != "darwin":
        return None
    binary = probe.lookup("pbpaste")
    if not binary:
        return None
    result = runner([binary], timeout=READ_SOURCE_TIMEOUT)
    if result.code != 0:
        return None
    return result.stdout.strip()


def _write_clipboard(pbcopy: str, runner: CommandRunner, text: str) -> bool:
    result = runner([pbcopy], stdin=text, timeout=READ_SOURCE_TIMEOUT)
    return result.code == 0


def _restore_clipboard(pbcopy: str, runner: CommandRunner, previous: str | None) -> None:
    if previous is None:
        return
    _write_clipboard(pbcopy, runner, previous)


def _nothing_selected(focus: FocusTarget | None) -> str:
    """Empty selection. Names the captured app when both reads missed."""
    if focus is None or not focus.known:
        return _NOTHING_SELECTED
    name = focus.name.strip() or "unknown"
    bundle = focus.bundle_id.strip() or "unknown"
    return f"{_NOTHING_SELECTED}; app={name} bundle={bundle}"


def _copied_after_marker(
    platform: str,
    probe: CommandProbe,
    runner: CommandRunner,
    marker: str,
) -> str | None:
    """Text Command-C wrote, once the clipboard is no longer `marker`.

    The keystroke returns before the captured app updates the pasteboard, so
    the first read is often still the marker. Later reads are the selection.
    The marker itself is never returned.
    """
    for attempt in range(_COPY_READ_ATTEMPTS):
        copied = _clipboard_text(platform, probe, runner)
        if copied and copied != marker:
            return copied
        if attempt + 1 < _COPY_READ_ATTEMPTS:
            time.sleep(_COPY_READ_PAUSE)
    return None


def _plant_marker(
    pbcopy: str,
    platform: str,
    probe: CommandProbe,
    runner: CommandRunner,
    previous: str | None,
) -> str | None:
    """Replace the clipboard with a marker. None when the marker did not stick."""
    marker = f"{_CLIPBOARD_MARKER}{uuid4().hex}"
    if not _write_clipboard(pbcopy, runner, marker):
        return None
    if _clipboard_text(platform, probe, runner) == marker:
        return marker
    _restore_clipboard(pbcopy, runner, previous)
    return None


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
    3. Cmd+C via osascript. Option is released, then a short pause, then a plain
       Command-C to the captured process. When pbcopy is available, a private
       marker is written first. The clipboard is read again until it differs
       from that marker or the brief retries run out. The first read is often
       still the marker, because the keystroke returns before the app copies.
       A later read that differs is the selection, including when that text was
       already on the clipboard. The marker is never spoken. If every read is
       still the marker, nothing was selected: the previous clipboard is
       restored and is not spoken, and the error names the captured app.
       Accessibility text is returned before any of this and does not require
       the clipboard to change.

    Without pbcopy, an unchanged clipboard (including leftover dictation paste)
    is empty selection — never a coding-reply readout.
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
        pbcopy = probe.lookup("pbcopy")
        marker: str | None = None
        if pbcopy:
            before = _clipboard_text(platform, probe, runner)
            marker = _plant_marker(pbcopy, platform, probe, runner, before)
        else:
            try:
                before = read_clipboard(platform, probe, runner)
            except SpeakError:
                before = None
        copy_argv = (
            [osascript, "-e", ACTIVATE_AND_COPY_SCRIPT, focus.bundle_id, focus.name]
            if known and focus is not None
            else [osascript, "-e", COPY_SELECTION_SCRIPT]
        )
        typed = runner(copy_argv, timeout=READ_SOURCE_TIMEOUT)
        if typed.code != 0:
            if marker is not None and pbcopy is not None:
                _restore_clipboard(pbcopy, runner, before)
            reason = error_tail(typed.stderr) or f"exit {typed.code}"
            raise SpeakError(f"could not copy selection ({reason})")
        if marker is not None and pbcopy is not None:
            copied = _copied_after_marker(platform, probe, runner, marker)
            if copied:
                return copied
            _restore_clipboard(pbcopy, runner, before)
            raise SpeakError(_nothing_selected(focus))
        try:
            after = read_clipboard(platform, probe, runner)
        except SpeakError:
            after = None
        if after and after != before:
            return after
        raise SpeakError(_nothing_selected(focus))
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
                raise SpeakError(_NOTHING_SELECTED)
            return text
    raise SpeakError("no selection tool on PATH (need xclip or xsel)")


def _run_stage(
    runner: CommandRunner,
    argv: list[str],
    *,
    stdin: str | None = None,
    timeout: float | None = None,
    env: Mapping[str, str] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> CommandResult:
    """Run one speak stage. The real runner kills the child group when cancelled.

    Injected test runners stay synchronous. A cancel code from either path is a stop.
    """
    if cancelled is not None and runner is run_command:
        return run_command_cancellable(
            argv,
            stdin=stdin,
            timeout=timeout,
            env=env,
            cancelled=cancelled,
        )
    return runner(argv, stdin=stdin, timeout=timeout, env=env)


def _stopped(result: CommandResult, cancelled: Callable[[], bool] | None) -> bool:
    if result.code == CANCELLED_CODE:
        return True
    return cancelled is not None and cancelled()


def speak(
    paths: VoicePaths,
    probe: CommandProbe,
    runner: CommandRunner,
    text: str,
    *,
    platform: str,
    home: Path,
    env: Mapping[str, str],
    cancelled: Callable[[], bool] | None = None,
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
    library = find_espeak_library(home, binary, platform=platform)
    data = find_espeak_data(home, binary, platform=platform)
    speed = load_settings(paths).tts_speed
    scale = length_scale_for_speed(speed)
    piper_cmd = piper_argv(binary, voice, wav, espeak_data=data, length_scale=scale)
    if cancelled is not None and cancelled():
        raise CancelledError("stopped")
    synthesized = _run_stage(
        runner,
        piper_cmd,
        stdin=cleaned + "\n",
        timeout=PIPER_TIMEOUT,
        env=piper_library_env(platform, binary, library),
        cancelled=cancelled,
    )
    if _stopped(synthesized, cancelled):
        raise CancelledError("stopped")
    if synthesized.code != 0:
        reason = error_tail(synthesized.stderr) or f"exit {synthesized.code}"
        raise SpeakError(f"piper failed ({reason})")
    if not wav.is_file():
        raise SpeakError(f"piper exited 0 but wrote no audio: {wav}")
    if cancelled is not None and cancelled():
        raise CancelledError("stopped")
    play_cmd = play_argv(player, player_bin, wav)
    played = _run_stage(runner, play_cmd, timeout=PLAY_TIMEOUT, cancelled=cancelled)
    if _stopped(played, cancelled):
        raise CancelledError("stopped")
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

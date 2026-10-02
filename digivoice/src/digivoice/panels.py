"""TTY panes for doctor, history, and system controls.

Doctor walks each check with the status word on the left and a short line.
History is one page at a time: open a take to read it, then copy or delete.
System holds doctor, reload, reset, restart, and update.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TextIO

from digivoice.doctor import doctor_ready
from digivoice.history import delete_entry, read_history
from digivoice.models import DoctorCheck, HistoryEntry, VoicePaths
from digivoice.paste import copy_to_clipboard
from digivoice.probe import CommandProbe
from digivoice.reload import run_reload
from digivoice.runner import CommandRunner, run_command
from digivoice.settings import default_settings, save_settings
from digivoice.tui import (
    _ANSI_RESET,
    _compose,
    _is_tty,
    _read_key,
    _term_size,
    _use_ansi,
    _use_screen,
    _visible_len,
    choose,
    fullscreen_leave,
    wrap_text,
)

_PAGE = 8
_OK = "\x1b[32m"
_BAD = "\x1b[31m"
_INFO = "\x1b[38;5;145m"

SYSTEM_MENU = (
    "Doctor (health checks, one row at a time)",
    "Reload (ask Hammerspoon to reload its config)",
    "Reset settings (defaults only; history and models stay)",
    "Restart (quit this screen and open digivoice again)",
    "Update (reinstall hint; not an in-app updater yet)",
)

# Short lines for the doctor screen. The CLI report still prints full paths.
_SUMMARY: dict[tuple[str, str], str] = {
    ("whisper-cli", "ok"): "Whisper is installed",
    ("whisper-cli", "missing"): "Whisper is not installed",
    ("piper", "ok"): "Piper is installed",
    ("piper", "missing"): "Piper is not installed",
    ("sox", "ok"): "Sox is installed",
    ("sox", "missing"): "Sox is not installed",
    ("ffmpeg", "ok"): "FFmpeg is installed",
    ("ffmpeg", "missing"): "FFmpeg is not installed",
    ("capture", "ok"): "Microphone capture is ready",
    ("capture", "missing"): "Microphone capture is missing",
    ("models", "ok"): "Speech model is on disk",
    ("models", "missing"): "Speech model is missing",
    ("settings", "ok"): "Settings file is valid",
    ("settings", "missing"): "Settings file needs a fix",
    ("settings", "info"): "Using default settings",
    ("hotkeys", "ok"): "Hotkeys are documented",
    ("hotkeys", "missing"): "Hotkey notes are missing",
    ("hammerspoon", "ok"): "Hammerspoon adapter is installed",
    ("hammerspoon", "missing"): "Hammerspoon adapter is missing",
    ("paths", "info"): "Data folders are set",
    ("rewrite", "ok"): "Rewrite is ready",
    ("rewrite", "missing"): "Rewrite is not ready",
    ("rewrite", "info"): "Rewrite is off",
    ("detection", "info"): "Word checks are off",
    ("tcc", "info"): "Microphone permission is not checked here",
    ("interrupt", "info"): "Stop keeps the take. Esc discards it",
}

_READY = "All set. Local speech is ready."
_NOT_READY = "Not ready. The red rows need a fix."
_UPDATE = (
    "digivoice update is not wired yet. Reinstall with "
    "uv tool install --reinstall --editable ./digivoice"
)


def _color_word(status: str, *, color: bool) -> str:
    word = {"ok": "ok", "missing": "not ok", "info": "info"}[status]
    if not color:
        return word
    paint = {"ok": _OK, "missing": _BAD, "info": _INFO}[status]
    return f"{paint}{word}{_ANSI_RESET}"


def doctor_summary(check: DoctorCheck) -> str:
    """One short line a person can read. Paths stay in the CLI report."""
    known = _SUMMARY.get((check.id, check.status))
    if known:
        return known
    if check.id == "history":
        if check.detail.startswith("present"):
            return "History is on disk"
        return "No history yet"
    return check.id.replace("-", " ")


def _clip_visible(text: str, width: int) -> str:
    """Cut `text` to `width` visible columns, keeping any leading SGR."""
    if width < 1:
        return ""
    if "\x1b" not in text:
        if len(text) <= width:
            return text
        if width < 2:
            return text[:width]
        return text[: width - 1] + "…"
    kept: list[str] = []
    visible = 0
    index = 0
    while index < len(text) and visible < width:
        if text.startswith("\x1b", index):
            end = text.find("m", index)
            if end < 0:
                break
            kept.append(text[index : end + 1])
            index = end + 1
            continue
        if visible == width - 1 and index < len(text) - 1:
            kept.append("…")
            visible += 1
            break
        kept.append(text[index])
        visible += 1
        index += 1
    if "\x1b" in text:
        kept.append(_ANSI_RESET)
    return "".join(kept)


def _fit_visible(text: str, width: int) -> str:
    if _visible_len(text) > width:
        text = _clip_visible(text, width)
    visible = _visible_len(text)
    if visible < width:
        text += " " * (width - visible)
    return text


def _panel_width() -> int:
    cols, _rows = _term_size()
    return max(36, min(88, cols - 6))


def _doctor_lines(check: DoctorCheck, *, color: bool, width: int) -> list[str]:
    word = {"ok": "ok", "missing": "not ok", "info": "info"}[check.status]
    text_w = max(8, width - 8)
    wrapped = wrap_text(doctor_summary(check), text_w)
    painted = _color_word(check.status, color=color)
    gap = (" " * (6 - len(word))) + "  "
    lines = [f"{painted}{gap}{wrapped[0]}"]
    indent = " " * 8
    lines.extend(indent + extra for extra in wrapped[1:])
    return lines


def _paint_block(stdout: TextIO, title: str, body: list[str], *, color: bool) -> str:
    cols, rows = _term_size()
    panel_w = _panel_width()
    inner = max(8, panel_w - 3)
    lines = [_fit_visible(f"■  {title}", panel_w), _fit_visible("│", panel_w)]
    for entry in body:
        if entry == "":
            lines.append(_fit_visible("│", panel_w))
            continue
        if "\x1b" in entry or _visible_len(entry) <= inner:
            chunks = [entry]
        else:
            chunks = wrap_text(entry, inner)
        for chunk in chunks:
            lines.append(_fit_visible("│  " + chunk, panel_w))
    lines.append(_fit_visible("└  esc back", panel_w))
    frame = _compose(
        [],
        lines,
        cols,
        rows,
        panel_w,
        clear=color and _is_tty(stdout),
        redraw=False,
        ansi=color and _use_screen(),
        screen=color and _use_screen() and _is_tty(stdout),
    )
    stdout.write(frame)
    stdout.flush()
    return frame


def present_doctor(
    checks: list[DoctorCheck],
    stdout: TextIO | None = None,
    stdin: TextIO | None = None,
    *,
    color: bool | None = None,
    pause: float = 0.08,
) -> str:
    """Walk every check, then say whether local speech is ready."""
    stdout = stdout or sys.stdout
    stdin = stdin or sys.stdin
    paint = _use_ansi() if color is None else color
    live = _is_tty(stdout) and pause > 0
    shown: list[DoctorCheck] = []
    frame = ""
    steps = checks if live else []
    for check in steps:
        shown.append(check)
        body = []
        for item in shown:
            body.extend(_doctor_lines(item, color=paint, width=max(8, _panel_width() - 3)))
        frame = _paint_block(stdout, "Doctor", body, color=paint)
        time.sleep(pause)
    shown = list(checks)
    ready = doctor_ready(shown)
    inner = max(8, _panel_width() - 3)
    body: list[str] = []
    for item in shown:
        body.extend(_doctor_lines(item, color=paint, width=inner))
    body.append("")
    closing = _READY if ready else _NOT_READY
    if paint:
        tone = _OK if ready else _BAD
        closing = f"{tone}{closing}{_ANSI_RESET}"
    body.append(closing)
    frame = _paint_block(stdout, "Doctor", body, color=paint)
    if _is_tty(stdin):
        try:
            _read_key(stdin)
        except (OSError, ValueError):
            pass
    return frame


def _clip(entry: HistoryEntry) -> str:
    text = " ".join(entry.text.split())
    if len(text) > 48:
        text = text[:47] + "…"
    clock = entry.ts[5:16] if len(entry.ts) >= 16 else entry.ts
    return f"{clock}  {entry.kind}  {text}"


def _write_full(entry: HistoryEntry, stdout: TextIO) -> None:
    width = max(24, min(72, _term_size()[0] - 4))
    stdout.write("\n".join(wrap_text(entry.text, width)) + "\n")
    stdout.flush()


def browse_history(
    paths: VoicePaths,
    platform: str,
    probe: CommandProbe,
    runner: CommandRunner | None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """Newest takes first, one page at a time. Enter shows the full text."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    active = runner or run_command
    reading = read_history(paths.history_file)
    ordered = list(reversed(reading.entries))
    if not ordered:
        stdout.write("  no takes yet\n")
        stdout.flush()
        return
    page = 0
    while ordered:
        pages = max(1, (len(ordered) + _PAGE - 1) // _PAGE)
        page = min(page, pages - 1)
        visible = ordered[page * _PAGE : (page + 1) * _PAGE]
        picked = choose(
            "History",
            [_clip(entry) for entry in visible],
            stdin,
            stdout,
            subtitle=(
                f"Page {page + 1} of {pages}. Left and right change pages. Enter opens the take."
            ),
            paging=True,
        )
        if picked is None:
            return
        if picked == "page-prev":
            page = max(0, page - 1)
            continue
        if picked == "page-next":
            page = min(pages - 1, page + 1)
            continue
        if not isinstance(picked, int) or not 0 <= picked < len(visible):
            continue
        entry = visible[picked]
        _write_full(entry, stdout)
        while True:
            action = choose(
                "Take",
                [
                    "Copy (put this take on the clipboard)",
                    "Delete (remove this take)",
                    "Back",
                ],
                stdin,
                stdout,
                subtitle="The full text is above. Esc goes up.",
            )
            if action == 0:
                copied = copy_to_clipboard(platform, probe, active, entry.text)
                stdout.write(f"  {copied.detail}\n")
                stdout.flush()
                continue
            if action == 1:
                delete_entry(paths.history_file, entry)
                stdout.write("  deleted\n")
                stdout.flush()
                ordered = list(reversed(read_history(paths.history_file).entries))
                break
            break
        if not ordered:
            stdout.write("  no takes yet\n")
            stdout.flush()
            return


def restart_digivoice() -> None:
    """Replace this process with a fresh digivoice. Does not return."""
    os.execv(sys.executable, [sys.executable, *sys.argv])


def browse_system(
    paths: VoicePaths,
    platform: str,
    home: Path,
    env: Mapping[str, str],
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    *,
    runner: CommandRunner | None = None,
    restart: Callable[[], None] | None = None,
    doctor: Callable[[], None] | None = None,
) -> None:
    """Doctor, reload, reset, restart, and update. Esc returns to home."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    while True:
        picked = choose(
            "System",
            list(SYSTEM_MENU),
            stdin,
            stdout,
            subtitle="Controls for this install. Esc goes up.",
            detail=True,
        )
        if picked is None:
            return
        if picked == 0:
            if doctor is not None:
                doctor()
        elif picked == 1:
            result = run_reload(platform, home, env, runner=runner)
            text = result.stdout.strip() or result.stderr.strip() or "reload finished"
            stdout.write(text + "\n")
            stdout.flush()
        elif picked == 2:
            answer = choose(
                "Reset settings",
                ["Reset (back to defaults)", "Back"],
                stdin,
                stdout,
                subtitle="History and downloaded models stay on disk.",
            )
            if answer == 0:
                save_settings(paths, default_settings())
                stdout.write("  settings reset\n")
                stdout.flush()
        elif picked == 3:
            answer = choose(
                "Restart",
                ["Restart digivoice", "Back"],
                stdin,
                stdout,
                subtitle="Hammerspoon stops, then this screen opens again.",
            )
            if answer == 0:
                fullscreen_leave(stdout)
                if restart is not None:
                    restart()
                    return
                restart_digivoice()
        elif picked == 4:
            stdout.write(_UPDATE + "\n")
            stdout.flush()

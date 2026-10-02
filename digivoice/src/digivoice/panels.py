"""TTY panes for doctor, history, and system controls.

Doctor walks each check, then paints ok in green and a failure in red.
History opens one take at a time and can copy it. System groups reload,
reset, restart, and update so they are not separate home rows.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TextIO

from digivoice.doctor import doctor_ready
from digivoice.history import read_history
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
)

_PAGE = 8
_OK = "\x1b[32m"
_BAD = "\x1b[31m"
_INFO = "\x1b[38;5;145m"

SYSTEM_MENU = (
    "Reload (ask Hammerspoon to reload its config)",
    "Reset settings (defaults only; history and models stay)",
    "Restart (quit this screen and open digivoice again)",
    "Update (reinstall hint; not an in-app updater yet)",
)

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


def _check_line(check: DoctorCheck, *, color: bool) -> str:
    return f"{check.id}  {_color_word(check.status, color=color)}  {check.detail}"


def _fit_visible(text: str, width: int) -> str:
    visible = _visible_len(text)
    if visible >= width:
        return text
    return text + (" " * (width - visible))


def _paint_block(stdout: TextIO, title: str, body: list[str], *, color: bool) -> str:
    cols, rows = _term_size()
    panel_w = max(36, min(88, cols - 6))
    lines = [_fit_visible(f"■  {title}", panel_w), _fit_visible("│", panel_w)]
    for entry in body:
        lines.append(_fit_visible("│  " + entry, panel_w))
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
        body = [_check_line(item, color=paint) for item in shown]
        frame = _paint_block(stdout, "Doctor", body, color=paint)
        time.sleep(pause)
    shown = list(checks)
    ready = doctor_ready(shown)
    body = [_check_line(item, color=paint) for item in shown]
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


def browse_history(
    paths: VoicePaths,
    platform: str,
    probe: CommandProbe,
    runner: CommandRunner | None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """Newest takes first. The last row loads older ones. Enter opens a take."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    active = runner or run_command
    reading = read_history(paths.history_file)
    ordered = list(reversed(reading.entries))
    if not ordered:
        stdout.write("  no takes yet\n")
        stdout.flush()
        return
    window = _PAGE
    while True:
        visible = ordered[:window]
        labels = [_clip(entry) for entry in visible]
        if window < len(ordered):
            labels.append(f"Older ({len(ordered) - window} more)")
        picked = choose(
            "History",
            labels,
            stdin,
            stdout,
            subtitle="Enter opens a take. Older loads the next ones. Esc goes up.",
        )
        if picked is None:
            return
        if picked == len(visible):
            window = min(len(ordered), window + _PAGE)
            continue
        entry = visible[picked]
        while True:
            action = choose(
                entry.ts,
                ["Copy (put this take on the clipboard)", "Back"],
                stdin,
                stdout,
                subtitle=entry.text,
            )
            if action != 0:
                break
            copied = copy_to_clipboard(platform, probe, active, entry.text)
            stdout.write(f"  {copied.detail}\n")
            stdout.flush()


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
) -> None:
    """Reload, reset, restart, and update. Esc returns to home."""
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
            result = run_reload(platform, home, env, runner=runner)
            text = result.stdout.strip() or result.stderr.strip() or "reload finished"
            stdout.write(text + "\n")
            stdout.flush()
        elif picked == 1:
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
        elif picked == 2:
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
        elif picked == 3:
            stdout.write(_UPDATE + "\n")
            stdout.flush()

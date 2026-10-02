"""TTY panes for doctor, history, and system controls.

Doctor walks each check with the status word on the left and a short line.
History is one page at a time: open a take to read it, then copy or delete.
System holds doctor, reload, reset, restart, update, and logs.
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
from digivoice.nav import section_of
from digivoice.paste import copy_to_clipboard
from digivoice.probe import CommandProbe
from digivoice.reload import run_reload
from digivoice.runner import CommandRunner, run_command
from digivoice.settings import default_settings, save_settings
from digivoice.status import read_system_log, system_log_path
from digivoice.tui import (
    _ANSI_RESET,
    NAV_FOOTER,
    MenuBlock,
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

SYSTEM_BLOCKS: tuple[MenuBlock, ...] = (
    MenuBlock(action="Doctor", path="/doctor"),
    MenuBlock(action="Reload", path="/reload"),
    MenuBlock(action="Reset", path="/reset"),
    MenuBlock(action="Restart", path="/restart"),
    MenuBlock(action="Update", path="/update"),
    MenuBlock(action="Logs", path="/system/logs"),
)
SYSTEM_MENU = tuple(block.action for block in SYSTEM_BLOCKS)

_TAKE_BLOCKS: tuple[MenuBlock, ...] = (
    MenuBlock(action="Copy", shortcut="c", path="/history/copy"),
    MenuBlock(action="Delete", shortcut="d", path="/history/delete"),
    MenuBlock(action="Back", shortcut="esc", path="/history"),
)
_TAKE_KEYS = {"c": 0, "C": 0, "d": 1, "D": 1, "copy": 0}
_SYSTEM_KIND = {
    "doctor": 0,
    "reload": 1,
    "reset": 2,
    "restart": 3,
    "update": 4,
    "logs": 5,
}

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
    lines.append(_fit_visible("└  " + NAV_FOOTER, panel_w))
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
            while True:
                key = _read_key(stdin)
                if key in {None, "esc", "q", "Q"}:
                    break
        except (OSError, ValueError):
            pass
    return frame


def _preview(entry: HistoryEntry) -> str:
    text = " ".join(entry.text.split())
    if len(text) > 48:
        return text[:47] + "…"
    return text


def _when(entry: HistoryEntry) -> str:
    """Timestamp under the text. Gray metadata, not part of the sentence."""
    ts = entry.ts
    if len(ts) >= 16:
        clock = f"{ts[5:10]} {ts[11:16]}"
    else:
        clock = ts
    return f"{clock}  {entry.kind}"


def _history_blocks(visible: list[HistoryEntry]) -> list[MenuBlock]:
    return [MenuBlock(action=_preview(entry), meta=_when(entry)) for entry in visible]


def _write_full(entry: HistoryEntry, stdout: TextIO) -> None:
    width = max(24, min(72, _term_size()[0] - 4))
    stdout.write("\n".join(wrap_text(entry.text, width)) + "\n")
    stdout.flush()


def _follow_path(picked: str, on_path: Callable[[str], None] | None) -> None:
    if on_path is not None:
        on_path(picked)


def browse_history(
    paths: VoicePaths,
    platform: str,
    probe: CommandProbe,
    runner: CommandRunner | None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    *,
    on_path: Callable[[str], None] | None = None,
) -> None:
    """Newest takes first, one page at a time. Enter shows the full text."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    active = runner or run_command
    reading = read_history(paths.history_file)
    ordered = list(reversed(reading.entries))
    if not ordered:
        choose(
            "History",
            stdin=stdin,
            stdout=stdout,
            subtitle="/history",
            blocks=(MenuBlock(action="No takes yet", path="/history"),),
        )
        return
    page = 0
    history_at = 0
    while ordered:
        pages = max(1, (len(ordered) + _PAGE - 1) // _PAGE)
        page = min(page, pages - 1)
        visible = ordered[page * _PAGE : (page + 1) * _PAGE]
        page_label = f"/history  {page + 1}/{pages}" if pages > 1 else "/history"
        picked = choose(
            "History",
            stdin=stdin,
            stdout=stdout,
            subtitle=page_label,
            paging=pages > 1,
            blocks=_history_blocks(visible),
            start_at=history_at,
        )
        if isinstance(picked, int):
            history_at = picked
        if picked is None:
            return
        if isinstance(picked, str) and picked.startswith("/"):
            if section_of(picked) == "history":
                continue
            _follow_path(picked, on_path)
            return
        if picked == "page-prev":
            page = max(0, page - 1)
            history_at = 0
            continue
        if picked == "page-next":
            page = min(pages - 1, page + 1)
            history_at = 0
            continue
        if not isinstance(picked, int) or not 0 <= picked < len(visible):
            continue
        entry = visible[picked]
        _write_full(entry, stdout)
        width = max(24, min(72, _term_size()[0] - 4))
        while True:
            action = choose(
                "Take",
                stdin=stdin,
                stdout=stdout,
                subtitle="/history",
                blocks=_TAKE_BLOCKS,
                shortcuts=_TAKE_KEYS,
                lead=wrap_text(entry.text, width),
                lead_meta=_when(entry),
            )
            copy_now = action == 0 or action == "/history/copy"
            delete_now = action == 1 or action == "/history/delete"
            if copy_now:
                copied = copy_to_clipboard(platform, probe, active, entry.text)
                stdout.write(f"  {copied.detail}\n")
                stdout.flush()
                continue
            if delete_now:
                delete_entry(paths.history_file, entry)
                stdout.write("  deleted\n")
                stdout.flush()
                ordered = list(reversed(read_history(paths.history_file).entries))
                break
            if isinstance(action, str) and action.startswith("/"):
                _follow_path(action, on_path)
                return
            break
        if not ordered:
            choose(
                "History",
                stdin=stdin,
                stdout=stdout,
                subtitle="/history",
                blocks=(MenuBlock(action="No takes yet", path="/history"),),
            )
            return


def present_logs(
    paths: VoicePaths,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """Show the whole system log inside the menu. A missing file stays on the page."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    lines = [line for line in read_system_log(system_log_path(paths)).splitlines() if line.strip()]
    if lines:
        blocks = tuple(MenuBlock(action=line, path="/system/logs") for line in lines)
    else:
        blocks = (MenuBlock(action="No log yet", path="/system/logs"),)
    choose("Logs", stdin=stdin, stdout=stdout, subtitle="/system/logs", blocks=blocks)


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
    on_path: Callable[[str], None] | None = None,
) -> None:
    """Doctor, reload, reset, restart, update, and logs. Esc returns to home."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    system_at = 0
    while True:
        picked = choose(
            "System",
            stdin=stdin,
            stdout=stdout,
            subtitle="/system",
            blocks=SYSTEM_BLOCKS,
            start_at=system_at,
        )
        if isinstance(picked, int):
            system_at = picked
        if picked is None:
            return
        if isinstance(picked, str) and picked.startswith("/"):
            if on_path is not None:
                on_path(picked)
                return
            kind = section_of(picked)
            picked = _SYSTEM_KIND.get(kind)
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
                "Reset",
                stdin=stdin,
                stdout=stdout,
                subtitle="/reset",
                blocks=(
                    MenuBlock(action="Reset", path="/reset"),
                    MenuBlock(action="Back", shortcut="esc", path="/system"),
                ),
            )
            if answer == 0:
                save_settings(paths, default_settings())
                stdout.write("  settings reset\n")
                stdout.flush()
        elif picked == 3:
            answer = choose(
                "Restart",
                stdin=stdin,
                stdout=stdout,
                subtitle="/restart",
                blocks=(
                    MenuBlock(action="Restart", path="/restart"),
                    MenuBlock(action="Back", shortcut="esc", path="/system"),
                ),
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
        elif picked == 5:
            present_logs(paths, stdin, stdout)

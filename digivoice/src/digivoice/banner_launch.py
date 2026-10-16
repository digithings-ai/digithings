"""Banner click: focus an open digivoice terminal, or open one.

The Hammerspoon adapter uses the same rule. Callers pass a launcher, so unit
tests never start Terminal or Hammerspoon.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

TUI_PID_NAME = "tui.pid"


def tui_pid_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / TUI_PID_NAME


def tui_is_open(pid_text: str | None) -> bool:
    """True when the pid file holds a single integer."""
    if not pid_text:
        return False
    return pid_text.strip().isdigit()


def read_tui_open(data_dir: str | Path) -> bool:
    try:
        text = tui_pid_path(data_dir).read_text(encoding="utf-8")
    except OSError:
        return False
    return tui_is_open(text)


def mark_tui_open(data_dir: str | Path) -> None:
    """Record that this process is the open terminal UI. Fails soft."""
    path = tui_pid_path(data_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    except OSError:
        return


def mark_tui_closed(data_dir: str | Path) -> None:
    try:
        tui_pid_path(data_dir).unlink(missing_ok=True)
    except OSError:
        return


def banner_click(*, already_open: bool, launcher: Callable[[str], None]) -> str:
    """Focus the terminal UI when it is up. Open it once when it is not."""
    action = "focus" if already_open else "open"
    launcher(action)
    return action

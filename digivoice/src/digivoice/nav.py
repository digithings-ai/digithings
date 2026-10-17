"""Slash paths shared by the TUI and the CLI.

Every screen row has a path. ``digivoice /doctor`` and ``digivoice doctor``
open the same place. ``/quit`` is the only full stop.
"""

from __future__ import annotations

_EXACT: dict[str, str] = {
    "/quit": "quit",
    "/doctor": "doctor",
    "/system/doctor": "doctor",
    "/history": "history",
    "/history/copy": "history-copy",
    "/history/delete": "history-delete",
    "/settings": "settings",
    "/system": "system",
    "/reload": "reload",
    "/system/reload": "reload",
    "/reset": "reset",
    "/system/reset": "reset",
    "/restart": "restart",
    "/system/restart": "restart",
    "/update": "update",
    "/system/update": "update",
    "/logs": "logs",
    "/system/logs": "logs",
}


class QuitRequested(Exception):
    """Explicit quit. Hammerspoon stops. Closing the terminal does not raise this."""


def norm_path(raw: str) -> str:
    """``doctor`` and ``/system/doctor/`` both become a single slash path."""
    text = raw.strip()
    if not text.startswith("/"):
        text = "/" + text
    parts = [part for part in text.split("/") if part]
    return "/" + "/".join(parts)


def section_of(path: str) -> str:
    """Stable name for a slash path. Empty when nothing maps."""
    normal = norm_path(path)
    if normal in _EXACT:
        return _EXACT[normal]
    if normal.startswith("/settings/"):
        return "settings"
    return ""

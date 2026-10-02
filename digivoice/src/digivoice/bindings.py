"""Hotkey names. The same rules as ``hammerspoon/hotkeys.lua``.

A string that does not parse is not stored. The caller keeps the previous bind.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# ANSI keycodes (Mac). Modifier keys are phrases, not this table.
_KEYS: dict[str, int] = {
    "a": 0,
    "b": 11,
    "c": 8,
    "d": 2,
    "e": 14,
    "f": 3,
    "g": 5,
    "h": 4,
    "i": 34,
    "j": 38,
    "k": 40,
    "l": 37,
    "m": 46,
    "n": 45,
    "o": 31,
    "p": 35,
    "q": 12,
    "r": 15,
    "s": 1,
    "t": 17,
    "u": 32,
    "v": 9,
    "w": 13,
    "x": 7,
    "y": 16,
    "z": 6,
    "0": 29,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "5": 23,
    "6": 22,
    "7": 26,
    "8": 28,
    "9": 25,
    "space": 49,
    "tab": 48,
    "return": 36,
    "enter": 36,
    "esc": 53,
    "escape": 53,
    "delete": 51,
    "backspace": 51,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
}

_MODS: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "cmd": "cmd",
    "command": "cmd",
    "super": "cmd",
    "meta": "cmd",
}


class BindingSpec(BaseModel):
    """One parsed bind. ``kind`` is ``flags`` for Option or ``key`` for a key."""

    model_config = ConfigDict(extra="ignore")

    keycode: int
    kind: Literal["flags", "key"]
    ctrl: bool = False
    shift: bool = False
    alt: bool = False
    cmd: bool = False
    double: bool = False


def _phrase(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _split_plus(text: str) -> list[str]:
    return [part.strip() for part in text.split("+") if part.strip()]


def parse_binding(text: str) -> BindingSpec | None:
    """A spec, or None when ``text`` is not a key the adapter can arm."""
    name = _phrase(text)
    if not name:
        return None
    if name in {"right option", "right alt"}:
        return BindingSpec(keycode=61, kind="flags", alt=True)
    if name in {"left option", "left alt"}:
        return BindingSpec(keycode=58, kind="flags", alt=True)
    if name in {"double-tap left option", "double tap left option"}:
        return BindingSpec(keycode=58, kind="flags", alt=True, double=True)
    if name in {"esc", "escape"}:
        return BindingSpec(keycode=53, kind="key")
    if name in {"option", "alt", "opt"}:
        return BindingSpec(keycode=61, kind="flags", alt=True)
    ctrl = shift = alt = cmd = double = False
    key: str | None = None
    for token in _split_plus(name):
        if token in {"double-tap", "doubletap"}:
            double = True
            continue
        mod = _MODS.get(token)
        if mod == "ctrl":
            ctrl = True
        elif mod == "shift":
            shift = True
        elif mod == "alt":
            alt = True
        elif mod == "cmd":
            cmd = True
        elif key is None and token in _KEYS:
            key = token
        else:
            return None
    if key is None:
        return None
    return BindingSpec(
        keycode=_KEYS[key],
        kind="key",
        ctrl=ctrl,
        shift=shift,
        alt=alt,
        cmd=cmd,
        double=double,
    )


def binding_warning(role: str, text: str, previous: str) -> str | None:
    """None when ``text`` parses. Otherwise the sentence that names the kept bind."""
    if parse_binding(text) is not None:
        return None
    return f"{role} binding '{text}' is not a key; keeping {previous}"

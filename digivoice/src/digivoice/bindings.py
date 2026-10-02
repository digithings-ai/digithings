"""Hotkey names. The same rules as ``hammerspoon/hotkeys.lua``.

A string that does not parse is not stored. The caller keeps the previous bind.
A name another role already arms is not stored either. While the field is open,
``hotkey.capture`` tells the event tap to pass keys through.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Mapping

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


def same_binding(left: BindingSpec, right: BindingSpec) -> bool:
    """True when two names arm the same key, modifiers, and double-tap."""
    return (
        left.keycode == right.keycode
        and left.kind == right.kind
        and left.ctrl == right.ctrl
        and left.shift == right.shift
        and left.alt == right.alt
        and left.cmd == right.cmd
        and left.double == right.double
    )


def binding_conflict(role: str, text: str, current: Mapping[str, str]) -> str | None:
    """None when ``text`` is free, or it is already this role's bind.

    An unparseable name is None here. ``binding_warning`` covers that.
    A different role that already arms the same key is named in the sentence.
    """
    spec = parse_binding(text)
    if spec is None:
        return None
    for other in ("dictation", "speak", "cancel"):
        if other == role:
            continue
        owned = parse_binding(str(current.get(other, "")))
        if owned is not None and same_binding(spec, owned):
            previous = current.get(role, "")
            return f"{role} binding '{text}' is already {other}; keeping {previous}"
    return None


CAPTURE_FLAG_NAME = "hotkey.capture"


def capture_flag_path(data_dir: str | Path) -> Path:
    """File the event tap reads. ``1`` means the hotkey field is open."""
    return Path(data_dir) / CAPTURE_FLAG_NAME


def set_hotkey_capture(data_dir: str | Path, active: bool) -> None:
    """Write or remove the capture flag. A disk error does not raise."""
    target = capture_flag_path(data_dir)
    try:
        if not active:
            target.unlink(missing_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.tmp")
        temp.write_text("1\n", encoding="utf-8")
        os.replace(temp, target)
    except OSError:
        return

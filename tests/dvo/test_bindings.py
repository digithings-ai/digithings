"""Hotkey names match hammerspoon/hotkeys.lua. Garbage is not a bind."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.bindings import (
    binding_conflict,
    binding_warning,
    capture_flag_path,
    parse_binding,
    set_hotkey_capture,
)

pytestmark = pytest.mark.unit


def test_supported_names_parse() -> None:
    right = parse_binding("Right Option")
    assert right is not None and right.keycode == 61 and right.kind == "flags"
    speak = parse_binding("Double-tap Left Option")
    assert speak is not None and speak.double is True and speak.keycode == 58
    cancel = parse_binding("Esc")
    assert cancel is not None and cancel.keycode == 53 and cancel.kind == "key"
    chord = parse_binding("ctrl+shift+space")
    assert chord is not None
    assert chord.ctrl is True and chord.shift is True and chord.keycode == 49


def test_garbage_is_not_a_key() -> None:
    assert parse_binding("not-a-key") is None
    assert parse_binding("f5") is None
    assert parse_binding("ctrl+shift") is None
    warning = binding_warning("dictation", "not-a-key", "Right Option")
    assert warning == "dictation binding 'not-a-key' is not a key; keeping Right Option"
    assert binding_warning("dictation", "Esc", "Right Option") is None


def test_a_binding_another_role_already_has_is_refused() -> None:
    current = {
        "dictation": "Right Option",
        "speak": "Double-tap Left Option",
        "cancel": "Esc",
    }
    taken = binding_conflict("dictation", "Esc", current)
    assert taken == "dictation binding 'Esc' is already cancel; keeping Right Option"
    same = binding_conflict("dictation", "option", current)
    assert same is None
    again = binding_conflict("speak", "Double-tap Left Option", current)
    assert again is None
    assert binding_conflict("dictation", "not-a-key", current) is None


def test_capture_flag_is_written_and_removed(tmp_path: Path) -> None:
    set_hotkey_capture(tmp_path, True)
    flag = capture_flag_path(tmp_path)
    assert flag.read_text(encoding="utf-8") == "1\n"
    set_hotkey_capture(tmp_path, False)
    assert not flag.exists()


def test_bare_option_is_right_option() -> None:
    for name in ("option", "alt", "opt", "Option"):
        spec = parse_binding(name)
        assert spec is not None
        assert spec.keycode == 61
        assert spec.kind == "flags"
    left = parse_binding("Left Option")
    assert left is not None and left.keycode == 58

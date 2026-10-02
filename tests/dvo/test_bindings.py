"""Hotkey names match hammerspoon/hotkeys.lua. Garbage is not a bind."""

from __future__ import annotations

import pytest
from digivoice.bindings import binding_warning, parse_binding

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

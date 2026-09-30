"""Paste into the focused app: macOS only, never fatal."""

from __future__ import annotations

import pytest
from digivoice.paste import KEYSTROKE_SCRIPT, paste

from tests.dvo.fakes import FakeProbe, FakeReply, FakeRunner

pytestmark = pytest.mark.unit

TEXT = "ship it"
DARWIN_TOOLS = {"pbcopy": "/usr/bin/pbcopy", "osascript": "/usr/bin/osascript"}
ACCESSIBILITY_DENIED = FakeReply(
    code=1,
    stderr=(
        "execution error: Not authorized to send Apple events to System Events. (-1743)\n"
        "osascript: System Events got an error: Not allowed assistive access."
    ),
)


def test_paste_off_darwin_is_a_skip_not_an_error() -> None:
    runner = FakeRunner()
    result = paste("linux", FakeProbe(commands=dict(DARWIN_TOOLS)), runner, TEXT)
    assert result.attempted is False
    assert result.pasted is False
    assert "stdout" in result.detail
    assert runner.calls == []


def test_paste_copies_then_keystrokes() -> None:
    runner = FakeRunner({"pbcopy": FakeReply(), "osascript": FakeReply()})
    result = paste("darwin", FakeProbe(commands=dict(DARWIN_TOOLS)), runner, TEXT)
    assert result.pasted is True
    assert runner.programs == ["pbcopy", "osascript"]
    copied, typed = runner.calls
    # The transcript travels over stdin, never inside an AppleScript string.
    assert copied.stdin == TEXT
    assert typed.argv == ["/usr/bin/osascript", "-e", KEYSTROKE_SCRIPT]
    assert "v" in KEYSTROKE_SCRIPT and "command down" in KEYSTROKE_SCRIPT


def test_denied_accessibility_is_reported_but_not_raised() -> None:
    runner = FakeRunner({"pbcopy": FakeReply(), "osascript": ACCESSIBILITY_DENIED})
    result = paste("darwin", FakeProbe(commands=dict(DARWIN_TOOLS)), runner, TEXT)
    assert result.attempted is True
    assert result.pasted is False
    assert "Accessibility" in result.detail
    assert "assistive access" in result.detail


def test_a_missing_paste_tool_is_skipped() -> None:
    runner = FakeRunner()
    result = paste("darwin", FakeProbe(commands={"pbcopy": "/usr/bin/pbcopy"}), runner, TEXT)
    assert result.attempted is False
    assert "osascript" in result.detail
    assert runner.calls == []


def test_a_failed_clipboard_copy_does_not_keystroke() -> None:
    runner = FakeRunner({"pbcopy": FakeReply(code=1, stderr="pbcopy: broken pipe")})
    result = paste("darwin", FakeProbe(commands=dict(DARWIN_TOOLS)), runner, TEXT)
    assert result.pasted is False
    assert "broken pipe" in result.detail
    assert runner.programs == ["pbcopy"]

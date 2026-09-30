"""Paste the transcript into the focused app. macOS only, and never fatal.

Two steps so no user text is ever interpolated into an AppleScript string: the
transcript goes to the clipboard over stdin with `pbcopy`, then `osascript`
sends a Command-V keystroke. The keystroke is what needs the Accessibility
grant; when it is denied dictation still succeeds because the transcript is
already on stdout.
"""

from __future__ import annotations

from digivoice.models import PasteResult
from digivoice.probe import CommandProbe
from digivoice.runner import CommandRunner, error_tail

KEYSTROKE_SCRIPT = 'tell application "System Events" to keystroke "v" using command down'
ACCESSIBILITY_HINT = "grant Accessibility in System Settings > Privacy & Security > Accessibility"
PASTE_TIMEOUT = 5.0


def paste(platform: str, probe: CommandProbe, runner: CommandRunner, text: str) -> PasteResult:
    if platform != "darwin":
        return PasteResult(
            attempted=False,
            pasted=False,
            detail="focused-app paste is macOS only; the transcript is on stdout",
        )
    pbcopy = probe.lookup("pbcopy")
    osascript = probe.lookup("osascript")
    missing = [name for name, path in (("pbcopy", pbcopy), ("osascript", osascript)) if not path]
    if missing:
        return PasteResult(
            attempted=False,
            pasted=False,
            detail=f"missing on PATH: {', '.join(missing)}",
        )
    copied = runner([str(pbcopy), "w"], stdin=text, timeout=PASTE_TIMEOUT)
    if copied.code != 0:
        reason = error_tail(copied.stderr) or f"exit {copied.code}"
        return PasteResult(attempted=True, pasted=False, detail=f"pbcopy failed ({reason})")
    typed = runner([str(osascript), "-e", KEYSTROKE_SCRIPT], timeout=PASTE_TIMEOUT)
    if typed.code != 0:
        reason = error_tail(typed.stderr) or f"exit {typed.code}"
        return PasteResult(
            attempted=True,
            pasted=False,
            detail=f"keystroke failed ({reason}); {ACCESSIBILITY_HINT}",
        )
    return PasteResult(attempted=True, pasted=True, detail="pasted into the focused app")

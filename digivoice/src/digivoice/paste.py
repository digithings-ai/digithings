"""Paste the transcript into the focused app. macOS only, and never fatal.

Two steps so no user text is ever interpolated into an AppleScript string: the
transcript goes to the clipboard over stdin with `pbcopy`, then `osascript`
sends a Command-V keystroke. The keystroke is what needs the Accessibility
grant; when it is denied dictation still succeeds because the transcript is
already on stdout.
"""

from __future__ import annotations

from digivoice.focus import FocusTarget
from digivoice.models import PasteResult
from digivoice.probe import CommandProbe
from digivoice.runner import CommandRunner, error_tail

KEYSTROKE_SCRIPT = 'tell application "System Events" to keystroke "v" using command down'
# Bundle id and name arrive as argv. The transcript never enters this script.
ACTIVATE_AND_PASTE_SCRIPT = """on run argv
  set targetId to item 1 of argv
  set targetName to item 2 of argv
  tell application "System Events"
    if targetId is not "" then
      set proc to first process whose bundle identifier is targetId
    else
      set proc to first process whose name is targetName
    end if
    set frontmost of proc to true
  end tell
  delay 0.2
  tell application "System Events" to keystroke "v" using command down
end run"""
ACCESSIBILITY_HINT = "grant Accessibility in System Settings > Privacy & Security > Accessibility"
PASTE_TIMEOUT = 5.0
EMPTY_TEXT_DETAIL = "nothing to paste (empty text)"


def _paste_argv(osascript: str, focus: FocusTarget | None) -> list[str]:
    # `osascript -e` does not treat a later `-` as end of options. That dash
    # became AppleScript argv item 1, so Command-V never reached the focused app.
    if focus is not None and focus.known:
        return [osascript, "-e", ACTIVATE_AND_PASTE_SCRIPT, focus.bundle_id, focus.name]
    return [osascript, "-e", KEYSTROKE_SCRIPT]


def paste(
    platform: str,
    probe: CommandProbe,
    runner: CommandRunner,
    text: str,
    focus: FocusTarget | None = None,
) -> PasteResult:
    if not text.strip():
        return PasteResult(attempted=False, pasted=False, detail=EMPTY_TEXT_DETAIL)
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
    copied = runner([str(pbcopy)], stdin=text, timeout=PASTE_TIMEOUT)
    if copied.code != 0:
        reason = error_tail(copied.stderr) or f"exit {copied.code}"
        return PasteResult(attempted=True, pasted=False, detail=f"pbcopy failed ({reason})")
    typed = runner(_paste_argv(str(osascript), focus), timeout=PASTE_TIMEOUT)
    if typed.code != 0:
        reason = error_tail(typed.stderr) or f"exit {typed.code}"
        return PasteResult(
            attempted=True,
            pasted=False,
            detail=f"keystroke failed ({reason}); {ACCESSIBILITY_HINT}",
        )
    target = focus.name if focus is not None and focus.name else "the focused app"
    return PasteResult(attempted=True, pasted=True, detail=f"pasted into {target}")


def copy_to_clipboard(
    platform: str,
    probe: CommandProbe,
    runner: CommandRunner,
    text: str,
) -> PasteResult:
    """Copy text to the system clipboard without pasting. Fail soft."""
    if not text.strip():
        return PasteResult(attempted=False, pasted=False, detail=EMPTY_TEXT_DETAIL)
    if platform == "darwin":
        pbcopy = probe.lookup("pbcopy")
        if not pbcopy:
            return PasteResult(
                attempted=False,
                pasted=False,
                detail="pbcopy not on PATH",
            )
        copied = runner([str(pbcopy)], stdin=text, timeout=PASTE_TIMEOUT)
        if copied.code != 0:
            reason = error_tail(copied.stderr) or f"exit {copied.code}"
            return PasteResult(attempted=True, pasted=False, detail=f"pbcopy failed ({reason})")
        return PasteResult(attempted=True, pasted=True, detail="copied to clipboard")
    # Linux: wl-copy then xclip then xsel.
    for name, argv_extra in (
        ("wl-copy", []),
        ("xclip", ["-selection", "clipboard"]),
        ("xsel", ["--clipboard", "--input"]),
    ):
        binary = probe.lookup(name)
        if not binary:
            continue
        copied = runner([str(binary), *argv_extra], stdin=text, timeout=PASTE_TIMEOUT)
        if copied.code == 0:
            return PasteResult(attempted=True, pasted=True, detail=f"copied via {name}")
        reason = error_tail(copied.stderr) or f"exit {copied.code}"
        return PasteResult(attempted=True, pasted=False, detail=f"{name} failed ({reason})")
    return PasteResult(
        attempted=False,
        pasted=False,
        detail="no clipboard tool on PATH (need pbcopy, wl-copy, xclip, or xsel)",
    )

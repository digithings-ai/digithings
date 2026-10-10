"""The app that had focus when a take started.

Dictation and speak-selection follow that app. The name and bundle id are
passed as argv, never interpolated into an AppleScript string.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from digivoice.probe import CommandProbe
from digivoice.runner import CommandRunner

FOCUS_TIMEOUT = 5.0
FRONTMOST_SCRIPT = """tell application "System Events"
  set p to first process whose frontmost is true
  set bid to bundle identifier of p
  if bid is missing value then set bid to ""
  return (name of p) & linefeed & bid
end tell"""


class FocusTarget(BaseModel):
    """Frontmost app captured before a take can move focus."""

    model_config = ConfigDict(frozen=True)

    name: str = ""
    bundle_id: str = ""

    @property
    def known(self) -> bool:
        return bool(self.name.strip() or self.bundle_id.strip())


def focus_target(name: str = "", bundle_id: str = "") -> FocusTarget:
    return FocusTarget(name=name.strip(), bundle_id=bundle_id.strip())


def capture_frontmost(platform: str, probe: CommandProbe, runner: CommandRunner) -> FocusTarget:
    """Read the frontmost process. Unknown or non-macOS is an empty target."""
    if platform != "darwin":
        return FocusTarget()
    osascript = probe.lookup("osascript")
    if not osascript:
        return FocusTarget()
    result = runner([osascript, "-e", FRONTMOST_SCRIPT], timeout=FOCUS_TIMEOUT)
    if result.code != 0:
        return FocusTarget()
    lines = [line.strip() for line in result.stdout.splitlines()]
    name = lines[0] if lines else ""
    bundle = lines[1] if len(lines) > 1 else ""
    if bundle.casefold() == "missing value":
        bundle = ""
    return focus_target(name, bundle)

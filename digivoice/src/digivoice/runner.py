"""Run child processes from an argv list. Never a shell, and injectable for tests.

Every external binary digivoice talks to — sox, ffmpeg, whisper-cli, pbcopy,
osascript — goes through a `CommandRunner`. Unit tests pass their own runner, so
no test ever needs a real microphone, sound card, or model.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, Field


class CommandResult(BaseModel):
    argv: list[str] = Field(default_factory=list)
    code: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None = None,
        timeout: float | None = None,
    ) -> CommandResult: ...


def run_command(
    argv: Sequence[str],
    *,
    stdin: str | None = None,
    timeout: float | None = None,
) -> CommandResult:
    """Run `argv` with no shell. Missing binary and timeout become exit codes."""
    command = [str(part) for part in argv]
    try:
        completed = subprocess.run(
            command,
            # An empty stdin, never the parent's, so no child can block on the terminal.
            input=stdin if stdin is not None else "",
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return CommandResult(argv=command, code=127, stderr=f"not found: {command[0]}")
    except subprocess.TimeoutExpired:
        return CommandResult(argv=command, code=124, stderr=f"timed out after {timeout}s")
    return CommandResult(
        argv=command,
        code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def error_tail(text: str, limit: int = 400) -> str:
    """Last few lines of a tool's stderr, trimmed from the front to fit `limit`."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    tail = " | ".join(lines[-3:])
    if len(tail) > limit:
        tail = tail[-limit:]
    return tail

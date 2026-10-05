"""Run child processes from an argv list. Never a shell, and injectable for tests.

Every external binary digivoice talks to — sox, ffmpeg, whisper-cli, pbcopy,
osascript — goes through a `CommandRunner`. Unit tests pass their own runner, so
no test ever needs a real microphone, sound card, or model.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable, Sequence
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


CANCELLED_CODE = 130
_CANCEL_POLL_SECONDS = 0.05
_KILL_WAIT_SECONDS = 2.0


def _kill_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass
    try:
        proc.wait(timeout=_KILL_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        pass


def run_command_cancellable(
    argv: Sequence[str],
    *,
    stdin: str | None = None,
    timeout: float | None = None,
    cancelled: Callable[[], bool],
) -> CommandResult:
    """Like `run_command`, but kills the child as soon as `cancelled()` turns true.

    A cancelled child comes back as `CANCELLED_CODE`; the caller decides what a
    cancel means. The child runs in its own session so its helpers die with it.
    """
    command = [str(part) for part in argv]
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except FileNotFoundError:
        return CommandResult(argv=command, code=127, stderr=f"not found: {command[0]}")
    deadline = None if timeout is None else time.monotonic() + timeout
    pending_input: str | None = stdin if stdin is not None else ""
    while True:
        if cancelled():
            _kill_group(proc)
            return CommandResult(argv=command, code=CANCELLED_CODE, stderr="cancelled")
        if deadline is not None and time.monotonic() >= deadline:
            _kill_group(proc)
            return CommandResult(argv=command, code=124, stderr=f"timed out after {timeout}s")
        try:
            out, err = proc.communicate(input=pending_input, timeout=_CANCEL_POLL_SECONDS)
        except subprocess.TimeoutExpired:
            # communicate() keeps the input it already queued; do not send it twice.
            pending_input = None
            continue
        return CommandResult(argv=command, code=proc.returncode, stdout=out, stderr=err)


def cancellable_runner(base: CommandRunner, cancelled: Callable[[], bool]) -> CommandRunner:
    """Make the real runner interruptible. Injected runners pass through untouched.

    Unit-test fakes finish instantly, and the pipeline re-checks the cancel token
    between stages, so only the real subprocess runner needs the polling loop.
    """
    if base is not run_command:
        return base

    def _run(
        argv: Sequence[str],
        *,
        stdin: str | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        return run_command_cancellable(argv, stdin=stdin, timeout=timeout, cancelled=cancelled)

    return _run


def error_tail(text: str, limit: int = 400) -> str:
    """Last few lines of a tool's stderr, trimmed from the front to fit `limit`."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    tail = " | ".join(lines[-3:])
    if len(tail) > limit:
        tail = tail[-limit:]
    return tail

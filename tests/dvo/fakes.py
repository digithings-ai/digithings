"""In-memory command probe and runner for digivoice unit tests.

Nothing here touches a real microphone, sound card, model, or clipboard.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from digivoice.runner import CommandResult


class FakeProbe:
    def __init__(
        self,
        commands: dict[str, str] | None = None,
        executables: set[str] | None = None,
        directories: set[str] | None = None,
        files: set[str] | None = None,
    ) -> None:
        self._commands = commands or {}
        self._executables = executables or set()
        self._directories = directories or set()
        self._files = files or set()

    def lookup(self, command: str) -> str | None:
        return self._commands.get(command)

    def executable(self, path: str) -> bool:
        return path in self._executables

    def is_dir(self, path: str) -> bool:
        return path in self._directories

    def is_file(self, path: str) -> bool:
        return path in self._files


@dataclass(frozen=True)
class FakeCall:
    argv: list[str]
    stdin: str | None
    timeout: float | None

    @property
    def program(self) -> str:
        return Path(self.argv[0]).name


@dataclass(frozen=True)
class FakeReply:
    code: int = 0
    stdout: str = ""
    stderr: str = ""


# A response is either a fixed reply or a callable that sees the call, so a fake
# capture can write the wav the real recorder would have written.
FakeResponse = FakeReply | Callable[[FakeCall], FakeReply]


class FakeRunner:
    """Return scripted results keyed by program name and record every call."""

    def __init__(self, responses: Mapping[str, FakeResponse] | None = None) -> None:
        self._responses = dict(responses or {})
        self.calls: list[FakeCall] = []

    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        call = FakeCall(argv=[str(part) for part in argv], stdin=stdin, timeout=timeout)
        self.calls.append(call)
        response = self._responses.get(call.program, FakeReply())
        reply = response(call) if callable(response) else response
        return CommandResult(
            argv=call.argv, code=reply.code, stdout=reply.stdout, stderr=reply.stderr
        )

    @property
    def programs(self) -> list[str]:
        return [call.program for call in self.calls]

    def call_for(self, program: str) -> FakeCall | None:
        return next((call for call in self.calls if call.program == program), None)


def writes_wav(reply: FakeReply | None = None) -> Callable[[FakeCall], FakeReply]:
    """A capture response that drops a placeholder file at the wav path in argv.

    The wav is the first argument ending in `.wav`, so this works for both the
    sox argv (output before the effect chain) and the ffmpeg argv (output last).
    """

    def _respond(call: FakeCall) -> FakeReply:
        wav = next(Path(part) for part in call.argv if part.endswith(".wav"))
        wav.parent.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(b"RIFF0000WAVEfmt ")
        return reply or FakeReply()

    return _respond

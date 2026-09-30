"""In-memory command probe for digivoice unit tests."""

from __future__ import annotations


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

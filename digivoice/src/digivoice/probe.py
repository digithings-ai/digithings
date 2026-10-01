"""Executable lookup. Filesystem checks only — no shell."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class CommandProbe(Protocol):
    def lookup(self, command: str) -> str | None: ...

    def executable(self, path: str) -> bool: ...

    def is_dir(self, path: str) -> bool: ...

    def is_file(self, path: str) -> bool: ...


def lookup_on_path(command: str, path_env: str | None) -> str | None:
    if not path_env:
        return None
    for directory in path_env.split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / command
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


class FilesystemProbe:
    def __init__(self, path_env: str | None) -> None:
        self._path_env = path_env

    def lookup(self, command: str) -> str | None:
        return lookup_on_path(command, self._path_env)

    def executable(self, path: str) -> bool:
        candidate = Path(path)
        return candidate.is_file() and os.access(candidate, os.X_OK)

    def is_dir(self, path: str) -> bool:
        return Path(path).is_dir()

    def is_file(self, path: str) -> bool:
        return Path(path).is_file()


def real_probe(path_env: str | None) -> FilesystemProbe:
    return FilesystemProbe(path_env)

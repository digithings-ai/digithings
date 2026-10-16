"""Executable lookup. Filesystem checks only — no shell."""

from __future__ import annotations

import os
from collections.abc import Sequence
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


# Where Homebrew and other macOS installs land. GUI launchers (Hammerspoon,
# launchd, agents with a scrubbed env) often run with a PATH that has none of
# them, so a tool lookup also tries these after the caller's PATH.
FALLBACK_TOOL_DIRS: tuple[str, ...] = ("/opt/homebrew/bin", "/usr/local/bin")


def augmented_path(path_env: str | None, extra: Sequence[str] = FALLBACK_TOOL_DIRS) -> str:
    """The caller's PATH with the fallback tool dirs appended once each."""
    parts = [part for part in (path_env or "").split(os.pathsep) if part]
    for directory in extra:
        if directory not in parts:
            parts.append(directory)
    return os.pathsep.join(parts)


class FilesystemProbe:
    def __init__(
        self, path_env: str | None, fallback_dirs: Sequence[str] = FALLBACK_TOOL_DIRS
    ) -> None:
        self._path_env = path_env
        self._fallback_dirs = tuple(fallback_dirs)

    def lookup(self, command: str) -> str | None:
        found = lookup_on_path(command, self._path_env)
        if found:
            return found
        return lookup_on_path(command, os.pathsep.join(self._fallback_dirs))

    def executable(self, path: str) -> bool:
        candidate = Path(path)
        return candidate.is_file() and os.access(candidate, os.X_OK)

    def is_dir(self, path: str) -> bool:
        return Path(path).is_dir()

    def is_file(self, path: str) -> bool:
        return Path(path).is_file()


def real_probe(
    path_env: str | None, fallback_dirs: Sequence[str] = FALLBACK_TOOL_DIRS
) -> FilesystemProbe:
    return FilesystemProbe(path_env, fallback_dirs)

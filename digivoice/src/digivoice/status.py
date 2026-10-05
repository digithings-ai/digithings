"""Live status + cancel hand-off between the digivoice CLI and the status banner.

The CLI writes `status.json` into the data directory as a take moves through its
stages; the Hammerspoon banner polls it and draws. The banner is display only.
The one thing that flows the other way is cancel: an adapter (or `digivoice
cancel`) creates the cancel-file and the running `dict` discards the take.

Everything here fails soft. A status file that cannot be written must never turn
a good dictation into an error.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from digivoice.models import VoicePaths

STATUS_FILE_NAME = "status.json"
DEFAULT_CANCEL_FILE_NAME = "dict.cancel"
# Exit code of `dict` for a cancelled take. Not 0 (nothing was produced) and not 1
# (nothing failed), so adapters can tell "user pressed Esc" from an error.
CANCELLED_EXIT = 3

StatusKind = Literal["dict", "speak"]
StatusState = Literal[
    "loading",
    "recording",
    "transcribing",
    "rewriting",
    "pasting",
    "speaking",
    "done",
    "cancelled",
    "empty",
    "error",
]
TERMINAL_STATES: frozenset[str] = frozenset({"done", "cancelled", "empty", "error"})


class StatusSnapshot(BaseModel):
    """What the banner shows. `text` is the transcript / selection / rewritten text."""

    session: str
    kind: StatusKind
    state: StatusState
    text: str = ""
    detail: str = ""
    updated_ms: int
    pid: int


def status_path(paths: VoicePaths) -> Path:
    return Path(paths.data_dir) / STATUS_FILE_NAME


def default_cancel_file(paths: VoicePaths) -> Path:
    return Path(paths.data_dir) / DEFAULT_CANCEL_FILE_NAME


def read_status(path: str | Path) -> StatusSnapshot | None:
    """Latest snapshot, or None when missing / unreadable / from a future shape."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return StatusSnapshot.model_validate(raw)
    except (OSError, ValueError, ValidationError):
        return None


class StatusReporter:
    """Write `status.json` atomically. Disabled reporters and write errors are no-ops."""

    def __init__(
        self,
        path: str | Path | None,
        kind: StatusKind,
        *,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self._path = Path(path) if path is not None else None
        self._kind: StatusKind = kind
        self._session = uuid4().hex[:12]
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    @property
    def enabled(self) -> bool:
        return self._path is not None

    def update(self, state: StatusState, *, text: str = "", detail: str = "") -> None:
        if self._path is None:
            return
        snapshot = StatusSnapshot(
            session=self._session,
            kind=self._kind,
            state=state,
            text=text,
            detail=detail,
            updated_ms=self._clock_ms(),
            pid=os.getpid(),
        )
        temp = self._path.with_name(f"{self._path.name}.{os.getpid()}.tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(snapshot.model_dump_json() + "\n", encoding="utf-8")
            os.replace(temp, self._path)
        except OSError:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


class CancelToken:
    """Cancel is requested by creating the cancel-file; the take then discards itself."""

    def __init__(self, path: str | Path | None) -> None:
        self._path = Path(path) if path is not None else None

    @property
    def path(self) -> Path | None:
        return self._path

    def requested(self) -> bool:
        return self._path is not None and self._path.exists()

    def clear(self) -> None:
        if self._path is None:
            return
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass


def request_cancel(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("cancel\n", encoding="utf-8")
    return target

"""Append-only JSONL history: one `HistoryEntry` per line, plus read and filter.

The file is the record of a session, so it is only ever appended to. Reads are
lenient — a line written by a future digivoice, or a truncated write, is counted
in `skipped` rather than taking the whole listing down.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from digivoice.models import HistoryEntry, HistoryRead


def utc_now_iso() -> str:
    """ISO-8601 UTC with milliseconds and a `Z` suffix: 2026-09-30T12:00:00.000Z."""
    return datetime.now(tz=UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def dict_entry(text: str, wav: str | None) -> HistoryEntry:
    return HistoryEntry(ts=utc_now_iso(), kind="dict", text=text, wav=wav)


def speak_entry(text: str) -> HistoryEntry:
    return HistoryEntry(ts=utc_now_iso(), kind="speak", text=text, wav=None)


def append_entry(path: str | Path, entry: HistoryEntry) -> Path:
    """Append one JSON object as a line. Parent directories are created."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(entry.model_dump_json() + "\n")
    return target


def read_history(path: str | Path) -> HistoryRead:
    target = Path(path)
    if not target.is_file():
        return HistoryRead(entries=[], skipped=0, present=False)
    entries: list[HistoryEntry] = []
    skipped = 0
    with target.open(encoding="utf-8") as handle:
        for line in handle:
            candidate = line.strip()
            if not candidate:
                continue
            try:
                entries.append(HistoryEntry.model_validate_json(candidate))
            except ValidationError:
                skipped += 1
    return HistoryRead(entries=entries, skipped=skipped, present=True)


def select(
    entries: list[HistoryEntry],
    *,
    last: int | None = None,
    grep: str | None = None,
) -> list[HistoryEntry]:
    """Grep first, then keep the last N of what matched."""
    picked = entries
    if grep:
        needle = grep.casefold()
        picked = [entry for entry in picked if needle in entry.text.casefold()]
    if last is not None:
        picked = picked[-last:]
    return picked


def last_dict_text(path: str | Path) -> str | None:
    """Most recent kind:dict entry with non-empty text, if any."""
    reading = read_history(path)
    for entry in reversed(reading.entries):
        if entry.kind != "dict":
            continue
        text = entry.text.strip()
        if text:
            return text
    return None


def last_speakable_text(path: str | Path) -> str | None:
    """Most recent history entry with non-empty text (dict or speak).

    Kept for callers that want any text. Hotkey speak uses --selection only and
    must not fall back to history (especially not kind:dict).
    """
    reading = read_history(path)
    for entry in reversed(reading.entries):
        text = entry.text.strip()
        if text:
            return text
    return None


def format_entry(entry: HistoryEntry) -> str:
    return f"{entry.ts}  {entry.kind}  {entry.text}"

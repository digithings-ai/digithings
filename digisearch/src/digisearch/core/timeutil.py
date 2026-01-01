"""Timestamp serialization shared by the SQLite-backed stores.

Both stores persist timestamps as UTC ISO-8601 with microsecond precision so
row ordering matches lexicographic string ordering. Keeping the format in one
place stops the two stores from drifting on precision or offset handling.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_iso(value: datetime) -> str:
    """Serialize *value* as UTC ISO-8601; a naive value is read as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds")

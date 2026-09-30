"""History JSONL: append shape, tolerant reads, and the two filters."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from digivoice.history import (
    append_entry,
    dict_entry,
    format_entry,
    read_history,
    select,
    utc_now_iso,
)
from digivoice.models import HistoryEntry

pytestmark = pytest.mark.unit


def _entry(text: str, wav: str | None = None) -> HistoryEntry:
    return dict_entry(text, wav)


def test_dict_entry_is_kind_dict_with_an_iso_utc_ts() -> None:
    entry = _entry("ship it")
    assert entry.kind == "dict"
    assert entry.ts.endswith("Z")
    stamp = datetime.fromisoformat(entry.ts.replace("Z", "+00:00"))
    assert stamp.tzinfo == UTC
    assert entry.wav is None


def test_append_creates_parent_directories_and_one_json_object_per_line(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "history.jsonl"
    append_entry(target, _entry("first", "/tmp/a.wav"))
    append_entry(target, _entry("second"))
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert list(first) == ["ts", "kind", "text", "wav"]
    assert first == {
        "ts": first["ts"],
        "kind": "dict",
        "text": "first",
        "wav": "/tmp/a.wav",
    }
    assert json.loads(lines[1])["wav"] is None


def test_append_never_rewrites_earlier_entries(tmp_path: Path) -> None:
    target = tmp_path / "history.jsonl"
    append_entry(target, _entry("one"))
    before = target.read_text(encoding="utf-8")
    append_entry(target, _entry("two"))
    after = target.read_text(encoding="utf-8")
    assert after.startswith(before)


def test_reading_a_missing_file_is_not_an_error(tmp_path: Path) -> None:
    reading = read_history(tmp_path / "nope.jsonl")
    assert reading.present is False
    assert reading.entries == []


def test_unreadable_lines_are_skipped_not_fatal(tmp_path: Path) -> None:
    target = tmp_path / "history.jsonl"
    target.write_text(
        "\n".join(
            [
                json.dumps({"ts": utc_now_iso(), "kind": "dict", "text": "good", "wav": None}),
                "{not json",
                "",
                json.dumps({"kind": "dict"}),
            ]
        ),
        encoding="utf-8",
    )
    reading = read_history(target)
    assert [entry.text for entry in reading.entries] == ["good"]
    assert reading.skipped == 2


def test_last_keeps_the_newest_entries() -> None:
    entries = [_entry(f"line {index}") for index in range(4)]
    assert [entry.text for entry in select(entries, last=2)] == ["line 2", "line 3"]


def test_grep_filters_on_text_case_insensitively() -> None:
    entries = [_entry("ship it"), _entry("Ship tomorrow"), _entry("hold on")]
    assert [entry.text for entry in select(entries, grep="SHIP")] == [
        "ship it",
        "Ship tomorrow",
    ]


def test_grep_applies_before_last() -> None:
    entries = [_entry("keep 1"), _entry("drop"), _entry("keep 2"), _entry("keep 3")]
    picked = select(entries, last=2, grep="keep")
    assert [entry.text for entry in picked] == ["keep 2", "keep 3"]


def test_no_match_returns_nothing() -> None:
    assert select([_entry("hello")], grep="absent") == []


def test_format_entry_is_one_line_with_ts_kind_and_text() -> None:
    entry = HistoryEntry(ts="2026-09-30T12:00:00.000Z", kind="dict", text="ship it", wav=None)
    assert format_entry(entry) == "2026-09-30T12:00:00.000Z  dict  ship it"

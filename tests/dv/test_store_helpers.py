"""Unit tests for the helpers shared by the vault store backends."""

from __future__ import annotations

import re

import pytest
from digivault.store_helpers import escape_like, first_env

pytestmark = pytest.mark.unit


def test_first_env_skips_blank_values_and_strips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DV_FIRST", "   ")
    monkeypatch.setenv("DV_SECOND", "  resolved  ")
    monkeypatch.setenv("DV_THIRD", "ignored")
    assert first_env("DV_FIRST", "DV_SECOND", "DV_THIRD") == "resolved"


def test_first_env_returns_empty_string_when_nothing_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DV_ABSENT_A", raising=False)
    monkeypatch.delenv("DV_ABSENT_B", raising=False)
    assert first_env("DV_ABSENT_A", "DV_ABSENT_B") == ""


def _like_prefix_matches(escaped_prefix: str, candidate: str) -> bool:
    """Emulate SQL ``LIKE '<escaped_prefix>%' ESCAPE '\\'``."""
    pattern: list[str] = []
    index = 0
    while index < len(escaped_prefix):
        char = escaped_prefix[index]
        if char == "\\":
            index += 1
            pattern.append(re.escape(escaped_prefix[index]))
        elif char == "%":
            pattern.append(".*")
        elif char == "_":
            pattern.append(".")
        else:
            pattern.append(re.escape(char))
        index += 1
    return re.match("".join(pattern), candidate) is not None


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("plain/path", "plain/path"),
        ("clients/my_corp", "clients/my\\_corp"),
        ("50%_off", "50\\%\\_off"),
        ("back\\slash", "back\\\\slash"),
    ],
)
def test_escape_like_neutralises_every_like_metacharacter(raw: str, escaped: str) -> None:
    assert escape_like(raw) == escaped


def test_escape_like_keeps_a_sibling_corpus_out_of_reach() -> None:
    """An unescaped ``_`` in a prefix would match a sibling tenant's rows."""
    escaped = escape_like("clients/my_corp")
    assert _like_prefix_matches(escaped, "clients/my_corp/note.md")
    assert not _like_prefix_matches(escaped, "clients/myXcorp/note.md")

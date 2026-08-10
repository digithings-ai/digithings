"""Unit tests for the response-language directive builder."""

from __future__ import annotations

import pytest

from digigraph.languages import LANGUAGE_NAMES, resolve_language_directive

pytestmark = pytest.mark.unit


def test_language_names_covers_the_curated_list() -> None:
    assert LANGUAGE_NAMES == {
        "en": "English",
        "de": "German",
        "it": "Italian",
        "es": "Spanish",
        "fr": "French",
    }


def test_resolve_language_directive_for_known_non_english_code() -> None:
    directive = resolve_language_directive("de")
    assert directive is not None
    assert "German" in directive


def test_resolve_language_directive_is_case_insensitive() -> None:
    assert resolve_language_directive("DE") == resolve_language_directive("de")


def test_resolve_language_directive_none_for_english() -> None:
    assert resolve_language_directive("en") is None


@pytest.mark.parametrize("bad", [None, "", "  ", "xx", "klingon", "<script>"])
def test_resolve_language_directive_none_for_unknown_or_missing(bad: str | None) -> None:
    assert resolve_language_directive(bad) is None

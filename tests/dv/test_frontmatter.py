"""Frontmatter parse/serialize round-trip tests."""

from __future__ import annotations

import pytest

from digivault import dump_frontmatter, set_keys, split_frontmatter

pytestmark = pytest.mark.unit


def test_split_no_frontmatter() -> None:
    fm, body = split_frontmatter("# Title\n\nbody text\n")
    assert fm == {}
    assert body == "# Title\n\nbody text\n"


def test_split_basic_frontmatter() -> None:
    text = "---\ntitle: DigiGraph\ntags: [module, shipped]\n---\n# DigiGraph\n\nbody\n"
    fm, body = split_frontmatter(text)
    assert fm == {"title": "DigiGraph", "tags": ["module", "shipped"]}
    assert body == "# DigiGraph\n\nbody\n"


def test_unterminated_fence_is_body() -> None:
    text = "---\ntitle: oops\nno closing fence\n"
    fm, body = split_frontmatter(text)
    assert fm == {}
    assert body == text


def test_round_trip_preserves_body_and_keys() -> None:
    text = "---\ntitle: A\nstatus: shipped\n---\n# A\n\nhello\n"
    fm, body = split_frontmatter(text)
    rebuilt = dump_frontmatter(fm, body)
    fm2, body2 = split_frontmatter(rebuilt)
    assert fm2 == fm
    assert body2 == body


def test_dump_empty_frontmatter_returns_body() -> None:
    assert dump_frontmatter({}, "# Just body\n") == "# Just body\n"


def test_set_keys_merges_and_persists() -> None:
    text = "---\ntitle: A\n---\nbody\n"
    out = set_keys(text, {"status": "shipped", "title": "A2"})
    fm, _ = split_frontmatter(out)
    assert fm == {"title": "A2", "status": "shipped"}


def test_set_keys_adds_frontmatter_when_absent() -> None:
    out = set_keys("# Only body\n", {"title": "X"})
    fm, body = split_frontmatter(out)
    assert fm == {"title": "X"}
    assert "# Only body" in body

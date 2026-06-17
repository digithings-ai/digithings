"""Wikilink parse/rewrite tests."""

from __future__ import annotations

import pytest

from digivault import parse_links, rewrite_target
from digivault.wikilinks import map_targets

pytestmark = pytest.mark.unit


def test_parse_plain_link() -> None:
    (link,) = parse_links("see [[digigraph]] for details")
    assert link.target == "digigraph"
    assert link.heading is None
    assert link.alias is None
    assert link.embed is False


def test_parse_heading_alias_and_embed() -> None:
    links = parse_links("[[digigraph#api|the API]] and ![[diagram]]")
    assert links[0].target == "digigraph"
    assert links[0].heading == "api"
    assert links[0].alias == "the API"
    assert links[1].target == "diagram"
    assert links[1].embed is True


def test_links_in_code_are_ignored() -> None:
    text = "real [[one]]\n```\nfake [[two]]\n```\ninline `[[three]]`\n"
    targets = [link.target for link in parse_links(text)]
    assert targets == ["one"]


def test_rewrite_target_preserves_heading_and_alias() -> None:
    text = "[[old#sec|Alias]] and [[old]] and [[keep]]"
    out = rewrite_target(text, "old", "new")
    assert out == "[[new#sec|Alias]] and [[new]] and [[keep]]"


def test_rewrite_does_not_touch_code() -> None:
    text = "[[old]]\n```\n[[old]]\n```\n"
    out = rewrite_target(text, "old", "new")
    assert out == "[[new]]\n```\n[[old]]\n```\n"


def test_map_targets() -> None:
    out = map_targets("[[a]] [[b]]", lambda t: t.upper() if t == "a" else None)
    assert out == "[[A]] [[b]]"

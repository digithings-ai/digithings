"""SKILL.md render/parse round-trip tests."""

from __future__ import annotations

import pytest

from digiskills.frontmatter import parse_skill_md, render_skill_md
from digiskills.models import SkillManifest

pytestmark = pytest.mark.unit


def test_render_starts_with_delimiter() -> None:
    manifest = SkillManifest(name="acme-sdk", description="d")
    text = render_skill_md(manifest, "body")
    assert text.startswith("---\n")


def test_render_parse_round_trip() -> None:
    manifest = SkillManifest(name="acme-sdk", description="How to use the Acme SDK")
    body = "# acme-sdk\n\nDo the thing.\n"
    text = render_skill_md(manifest, body)
    parsed_manifest, parsed_body = parse_skill_md(text)
    assert parsed_manifest == manifest
    assert parsed_body.strip() == body.strip()


def test_render_strips_surrounding_body_newlines() -> None:
    manifest = SkillManifest(name="acme-sdk", description="d")
    text = render_skill_md(manifest, "\n\nbody content\n\n\n")
    _, body = parse_skill_md(text)
    assert body.strip() == "body content"


def test_parse_missing_frontmatter_raises() -> None:
    with pytest.raises(ValueError, match="frontmatter"):
        parse_skill_md("# no frontmatter here\n")


def test_parse_unclosed_frontmatter_raises() -> None:
    with pytest.raises(ValueError, match="closed"):
        parse_skill_md("---\nname: x\ndescription: y\n")

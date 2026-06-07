"""Unit tests for digiquant.olympus.atlas.skills."""

from __future__ import annotations


import pytest

from digiquant.olympus.atlas.skills import (
    MalformedFrontmatterError,
    SkillNotFoundError,
    _split_frontmatter,
    list_skill_slugs,
    load_skill,
    load_skill_with_frontmatter,
)


@pytest.mark.unit
class TestSkillLoader:
    def test_load_real_skill_strips_frontmatter(self) -> None:
        """The orchestrator skill ships with YAML frontmatter; body must not include it."""
        body = load_skill("orchestrator")
        assert body  # non-empty
        assert not body.startswith("---")
        # Orchestrator SKILL.md's first heading is the title; frontmatter's
        # ``name`` / ``description`` keys must not leak into the body.
        assert "name: market-orchestrator" not in body

    def test_frontmatter_exposes_name_and_description(self) -> None:
        meta, body = load_skill_with_frontmatter("orchestrator")
        assert meta.get("name") == "market-orchestrator"
        assert isinstance(meta.get("description"), str)
        assert body

    def test_missing_skill_raises_clear_error(self) -> None:
        with pytest.raises(SkillNotFoundError):
            load_skill("nonexistent-skill-slug")

    def test_list_slugs_includes_known_skills(self) -> None:
        slugs = list_skill_slugs()
        # A stable subset we know ships today.
        for expected in ("orchestrator", "macro", "equity", "daily-delta"):
            assert expected in slugs, f"{expected!r} missing from list_skill_slugs()"

    def test_load_skill_is_cached(self) -> None:
        """Second call returns the same object (lru_cache)."""
        a = load_skill("orchestrator")
        b = load_skill("orchestrator")
        assert a is b


@pytest.mark.unit
class TestSplitFrontmatter:
    """Exercise _split_frontmatter directly with in-memory strings — no disk setup."""

    def test_no_frontmatter_returns_empty_meta(self) -> None:
        raw = "# Plain markdown\n\nNo frontmatter here.\n"
        meta, body = _split_frontmatter(raw)
        assert meta == {}
        assert body == raw

    def test_well_formed_frontmatter_parses(self) -> None:
        raw = "---\nname: x\ndescription: y\n---\n# Body\n"
        meta, body = _split_frontmatter(raw)
        assert meta == {"name": "x", "description": "y"}
        assert body.startswith("# Body")

    def test_unclosed_fence_raises(self) -> None:
        """Opening --- without a closing fence used to silently fall back;
        now it must raise so the authoring error is visible."""
        raw = "---\nname: oops\nno_close_fence\n"
        with pytest.raises(MalformedFrontmatterError, match="closing fence"):
            _split_frontmatter(raw)

    def test_non_mapping_yaml_raises(self) -> None:
        """A YAML list (not dict) between fences is not valid frontmatter."""
        raw = "---\n- one\n- two\n---\nbody\n"
        with pytest.raises(MalformedFrontmatterError, match="YAML mapping"):
            _split_frontmatter(raw)

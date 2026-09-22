"""Unit tests for digiquant.research.skills."""

from __future__ import annotations

import pytest
from digiquant.research.skills import (
    MalformedFrontmatterError,
    SkillNotFoundError,
    _split_frontmatter,
    list_skill_slugs,
    load_skill,
    load_skill_edit,
    load_skill_with_frontmatter,
)


@pytest.mark.unit
class TestSkillLoader:
    def test_load_real_skill_strips_frontmatter(self) -> None:
        """The equity skill ships with YAML frontmatter; body must not include it."""
        body = load_skill("equity")
        assert body  # non-empty
        assert not body.startswith("---")
        assert "name: market-equity" not in body

    def test_frontmatter_exposes_name_and_description(self) -> None:
        meta, body = load_skill_with_frontmatter("equity")
        assert meta.get("name") == "market-equity"
        assert isinstance(meta.get("description"), str)
        assert body

    def test_missing_skill_raises_clear_error(self) -> None:
        with pytest.raises(SkillNotFoundError):
            load_skill("nonexistent-skill-slug")

    def test_list_slugs_includes_known_skills(self) -> None:
        slugs = list_skill_slugs()
        # A stable subset we know ships today.
        for expected in ("macro", "equity", "digest", "decision-reflector"):
            assert expected in slugs, f"{expected!r} missing from list_skill_slugs()"

    def test_load_skill_is_cached(self) -> None:
        """Second call returns the same object (lru_cache)."""
        a = load_skill("equity")
        b = load_skill("equity")
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


@pytest.mark.unit
class TestToolUseContract:
    """The prompt/tool-contract boundary appended to every skill (#4490).

    The defect these pin: a segment whose wired surface is only the pre-fetched
    ``web_grounding`` block plus ``query_research``/``fetch_prior_document`` read a skill
    telling it to go fetch six things it has no tool for, then re-phrased the same query
    until ``run_tools`` exhausted its 24-round budget (2621 s for ``alt-sentiment-news``).
    """

    def test_contract_present_on_full_skill(self) -> None:
        for slug in ("alt-sentiment-news", "commodities", "international", "equity"):
            assert "## Tools (read this before you plan a single call)" in load_skill(slug)

    def test_contract_names_this_segment(self) -> None:
        """`{slug}` must be substituted — the segment needs to know which document is its own."""
        body = load_skill("alt-sentiment-news")
        contract = body[body.index("## Tools") : body.index("## Research memo")]
        assert "alt-sentiment-news" in contract
        assert "{slug}" not in contract

    def test_contract_reaches_the_edit_path_too(self) -> None:
        """#4490: the same fiction appears in the ``-edit.md`` variants; the contract is
        appended at the load chokepoint so both paths get it."""
        body = load_skill_edit("alt-sentiment-news")
        assert "## Tools (read this before you plan a single call)" in body
        assert "{slug}" not in body

    def test_contract_imposes_no_limits(self) -> None:
        """The owner's constraint: fix convergence with instruction, not caps. Guard against
        a future edit smuggling a time or tool-call limit back in."""
        contract = load_skill("commodities")
        contract = contract[contract.index("## Tools") : contract.index("## Research memo")]
        lowered = contract.lower()
        for banned in ("call limit", "tool-call limit", "time limit", "minute limit", "budget of"):
            assert banned not in lowered, f"contract must not impose {banned!r}"

    def test_contract_states_the_run_date_document_does_not_exist(self) -> None:
        contract = load_skill("macro")
        contract = contract[contract.index("## Tools") : contract.index("## Research memo")]
        assert "does not exist yet" in contract

"""The portfolio tool-use contract (#4524).

One portfolio asset-analyst worker (ticker LQD) looped to ``run_tools``' 24-round cap for
~59 minutes on the 2026-09-22 pipeline run (job 106686465693): it started at 12:02:24,
never logged ``analyst-worker … done`` while nine sibling tickers did, no ``[7/10 …]``
marker followed, and the attempt ended ``exhausted max_tool_rounds=24`` before the run hit
its 230-minute step timeout. This is the portfolio-side counterpart of #4490: the loader
told the model nothing about its toolset, so it kept re-querying stored rows.

The fix is a contract appended at the single portfolio skills load chokepoint, gated to the
skills whose turn is actually bound to tools. It introduces NO time limit and NO tool-call
limit (m1064); the guard rail is "use as many calls as the work genuinely needs, then
converge".
"""

from __future__ import annotations

import re

import pytest
from digiquant.portfolio.skills import (
    PORTFOLIO_TOOL_USE_CONTRACT,
    SkillNotFoundError,
    load_skill,
    load_skill_edit,
    load_skill_full,
)

pytestmark = pytest.mark.unit

HEADING = "## Tools (read this before you plan a single call)"

# `tools=tools` is passed for these by the phase that loads them.
TOOL_GROUNDED_SKILLS = (
    "asset-analyst",
    "deliberation",
    "deliberation-analyst-response",
    "market-thesis-exploration",
    "pm-allocation-memo",
    "pm-direction",
    "pm-rebalance-decision",
    "portfolio-manager",
    "risk-aggressive",
    "risk-conservative",
    "thesis",
    "thesis-vehicle-map",
)
# Loaded without tools: coverage-director passes ``tools=None``; pipeline-evolution is
# tool-less. Claiming a toolset for either would be the #4490 review's major finding.
TOOL_LESS_SKILLS = ("coverage-director", "pipeline-evolution")

DEBATE_SKILLS = ("deliberation", "deliberation-analyst-response")


def _loaded(slug: str) -> dict[str, str]:
    """Every loader output that exists for ``slug``.

    Not every slug has all three files — ``deliberation-analyst-response`` resolves only
    through its family ``*-full.md``, and ``coverage-director`` ships no ``SKILL.md``.
    """
    out: dict[str, str] = {}
    for name, loader in (
        ("skill", load_skill),
        ("full", load_skill_full),
        ("edit", load_skill_edit),
    ):
        try:
            out[name] = loader(slug)
        except SkillNotFoundError:
            continue
    assert out, f"no loader resolves {slug!r}"
    return out


class TestContractReachesToolGroundedSkills:
    @pytest.mark.parametrize("slug", TOOL_GROUNDED_SKILLS)
    def test_full_skill_carries_the_contract(self, slug: str) -> None:
        assert HEADING in load_skill_full(slug)

    @pytest.mark.parametrize("slug", TOOL_GROUNDED_SKILLS)
    def test_default_skill_carries_the_contract(self, slug: str) -> None:
        loaded = _loaded(slug)
        if "skill" not in loaded:
            pytest.skip(f"{slug} ships no SKILL.md")
        assert HEADING in loaded["skill"]

    def test_edit_skill_carries_the_contract(self) -> None:
        assert HEADING in load_skill_edit("asset-analyst")

    def test_exported_constant_is_the_appended_block(self) -> None:
        body = load_skill_full("asset-analyst")
        assert PORTFOLIO_TOOL_USE_CONTRACT in body


class TestGateIsPinned:
    def test_gate_is_exactly_the_documented_set(self) -> None:
        """A new tool-grounded portfolio skill must be a deliberate gate addition.

        The gate is an allowlist, so a missed skill would silently keep looping; pinning it
        here means the omission fails a test instead of a production run.
        """
        from digiquant.portfolio.skills import _TOOL_CONTRACT_SKILLS

        assert _TOOL_CONTRACT_SKILLS == frozenset(TOOL_GROUNDED_SKILLS)


class TestContractScope:
    @pytest.mark.parametrize("slug", TOOL_LESS_SKILLS)
    def test_tool_less_skills_do_not_carry_it(self, slug: str) -> None:
        for text in _loaded(slug).values():
            assert HEADING not in text


class TestContractSaysWhatMakesItConverge:
    def test_states_repeat_calls_return_the_same_rows(self) -> None:
        lowered = PORTFOLIO_TOOL_USE_CONTRACT.lower()
        assert "the same rows" in lowered
        assert "cannot surface a row" in lowered
        # Live enrichment tools are cached, so re-calling them is not a way to get more.
        assert "are cached" in lowered
        assert "empty result is an answer" in lowered

    def test_states_the_toolset_is_the_request_schemas(self) -> None:
        lowered = PORTFOLIO_TOOL_USE_CONTRACT.lower()
        assert "this request's tool schemas" in lowered
        assert "no shell" in lowered

    def test_states_converge(self) -> None:
        lowered = PORTFOLIO_TOOL_USE_CONTRACT.lower()
        assert "converge" in lowered
        assert "does not add evidence" in lowered or "do not add evidence" in lowered

    def test_imposes_no_time_or_tool_call_limit(self) -> None:
        lowered = PORTFOLIO_TOOL_USE_CONTRACT.lower()
        for banned in ("call limit", "tool-call limit", "time limit", "minute limit", "budget of"):
            assert banned not in lowered, f"contract must not impose {banned!r}"
        cap = re.search(
            r"\b(?:max(?:imum)?|at most|no more than|up to)\b[^.]{0,60}"
            r"\b(?:calls?|tools?|rounds?|minutes?|seconds?)\b",
            lowered,
        )
        assert cap is None, f"contract must not cap the work: {cap!r}"


class TestContractIsTrueHere:
    def test_does_not_reuse_the_research_only_claim(self) -> None:
        # The research contract says today's document does not exist yet. On the
        # portfolio side the inputs carry the run's own material, so that claim is false.
        assert "does not exist yet" not in PORTFOLIO_TOOL_USE_CONTRACT.lower()

    def test_no_unsubstituted_placeholders(self) -> None:
        assert re.search(r"\{[A-Za-z_]+\}", PORTFOLIO_TOOL_USE_CONTRACT) is None


class TestDebateTurnsKeepTheirOwnContract:
    @pytest.mark.parametrize("slug", DEBATE_SKILLS)
    def test_exactly_one_tool_heading(self, slug: str) -> None:
        assert load_skill_full(slug).count(HEADING) == 1

    @pytest.mark.parametrize("slug", DEBATE_SKILLS)
    def test_debate_contract_is_the_one_appended(self, slug: str) -> None:
        body = load_skill_full(slug)
        assert PORTFOLIO_TOOL_USE_CONTRACT not in body
        assert "This is a conversation" in body

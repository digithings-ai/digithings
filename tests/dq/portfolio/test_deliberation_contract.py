"""Pins the deliberation turn contract appended by ``portfolio.skills`` (#4513).

The cheap house model emitted PARTIAL ``forecast_amendment`` payloads — omitting
``thesis_valid_probability`` / ``raw_uncertainty`` / ``bear_return``, and inventing keys such
as ``conditional_entry`` and ``convision_score``. ``_resolve_forecast_amendment`` validates an
amendment as a complete ``ForecastTerms`` and hard-fails (#3078), so the whole debate was
discarded and the ticker silently carried the analyst stance (prod 2026-09-22: SPY, ETH-USD,
TLT, UUP). The deliberation skills never mentioned the field at all, and the model receives no
schema field list because the model field is an untyped ``dict[str, Any]``.

The contract closes that prompt gap at the single load chokepoint, the same way
``EDIT_SCHEMA_CONSTRAINTS`` (portfolio) and ``TOOL_USE_CONTRACT`` (research) are appended: it
cannot drift between the two debate skills.
"""

from __future__ import annotations

import re

import pytest
from digiquant.portfolio.models.forecast import ForecastTerms
from digiquant.portfolio.skills import (
    DELIBERATION_AMENDMENT_CONTRACT,
    DELIBERATION_TOOL_USE_CONTRACT,
    load_skill_full,
)

pytestmark = pytest.mark.unit

DELIBERATION_SLUGS = ("deliberation", "deliberation-analyst-response")

# Skills that must NOT receive the debate contract: ``forecast_amendment`` only exists on the
# two deliberation turn models, and not all of these are tool-grounded
# (``pipeline-evolution`` loads without tools), so the tool claims would be false there.
# Mirrors the #4490 review finding.
NON_DEBATE_SLUGS = (
    "asset-analyst",
    "coverage-director",
    "pm-direction",
    "pipeline-evolution",
)


def _required_terms_fields() -> list[str]:
    return [name for name, field in ForecastTerms.model_fields.items() if field.is_required()]


class TestAmendmentContractReachesTheDebate:
    @pytest.mark.parametrize("slug", DELIBERATION_SLUGS)
    def test_contract_appended(self, slug: str) -> None:
        body = load_skill_full(slug)
        assert "## Forecast amendment" in body
        assert "## Tools (read this before you plan a single call)" in body

    @pytest.mark.parametrize("slug", DELIBERATION_SLUGS)
    def test_contract_names_every_required_field(self, slug: str) -> None:
        body = load_skill_full(slug)
        missing = [name for name in _required_terms_fields() if f"``{name}``" not in body]
        assert missing == []

    def test_contract_covers_the_observed_production_failures(self) -> None:
        # The exact fields the 2026-09-22 run omitted, and the keys it invented.
        body = load_skill_full("deliberation-analyst-response")
        for field in ("thesis_valid_probability", "raw_uncertainty", "bear_return", "base_return"):
            assert f"``{field}``" in body
        assert "conditional_entry" in body
        assert "convision_score" in body

    @pytest.mark.parametrize("slug", DELIBERATION_SLUGS)
    def test_contract_states_omit_when_unchanged(self, slug: str) -> None:
        lowered = load_skill_full(slug).lower()
        assert "omit the field" in lowered
        assert "complete replacement" in lowered

    @pytest.mark.parametrize("slug", DELIBERATION_SLUGS)
    def test_contract_states_the_economics_rules(self, slug: str) -> None:
        body = load_skill_full(slug)
        assert "bear <= base <= bull" in body
        assert "exactly" in body
        assert "1.0" in body
        assert "renormalis" in body

    @pytest.mark.parametrize("slug", DELIBERATION_SLUGS)
    def test_tenor_is_identity_not_new_economics(self, slug: str) -> None:
        body = load_skill_full(slug)
        assert "copies them from the analyst's base forecast" in body
        assert "trading sessions" in body


class TestContractScope:
    @pytest.mark.parametrize("slug", NON_DEBATE_SLUGS)
    def test_not_appended_to_other_skills(self, slug: str) -> None:
        body = load_skill_full(slug)
        assert "## Forecast amendment" not in body
        assert "## Tools (read this before you plan a single call)" not in body

    def test_constants_are_the_appended_blocks(self) -> None:
        body = load_skill_full("deliberation")
        assert DELIBERATION_AMENDMENT_CONTRACT in body
        assert DELIBERATION_TOOL_USE_CONTRACT in body


class TestContractImposesNoLimits:
    @pytest.mark.parametrize("slug", DELIBERATION_SLUGS)
    def test_no_time_or_call_limit(self, slug: str) -> None:
        lowered = load_skill_full(slug).lower()
        for banned in ("call limit", "tool-call limit", "time limit", "minute limit", "budget of"):
            assert banned not in lowered, f"contract must not impose {banned!r}"


class TestToolContractIsTrueForPortfolio:
    @pytest.mark.parametrize("slug", DELIBERATION_SLUGS)
    def test_does_not_reuse_the_research_only_claim(self, slug: str) -> None:
        # The research contract's "your document does not exist yet" claim is FALSE here: the
        # analyst document for today is written earlier in the same run.
        assert "does not exist yet" not in load_skill_full(slug).lower()

    @pytest.mark.parametrize("slug", DELIBERATION_SLUGS)
    def test_tool_contract_has_no_format_placeholders(self, slug: str) -> None:
        # Appended verbatim (unlike research's ``{slug}`` template), so a brace here would be an
        # authoring error waiting for a downstream ``.format``.
        assert re.search(r"\{[A-Za-z_]+\}", load_skill_full(slug)) is None

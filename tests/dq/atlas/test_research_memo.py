"""ResearchMemo envelope (WP-C): markdown body, not SegmentReport JSON slots."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.olympus.atlas.segments import ResearchMemo, Source
from digiquant.olympus.atlas.skills import RESEARCH_MEMO_RULES, load_skill, load_skill_edit

pytestmark = pytest.mark.unit


def test_research_memo_accepts_markdown_body_and_optional_sources() -> None:
    memo = ResearchMemo(
        segment="alt-sentiment-news",
        date=date(2026, 8, 31),
        body=(
            "# Sentiment — 2026-08-31\n\n"
            "## Headlines\n\n"
            "Risk appetite faded after [Powell remarks](https://www.federalreserve.gov/).\n"
        ),
        sources=[Source(id="fed", title="Powell", url="https://www.federalreserve.gov/")],
        internal_bias="bearish",
    )
    dumped = memo.model_dump()
    assert dumped["body"].startswith("# Sentiment")
    assert "Powell remarks" in dumped["body"]
    assert dumped["internal_bias"] == "bearish"
    assert "bias" not in ResearchMemo.model_fields
    assert "headline" not in ResearchMemo.model_fields
    assert "material_findings" not in ResearchMemo.model_fields
    assert "data_quality" not in ResearchMemo.model_fields
    assert "confidence" not in ResearchMemo.model_fields


def test_research_memo_internal_bias_is_optional_and_not_required() -> None:
    memo = ResearchMemo(segment="bonds", date=date(2026, 8, 31), body="## Curve\n\nSteepening.")
    assert memo.internal_bias is None
    assert memo.sources == []


def test_legacy_segment_report_row_composes_a_body_for_edit_merge() -> None:
    """Historical library rows have headline/findings/notes, not `body`."""
    prior = {
        "segment": "bonds",
        "date": "2026-06-12",
        "bias": "neutral",
        "headline": "Curve steepens as front-end yields ease.",
        "material_findings": [
            {
                "label": "CTAs short USTs",
                "summary": "Systematic funds hold short duration.",
                "source_ids": ["1"],
            }
        ],
        "sources": [{"id": "1", "title": "Rates wrap", "url": "https://example.com/rates"}],
        "notes": "No spread data retrieved.",
        "data_quality": "medium",
        "confidence": 0.7,
        "yield_curve_shape": "steepening",
    }
    memo = ResearchMemo.model_validate(prior)
    assert "Curve steepens" in memo.body
    assert "CTAs short USTs" in memo.body
    assert "No spread data retrieved." in memo.body
    assert memo.internal_bias == "neutral"
    assert memo.segment == "bonds"


def test_empty_body_is_valid_for_absent_stubs() -> None:
    memo = ResearchMemo(segment="inst-institutional-flows", date=date(2026, 8, 31), body="")
    assert memo.body == ""


def test_loaded_skills_instruct_markdown_not_fake_metrics() -> None:
    body = load_skill("alt-sentiment-news")
    assert RESEARCH_MEMO_RULES in body
    lowered = RESEARCH_MEMO_RULES.lower()
    assert "markdown" in lowered
    assert "signals" in lowered
    assert "data-quality" in lowered or "data_quality" in lowered
    assert "confidence" in lowered


def test_edit_skills_also_carry_research_memo_rules() -> None:
    body = load_skill_edit("bonds")
    assert RESEARCH_MEMO_RULES in body

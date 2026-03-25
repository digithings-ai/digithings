"""Golden fixture: ResearchBrief validates without a live LLM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from digigraph.research_brief_models import ResearchBrief


@pytest.mark.unit
def test_research_brief_golden_fixture() -> None:
    path = Path(__file__).resolve().parent.parent / "fixtures" / "research_brief_golden.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    brief = ResearchBrief.model_validate(data)
    assert brief.themes and brief.themes[0].source_ids
    assert "GC" in brief.suggested_symbols


@pytest.mark.unit
def test_profiling_questions_merge() -> None:
    from digigraph.trading_profile import profiling_questions_for_workflow

    brief = ResearchBrief(profiling_questions=["Custom Q?"])
    qs = profiling_questions_for_workflow(brief, {})
    assert "Custom Q?" in qs

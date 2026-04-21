"""Integration tests for Phase 1 + Phase 2 wiring.

Uses a fake LLM (patches ``digigraph.graph.research_agent.chat_completion``
at the module boundary) so no network calls. Verifies:
- Each phase-1 / phase-2 node produces a validated SegmentPayload.
- Fan-out topology actually calls all segments in a phase.
- Output dicts key by segment slug.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa: F401 — used for fake-completion dict shape
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant_atlas.phases.phase1_altdata import (
    CtaPositioningReport,
    OptionsDerivativesReport,
    PoliticianSignalsReport,
    SentimentNewsReport,
    build_phase1,
)
from digiquant_atlas.phases.phase2_institutional import (
    HedgeFundIntelReport,
    InstitutionalFlowsReport,
    build_phase2,
)
from digiquant_atlas.state import AtlasResearchState


def _make_fake_completion_for_model(model_cls: type[BaseModel]) -> str:
    """Return JSON satisfying ``model_cls`` with minimum required fields."""
    payload: dict[str, Any] = {
        "segment": "test-segment",
        "date": "2026-04-20",
        "bias": "neutral",
        "headline": "Test headline",
        "material_findings": [],
        "sources": [],
        "notes": "",
    }
    # Segment-specific extensions: all optional, so the base is sufficient.
    return json.dumps(payload)


def _dispatch_fake_completion(_model: str, messages: list[dict[str, Any]], **_: Any) -> str:
    """Route the fake LLM response based on which output schema is in the user message.

    run_research_agent encodes the schema's class name into the user content;
    we inspect that to return a payload that fits the right model.
    """
    user_block = messages[1]["content"]
    # user_block is a list of content parts; the schema part is the last one.
    schema_part = next(
        (p for p in user_block if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")),
        None,
    )
    assert schema_part is not None, "fake completion could not locate OUTPUT_SCHEMA block"
    schema_text = schema_part["text"]
    # Map the class name to its model for validation.
    for cls in (
        SentimentNewsReport,
        CtaPositioningReport,
        OptionsDerivativesReport,
        PoliticianSignalsReport,
        InstitutionalFlowsReport,
        HedgeFundIntelReport,
    ):
        if cls.__name__ in schema_text:
            return _make_fake_completion_for_model(cls)
    raise AssertionError("no known model referenced in OUTPUT_SCHEMA block")


@pytest.mark.unit
class TestPhase1AltData:
    def test_fan_out_produces_four_segments(self) -> None:
        compiled = build_pipeline(AtlasResearchState, [build_phase1()])
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        with patch(
            "digigraph.graph.research_agent.chat_completion",
            side_effect=_dispatch_fake_completion,
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        # All four segment slugs present.
        assert set(final.phase1_outputs.keys()) == {
            "alt-sentiment-news",
            "alt-cta-positioning",
            "alt-options-derivatives",
            "alt-politician-signals",
        }
        # Each slot carries a fresh payload (not Carried).
        for slot in final.phase1_outputs.values():
            assert slot.payload.source == "today"
            assert slot.payload.body["headline"] == "Test headline"


@pytest.mark.unit
class TestPhase2Institutional:
    def test_fan_out_produces_two_segments(self) -> None:
        compiled = build_pipeline(AtlasResearchState, [build_phase2()])
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        with patch(
            "digigraph.graph.research_agent.chat_completion",
            side_effect=_dispatch_fake_completion,
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        assert set(final.phase2_outputs.keys()) == {
            "inst-institutional-flows",
            "inst-hedge-fund-intel",
        }
        for slot in final.phase2_outputs.values():
            assert slot.payload.source == "today"


@pytest.mark.unit
class TestChainedPhases:
    def test_phase1_then_phase2_sequential(self) -> None:
        """Phases run sequentially; phase 2 starts only after all of phase 1."""
        compiled = build_pipeline(
            AtlasResearchState,
            [build_phase1(), build_phase2()],
        )
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        with patch(
            "digigraph.graph.research_agent.chat_completion",
            side_effect=_dispatch_fake_completion,
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        assert len(final.phase1_outputs) == 4
        assert len(final.phase2_outputs) == 2

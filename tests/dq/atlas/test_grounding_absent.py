"""Grounding-absent flag for web-search-dependent segments (#946).

A segment whose ``SegmentNodeSpec`` declares ``live_search=True`` (or
``ai_portfolios=True``) but receives no ``web_grounding`` from
``build_grounding`` must have ``grounding_absent=True`` injected into its
``phase_inputs`` so downstream output is honestly labeled low-confidence
rather than fabricated.  Mirrors the Phase 2 institutional circuit-breaker
pattern (#928).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa  # scored-lint suppression: heterogeneous fake message/dict shapes
from unittest.mock import patch

import pytest

from digiquant.olympus.atlas.phases._node_factory import (
    SegmentNodeSpec,
    build_segment_node,
)
from digiquant.olympus.atlas.segments import SegmentReport
from digiquant.olympus.atlas.state import AtlasResearchState


class _MinimalReport(SegmentReport):
    pass


_SPEC_LIVE = SegmentNodeSpec(
    segment_slug="test-live",
    skill_slug="alt-sentiment-news",
    output_model=_MinimalReport,
    phase_outputs_field="phase1_outputs",
    live_search=True,
)

_SPEC_NO_SEARCH = SegmentNodeSpec(
    segment_slug="test-no-search",
    skill_slug="alt-options-derivatives",
    output_model=_MinimalReport,
    phase_outputs_field="phase1_outputs",
    live_search=False,
)

_SPEC_FALLBACK = SegmentNodeSpec(
    segment_slug="test-fallback",
    skill_slug="macro",
    output_model=_MinimalReport,
    phase_outputs_field="phase1_outputs",
    live_search=True,
    live_search_is_fallback=True,
    use_data_tools=True,
)


def _state() -> AtlasResearchState:
    return AtlasResearchState(run_type="baseline", run_date=date(2026, 6, 20))


def _fake_completion(_model: str, messages: list[dict[str, Any]], **_: Any) -> str:
    return json.dumps(
        {
            "segment": "test",
            "date": "2026-06-20",
            "bias": "neutral",
            "headline": "test",
            "material_findings": [],
            "sources": [],
            "notes": "",
        }
    )


@pytest.mark.unit
class TestGroundingAbsentFlag:
    """The ``grounding_absent`` flag in phase_inputs."""

    def _run_capturing(self, spec: SegmentNodeSpec, web_grounding: dict | None) -> dict:
        """Build a segment node, patch grounding + the LLM call, capture phase_inputs."""
        captured: dict[str, Any] = {}

        def _fake_research_agent(
            skill_text: str,
            phase_inputs: dict,
            shared_context: dict,
            output_model: type,
            **kwargs: Any,
        ) -> Any:
            captured.update(phase_inputs)
            return output_model.model_validate(
                {
                    "segment": spec.segment_slug,
                    "date": "2026-06-20",
                    "bias": "neutral",
                    "headline": "test",
                    "material_findings": [],
                    "sources": [],
                    "notes": "",
                }
            )

        node = build_segment_node(spec)
        with (
            patch(
                "digiquant.olympus.atlas.phases._node_factory.build_grounding",
                return_value=(None, None, web_grounding),
            ),
            patch(
                "digiquant.olympus.atlas.phases._node_factory.run_research_agent",
                side_effect=_fake_research_agent,
            ),
        ):
            node(_state())

        return captured

    def test_live_search_with_no_grounding_sets_flag(self) -> None:
        """A live_search=True segment whose web_grounding resolves to None
        must have ``grounding_absent=True`` in its phase_inputs."""
        captured = self._run_capturing(_SPEC_LIVE, web_grounding=None)
        assert captured.get("grounding_absent") is True

    def test_live_search_with_grounding_does_not_set_flag(self) -> None:
        """A live_search=True segment that receives real web_grounding
        must NOT have ``grounding_absent`` set."""
        grounding = {"summary": "some grounding", "citations": []}
        captured = self._run_capturing(_SPEC_LIVE, web_grounding=grounding)
        assert captured.get("grounding_absent") is not True

    def test_no_search_segment_never_sets_flag(self) -> None:
        """A segment without live_search/ai_portfolios never gets the flag,
        even when web_grounding is None."""
        captured = self._run_capturing(_SPEC_NO_SEARCH, web_grounding=None)
        assert "grounding_absent" not in captured

    def test_fallback_segment_no_grounding_does_not_set_flag(self) -> None:
        """A ``live_search_is_fallback`` segment (e.g. macro, #711) is grounded by its
        primary ingested-data layer; the paid web_search is a stale-only supplement that is
        skipped on the fresh-data hot path. Its absence is NOT an ungrounded segment, so
        ``grounding_absent`` must not be flagged (it would wrongly tell the analyst to lower
        conviction despite fresh FRED data)."""
        captured = self._run_capturing(_SPEC_FALLBACK, web_grounding=None)
        assert "grounding_absent" not in captured

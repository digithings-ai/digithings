"""Phase 2 institutional circuit-breaker (#928).

Jun 17–19 prod ran the institutional LLM + live web search yet produced zero
``inst-*`` documents (no ingest). These tests pin the breaker: on a DELTA run
whose institutional layer has been absent for ``>= 3`` consecutive runs, the
``inst-*`` nodes skip their paid LLM/search and emit a deterministic "absent"
stub with zero search spend; baseline always runs Phase 2 fully; a delta with
a fresh institutional layer runs Phase 2 fully.

The "absent" path asserts the research agent (and therefore the web-search
grounding pre-pass) is never invoked — that is the cost the breaker exists to
cut.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa: F401 — fake-completion dict shape
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.olympus.atlas.diagnostics import summarize_run
from digiquant.olympus.atlas.phases.phase2_institutional import (
    ABSENCE_BREAKER_THRESHOLD,
    INST_ABSENT_REASON,
    HedgeFundIntelReport,
    InstitutionalFlowsReport,
    build_phase2,
)
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    DataLayerSnapshot,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

_INST_SLUGS = {"inst-institutional-flows", "inst-hedge-fund-intel"}


def _fake_completion(_model: str, messages: list[dict[str, Any]], **_: Any) -> str:
    """Minimal valid institutional report; routes by the schema in the user block."""
    user_block = messages[1]["content"]
    schema_part = next(
        (p for p in user_block if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")),
        None,
    )
    assert schema_part is not None
    schema_text = schema_part["text"]
    for cls in (InstitutionalFlowsReport, HedgeFundIntelReport):
        if cls.__name__ in schema_text:
            return json.dumps(
                {
                    "segment": "inst",
                    "date": "2026-06-20",
                    "bias": "neutral",
                    "headline": "Fresh institutional read",
                    "material_findings": [],
                    "sources": [],
                    "notes": "",
                }
            )
    raise AssertionError("no institutional model in OUTPUT_SCHEMA block")


def _data_layer(streak: int) -> DataLayerSnapshot:
    return DataLayerSnapshot(
        institutional_absence_streak=streak,
        institutional_data_available=streak == 0,
    )


def _invoke_phase2(state: AtlasResearchState) -> AtlasResearchState:
    compiled = build_pipeline(AtlasResearchState, [build_phase2()])
    with (
        patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=_fake_completion,
        ) as agent_call,
        patch("digiquant.olympus.atlas.data.web_grounding.fetch_web_grounding") as web_search,
    ):
        result = compiled.invoke(state)
        state.__dict__["_agent_call"] = agent_call
        state.__dict__["_web_search"] = web_search
    final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result
    final.__dict__["_agent_call"] = state.__dict__["_agent_call"]
    final.__dict__["_web_search"] = state.__dict__["_web_search"]
    return final


@pytest.mark.unit
class TestPhase2CircuitBreaker:
    def test_delta_absent_for_threshold_runs_skips_with_zero_search(self) -> None:
        """Delta + streak >= 3 → inst-* skipped, deterministic absent stub, no search."""
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            baseline_date=date(2026, 6, 14),
            data_layer=_data_layer(ABSENCE_BREAKER_THRESHOLD),
        )
        final = _invoke_phase2(state)

        assert set(final.phase2_outputs) == _INST_SLUGS
        for slug, slot in final.phase2_outputs.items():
            # Deterministic absent stub (fresh 'today' slot, not a baseline carry).
            assert slot.payload.source == "today"
            body = slot.payload.body
            assert body["data_quality"] == "absent"
            assert body["bias"] == "neutral"
            assert body["material_findings"] == []
            assert body["circuit_breaker"] == INST_ABSENT_REASON
            assert INST_ABSENT_REASON in body["notes"]
            assert slot.payload.segment == slug

        # Zero LLM spend AND zero search spend — the whole point of the breaker.
        assert final.__dict__["_agent_call"].call_count == 0
        assert final.__dict__["_web_search"].call_count == 0

    def test_delta_absent_records_skip_reason_in_diagnostics(self) -> None:
        """Diagnostics breakdown records that inst-* skipped, with the reason."""
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            baseline_date=date(2026, 6, 14),
            data_layer=_data_layer(ABSENCE_BREAKER_THRESHOLD + 2),
        )
        final = _invoke_phase2(state)

        summary = summarize_run(final)
        phase2 = summary.breakdown["phase2_outputs"]
        skips = phase2["circuit_breaker_skips"]
        assert set(skips) == _INST_SLUGS
        assert all(reason == INST_ABSENT_REASON for reason in skips.values())

    def test_baseline_runs_phase2_fully_regardless_of_streak(self) -> None:
        """Baseline always runs Phase 2 fully — even with a long absence streak."""
        state = AtlasResearchState(
            run_type="baseline",
            run_date=date(2026, 6, 20),
            data_layer=_data_layer(ABSENCE_BREAKER_THRESHOLD + 5),
        )
        final = _invoke_phase2(state)

        assert set(final.phase2_outputs) == _INST_SLUGS
        for slot in final.phase2_outputs.values():
            assert slot.payload.source == "today"
            assert slot.payload.body.get("circuit_breaker") is None
            assert slot.payload.body["headline"] == "Fresh institutional read"
        # Full run → the research agent was actually called for each segment.
        assert final.__dict__["_agent_call"].call_count == len(_INST_SLUGS)

    def test_delta_fresh_layer_runs_phase2(self) -> None:
        """Delta + streak 0 (layer fresh) → Phase 2 runs fully."""
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            baseline_date=date(2026, 6, 14),
            data_layer=_data_layer(0),
        )
        final = _invoke_phase2(state)

        assert set(final.phase2_outputs) == _INST_SLUGS
        for slot in final.phase2_outputs.values():
            assert slot.payload.source == "today"
            assert slot.payload.body.get("circuit_breaker") is None
        assert final.__dict__["_agent_call"].call_count == len(_INST_SLUGS)

    def test_delta_just_below_threshold_runs_phase2(self) -> None:
        """Delta + streak == threshold-1 → not yet tripped, Phase 2 runs."""
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            baseline_date=date(2026, 6, 14),
            data_layer=_data_layer(ABSENCE_BREAKER_THRESHOLD - 1),
        )
        final = _invoke_phase2(state)

        for slot in final.phase2_outputs.values():
            assert slot.payload.body.get("circuit_breaker") is None
        assert final.__dict__["_agent_call"].call_count == len(_INST_SLUGS)


@pytest.mark.unit
class TestInstitutionalAbsenceStreak:
    """Unit tests for the pre-flight probe that feeds the breaker."""

    def _docs(self, *rows: tuple[str, str]) -> list[dict[str, str]]:
        return [{"date": d, "document_key": k} for d, k in rows]

    def test_no_documents_returns_zero(self) -> None:
        from digiquant.olympus.atlas.supabase_io import query_institutional_absence_streak

        client = FakeSupabaseClient(canned_reads={"documents": []})
        streak = query_institutional_absence_streak(client=client, run_date=date(2026, 6, 20))
        assert streak == 0

    def test_three_consecutive_absent_runs(self) -> None:
        from digiquant.olympus.atlas.supabase_io import query_institutional_absence_streak

        # Three recent run-dates published other docs but no inst-*; an older one did.
        docs = self._docs(
            ("2026-06-19", "macro"),
            ("2026-06-18", "equity"),
            ("2026-06-17", "macro"),
            ("2026-06-16", "inst-institutional-flows"),
            ("2026-06-16", "macro"),
        )
        client = FakeSupabaseClient(canned_reads={"documents": docs})
        streak = query_institutional_absence_streak(client=client, run_date=date(2026, 6, 20))
        assert streak == 3

    def test_streak_breaks_when_latest_run_has_inst(self) -> None:
        from digiquant.olympus.atlas.supabase_io import query_institutional_absence_streak

        docs = self._docs(
            ("2026-06-19", "inst-hedge-fund-intel"),  # most recent published inst-*
            ("2026-06-18", "macro"),
            ("2026-06-17", "macro"),
        )
        client = FakeSupabaseClient(canned_reads={"documents": docs})
        streak = query_institutional_absence_streak(client=client, run_date=date(2026, 6, 20))
        assert streak == 0

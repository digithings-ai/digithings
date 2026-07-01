"""Tests for fail-soft research nodes (Pillar 1A).

A single empty/invalid LLM response (or transient provider error) must degrade
ONE segment to a Carried slot + PhaseError, never abort the whole run. Regression
guard for the live 2026-06-14 baseline that died when ``sector-utilities`` got an
empty OpenRouter body.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.phases.fail_soft import (
    NODE_FAILED_REASON,
    run_segment_fail_soft,
)
from digiquant.olympus.atlas.phases.phase5_equities import (
    EquityOverviewReport,
    build_phase5,
)
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    PhaseError,
    SegmentPayload,
    SegmentSlot,
    _merge_append_list,
)


@pytest.mark.unit
class TestMergeAppendList:
    def test_concatenates_left_then_right(self) -> None:
        left = [PhaseError(phase="p", node="a", message="x")]
        right = [PhaseError(phase="p", node="b", message="y")]
        merged = _merge_append_list(left, right)
        assert [e.node for e in merged] == ["a", "b"]

    def test_handles_none_sides(self) -> None:
        e = [PhaseError(phase="p", node="a", message="x")]
        assert _merge_append_list(None, e) == e
        assert _merge_append_list(e, None) == e
        assert _merge_append_list(None, None) == []

    def test_does_not_mutate_inputs(self) -> None:
        left = [PhaseError(phase="p", node="a", message="x")]
        _merge_append_list(left, [PhaseError(phase="p", node="b", message="y")])
        assert len(left) == 1  # left untouched


@pytest.mark.unit
class TestRunSegmentFailSoft:
    def test_success_returns_fresh_slot_no_errors(self) -> None:
        model = EquityOverviewReport(
            segment="equity", date=date(2026, 6, 14), bias="neutral", headline="ok"
        )
        slot, errors = run_segment_fail_soft(
            run_fn=lambda: model,
            segment_slug="equity",
            phase="phase5_outputs",
            run_date=date(2026, 6, 14),
            baseline_date=None,
        )
        assert errors == []
        assert slot.payload.source == "today"
        assert isinstance(slot.payload, SegmentPayload)
        assert slot.payload.body["headline"] == "ok"

    def test_failure_degrades_to_carried_with_error(self) -> None:
        def boom() -> EquityOverviewReport:
            raise ValueError("empty body")

        slot, errors = run_segment_fail_soft(
            run_fn=boom,
            segment_slug="sector-utilities",
            phase="phase5_outputs",
            run_date=date(2026, 6, 14),
            baseline_date=date(2026, 6, 7),
        )
        # Carried, pointing at the baseline, marked as a node failure (not a triage carry).
        assert slot.payload.source == "carried"
        assert slot.payload.reason == NODE_FAILED_REASON  # type: ignore[union-attr]
        assert slot.payload.baseline_date == date(2026, 6, 7)  # type: ignore[union-attr]
        # One structured, attributable error.
        assert len(errors) == 1
        assert errors[0].node == "sector-utilities"
        assert errors[0].phase == "phase5_outputs"
        assert "ValueError" in errors[0].message

    def test_carried_falls_back_to_run_date_when_no_baseline(self) -> None:
        def boom() -> EquityOverviewReport:
            raise RuntimeError("provider 500")

        slot, _ = run_segment_fail_soft(
            run_fn=boom,
            segment_slug="macro",
            phase="phase3_output",
            run_date=date(2026, 6, 14),
            baseline_date=None,
        )
        assert slot.payload.baseline_date == date(2026, 6, 14)  # type: ignore[union-attr]

    def test_message_is_truncated(self) -> None:
        def boom() -> EquityOverviewReport:
            raise ValueError("x" * 1000)

        _, errors = run_segment_fail_soft(
            run_fn=boom,
            segment_slug="s",
            phase="p",
            run_date=date(2026, 6, 14),
            baseline_date=None,
        )
        assert len(errors[0].message) <= 500


@pytest.mark.unit
class TestPhase5FailSoftIntegration:
    """Drive the real Phase 5 pipeline with an empty LLM body — it must NOT raise."""

    def _seed(self) -> AtlasResearchState:
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 6, 14))
        state.phase3_output = SegmentSlot(
            payload=SegmentPayload(
                segment="macro",
                body={"regime_label": "Slowing / Cooling / Neutral / Mixed"},
                as_of=date(2026, 6, 14),
            )
        )
        return state

    def test_empty_response_carries_every_segment_and_records_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import patch

        from digigraph.graph.pipeline_builder import build_pipeline

        # Force the no-tools path so completion_text is the LLM seam we mock.
        monkeypatch.setenv("ATLAS_DATA_TOOLS", "0")

        compiled = build_pipeline(AtlasResearchState, build_phase5())
        state = self._seed()

        # Empty body → json.loads("") raises → run_research_agent exhausts retries
        # and raises → fail-soft degrades the segment. The run must complete.
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=lambda *a, **k: "",
        ):
            result = compiled.invoke(state)

        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        # Equity + 11 sectors all degraded to carried (the scorecard is deterministic).
        assert final.phase5_outputs["equity"].payload.source == "carried"
        sector_slugs = [
            k for k in final.phase5_outputs if k.startswith("sector-") and k != "sector-scorecard"
        ]
        assert len(sector_slugs) == 11
        assert all(final.phase5_outputs[s].payload.source == "carried" for s in sector_slugs)

        # Every failure is recorded (append reducer kept all 12 across the fan-in),
        # and all marked as node-failure carries.
        assert len(final.errors) == 12
        assert {e.phase for e in final.errors} == {"phase5_outputs"}
        carried_reasons = {
            final.phase5_outputs[s].payload.reason  # type: ignore[union-attr]
            for s in sector_slugs
        }
        assert carried_reasons == {NODE_FAILED_REASON}

        # Deterministic scorecard still ran — with no fresh sectors it has 0 rows.
        scorecard = final.phase5_outputs["sector-scorecard"].payload.body  # type: ignore[union-attr]
        assert scorecard["rows"] == []

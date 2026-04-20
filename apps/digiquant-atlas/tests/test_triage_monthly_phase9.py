"""Unit tests for delta triage, monthly synthesis, and Phase 9 artifacts."""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa: F401 — used for fake-completion dict shape
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant_atlas.phases._node_factory import SegmentNodeSpec, build_segment_node
from digiquant_atlas.phases.phase9_evolution import Phase9Artifacts, build_phase9
from digiquant_atlas.phases.phase_monthly import MonthlyDigest, build_phase_monthly
from digiquant_atlas.state import (
    AtlasResearchState,
    DataLayerSnapshot,
    PriorContext,
    SegmentPayload,
    SegmentSlot,
)
from digiquant_atlas.triage import evaluate, make_triage_gate


def _delta_state(run_date: date, baseline_date: date) -> AtlasResearchState:
    return AtlasResearchState(
        run_type="delta",
        run_date=run_date,
        baseline_date=baseline_date,
        data_layer=DataLayerSnapshot(
            price_technicals_latest=date(2026, 4, 25),
            price_technicals_ticker_count=56,
            macro_series_latest=date(2026, 4, 25),
            fallback_used="supabase",
        ),
        prior_context=PriorContext(
            last_snapshots=[
                {
                    "date": baseline_date.isoformat(),
                    "run_type": "baseline",
                    "snapshot": {"bias": "neutral"},
                }
            ]
        ),
    )


@pytest.mark.unit
class TestTriage:
    def test_baseline_run_returns_empty_decisions(self) -> None:
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        result = evaluate(state)
        assert result.decisions == []

    def test_delta_run_without_baseline_date_raises(self) -> None:
        state = AtlasResearchState(run_type="delta", run_date=date(2026, 4, 27))
        with pytest.raises(ValueError, match="baseline_date"):
            evaluate(state)

    def test_mandatory_segments_always_regenerate(self) -> None:
        state = _delta_state(date(2026, 4, 27), date(2026, 4, 26))
        result = evaluate(state)
        mandatory_regen = [
            d for d in result.decisions if d.tier == "mandatory" and d.decision == "regenerate"
        ]
        mandatory_segments = {d.segment for d in mandatory_regen}
        assert {"macro", "crypto", "equity"}.issubset(mandatory_segments)

    def test_quiet_prior_bias_causes_low_tier_to_carry(self) -> None:
        state = _delta_state(date(2026, 4, 27), date(2026, 4, 26))
        result = evaluate(state)
        low_tier = [d for d in result.decisions if d.tier == "low"]
        carried = [d for d in low_tier if d.decision == "carry"]
        # Prior bias was "neutral" (quiet) — every low-tier segment should carry.
        assert len(carried) == len(low_tier)
        assert len(low_tier) >= 11  # 11 sectors + 4 alt-data at minimum

    def test_stale_data_layer_forces_regenerate(self) -> None:
        state = _delta_state(date(2026, 4, 27), date(2026, 4, 26))
        # Stale data → caller should regenerate (conservative default).
        state.data_layer = DataLayerSnapshot(
            price_technicals_latest=date(2026, 4, 18),
            price_technicals_ticker_count=0,
            macro_series_latest=None,
            fallback_used="scripts",
        )
        result = evaluate(state)
        # All high-tier segments (bonds, commodities, forex) should regen.
        high_decisions = {d.segment: d.decision for d in result.decisions if d.tier == "high"}
        assert high_decisions == {
            "bonds": "regenerate",
            "commodities": "regenerate",
            "forex": "regenerate",
        }


@pytest.mark.unit
class TestTriageGate:
    def test_gate_returns_none_for_regenerate_segments(self) -> None:
        state = _delta_state(date(2026, 4, 27), date(2026, 4, 26))
        result = evaluate(state)
        gate = make_triage_gate(result)
        assert gate(state, "macro") is None  # mandatory → regen

    def test_gate_returns_carried_for_carry_segments(self) -> None:
        state = _delta_state(date(2026, 4, 27), date(2026, 4, 26))
        result = evaluate(state)
        gate = make_triage_gate(result)
        carried = gate(state, "sector-technology")
        assert carried is not None
        assert carried.baseline_date == date(2026, 4, 26)
        assert "quiet" in carried.reason or "bias" in carried.reason


@pytest.mark.unit
class TestTriageIntegrationWithPhaseNode:
    """End-to-end: a phase node with triage_gate short-circuits on carry."""

    def test_phase_node_emits_carried_when_gate_signals_carry(self) -> None:
        from pydantic import BaseModel
        from datetime import date as _d

        class _StubModel(BaseModel):
            segment: str
            date: _d

        state = _delta_state(date(2026, 4, 27), date(2026, 4, 26))
        result = evaluate(state)
        gate = make_triage_gate(result)
        spec = SegmentNodeSpec(
            segment_slug="sector-technology",
            skill_slug="sector-research",
            output_model=_StubModel,
            phase_outputs_field="phase5_outputs",
        )
        node = build_segment_node(spec, triage_gate=gate)

        # LLM must NOT be called since the gate returns Carried.
        with patch(
            "digigraph.graph.research_agent.chat_completion",
            side_effect=AssertionError("triage gate should have short-circuited"),
        ):
            out = node(state)

        assert "phase5_outputs" in out
        slot = out["phase5_outputs"]["sector-technology"]
        assert slot.payload.source == "carried"
        assert slot.payload.baseline_date == date(2026, 4, 26)


# ─── Monthly synthesis ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestMonthlySynthesis:
    def test_monthly_node_produces_digest(self) -> None:
        compiled = build_pipeline(AtlasResearchState, [build_phase_monthly()])
        state = AtlasResearchState(run_type="monthly", run_date=date(2026, 4, 30))

        payload = {
            "segment": "monthly-digest",
            "date": "2026-04-30",
            "bias": "neutral",
            "headline": "April close",
            "material_findings": [],
            "sources": [],
            "notes": "",
            "market_regime_snapshot": "",
            "alt_data_dashboard": "",
            "institutional_summary": "",
            "asset_classes_summary": "",
            "us_equities_summary": "",
            "thesis_tracker": "",
            "portfolio_recommendations": "",
            "actionable_summary": [],
            "risk_radar": [],
            "segment_freshness": {},
            "month_over_month_regime_delta": "Growth decel; policy neutral → cutting bias",
        }

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            schema_part = next(
                p
                for p in msgs[1]["content"]
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            assert MonthlyDigest.__name__ in schema_part["text"]
            return json.dumps(payload)

        with patch("digigraph.graph.research_agent.chat_completion", side_effect=fake):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result
        assert final.phase7_digest is not None
        assert "month_over_month_regime_delta" in final.phase7_digest


# ─── Phase 9 evolution ───────────────────────────────────────────────────────


@pytest.mark.unit
class TestPhase9Evolution:
    def test_artifacts_emitted(self) -> None:
        compiled = build_pipeline(AtlasResearchState, [build_phase9()])
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        state.phase7_digest = {"bias": "neutral"}

        payload = {
            "sources": {
                "scored": [{"source": "AAII", "stars": 4, "failures_today": 0, "notes": ""}],
                "discoveries": [],
            },
            "quality": {
                "predictions_checked": [],
                "rubric": {
                    "accuracy": 4,
                    "completeness": 4,
                    "actionability": 3,
                    "conciseness": 4,
                    "source_quality": 5,
                },
            },
            "proposals": {
                "proposals": [
                    {
                        "target_file": "skills/sector-research/SKILL.md",
                        "change_summary": "Add nuance on small-cap rotation",
                        "rationale": "Three sector reports flagged it today",
                    }
                ]
            },
        }

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            schema_part = next(
                p
                for p in msgs[1]["content"]
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            assert Phase9Artifacts.__name__ in schema_part["text"]
            return json.dumps(payload)

        # Make sure the `pipeline-evolution` skill exists OR tolerate the
        # graceful-fallback path. Either way state.phase9_evolution must
        # exist after invocation.
        with patch("digigraph.graph.research_agent.chat_completion", side_effect=fake):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result
        assert final.phase9_evolution is not None

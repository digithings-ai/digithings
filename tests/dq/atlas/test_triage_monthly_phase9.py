"""Unit tests for delta triage, monthly synthesis, and Phase 9 artifacts."""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa: F401 — used for fake-completion dict shape
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.atlas.phases._node_factory import SegmentNodeSpec, build_segment_node
from digiquant.atlas.phases.phase9_evolution import Phase9Artifacts, build_phase9
from digiquant.atlas.phases.phase_monthly import MonthlyDigest, build_phase_monthly
from digiquant.atlas.state import (
    AtlasResearchState,
    DataLayerSnapshot,
    PriorContext,
)
from digiquant.atlas.triage import evaluate, make_triage_gate


def _delta_state(
    run_date: date,
    baseline_date: date,
    *,
    bias_by_segment: dict[str, str] | None = None,
    price_deltas: dict[str, float] | None = None,
) -> AtlasResearchState:
    """Build a delta-run state with per-segment bias baked in.

    ``bias_by_segment`` (if given) populates snapshot.bias_by_segment so the
    triage evaluator has real per-segment evidence to decide on. When omitted,
    the snapshot has no per-segment bias → triage conservatively regenerates.

    ``price_deltas`` (if given) populates ``state.price_deltas`` directly --
    bypassing the Supabase fetch path so tests can assert evaluator behavior
    against fixed inputs.
    """
    snap: dict[str, Any] = {"bias": "neutral"}
    if bias_by_segment is not None:
        snap["bias_by_segment"] = dict(bias_by_segment)
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
                    "snapshot": snap,
                }
            ]
        ),
        price_deltas=dict(price_deltas) if price_deltas is not None else {},
    )


def _quiet_bias_for_all_segments() -> dict[str, str]:
    """Return a bias_by_segment mapping that marks every known segment quiet.

    Used by tests that want to verify low-tier carry behavior — every
    segment must report neutral for the low-tier rule to evaluate as carry.
    """
    from digiquant.atlas.sectors_config import load_sectors

    slugs = [
        "alt-sentiment-news",
        "alt-cta-positioning",
        "alt-options-derivatives",
        "alt-politician-signals",
        "inst-institutional-flows",
        "inst-hedge-fund-intel",
        "macro",
        "bonds",
        "commodities",
        "forex",
        "crypto",
        "international",
        "equity",
    ]
    for s in load_sectors():
        slugs.append(s.slug)
    return {s: "neutral" for s in slugs}


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
        # Every segment reports neutral in yesterday's per-segment bias →
        # low-tier rule evaluates to carry for all.
        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            bias_by_segment=_quiet_bias_for_all_segments(),
        )
        result = evaluate(state)
        low_tier = [d for d in result.decisions if d.tier == "low"]
        carried = [d for d in low_tier if d.decision == "carry"]
        assert len(carried) == len(low_tier)
        assert len(low_tier) >= 11  # 11 sectors + 4 alt-data at minimum

    def test_missing_per_segment_bias_defaults_to_regenerate(self) -> None:
        """Without per-segment evidence, triage must conservatively regen —
        matching the rubric. (Previous implementation silently used the
        global digest bias as a per-segment proxy, which masked this case.)"""
        state = _delta_state(date(2026, 4, 27), date(2026, 4, 26))  # no bias_by_segment
        result = evaluate(state)
        low_tier = [d for d in result.decisions if d.tier == "low"]
        # Every low-tier segment should regenerate since we have no per-segment
        # evidence that it's quiet.
        assert all(d.decision == "regenerate" for d in low_tier)

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
class TestTriagePriceDeltas:
    """Wired-in price-delta signal: triage actually carries on quiet days."""

    def test_high_tier_carries_when_price_quiet_and_bias_neutral(self) -> None:
        # Bonds tickers all moved < 0.5%; bond_bias is neutral.
        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            bias_by_segment={"bonds": "neutral"},
            price_deltas={"TLT": 0.001, "IEF": -0.002, "SHY": 0.0001},
        )
        result = evaluate(state)
        bonds = next(d for d in result.decisions if d.segment == "bonds")
        assert bonds.decision == "carry"
        assert "price_quiet" in bonds.reason
        assert "bias=neutral" in bonds.reason

    def test_high_tier_regens_on_price_move_above_threshold(self) -> None:
        # TLT down 1.2% — well above the 0.5% high-tier threshold.
        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            bias_by_segment={"bonds": "neutral"},
            price_deltas={"TLT": -0.012, "IEF": 0.001, "SHY": 0.0},
        )
        result = evaluate(state)
        bonds = next(d for d in result.decisions if d.segment == "bonds")
        assert bonds.decision == "regenerate"
        assert "price_move" in bonds.reason
        assert ">threshold" in bonds.reason

    def test_high_tier_regens_when_no_price_delta_data(self) -> None:
        """No price_deltas + no bias signal → conservative regen."""
        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            # No bias_by_segment, no price_deltas.
        )
        result = evaluate(state)
        bonds = next(d for d in result.decisions if d.segment == "bonds")
        assert bonds.decision == "regenerate"
        assert "no_price_delta" in bonds.reason

    def test_high_tier_regens_on_directional_bias_even_with_quiet_tape(self) -> None:
        """A bullish/bearish prior bias overrides a quiet price tape — the
        analyst already had a directional view we shouldn't silently drop."""
        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            bias_by_segment={"commodities": "bullish"},
            price_deltas={"GLD": 0.001, "SLV": -0.002},
        )
        result = evaluate(state)
        commodities = next(d for d in result.decisions if d.segment == "commodities")
        assert commodities.decision == "regenerate"
        assert "segment_bias=bullish" in commodities.reason

    def test_low_tier_regens_on_tracked_name_move_above_threshold(self) -> None:
        """Sector with neutral bias but a 2% ETF move regens on the price
        channel alone — this is the path that fires on news-driven days."""
        # Use the full quiet-bias map so every other low-tier carries.
        bias = _quiet_bias_for_all_segments()
        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            bias_by_segment=bias,
            price_deltas={"XLK": 0.021, "XLV": 0.001, "XLE": 0.0, "XLF": 0.0001},
        )
        result = evaluate(state)
        tech = next(d for d in result.decisions if d.segment == "sector-technology")
        assert tech.decision == "regenerate"
        assert "tracked_name_move" in tech.reason
        # Other sectors with quiet tape + neutral bias should carry.
        healthcare = next(d for d in result.decisions if d.segment == "sector-healthcare")
        assert healthcare.decision == "carry"

    def test_low_tier_carries_on_quiet_tape_and_neutral_bias(self) -> None:
        bias = _quiet_bias_for_all_segments()
        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            bias_by_segment=bias,
            price_deltas={"XLK": 0.005, "XLV": -0.003},
        )
        result = evaluate(state)
        tech = next(d for d in result.decisions if d.segment == "sector-technology")
        assert tech.decision == "carry"
        assert "price_quiet" in tech.reason

    def test_low_tier_regens_on_bias_shift_regardless_of_price(self) -> None:
        """A bullish prior bias regens the segment even if the tape is dead."""
        bias = _quiet_bias_for_all_segments()
        bias["sector-technology"] = "bullish"
        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            bias_by_segment=bias,
            price_deltas={"XLK": 0.0001},
        )
        result = evaluate(state)
        tech = next(d for d in result.decisions if d.segment == "sector-technology")
        assert tech.decision == "regenerate"
        assert "segment_bias=bullish" in tech.reason

    def test_low_tier_regens_when_no_bias_and_no_price_data(self) -> None:
        # No bias + no price → conservative regen (matches the docstring).
        state = _delta_state(date(2026, 4, 27), date(2026, 4, 26))
        result = evaluate(state)
        low = [d for d in result.decisions if d.tier == "low"]
        assert all(d.decision == "regenerate" for d in low)
        # Reason for sectors should mention both missing channels.
        tech = next(d for d in result.decisions if d.segment == "sector-technology")
        assert "no_per_segment_bias" in tech.reason
        assert "no_price_data" in tech.reason

    def test_negative_move_above_threshold_also_regens(self) -> None:
        """Threshold is on absolute value — a 1% drop should regen too."""
        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            bias_by_segment={"forex": "neutral"},
            price_deltas={"UUP": -0.012},
        )
        result = evaluate(state)
        forex = next(d for d in result.decisions if d.segment == "forex")
        assert forex.decision == "regenerate"
        assert "price_move=1.20%" in forex.reason


@pytest.mark.unit
class TestTriageGate:
    def test_gate_returns_none_for_regenerate_segments(self) -> None:
        state = _delta_state(date(2026, 4, 27), date(2026, 4, 26))
        result = evaluate(state)
        gate = make_triage_gate(result)
        assert gate(state, "macro") is None  # mandatory → regen

    def test_gate_returns_carried_for_carry_segments(self) -> None:
        # Sector-technology reports neutral in yesterday's per-segment bias →
        # low-tier rule evaluates to carry.
        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            bias_by_segment=_quiet_bias_for_all_segments(),
        )
        result = evaluate(state)
        gate = make_triage_gate(result)
        carried = gate(state, "sector-technology")
        assert carried is not None
        assert carried.baseline_date == date(2026, 4, 26)
        assert "quiet" in carried.reason or "bias" in carried.reason


@pytest.mark.unit
class TestTriagePhaseNode:
    """End-to-end behaviour of the triage phase node (deps wiring + LLM-free)."""

    def test_node_skips_on_baseline_run(self) -> None:
        from digiquant.atlas.phases.triage_phase import build_triage_node

        node = build_triage_node(deps=None)
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        out = node(state)
        assert out == {}

    def test_node_runs_without_deps_falls_back_to_no_price_signal(self) -> None:
        """Without a Supabase client we still produce triage decisions —
        just with no price-delta signal. High-tier segments regen by
        default (matches the conservative-default contract)."""
        from digiquant.atlas.phases.triage_phase import build_triage_node

        node = build_triage_node(deps=None)
        state = _delta_state(date(2026, 4, 27), date(2026, 4, 26))
        out = node(state)
        assert "triage" in out
        assert "price_deltas" in out
        assert out["price_deltas"] == {}
        triage = out["triage"]
        bonds = next(d for d in triage.decisions if d.segment == "bonds")
        assert bonds.decision == "regenerate"

    def test_node_with_deps_loads_price_history_and_carries_quiet_segments(self) -> None:
        """Happy path: Supabase returns flat-tape rows for high-tier ETFs and
        the bonds segment carries while a sharp single-ETF mover regens."""
        from digiquant.atlas.phases.triage_phase import TriageDeps, build_triage_node
        from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

        # Bonds: TLT/IEF/SHY all flat. Commodities: GLD up 1.2% (above 0.5%).
        rows = [
            {"date": "2026-04-24", "ticker": "TLT", "close": 90.0},
            {"date": "2026-04-25", "ticker": "TLT", "close": 90.05},
            {"date": "2026-04-24", "ticker": "IEF", "close": 95.0},
            {"date": "2026-04-25", "ticker": "IEF", "close": 95.10},
            {"date": "2026-04-24", "ticker": "SHY", "close": 82.0},
            {"date": "2026-04-25", "ticker": "SHY", "close": 82.01},
            {"date": "2026-04-24", "ticker": "GLD", "close": 200.0},
            {"date": "2026-04-25", "ticker": "GLD", "close": 202.4},  # +1.2%
        ]
        client = FakeSupabaseClient(canned_reads={"price_history": rows})
        node = build_triage_node(TriageDeps(client=client))
        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            bias_by_segment=_quiet_bias_for_all_segments(),
        )
        out = node(state)
        # Price-delta map populated.
        assert "TLT" in out["price_deltas"]
        assert out["price_deltas"]["GLD"] == pytest.approx(0.012)
        # Bonds carry (quiet tape + neutral bias).
        bonds = next(d for d in out["triage"].decisions if d.segment == "bonds")
        assert bonds.decision == "carry"
        # Commodities regen (price-move > 0.5%).
        commodities = next(d for d in out["triage"].decisions if d.segment == "commodities")
        assert commodities.decision == "regenerate"

    def test_node_handles_missing_price_history_gracefully(self) -> None:
        """price_history empty → empty deltas → conservative regen everywhere."""
        from digiquant.atlas.phases.triage_phase import TriageDeps, build_triage_node
        from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

        client = FakeSupabaseClient(canned_reads={"price_history": []})
        node = build_triage_node(TriageDeps(client=client))
        state = _delta_state(date(2026, 4, 27), date(2026, 4, 26))
        out = node(state)
        assert out["price_deltas"] == {}
        bonds = next(d for d in out["triage"].decisions if d.segment == "bonds")
        assert bonds.decision == "regenerate"


@pytest.mark.unit
class TestTriageIntegrationWithPhaseNode:
    """End-to-end: a phase node with triage_gate short-circuits on carry."""

    def test_phase_node_emits_carried_when_gate_signals_carry(self) -> None:
        from pydantic import BaseModel
        from datetime import date as _d

        class _StubModel(BaseModel):
            segment: str
            date: _d

        state = _delta_state(
            date(2026, 4, 27),
            date(2026, 4, 26),
            bias_by_segment=_quiet_bias_for_all_segments(),
        )
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

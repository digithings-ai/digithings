"""Integration tests for Phase 6 bias row + Phase 7 digest synthesis +
Phase 7C analysts + Phase 7D PM rebalance.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa: F401 — used for fake-completion dict shape
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.olympus.atlas.phases.phase6_consolidate import build_phase6
from digiquant.olympus.atlas.phases.phase7_synthesis import (
    DigestSnapshot,
    _bodies,
    _enforce_research_only_boundary,
    build_phase7,
)
from digiquant.olympus.hermes.phases.phase7c_analyst import AnalystPayload, build_phase7c
from digiquant.olympus.hermes.phases.phase7d_pm import RebalanceDecision, build_phase7d
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    Carried,
    SegmentPayload,
    SegmentSlot,
)


def _seed_state_through_phase5() -> AtlasResearchState:
    """Populate phases 1–5 with minimal fresh slots so Phase 6+ has input."""
    state = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        config=AtlasConfigBundle(watchlist=["AAPL", "MSFT"]),
    )

    def _slot(slug: str, bias: str = "bullish", **extra: Any) -> SegmentSlot:
        body = {"segment": slug, "bias": bias, **extra}
        return SegmentSlot(payload=SegmentPayload(segment=slug, body=body, as_of=date(2026, 4, 26)))

    state.phase1_outputs = {
        "alt-sentiment-news": _slot("alt-sentiment-news"),
        "alt-cta-positioning": _slot("alt-cta-positioning", bias="neutral"),
        "alt-options-derivatives": _slot("alt-options-derivatives", vix_level=15.2),
        "alt-politician-signals": _slot("alt-politician-signals"),
    }
    state.phase2_outputs = {
        "inst-institutional-flows": _slot("inst-institutional-flows"),
        "inst-hedge-fund-intel": _slot("inst-hedge-fund-intel"),
    }
    state.phase3_output = _slot("macro", regime_label="Slowing / Cooling / Neutral / Mixed")
    state.phase4_outputs = {
        "bonds": _slot("bonds"),
        "commodities": _slot("commodities"),
        "forex": _slot("forex"),
        "crypto": _slot("crypto"),
        "international": _slot("international"),
    }
    state.phase5_outputs = {"equity": _slot("equity")}
    return state


# ─── Phase 6 tests ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPhase6BiasRow:
    def test_row_captures_phases_1_through_5(self) -> None:
        compiled = build_pipeline(AtlasResearchState, [build_phase6()])
        state = _seed_state_through_phase5()
        result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        row = final.phase6_bias_row
        assert row is not None
        assert row["date"] == "2026-04-26"
        assert row["macro_regime"].startswith("Slowing")
        assert row["equity_bias"] == "bullish"
        assert row["crypto_bias"] == "bullish"
        assert row["bond_bias"] == "bullish"
        assert row["vix_level"] == 15.2
        assert row["cta_direction"] == "neutral"
        assert row["notes"] == ""  # filled by Phase 7

    def test_no_llm_call(self) -> None:
        """Phase 6 is pure aggregation."""
        compiled = build_pipeline(AtlasResearchState, [build_phase6()])
        state = _seed_state_through_phase5()
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=AssertionError("Phase 6 must not call the LLM"),
        ):
            compiled.invoke(state)


# ─── Phase 7 tests ──────────────────────────────────────────────────────────


def _digest_payload() -> str:
    return json.dumps(
        {
            "segment": "master-digest",
            "date": "2026-04-26",
            "bias": "neutral",
            "headline": "Late-cycle consolidation",
            "material_findings": [],
            "sources": [],
            "notes": "",
            "market_regime_snapshot": "Growth slowing",
            "alt_data_dashboard": "Retail bullish; CTAs neutral",
            "institutional_summary": "Modest outflows",
            "asset_classes_summary": "Bonds rallying",
            "us_equities_summary": "Narrow breadth",
            "thesis_tracker": "",
            "portfolio_recommendations": "",
            "actionable_summary": [],
            "risk_radar": [],
            "segment_freshness": {},  # will be overwritten by deterministic derivation
        }
    )


@pytest.mark.unit
class TestPhase7Synthesis:
    def test_digest_synthesized_and_freshness_overwritten(self) -> None:
        compiled = build_pipeline(AtlasResearchState, [build_phase6(), build_phase7()])
        state = _seed_state_through_phase5()

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            schema_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            assert DigestSnapshot.__name__ in schema_part["text"]
            return _digest_payload()

        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=fake,
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        digest = final.phase7_digest
        assert digest is not None
        # Freshness map was overwritten with deterministic derivation; LLM's
        # empty dict does not leak into the persisted payload.
        assert digest["segment_freshness"], "freshness map must not be empty"
        assert digest["segment_freshness"]["macro"]["source"] == "today"
        assert digest["segment_freshness"]["equity"]["source"] == "today"


# ─── Phase 7 research-only boundary ─────────────────────────────────────────


@pytest.mark.unit
class TestPhase7ResearchOnlyBoundary:
    def test_enforce_strips_position_fields(self) -> None:
        digest = DigestSnapshot.model_validate(
            {
                "segment": "master-digest",
                "date": "2026-04-26",
                "bias": "neutral",
                "headline": "Test",
                "market_regime_snapshot": "Growth slowing",
                "alt_data_dashboard": "Neutral",
                "institutional_summary": "Flows flat",
                "asset_classes_summary": "Mixed",
                "us_equities_summary": "Narrow breadth",
                "thesis_tracker": "SPY momentum: intact",
                "portfolio_recommendations": "Overweight XLK; underweight XLF",
            }
        )
        stripped = _enforce_research_only_boundary(digest)
        assert stripped.thesis_tracker == ""
        assert stripped.portfolio_recommendations == ""

    def test_position_fields_stripped_after_synthesis(self) -> None:
        """LLM output with position fields must not leak into persisted digest."""
        compiled = build_pipeline(AtlasResearchState, [build_phase6(), build_phase7()])
        state = _seed_state_through_phase5()

        def fake(_m: str, _msgs: list[dict[str, Any]], **_: Any) -> str:
            payload = json.loads(_digest_payload())
            payload["thesis_tracker"] = "SPY momentum: intact"
            payload["portfolio_recommendations"] = "Overweight XLK; trim XLF"
            return json.dumps(payload)

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        assert final.phase7_digest is not None
        assert final.phase7_digest["thesis_tracker"] == ""
        assert final.phase7_digest["portfolio_recommendations"] == ""


# ─── Phase 7 today-only digest inputs (#927) ────────────────────────────────


def _carried_slot(slug: str, baseline: date = date(2026, 4, 19)) -> SegmentSlot:
    """A carry-forward slot (source='carried') as produced on a delta run."""
    return SegmentSlot(payload=Carried(baseline_date=baseline, reason="below_triage_threshold"))


@pytest.mark.unit
class TestPhase7TodayOnlyInputs:
    def test_bodies_excludes_carried_segments(self) -> None:
        """``_bodies`` must drop carried slots — only today-source bodies feed the LLM."""
        bag = {
            "bonds": SegmentSlot(
                payload=SegmentPayload(
                    segment="bonds", body={"segment": "bonds"}, as_of=date(2026, 4, 26)
                )
            ),
            "commodities": _carried_slot("commodities"),
            "forex": _carried_slot("forex"),
        }
        out = _bodies(bag)
        assert set(out) == {"bonds"}, "carried segments must not appear in digest inputs"

    def test_delta_inputs_smaller_than_unfiltered(self) -> None:
        """A delta state with many carried segments → the dict passed to the Phase-7
        prompt is strictly smaller than the unfiltered slot bag (carried bodies dropped).
        """
        state = _seed_state_through_phase5()
        state.run_type = "delta"
        # Carry-forward most of phases 4 and 1 (delta-run baseline carries).
        state.phase4_outputs = {
            "bonds": state.phase4_outputs["bonds"],  # only this one is fresh
            "commodities": _carried_slot("commodities"),
            "forex": _carried_slot("forex"),
            "crypto": _carried_slot("crypto"),
            "international": _carried_slot("international"),
        }
        state.phase1_outputs = {
            "alt-sentiment-news": state.phase1_outputs["alt-sentiment-news"],
            "alt-cta-positioning": _carried_slot("alt-cta-positioning"),
            "alt-options-derivatives": _carried_slot("alt-options-derivatives"),
            "alt-politician-signals": _carried_slot("alt-politician-signals"),
        }

        compiled = build_pipeline(AtlasResearchState, [build_phase6(), build_phase7()])
        captured: list[dict[str, Any]] = []

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            for part in msgs[1]["content"]:
                if isinstance(part, dict) and part.get("text", "").startswith("PHASE_INPUTS"):
                    captured.append(json.loads(part["text"].split(":", 1)[1].strip()))
                    break
            return _digest_payload()

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            compiled.invoke(state)

        assert captured, "LLM must have been called"
        phase_inputs = captured[0]
        # Filtered phase4 has only the fresh "bonds"; the raw bag has 5 entries.
        assert set(phase_inputs["phase4"]) == {"bonds"}
        assert len(phase_inputs["phase4"]) < len(state.phase4_outputs)
        # Filtered phase1 has only the fresh "alt-sentiment-news"; raw bag has 4.
        assert set(phase_inputs["phase1"]) == {"alt-sentiment-news"}
        assert len(phase_inputs["phase1"]) < len(state.phase1_outputs)


# ─── Phase 7 strip trade verbs from actionable_summary (#927) ───────────────


@pytest.mark.unit
class TestPhase7StripTradeVerbs:
    def test_trade_verbs_rewritten_to_research_language(self) -> None:
        """Trade/allocation verbs in ``actionable_summary`` are rewritten to
        watchlist/research language; ``portfolio_recommendations`` stays empty.
        """
        digest = DigestSnapshot.model_validate(
            {
                "segment": "master-digest",
                "date": "2026-04-26",
                "bias": "neutral",
                "headline": "Test",
                "market_regime_snapshot": "Growth slowing",
                "alt_data_dashboard": "Neutral",
                "institutional_summary": "Flows flat",
                "asset_classes_summary": "Mixed",
                "us_equities_summary": "Narrow breadth",
                "portfolio_recommendations": "",
                "actionable_summary": [
                    {
                        "priority": 1,
                        "label": "Overweight semiconductors into earnings",
                        "rationale": "Add to AI exposure; reduce exposure to financials.",
                    },
                    {
                        "priority": 2,
                        "label": "Rotate into defensives",
                        "rationale": "Trim cyclicals and increase exposure to staples.",
                    },
                ],
            }
        )
        stripped = _enforce_research_only_boundary(digest)

        # portfolio_recommendations stays empty (existing #859 behavior).
        assert stripped.portfolio_recommendations == ""

        joined = " ".join(
            f"{item.label} {item.rationale}".lower() for item in stripped.actionable_summary
        )
        for verb in (
            "overweight",
            "underweight",
            "reduce exposure",
            "increase exposure",
            "add to",
            "trim",
            "rotate into",
        ):
            assert verb not in joined, f"trade verb {verb!r} must be rewritten"
        # Items are preserved (rewritten, not dropped).
        assert len(stripped.actionable_summary) == 2

    def test_research_language_left_untouched(self) -> None:
        """Watchlist/research phrasing must pass through unchanged."""
        digest = DigestSnapshot.model_validate(
            {
                "segment": "master-digest",
                "date": "2026-04-26",
                "bias": "neutral",
                "headline": "Test",
                "market_regime_snapshot": "Growth slowing",
                "alt_data_dashboard": "Neutral",
                "institutional_summary": "Flows flat",
                "asset_classes_summary": "Mixed",
                "us_equities_summary": "Narrow breadth",
                "actionable_summary": [
                    {
                        "priority": 1,
                        "label": "Watch semiconductor breadth",
                        "rationale": "Monitor AI capex commentary into earnings.",
                    },
                ],
            }
        )
        stripped = _enforce_research_only_boundary(digest)
        item = stripped.actionable_summary[0]
        assert item.label == "Watch semiconductor breadth"
        assert item.rationale == "Monitor AI capex commentary into earnings."


# ─── Phase 7C tests ─────────────────────────────────────────────────────────


def _analyst_payload(ticker: str) -> str:
    return json.dumps(
        {
            "ticker": ticker,
            "conviction_score": 2,
            "stance": "buy",
            "thesis": "Strong fundamentals",
            "risks": "",
            "sources": [],
        }
    )


@pytest.mark.unit
class TestPhase7cAnalysts:
    def test_per_ticker_fan_out(self) -> None:
        # Phase 7C is now a 2-phase pipeline (4 specialists fan-out → join)
        # per #430. Spread both sub-phases. Each ticker triggers 4 LLM
        # calls (one per axis); the join is deterministic (no LLM).
        tickers = ["AAPL", "MSFT"]
        compiled = build_pipeline(AtlasResearchState, list(build_phase7c(tickers)))
        state = _seed_state_through_phase5()

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
            return json.dumps(
                {
                    "axis": body["axis"],
                    "ticker": body["ticker"],
                    "conviction_axis": 0.6,
                    "stance_axis": "buy",
                    "rationale": f"{body['axis']} likes {body['ticker']}",
                    "sources": [],
                }
            )

        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=fake,
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        # Both tickers got all 4 specialists.
        for ticker in tickers:
            assert ticker in final.phase7c_specialists
            assert len(final.phase7c_specialists[ticker]) == 4
        # Join produced unanimous-buy AnalystPayload for both.
        assert set(final.phase7c_analysts.keys()) == {"AAPL", "MSFT"}
        for ticker in tickers:
            payload = AnalystPayload.model_validate(final.phase7c_analysts[ticker])
            assert payload.stance == "buy"
            assert payload.conviction_score >= 1  # weighted-buy → positive

    def test_empty_watchlist_does_not_explode(self) -> None:
        # Both sub-phases must no-op cleanly when the watchlist is empty.
        compiled = build_pipeline(AtlasResearchState, list(build_phase7c([])))
        state = _seed_state_through_phase5()
        # No LLM call expected.
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=AssertionError("empty-watchlist node must not call LLM"),
        ):
            compiled.invoke(state)


# ─── Phase 7D tests ─────────────────────────────────────────────────────────


def _rebalance_payload() -> str:
    return json.dumps(
        {
            "recommended_portfolio": [
                {"ticker": "AAPL", "target_pct": 5.0},
                {"ticker": "MSFT", "target_pct": 5.0},
            ],
            "actions": [
                {
                    "ticker": "AAPL",
                    "action": "hold",
                    "current_pct": 5.0,
                    "target_pct": 5.0,
                    "rationale": "On target",
                }
            ],
            "notes": "Maintain defensive stance",
        }
    )


@pytest.mark.unit
class TestPhase7dPm:
    def test_rebalance_decision_produced(self) -> None:
        # build_phase7d returns three sub-phases (risk-aggressive →
        # risk-conservative → pm-rebalance) per #431. Spread them.
        compiled = build_pipeline(AtlasResearchState, list(build_phase7d()))
        state = _seed_state_through_phase5()
        state.phase7c_analysts = {"AAPL": {"ticker": "AAPL", "conviction_score": 2}}

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            schema_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            schema_text = schema_part["text"]
            # Dispatch on the validated schema name in the prompt.
            if "RiskCase" in schema_text and "RiskDebateSummary" not in schema_text:
                return json.dumps({"case": "Aggressive case for the rebalance."})
            if "RiskDebateSummary" in schema_text:
                return json.dumps(
                    {
                        "aggressive_case": "Aggressive case for the rebalance.",
                        "conservative_case": "Conservative case warns of late-cycle risk.",
                        "key_tension": "Growth vs. drawdown.",
                    }
                )
            assert RebalanceDecision.__name__ in schema_text
            return _rebalance_payload()

        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=fake,
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        reb = final.phase7d_rebalance
        assert reb is not None
        assert len(reb["recommended_portfolio"]) == 2
        assert reb["actions"][0]["action"] == "hold"
        # Risk debate must have populated both halves.
        debate = final.phase7d_risk_debate
        assert debate is not None
        assert debate["aggressive_case"] == "Aggressive case for the rebalance."
        assert "late-cycle" in debate["conservative_case"]
        assert debate["key_tension"] == "Growth vs. drawdown."

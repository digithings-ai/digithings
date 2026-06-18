"""Phase 7C-D Bull/Bear adversarial debate tests (#429, #814).

Covers:
- Bull node opens round 1, writes ``pending`` to state.
- Bear node reads ``pending`` and finalizes the round.
- Research manager produces DebateSummary from completed rounds.
- Round count reads from preferences (default 1).
- DebateSummary schema bounds (conviction_delta).
- PM phase consumes ``debate_summaries`` from state when present.
- Empty watchlist installs no-op nodes.
- Phase factories return correct phase counts (1 round → 3 phases:
  bull, bear, research-manager).
- conviction_delta is non-zero when the debate shifts conviction (#814).
- Multi-round graph (rounds=2) runs both rounds when configured (#814).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa: F401 — used for fake-completion dict shape
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.olympus.hermes.phases.phase7cd_debate import (
    DebateRound,
    DebateSummary,
    _deterministic_conviction_delta,
    _round_count,
    build_phase7cd,
    build_phase7cd_research_manager,
    build_phase7cd_round,
    clamp_debate_rounds,
)
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
)


@pytest.fixture(autouse=True)
def _no_data_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    # Deterministic tool-less completion path for completion_text mocks regardless of the
    # developer's Supabase env (the debate nodes now wire data tools when available).
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "0")


def _state(
    tickers: tuple[str, ...] = ("AAPL",), *, debate_rounds: int | None = None
) -> AtlasResearchState:
    config = AtlasConfigBundle(
        watchlist=list(tickers),
        preferences=({"debate_rounds": debate_rounds} if debate_rounds is not None else {}),
    )
    state = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        config=config,
    )
    state.phase6_bias_row = {"date": "2026-04-26"}
    state.phase7c_analysts = {
        ticker: {
            "ticker": ticker,
            "conviction_score": 2,
            "stance": "buy",
            "thesis": f"{ticker} setup is constructive",
            "risks": "",
            "sources": [],
        }
        for ticker in tickers
    }
    return state


def _bull_payload(ticker: str, round_number: int) -> str:
    return json.dumps(
        {
            "role": "bull",
            "ticker": ticker,
            "round_number": round_number,
            "argument": f"Bull case for {ticker}, round {round_number}",
        }
    )


def _bear_payload(ticker: str, round_number: int) -> str:
    return json.dumps(
        {
            "role": "bear",
            "ticker": ticker,
            "round_number": round_number,
            "argument": f"Bear case for {ticker}, round {round_number}",
        }
    )


def _summary_payload(ticker: str) -> str:
    return json.dumps(
        {
            "ticker": ticker,
            "rounds": [],
            "bull_thesis": f"{ticker} bull synthesis",
            "bear_thesis": f"{ticker} bear synthesis",
            "net_stance": "bullish",
            "conviction_delta": 1,
        }
    )


# ─── Round count ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestRoundCount:
    def test_default_is_one(self) -> None:
        assert _round_count(_state()) == 1

    def test_reads_from_preferences(self) -> None:
        assert _round_count(_state(debate_rounds=2)) == 2

    def test_clamps_to_max_5(self) -> None:
        assert _round_count(_state(debate_rounds=99)) == 5

    def test_clamps_to_min_1(self) -> None:
        assert _round_count(_state(debate_rounds=0)) == 1
        assert _round_count(_state(debate_rounds=-3)) == 1

    def test_garbage_falls_back_to_default(self) -> None:
        config = AtlasConfigBundle(preferences={"debate_rounds": "two"})
        s = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26), config=config)
        assert _round_count(s) == 1


# ─── Debate models ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDebateModels:
    def test_summary_conviction_delta_bounds(self) -> None:
        for delta in (-3, 3):
            with pytest.raises(ValidationError):
                DebateSummary(
                    ticker="AAPL",
                    rounds=[],
                    bull_thesis="a",
                    bear_thesis="b",
                    net_stance="neutral",
                    conviction_delta=delta,
                )

    def test_round_count_max_5(self) -> None:
        with pytest.raises(ValidationError):
            DebateRound(
                round_number=6,
                bull_argument="a",
                bear_argument="b",
            )


# ─── Single-round flow ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestSingleRound:
    def test_bull_then_bear_finalizes_round(self) -> None:
        compiled = build_pipeline(
            AtlasResearchState,
            list(build_phase7cd_round(1, ["AAPL"])),
        )
        state = _state()

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
            if body["role"] == "bull":
                return _bull_payload(body["ticker"], body["round_number"])
            return _bear_payload(body["ticker"], body["round_number"])

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        debate = final.phase7cd_debates["AAPL"]
        assert "rounds" in debate
        assert len(debate["rounds"]) == 1
        assert "Bull case for AAPL, round 1" in debate["rounds"][0]["bull_argument"]
        assert "Bear case for AAPL, round 1" in debate["rounds"][0]["bear_argument"]
        # ``pending`` should be cleared after the bear node finalizes the round.
        assert debate.get("pending", {}) == {}


@pytest.mark.unit
class TestResearchManager:
    def test_manager_emits_debate_summary(self) -> None:
        compiled = build_pipeline(
            AtlasResearchState,
            [build_phase7cd_research_manager(["AAPL"])],
        )
        state = _state()
        # Simulate that the bull/bear nodes already produced a completed round.
        state.phase7cd_debates = {
            "AAPL": {
                "rounds": [
                    {
                        "round_number": 1,
                        "bull_argument": "Bull case",
                        "bear_argument": "Bear case",
                    }
                ]
            }
        }

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
            return _summary_payload(body["ticker"])

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        summary = final.phase7cd_debates["AAPL"]
        assert summary["bull_thesis"] == "AAPL bull synthesis"
        assert summary["bear_thesis"] == "AAPL bear synthesis"
        assert summary["net_stance"] == "bullish"
        assert summary["conviction_delta"] == 1
        # Rounds are preserved verbatim from state.
        assert len(summary["rounds"]) == 1

    def test_manager_emits_neutral_when_no_rounds(self) -> None:
        """Defensive: if the bull/bear path was skipped, manager still produces a stable shape."""
        compiled = build_pipeline(
            AtlasResearchState,
            [build_phase7cd_research_manager(["AAPL"])],
        )
        state = _state()
        # No completed rounds in state → manager emits a neutral summary
        # without calling the LLM.
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=AssertionError("manager must not call LLM with no rounds"),
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        summary = final.phase7cd_debates["AAPL"]
        assert summary["net_stance"] == "neutral"
        assert summary["conviction_delta"] == 0
        assert summary.get("rounds_count") == 0


# ─── Full debate pipeline ───────────────────────────────────────────────────


@pytest.mark.unit
class TestFullDebatePipeline:
    def test_one_round_pipeline_writes_full_summary(self) -> None:
        compiled = build_pipeline(
            AtlasResearchState,
            list(build_phase7cd(["AAPL", "MSFT"], rounds=1)),
        )
        state = _state(("AAPL", "MSFT"))

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
            seg = body["segment"]
            if seg.startswith("bull-researcher-"):
                return _bull_payload(body["ticker"], body["round_number"])
            if seg.startswith("bear-researcher-"):
                return _bear_payload(body["ticker"], body["round_number"])
            return _summary_payload(body["ticker"])

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        for ticker in ("AAPL", "MSFT"):
            summary = final.phase7cd_debates[ticker]
            assert summary["net_stance"] == "bullish"
            assert summary["bull_thesis"] == f"{ticker} bull synthesis"
            assert len(summary["rounds"]) == 1


@pytest.mark.unit
class TestPhaseFactoryShape:
    def test_one_round_returns_three_phases(self) -> None:
        phases = build_phase7cd(["AAPL"], rounds=1)
        assert len(phases) == 3
        assert phases[0].name == "phase7cd_bull_round1"
        assert phases[1].name == "phase7cd_bear_round1"
        assert phases[2].name == "phase7cd_research_manager"

    def test_two_rounds_returns_five_phases(self) -> None:
        phases = build_phase7cd(["AAPL"], rounds=2)
        assert len(phases) == 5
        assert phases[-1].name == "phase7cd_research_manager"

    def test_empty_watchlist_yields_noop_phases(self) -> None:
        phases = build_phase7cd([], rounds=1)
        assert len(phases) == 3
        for phase in phases:
            assert len(phase.nodes) == 1
            assert "noop" in phase.nodes[0].name


# ─── PM integration ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPmConsumesDebateSummaries:
    def test_pm_phase_inputs_includes_debate_summaries_when_present(self) -> None:
        from digiquant.olympus.hermes.phases.phase7d_pm import _pm_node

        state = _state()
        state.phase7cd_debates = {
            "AAPL": {
                "ticker": "AAPL",
                "rounds": [],
                "bull_thesis": "BULL",
                "bear_thesis": "BEAR",
                "net_stance": "bullish",
                "conviction_delta": 1,
            }
        }

        captured: dict[str, str] = {}

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p for p in user_block if isinstance(p, dict) and "PHASE_INPUTS" in p.get("text", "")
            )
            captured["text"] = inputs_part["text"]
            return json.dumps({"recommended_portfolio": [], "actions": [], "notes": "ok"})

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            _pm_node(state)

        assert "debate_summaries" in captured["text"]
        assert "BULL" in captured["text"]
        assert "bullish" in captured["text"]

    def test_pm_works_with_empty_debate_summaries(self) -> None:
        """Graphs that don't wire the debate phase still produce a decision."""
        from digiquant.olympus.hermes.phases.phase7d_pm import _pm_node

        state = _state()
        # Default: phase7cd_debates = {} (no debate ran)

        with patch(
            "digigraph.graph.research_agent.completion_text",
            return_value=json.dumps(
                {"recommended_portfolio": [], "actions": [], "notes": "no-debate"}
            ),
        ):
            update = _pm_node(state)
        assert update["phase7d_rebalance"]["notes"] == "no-debate"


# ─── clamp_debate_rounds ────────────────────────────────────────────────────


@pytest.mark.unit
class TestClampDebateRounds:
    """clamp_debate_rounds must enforce [1, 5] and handle bad input."""

    def test_typical_values_pass_through(self) -> None:
        assert clamp_debate_rounds(1) == 1
        assert clamp_debate_rounds(3) == 3
        assert clamp_debate_rounds(5) == 5

    def test_below_one_clamped_to_one(self) -> None:
        assert clamp_debate_rounds(0) == 1
        assert clamp_debate_rounds(-3) == 1

    def test_above_five_clamped_to_five(self) -> None:
        assert clamp_debate_rounds(10) == 5
        assert clamp_debate_rounds(100) == 5

    def test_bad_type_returns_default(self) -> None:
        assert clamp_debate_rounds(None) == 1
        assert clamp_debate_rounds("abc") == 1
        assert clamp_debate_rounds(None, default=2) == 2

    def test_string_int_coerced(self) -> None:
        assert clamp_debate_rounds("3") == 3


# ─── Deterministic conviction_delta (#814) ──────────────────────────────────


@pytest.mark.unit
class TestDeterministicConvictionDelta:
    """_deterministic_conviction_delta must produce non-zero values when the
    debate's net_stance conflicts with or reinforces the pre-debate analyst
    conviction (#814 — conviction_delta was always 0 before this fix)."""

    def test_bullish_stance_gives_positive_delta(self) -> None:
        # Any bullish outcome should shift delta up.
        assert _deterministic_conviction_delta("bullish", 2) == 1

    def test_bearish_stance_gives_negative_delta(self) -> None:
        assert _deterministic_conviction_delta("bearish", 2) == -1

    def test_neutral_stance_gives_zero_delta(self) -> None:
        assert _deterministic_conviction_delta("neutral", 2) == 0

    def test_bullish_stance_stronger_correction_when_analyst_very_bearish(self) -> None:
        # Large negative pre-debate score → debate turned the table, use +2.
        assert _deterministic_conviction_delta("bullish", -4) == 2
        assert _deterministic_conviction_delta("bullish", -3) == 2

    def test_bearish_stance_stronger_correction_when_analyst_very_bullish(self) -> None:
        assert _deterministic_conviction_delta("bearish", 3) == -2
        assert _deterministic_conviction_delta("bearish", 4) == -2

    def test_delta_nonzero_for_spy_strong_buy_bearish_stance(self) -> None:
        # Explicit regression for the reported case: SPY analyst conviction +4 buy →
        # delta was always 0 before #814.  A bearish debate outcome must produce a
        # non-zero, negative delta.
        delta = _deterministic_conviction_delta("bearish", 4)
        assert delta != 0, "SPY conviction +4 buy with bearish debate must give non-zero delta"
        assert delta < 0

    def test_manager_node_produces_nonzero_delta_when_stance_is_bearish(self) -> None:
        """End-to-end: research manager node computes non-zero delta when LLM
        returns a bearish net_stance against a buy-biased analyst (#814)."""
        compiled = build_pipeline(
            AtlasResearchState,
            [build_phase7cd_research_manager(["SPY"])],
        )
        state = _state(("SPY",))
        # Analyst is strongly bullish (+4) — but the debate outcome is bearish.
        state.phase7c_analysts = {
            "SPY": {
                "ticker": "SPY",
                "conviction_score": 4,
                "stance": "buy",
                "thesis": "Strong momentum setup",
                "risks": "",
                "sources": [],
            }
        }
        state.phase7cd_debates = {
            "SPY": {
                "rounds": [
                    {
                        "round_number": 1,
                        "bull_argument": "Momentum is strong",
                        "bear_argument": "Overvalued on every metric; Fed still tightening",
                    }
                ]
            }
        }

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            # LLM says bearish — manager node must override conviction_delta to -2.
            return json.dumps(
                {
                    "ticker": "SPY",
                    "rounds": [],
                    "bull_thesis": "momentum play",
                    "bear_thesis": "overvalued; rate headwinds",
                    "net_stance": "bearish",
                    "conviction_delta": 0,  # LLM-returned 0 must be overridden
                }
            )

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        summary = final.phase7cd_debates["SPY"]
        assert summary["net_stance"] == "bearish"
        # Pre-debate conviction was +4 (≥ 3) and net_stance is bearish → expected delta = -2.
        assert summary["conviction_delta"] != 0, (
            "conviction_delta must not be 0 when stance ≠ neutral"
        )
        assert summary["conviction_delta"] == -2
        # rounds_count must also be present (#814).
        assert summary.get("rounds_count") == 1


# ─── Multi-round debate (#814) ──────────────────────────────────────────────


@pytest.mark.unit
class TestMultiRoundDebate:
    """Compile with rounds=2; assert both rounds run and rounds_count > 1."""

    def test_two_round_pipeline_runs_both_rounds(self) -> None:
        compiled = build_pipeline(
            AtlasResearchState,
            list(build_phase7cd(["AAPL"], rounds=2)),
        )
        state = _state(("AAPL",), debate_rounds=2)

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
            seg = body["segment"]
            if seg.startswith("bull-researcher-"):
                return _bull_payload(body["ticker"], body["round_number"])
            if seg.startswith("bear-researcher-"):
                return _bear_payload(body["ticker"], body["round_number"])
            # research-manager
            return json.dumps(
                {
                    "ticker": body["ticker"],
                    "rounds": [],
                    "bull_thesis": "strong bull case",
                    "bear_thesis": "mild bear case",
                    "net_stance": "bullish",
                    "conviction_delta": 1,
                }
            )

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        summary = final.phase7cd_debates["AAPL"]
        # Both rounds must have run — rounds list has 2 entries.
        assert len(summary["rounds"]) == 2, (
            f"Expected 2 debate rounds, got {len(summary['rounds'])}"
        )
        assert summary["rounds"][0]["round_number"] == 1
        assert summary["rounds"][1]["round_number"] == 2
        # rounds_count convenience field must equal the round list length.
        assert summary.get("rounds_count") == 2

    def test_preferences_debate_rounds_honored_by_compile_time_phases(self) -> None:
        """round count > 1 is honored: 2 rounds → 5 phases (2×bull+bear + manager)."""
        phases = build_phase7cd(["AAPL"], rounds=2)
        assert len(phases) == 5
        node_names = [n.name for phase in phases for n in phase.nodes]
        # Both round 1 and round 2 bull/bear nodes must be present.
        assert any("r1" in name for name in node_names)
        assert any("r2" in name for name in node_names)

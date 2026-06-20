"""Phase 7C-D debate gating tests (#933).

Gating skips the 3 LLM calls (bull → bear → research-manager) for a ticker
when the Phase 7C analyst payload shows tight agreement — a "rubber-stamp"
debate that would emit ``conviction_delta=0`` for zero portfolio impact.

Covers:
- ``_should_gate_debate`` predicate truth table (agreement vs disagreement,
  held-name-unchanged, prior_analyst materially changed, sell stance).
- Flag resolution: default ON for delta runs, OFF for baseline; explicit
  ``HERMES_DEBATE_GATING=0`` always disables; ``=1`` always enables.
- Runtime short-circuit: agreement + gating on → bull/bear nodes return ``{}``
  and the manager emits a deterministic neutral ``DebateSummary`` with
  ``conviction_delta=0`` and the LLM (``completion_text``) is NEVER called.
- Disagreement (high conviction or sell stance) → full debate path runs (LLM
  called).
- Telemetry: gated tickers carry a ``gated`` marker on the emitted summary.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState, PriorContext
from digiquant.olympus.hermes.phases.phase7cd_debate import (
    _debate_gating_enabled,
    _should_gate_debate,
    build_phase7cd,
)


@pytest.fixture(autouse=True)
def _no_data_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "0")


@pytest.fixture(autouse=True)
def _clear_gating_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    # Each test sets the flag explicitly; never inherit the developer's env.
    monkeypatch.delenv("HERMES_DEBATE_GATING", raising=False)


def _state(
    *,
    run_type: str = "delta",
    conviction_score: int = 1,
    stance: str = "hold",
    ticker: str = "AAPL",
    held: bool = False,
    prior_analyst: dict[str, Any] | None = None,
) -> AtlasResearchState:
    prior_book = [{"ticker": ticker, "weight": 0.05}] if held else []
    prior_ctx = PriorContext(
        prior_book=prior_book,
        prior_analyst_by_ticker={ticker: prior_analyst} if prior_analyst else {},
    )
    state = AtlasResearchState(
        run_type=run_type,
        run_date=date(2026, 6, 20),
        config=AtlasConfigBundle(watchlist=[ticker]),
        prior_context=prior_ctx,
    )
    state.phase6_bias_row = {"date": "2026-06-20"}
    payload: dict[str, Any] = {
        "ticker": ticker,
        "conviction_score": conviction_score,
        "stance": stance,
        "thesis": f"{ticker} thesis",
        "sources": [],
        "held_in_prior_book": held,
    }
    if prior_analyst:
        payload["prior_analyst"] = dict(prior_analyst)
    state.phase7c_analysts = {ticker: payload}
    return state


# ─── Flag resolution ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestGatingFlag:
    def test_default_on_for_delta(self) -> None:
        assert _debate_gating_enabled(_state(run_type="delta")) is True

    def test_default_off_for_baseline(self) -> None:
        assert _debate_gating_enabled(_state(run_type="baseline")) is False

    def test_default_off_for_monthly(self) -> None:
        assert _debate_gating_enabled(_state(run_type="monthly")) is False

    def test_env_zero_disables_on_delta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMES_DEBATE_GATING", "0")
        assert _debate_gating_enabled(_state(run_type="delta")) is False

    def test_env_one_enables_on_baseline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMES_DEBATE_GATING", "1")
        assert _debate_gating_enabled(_state(run_type="baseline")) is True


# ─── Predicate truth table ───────────────────────────────────────────────────


@pytest.mark.unit
class TestShouldGatePredicate:
    def test_agreement_gates(self) -> None:
        # |conviction| <= 2 and stance not sell → rubber stamp → gate.
        assert _should_gate_debate(_state(conviction_score=1, stance="hold"), "AAPL") is True
        assert _should_gate_debate(_state(conviction_score=2, stance="buy"), "AAPL") is True
        assert _should_gate_debate(_state(conviction_score=-2, stance="watch"), "AAPL") is True

    def test_high_conviction_never_gates(self) -> None:
        assert _should_gate_debate(_state(conviction_score=3, stance="buy"), "AAPL") is False
        assert _should_gate_debate(_state(conviction_score=-4, stance="buy"), "AAPL") is False

    def test_sell_stance_never_gates(self) -> None:
        # Even a low-magnitude sell must be debated.
        assert _should_gate_debate(_state(conviction_score=1, stance="sell"), "AAPL") is False

    def test_threshold_is_configurable(self) -> None:
        s = _state(conviction_score=2, stance="hold")
        assert _should_gate_debate(s, "AAPL", threshold=1) is False
        assert _should_gate_debate(s, "AAPL", threshold=2) is True

    def test_held_unchanged_prior_analyst_gates(self) -> None:
        # Held name whose prior analyst stance is unchanged → gate even if the
        # current conviction is high (the position is already understood).
        s = _state(
            conviction_score=4,
            stance="buy",
            held=True,
            prior_analyst={"stance": "buy", "conviction_score": 4},
        )
        assert _should_gate_debate(s, "AAPL") is True

    def test_held_changed_prior_analyst_does_not_gate(self) -> None:
        # Prior analyst materially changed (stance flip) → must debate.
        s = _state(
            conviction_score=4,
            stance="sell",
            held=True,
            prior_analyst={"stance": "buy", "conviction_score": 4},
        )
        assert _should_gate_debate(s, "AAPL") is False

    def test_missing_analyst_does_not_gate(self) -> None:
        s = _state(conviction_score=1, stance="hold")
        s.phase7c_analysts = {}
        assert _should_gate_debate(s, "AAPL") is False


# ─── Runtime short-circuit (no LLM calls) ────────────────────────────────────


def _fake_factory(calls: list[str]):
    def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
        user_block = msgs[1]["content"]
        inputs_part = next(
            p for p in user_block if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
        )
        body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
        seg = body["segment"]
        calls.append(seg)
        if seg.startswith("bull-researcher-"):
            return json.dumps(
                {
                    "role": "bull",
                    "ticker": body["ticker"],
                    "round_number": body["round_number"],
                    "argument": "bull",
                }
            )
        if seg.startswith("bear-researcher-"):
            return json.dumps(
                {
                    "role": "bear",
                    "ticker": body["ticker"],
                    "round_number": body["round_number"],
                    "argument": "bear",
                }
            )
        return json.dumps(
            {
                "ticker": body["ticker"],
                "rounds": [],
                "bull_thesis": "b",
                "bear_thesis": "r",
                "net_stance": "bullish",
                "conviction_delta": 1,
            }
        )

    return fake


@pytest.mark.unit
class TestRuntimeShortCircuit:
    def test_agreement_gating_on_skips_all_llm_calls(self) -> None:
        compiled = build_pipeline(AtlasResearchState, list(build_phase7cd(["AAPL"], rounds=1)))
        state = _state(run_type="delta", conviction_score=1, stance="hold")

        calls: list[str] = []
        with patch(
            "digigraph.graph.research_agent.completion_text", side_effect=_fake_factory(calls)
        ) as mock:
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        assert mock.call_count == 0, "gated debate must make zero LLM calls"
        assert calls == []
        summary = final.phase7cd_debates["AAPL"]
        assert summary["net_stance"] == "neutral"
        assert summary["conviction_delta"] == 0
        assert summary["rounds"] == []
        assert "gated" in summary["bull_thesis"]
        assert "gated" in summary["bear_thesis"]
        assert summary.get("gated") is True

    def test_disagreement_runs_full_debate(self) -> None:
        compiled = build_pipeline(AtlasResearchState, list(build_phase7cd(["AAPL"], rounds=1)))
        state = _state(run_type="delta", conviction_score=4, stance="buy")

        calls: list[str] = []
        with patch(
            "digigraph.graph.research_agent.completion_text", side_effect=_fake_factory(calls)
        ) as mock:
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        # bull + bear + manager → 3 LLM calls.
        assert mock.call_count == 3
        summary = final.phase7cd_debates["AAPL"]
        assert summary["net_stance"] == "bullish"
        assert summary.get("gated") is not True
        assert len(summary["rounds"]) == 1

    def test_sell_stance_runs_full_debate(self) -> None:
        compiled = build_pipeline(AtlasResearchState, list(build_phase7cd(["AAPL"], rounds=1)))
        state = _state(run_type="delta", conviction_score=1, stance="sell")

        calls: list[str] = []
        with patch(
            "digigraph.graph.research_agent.completion_text", side_effect=_fake_factory(calls)
        ) as mock:
            compiled.invoke(state)
        assert mock.call_count == 3

    def test_flag_off_runs_full_debate_on_agreement(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMES_DEBATE_GATING", "0")
        compiled = build_pipeline(AtlasResearchState, list(build_phase7cd(["AAPL"], rounds=1)))
        state = _state(run_type="delta", conviction_score=1, stance="hold")

        calls: list[str] = []
        with patch(
            "digigraph.graph.research_agent.completion_text", side_effect=_fake_factory(calls)
        ) as mock:
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        assert mock.call_count == 3, "HERMES_DEBATE_GATING=0 must force the full debate"
        assert final.phase7cd_debates["AAPL"].get("gated") is not True

    def test_baseline_does_not_gate_on_agreement(self) -> None:
        # Default OFF for baseline → existing baseline runs are unaffected.
        compiled = build_pipeline(AtlasResearchState, list(build_phase7cd(["AAPL"], rounds=1)))
        state = _state(run_type="baseline", conviction_score=1, stance="hold")

        calls: list[str] = []
        with patch(
            "digigraph.graph.research_agent.completion_text", side_effect=_fake_factory(calls)
        ) as mock:
            compiled.invoke(state)
        assert mock.call_count == 3

    def test_held_unchanged_gates_full_pipeline(self) -> None:
        compiled = build_pipeline(AtlasResearchState, list(build_phase7cd(["AAPL"], rounds=1)))
        state = _state(
            run_type="delta",
            conviction_score=4,
            stance="buy",
            held=True,
            prior_analyst={"stance": "buy", "conviction_score": 4},
        )

        calls: list[str] = []
        with patch(
            "digigraph.graph.research_agent.completion_text", side_effect=_fake_factory(calls)
        ) as mock:
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        assert mock.call_count == 0
        assert final.phase7cd_debates["AAPL"].get("gated") is True

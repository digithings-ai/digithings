"""H6 deliberation convergence tests (Olympus #930 PR 4b)."""

from __future__ import annotations

import json
from datetime import date
from typing import (
    Any,  # score:allow untyped any — scored-lint: heterogeneous fake-row / fixture dicts
)
from unittest.mock import patch

import pytest
from digigraph.graph.pipeline_builder import build_pipeline
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    FocusRosterEntry,
    PhaseHermesState,
    PriorContext,
)
from digiquant.olympus.hermes.focus_roster import with_fanout_ticker
from digiquant.olympus.hermes.models.deliberation import (
    DeliberationAnalystTurn,
    DeliberationPmTurn,
    DeliberationSummary,
    DeliberationTurn,
)
from digiquant.olympus.hermes.payloads import deliberation_summaries
from digiquant.olympus.hermes.phases import h6_deliberation
from digiquant.olympus.hermes.phases.h6_deliberation import (
    build_h6_deliberation,
    build_h6_from_state,
)


def _state() -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 6, 20),
        config=AtlasConfigBundle(watchlist=["AAPL"]),
    )
    state.phase_hermes = PhaseHermesState(
        focus_roster=[FocusRosterEntry(ticker="AAPL", roster_reason="held")],
        asset_analysts={
            "AAPL": {
                "ticker": "AAPL",
                "conviction_score": 3,
                "stance": "buy",
                "thesis": "growth intact",
                "risks": "margin compression",
                "sources": [],
            }
        },
    )
    return state


@pytest.mark.unit
class TestDeliberationConvergence:
    def test_pm_challenge_then_analyst_converges(self) -> None:
        compiled = build_pipeline(
            AtlasResearchState, [build_h6_deliberation(["AAPL"], held={"AAPL"})]
        )
        calls: list[str] = []

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            schema = next(
                p["text"].split("name: ")[1].split(")")[0]
                for msg in msgs
                for p in msg.get("content", [])
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            calls.append(schema)
            if schema == "DeliberationPmTurn":
                return json.dumps(
                    DeliberationPmTurn(
                        converged=False, challenge="justify the bull case"
                    ).model_dump()
                )
            if schema == "DeliberationAnalystTurn":
                return json.dumps(
                    DeliberationAnalystTurn(
                        converged=True,
                        response="updated evidence supports buy",
                        conclusion="aligned on buy",
                        net_stance="bullish",
                    ).model_dump()
                )
            raise AssertionError(f"unexpected schema {schema}")

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(_state())
        final = AtlasResearchState.model_validate(result)
        summary = final.phase_hermes.deliberation_summaries["AAPL"]
        assert summary["converged"] is True
        assert calls == ["DeliberationPmTurn", "DeliberationAnalystTurn"]

    def test_max_rounds_forces_convergence_with_phase_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_DELIBERATION_MAX_ROUNDS", "1")
        compiled = build_pipeline(
            AtlasResearchState, [build_h6_deliberation(["AAPL"], held={"AAPL"})]
        )

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            schema = next(
                p["text"].split("name: ")[1].split(")")[0]
                for msg in msgs
                for p in msg.get("content", [])
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            if schema == "DeliberationPmTurn":
                return json.dumps(
                    DeliberationPmTurn(
                        converged=False, challenge="push back on valuation"
                    ).model_dump()
                )
            if schema == "DeliberationAnalystTurn":
                return json.dumps(
                    DeliberationAnalystTurn(
                        converged=False,
                        response="still bullish on services growth",
                        conclusion="maintain buy",
                        net_stance="bullish",
                        conviction_delta=1,
                    ).model_dump()
                )
            raise AssertionError(f"unexpected schema {schema}")

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(_state())
        final = AtlasResearchState.model_validate(result)
        summary = final.phase_hermes.deliberation_summaries["AAPL"]
        assert summary["converged"] is True
        assert summary["escalated"] is True
        assert summary["cap_reason"] == "max_rounds"
        assert summary["net_stance"] == "bullish"
        assert final.errors
        assert final.errors[0].retryable is False
        assert "max_rounds" in final.errors[0].message

    def test_min_rounds_one_allows_instant_pm_convergence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The floor is opt-out: ATLAS_DELIBERATION_MIN_ROUNDS=1 restores the cheap quiet path
        # — a PM that converges on its first turn returns WITHOUT an analyst turn. (The
        # default floor is 2, exercised by the test below.)
        monkeypatch.setenv("ATLAS_DELIBERATION_MIN_ROUNDS", "1")
        compiled = build_pipeline(
            AtlasResearchState, [build_h6_deliberation(["AAPL"], held={"AAPL"})]
        )
        calls: list[str] = []

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            schema = next(
                p["text"].split("name: ")[1].split(")")[0]
                for msg in msgs
                for p in msg.get("content", [])
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            calls.append(schema)
            if schema == "DeliberationPmTurn":
                return json.dumps(
                    DeliberationPmTurn(
                        converged=True,
                        challenge="sized vs book; downside tested",
                        conclusion="agree, buy",
                        net_stance="bullish",
                    ).model_dump()
                )
            raise AssertionError(f"unexpected schema {schema}")

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            compiled.invoke(_state())
        assert calls == ["DeliberationPmTurn"]  # no analyst turn — instant convergence allowed

    def test_min_rounds_floor_blocks_round_one_rubber_stamp(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # With the floor raised to 2, a PM that wants to converge on round 1 is forced to
        # record its challenge and the analyst must respond before convergence is honored —
        # no more round-1 rubber-stamp (#945).
        monkeypatch.setenv("ATLAS_DELIBERATION_MIN_ROUNDS", "2")
        compiled = build_pipeline(
            AtlasResearchState, [build_h6_deliberation(["AAPL"], held={"AAPL"})]
        )
        calls: list[str] = []

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            schema = next(
                p["text"].split("name: ")[1].split(")")[0]
                for msg in msgs
                for p in msg.get("content", [])
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            calls.append(schema)
            if schema == "DeliberationPmTurn":
                return json.dumps(
                    DeliberationPmTurn(
                        converged=True, challenge="looks fine", conclusion="agree"
                    ).model_dump()
                )
            if schema == "DeliberationAnalystTurn":
                return json.dumps(
                    DeliberationAnalystTurn(
                        converged=True, response="confirmed", conclusion="agree"
                    ).model_dump()
                )
            raise AssertionError(f"unexpected schema {schema}")

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(_state())
        final = AtlasResearchState.model_validate(result)
        assert "DeliberationAnalystTurn" in calls  # the floor forced an analyst response
        summary = final.phase_hermes.deliberation_summaries["AAPL"]
        assert summary["converged"] is True
        assert len(summary["transcript"]) >= 2  # PM challenge + analyst response

    def test_deliberation_summaries_persist_convergence_metadata(self) -> None:
        # payloads.deliberation_summaries must carry converged / escalated / cap_reason /
        # rounds_count into the persisted document shape — the audit found them stripped
        # before the write, leaving zero observability (#945).
        state = _state()
        state.phase_hermes.deliberation_summaries = {
            "AAPL": DeliberationSummary(
                ticker="AAPL",
                converged=True,
                conclusion="aligned on buy",
                net_stance="bullish",
                conviction_delta=1,
                transcript=[
                    DeliberationTurn(role="pm", round_number=1, message="challenge"),
                    DeliberationTurn(role="analyst", round_number=1, message="response"),
                    DeliberationTurn(role="pm", round_number=2, message="converge"),
                ],
                escalated=True,
                cap_reason="max_rounds",
            ).model_dump(mode="json")
        }
        shaped = deliberation_summaries(state)["AAPL"]
        assert shaped["converged"] is True
        assert shaped["escalated"] is True
        assert shaped["cap_reason"] == "max_rounds"
        assert shaped["rounds_count"] == 2
        assert shaped["conclusion"] == "aligned on buy"


@pytest.mark.unit
class TestDeliberationFailureCarry:
    """#1742 — a crashed deliberation must be distinguishable from a benign carry.

    On 2026-07-31, 31 of 39 debates died and each published ``carried=true`` +
    ``converged=true`` — the same flags as the 4 intentional fingerprint skips.
    """

    @staticmethod
    def _run_h6(state: AtlasResearchState) -> dict[str, Any]:
        # Drives the production fan-out worker directly: this exercises the carry
        # construction without standing up the LLM plumbing the loop tests need.
        return build_h6_from_state().worker.run(with_fanout_ticker(state, "AAPL"))

    def test_crash_carry_is_flagged_and_is_not_converged(self) -> None:
        with patch.object(
            h6_deliberation,
            "run_deliberation_loop",
            side_effect=ValueError("Expecting value: line 1 column 1 (char 0)"),
        ):
            out = self._run_h6(_state())
        summary = out["phase_hermes"].deliberation_summaries["AAPL"]
        assert summary["carried"] is True
        assert summary["carry_reason"] == "llm_failure"
        # No PM challenge ran, so there is no debate to have converged.
        assert summary["converged"] is False
        assert summary["transcript"] == []
        assert summary["selection_reason"]  # WP11.3 provenance on failure path
        # The PhaseError shape the Atlas Hermes-density gate counts stays untouched.
        assert out["errors"][0].phase == "hermes_h6_deliberation"
        assert out["errors"][0].message.startswith("deliberation LLM failed")

    def test_fingerprint_skip_carry_is_labelled_benign(self) -> None:
        state = _state()
        state.prior_context = PriorContext(
            prior_deliberation_by_ticker={
                "AAPL": {
                    "conclusion_excerpt": "prior agreement",
                    "net_stance": "neutral",
                    "conviction_delta": 0,
                }
            }
        )
        with patch.object(h6_deliberation, "deliberation_skip_signal", return_value=True):
            out = self._run_h6(state)
        summary = out["phase_hermes"].deliberation_summaries["AAPL"]
        assert summary["carried"] is True
        assert summary["carry_reason"] == "fingerprint_skip"
        # The prior debate did converge; nothing moved, so it still stands (#925).
        assert summary["converged"] is True
        assert "errors" not in out

    def test_crash_carry_publishes_no_bear_thesis(self) -> None:
        state = _state()
        state.phase_hermes.deliberation_summaries = {
            "AAPL": DeliberationSummary(
                ticker="AAPL",
                converged=False,
                conclusion="growth intact",
                net_stance="bullish",
                carried=True,
                carry_reason="llm_failure",
            ).model_dump(mode="json")
        }
        shaped = deliberation_summaries(state)["AAPL"]
        assert shaped["carry_reason"] == "llm_failure"
        assert shaped["converged"] is False
        assert shaped["rounds_count"] == 0
        # The carried analyst thesis is a true statement about what happened; a bear case
        # byte-identical to it is not, and it made the document look two-sided.
        assert shaped["bull_thesis"] == "growth intact"
        assert shaped["bear_thesis"] == ""

    def test_benign_carry_keeps_the_mirrored_bear_fallback(self) -> None:
        state = _state()
        state.phase_hermes.deliberation_summaries = {
            "AAPL": DeliberationSummary(
                ticker="AAPL",
                conclusion="prior agreement",
                carried=True,
                carry_reason="fingerprint_skip",
            ).model_dump(mode="json")
        }
        shaped = deliberation_summaries(state)["AAPL"]
        assert shaped["carry_reason"] == "fingerprint_skip"
        assert shaped["bear_thesis"] == "prior agreement"

    def test_chat_transcript_publishes_without_mirrored_theses(self) -> None:
        # H6 has no bull/bear fields — remapping both to conclusion made the document
        # look two-sided while the real debate lived only under rounds/transcript.
        state = _state()
        state.phase_hermes.deliberation_summaries = {
            "DBO": DeliberationSummary(
                ticker="DBO",
                converged=True,
                conclusion="Pass — thesis completed, no position.",
                net_stance="neutral",
                conviction_delta=0,
                transcript=[
                    DeliberationTurn(
                        role="pm",
                        round_number=1,
                        message="Conviction 0 on a non-held ticker is a non-call.",
                    ),
                    DeliberationTurn(
                        role="analyst",
                        round_number=1,
                        message="Accepted. Recommend COMPLETED; no book add.",
                    ),
                ],
            ).model_dump(mode="json")
        }
        shaped = deliberation_summaries(state)["DBO"]
        assert shaped["rounds_count"] == 1
        assert shaped["transcript"][0]["role"] == "pm"
        assert shaped["rounds"][1]["role"] == "analyst"
        assert shaped["bull_thesis"] == ""
        assert shaped["bear_thesis"] == ""
        assert shaped["conclusion"].startswith("Pass")


@pytest.mark.unit
class TestH6SelectionWiring:
    """WP11.3 — selected success round floor, materiality blinding, failure provenance."""

    def test_enforce_selected_success_meets_two_round_floor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OLYMPUS_H6_SELECTION_MODE", "enforce")
        monkeypatch.setenv("ATLAS_DELIBERATION_MIN_ROUNDS", "2")
        compiled = build_pipeline(
            AtlasResearchState, [build_h6_deliberation(["AAPL"], held={"AAPL"})]
        )
        calls: list[str] = []

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            schema = next(
                p["text"].split("name: ")[1].split(")")[0]
                for msg in msgs
                for p in msg.get("content", [])
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            # Materiality / selection features must never appear in provider prompts.
            blob = json.dumps(msgs)
            assert "weight_pct" not in blob
            assert "h6_selection" not in blob
            assert "materiality" not in blob
            calls.append(schema)
            if schema == "DeliberationPmTurn":
                # Round-1 rubber-stamp blocked by min_rounds=2.
                return json.dumps(
                    DeliberationPmTurn(
                        converged=True,
                        challenge="justify sizing vs book",
                        conclusion="agree buy",
                        net_stance="bullish",
                    ).model_dump()
                )
            if schema == "DeliberationAnalystTurn":
                return json.dumps(
                    DeliberationAnalystTurn(
                        converged=True,
                        response="evidence supports buy",
                        conclusion="aligned on buy",
                        net_stance="bullish",
                    ).model_dump()
                )
            raise AssertionError(f"unexpected schema {schema}")

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(_state())
        final = AtlasResearchState.model_validate(result)
        summary = final.phase_hermes.deliberation_summaries["AAPL"]
        assert summary["converged"] is True
        assert summary["selection_reason"] == "decision_boundary"
        assert summary["h6_selection"]["budget"]["min_rounds"] >= 2
        assert "DeliberationAnalystTurn" in calls
        assert len(summary["transcript"]) >= 2

    def test_provider_failure_keeps_typed_selection_provenance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OLYMPUS_H6_SELECTION_MODE", "enforce")
        with patch.object(
            h6_deliberation,
            "run_deliberation_loop",
            side_effect=RuntimeError("provider unavailable"),
        ):
            out = build_h6_from_state().worker.run(with_fanout_ticker(_state(), "AAPL"))
        summary = out["phase_hermes"].deliberation_summaries["AAPL"]
        assert summary["carry_reason"] == "llm_failure"
        assert summary["converged"] is False
        assert summary["selection_reason"] == "decision_boundary"
        assert summary["h6_selection"]["action"] == "select"
        assert out["errors"][0].message.startswith("deliberation LLM failed")

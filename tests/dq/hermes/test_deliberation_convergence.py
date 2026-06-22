"""H6 deliberation convergence tests (Olympus #930 PR 4b)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa  # scored-lint: heterogeneous fake-row / fixture dicts
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    FocusRosterEntry,
    PhaseHermesState,
)
from digiquant.olympus.hermes.models.deliberation import (
    DeliberationAnalystTurn,
    DeliberationPmTurn,
    DeliberationSummary,
    DeliberationTurn,
)
from digiquant.olympus.hermes.payloads import deliberation_summaries
from digiquant.olympus.hermes.phases.h6_deliberation import build_h6_deliberation


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

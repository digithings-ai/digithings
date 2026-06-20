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
from digiquant.olympus.hermes.models.deliberation import DeliberationAnalystTurn, DeliberationPmTurn
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

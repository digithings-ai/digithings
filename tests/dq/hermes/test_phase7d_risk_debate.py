"""Phase 7D risk-temperament debate tests (#431)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa: F401 — used for fake-completion dict shape
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.hermes.phases.phase7d_pm import (
    RiskCase,
    RiskDebateSummary,
    build_phase7d,
    build_phase7d_pm,
    build_phase7d_risk_aggressive,
    build_phase7d_risk_conservative,
)
from digiquant.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
)


def _state_for_debate() -> AtlasResearchState:
    """Minimal state with phase 6 bias + phase 7C analyst payload."""
    state = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        config=AtlasConfigBundle(watchlist=["AAPL", "MSFT"]),
    )
    state.phase6_bias_row = {"date": "2026-04-26", "macro_regime": "late-cycle"}
    state.phase7c_analysts = {
        "AAPL": {"ticker": "AAPL", "conviction_score": 4, "stance": "buy"},
        "MSFT": {"ticker": "MSFT", "conviction_score": 2, "stance": "hold"},
    }
    return state


def _aggressive_payload() -> str:
    return json.dumps({"case": "Convictions on AAPL warrant a 3% lift; cash drag is the risk."})


def _conservative_payload(aggressive_input: str) -> str:
    """The conservative node's output IS the full RiskDebateSummary."""
    return json.dumps(
        {
            "aggressive_case": aggressive_input,
            "conservative_case": "Late-cycle regime + clustered tech exposure — cap the lift at 1%.",
            "key_tension": "Aggressive trusts conviction; Conservative warns regime is fragile.",
        }
    )


@pytest.mark.unit
class TestRiskAggressiveNode:
    def test_aggressive_node_writes_aggressive_case_only(self) -> None:
        compiled = build_pipeline(AtlasResearchState, [build_phase7d_risk_aggressive()])
        state = _state_for_debate()

        with patch(
            "digigraph.graph.research_agent.chat_completion",
            return_value=_aggressive_payload(),
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        debate = final.phase7d_risk_debate
        assert debate is not None
        assert debate["aggressive_case"] == (
            "Convictions on AAPL warrant a 3% lift; cash drag is the risk."
        )
        # Conservative half intentionally empty — the conservative node fills it.
        assert debate["conservative_case"] == ""
        assert debate["key_tension"] == ""

    def test_aggressive_node_uses_risk_aggressive_skill(self) -> None:
        from digiquant.hermes.phases.phase7d_pm import _risk_aggressive_node

        captured: dict[str, Any] = {}

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            schema_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            captured["schema_name"] = "RiskCase" if "RiskCase" in schema_part["text"] else "OTHER"
            return _aggressive_payload()

        with patch("digigraph.graph.research_agent.chat_completion", side_effect=fake):
            _risk_aggressive_node(_state_for_debate())

        assert captured.get("schema_name") == "RiskCase"


@pytest.mark.unit
class TestRiskConservativeNode:
    def test_conservative_node_writes_full_debate_summary(self) -> None:
        compiled = build_pipeline(AtlasResearchState, [build_phase7d_risk_conservative()])
        state = _state_for_debate()
        state.phase7d_risk_debate = {
            "aggressive_case": "Lift AAPL by 3%.",
            "conservative_case": "",
            "key_tension": "",
        }

        with patch(
            "digigraph.graph.research_agent.chat_completion",
            return_value=_conservative_payload("Lift AAPL by 3%."),
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        debate = final.phase7d_risk_debate
        assert debate is not None
        assert debate["aggressive_case"] == "Lift AAPL by 3%."
        assert "Late-cycle" in debate["conservative_case"]
        assert "Aggressive trusts conviction" in debate["key_tension"]


@pytest.mark.unit
class TestPmReadsRiskDebate:
    def test_pm_node_phase_inputs_include_risk_debate_when_set(self) -> None:
        from digiquant.hermes.phases.phase7d_pm import _pm_node

        state = _state_for_debate()
        state.phase7d_risk_debate = {
            "aggressive_case": "AGG",
            "conservative_case": "CONS",
            "key_tension": "TEN",
        }

        captured_inputs: dict[str, Any] = {}

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            # Find the PHASE_INPUTS chunk and parse it back to verify
            # risk_debate is threaded through.
            user_block = msgs[1]["content"]
            inputs_part = next(
                p for p in user_block if isinstance(p, dict) and "PHASE_INPUTS" in p.get("text", "")
            )
            captured_inputs["text"] = inputs_part["text"]
            return json.dumps({"recommended_portfolio": [], "actions": [], "notes": "n/a"})

        with patch("digigraph.graph.research_agent.chat_completion", side_effect=fake):
            _pm_node(state)

        assert "risk_debate" in captured_inputs["text"]
        assert "AGG" in captured_inputs["text"]
        assert "TEN" in captured_inputs["text"]

    def test_pm_node_works_with_empty_risk_debate(self) -> None:
        """Backward-compat: PM must still produce a decision when no debate ran."""
        from digiquant.hermes.phases.phase7d_pm import _pm_node

        state = _state_for_debate()
        # No risk debate populated — simulate skipping the debater nodes.

        with patch(
            "digigraph.graph.research_agent.chat_completion",
            return_value=json.dumps({"recommended_portfolio": [], "actions": [], "notes": "ok"}),
        ):
            update = _pm_node(state)
        assert update["phase7d_rebalance"]["notes"] == "ok"


@pytest.mark.unit
class TestPhase7dStructure:
    def test_build_phase7d_returns_three_sequential_phases(self) -> None:
        phases = build_phase7d()
        assert len(phases) == 3
        names = [p.name for p in phases]
        assert names == [
            "phase7d_risk_aggressive",
            "phase7d_risk_conservative",
            "phase7d_pm",
        ]

    def test_each_subphase_has_one_node(self) -> None:
        for phase in build_phase7d():
            assert len(phase.nodes) == 1, f"{phase.name} should have 1 node"

    def test_pm_phase_node_name_unchanged(self) -> None:
        pm = build_phase7d_pm()
        assert pm.nodes[0].name == "pm-rebalance"

    def test_full_phase7d_pipeline_compiles(self) -> None:
        """Smoke test: spread the three sub-phases into a pipeline cleanly."""
        compiled = build_pipeline(AtlasResearchState, list(build_phase7d()))
        assert compiled is not None

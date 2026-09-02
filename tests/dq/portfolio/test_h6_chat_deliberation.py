"""WP-F — H6 analyst replies use a meeting skill, not the H5 report skill."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import (
    Any,  # score:allow untyped any — scored-lint: heterogeneous fake-row / fixture dicts
)
from unittest.mock import patch

import pytest
from digigraph.graph.pipeline_builder import build_pipeline
from digiquant.research.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    FocusRosterEntry,
    PhaseHermesState,
)
from digiquant.portfolio.models.deliberation import (
    DeliberationAnalystTurn,
    DeliberationPmTurn,
)
from digiquant.portfolio.phases.h6_deliberation import build_h6_deliberation
from digiquant.portfolio.skills import load_skill_full

pytestmark = pytest.mark.unit

_H6_PATH = (
    Path(__file__).resolve().parents[3]
    / "digiquant/src/digiquant/olympus/hermes/phases/h6_deliberation.py"
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


def _schema_from_msgs(msgs: list[dict[str, Any]]) -> str:
    return next(
        p["text"].split("name: ")[1].split(")")[0]
        for msg in msgs
        for p in msg.get("content", [])
        if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
    )


class TestH6AnalystSkillLoad:
    def test_h6_source_loads_deliberation_analyst_response_not_h5(self) -> None:
        source = _H6_PATH.read_text(encoding="utf-8")
        assert 'load_skill_full("asset-analyst")' not in source
        assert 'load_skill_full("deliberation-analyst-response")' in source

    def test_analyst_turn_does_not_load_h5_asset_analyst_skill(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_DELIBERATION_MIN_ROUNDS", "2")
        loaded: list[str] = []

        def fake_load(slug: str) -> str:
            loaded.append(slug)
            return f"# stub skill {slug}"

        compiled = build_pipeline(
            AtlasResearchState, [build_h6_deliberation(["AAPL"], held={"AAPL"})]
        )
        pm_calls = {"n": 0}

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            schema = _schema_from_msgs(msgs)
            if schema == "DeliberationPmTurn":
                pm_calls["n"] += 1
                if pm_calls["n"] == 1:
                    return json.dumps(
                        DeliberationPmTurn(
                            converged=False, challenge="Why hold this versus the book?"
                        ).model_dump()
                    )
                return json.dumps(
                    DeliberationPmTurn(
                        converged=True,
                        challenge="",
                        conclusion="Agreed — keep the buy, size small versus the book.",
                        net_stance="bullish",
                    ).model_dump()
                )
            if schema == "DeliberationAnalystTurn":
                return json.dumps(
                    DeliberationAnalystTurn(
                        converged=False,
                        response="Services growth still funds the multiple.",
                    ).model_dump()
                )
            raise AssertionError(f"unexpected schema {schema}")

        with (
            patch(
                "digiquant.portfolio.phases.h6_deliberation.load_skill_full",
                side_effect=fake_load,
            ),
            patch("digigraph.graph.research_agent.completion_text", side_effect=fake),
        ):
            result = compiled.invoke(_state())

        final = AtlasResearchState.model_validate(result)
        summary = final.phase_hermes.deliberation_summaries["AAPL"]
        assert "asset-analyst" not in loaded
        assert "deliberation-analyst-response" in loaded
        assert "deliberation" in loaded
        transcript = summary["transcript"]
        assert transcript[-1]["role"] == "pm"
        assert "keep the buy" in transcript[-1]["message"]

    def test_deliberation_analyst_response_skill_is_a_meeting_reply(self) -> None:
        body = load_skill_full("deliberation-analyst-response")
        lowered = body.lower()
        assert "meeting" in lowered
        assert "conversational" in lowered
        assert "AnalystPayload" not in body
        assert "title block" in lowered or "title blocks" in lowered


class TestH6PmSkillChat:
    def test_pm_skill_asks_for_chat_not_challenge_heading(self) -> None:
        body = load_skill_full("deliberation")
        lowered = body.lower()
        assert "challenge:" not in lowered
        assert "chat" in lowered or "message" in lowered
        assert "converge" in lowered

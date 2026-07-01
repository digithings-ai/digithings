from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from digigraph.graph import research_agent


class _Out(BaseModel):
    regime: str
    note: str


@pytest.mark.unit
def test_tool_path_uses_run_tools_and_validates():
    calls = {}

    def fake_cwt(
        model,
        messages,
        tools,
        execute_tool,
        *,
        temperature=0.2,
        max_tool_rounds=5,
        on_tool_step=None,
        search_parameters=None,
    ):
        calls["tools"] = tools
        calls["search_parameters"] = search_parameters
        # Simulate the model grounding then emitting valid JSON.
        execute_tool("get_macro_series", {"series_ids": ["DFF"]})
        return json.dumps({"regime": "risk_on", "note": "grounded"})

    executed = []
    with patch.object(research_agent, "run_tools", side_effect=fake_cwt):
        result = research_agent.run_research_agent(
            skill_text="s",
            phase_inputs={},
            shared_context={},
            output_model=_Out,
            model="xai/grok-4.3",
            tools=[{"type": "function", "function": {"name": "get_macro_series"}}],
            execute_tool=lambda n, a: executed.append(n) or "{}",
            search_parameters={"mode": "on"},
        )
    assert result.regime == "risk_on"
    assert calls["search_parameters"] == {"mode": "on"}
    assert calls["tools"][0]["function"]["name"] == "get_macro_series"
    assert executed == ["get_macro_series"]


@pytest.mark.unit
def test_no_tools_keeps_structured_call():
    with patch.object(
        research_agent,
        "completion_text",
        return_value='{"regime":"neutral","note":"x"}',
    ) as cc:
        result = research_agent.run_research_agent(
            skill_text="s",
            phase_inputs={},
            shared_context={},
            output_model=_Out,
            model="xai/grok-4.3",
        )
    assert result.regime == "neutral"
    assert cc.called  # falls back to the structured-output path when no tools

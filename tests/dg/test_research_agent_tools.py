from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from digigraph.graph import research_agent
from pydantic import BaseModel

from digigraph import usage

PROSE_THEN_JSON = 'Sure! Here is the brief:\n{"regime":"risk_on","note":"n"}'


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


@pytest.mark.unit
def test_parallel_tool_keeps_phase_context() -> None:
    def fake_run_tools(
        model,
        messages,
        tools,
        execute_tool,
        **kwargs,
    ):
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(execute_tool, "get_macro_series", {"series_ids": ["DFF"]}).result()
        return json.dumps({"regime": "risk_on", "note": "grounded"})

    usage.start()
    try:
        with patch.object(research_agent, "run_tools", side_effect=fake_run_tools):
            research_agent.run_research_agent(
                skill_text="s",
                phase_inputs={},
                shared_context={},
                output_model=_Out,
                model="xai/grok-4.3",
                phase_slug="phase-2-rates",
                tools=[{"type": "function", "function": {"name": "get_macro_series"}}],
                execute_tool=lambda name, arguments: "{}",
            )
        event = usage.events_snapshot()[0]
    finally:
        usage.reset()

    assert event["phase"] == "phase-2-rates"
    assert event["operation"] == "_Out"


class TestEnforcedToolFreeRetry:
    """#1739 — a tool-grounded turn carries no provider-side schema enforcement, so the
    retry after a parse failure must be TOOL-FREE (which is what lets ``response_format``
    reach the provider) rather than a second, unenforced tool loop."""

    @pytest.mark.unit
    def test_retry_is_tool_free_and_carries_strict_response_format(self) -> None:
        with (
            patch.object(research_agent, "run_tools", return_value="I'll help! no json here") as rt,
            patch.object(
                research_agent, "completion_text", return_value='{"regime":"risk_on","note":"n"}'
            ) as ct,
        ):
            result = research_agent.run_research_agent(
                skill_text="s",
                phase_inputs={},
                shared_context={},
                output_model=_Out,
                model="openrouter/deepseek/deepseek-chat",
                tools=[{"type": "function", "function": {"name": "get_macro_series"}}],
                execute_tool=lambda n, a: "{}",
                max_retries=1,
            )
        assert result.regime == "risk_on"
        # The expensive tool loop runs exactly once; the retry does NOT re-run it.
        assert rt.call_count == 1
        assert ct.call_count == 1
        # ...and the retry is the enforced path: no tools, strict json_schema.
        kwargs = ct.call_args.kwargs
        assert "tools" not in kwargs
        assert kwargs["response_format"]["type"] == "json_schema"
        assert kwargs["response_format"]["json_schema"]["strict"] is True
        assert kwargs["response_format"]["json_schema"]["name"] == "_Out"

    @pytest.mark.unit
    def test_retry_sees_the_failing_prose_so_it_can_reformat_it(self) -> None:
        """``digillm.run_tools`` discards its tool-result messages, so the only grounding the
        retry can carry is the failing attempt's own text — it must be in the conversation."""
        seen: dict[str, object] = {}

        def fake_completion_text(model, messages, **kwargs):
            seen["messages"] = messages
            return '{"regime":"risk_off","note":"n"}'

        with (
            patch.object(research_agent, "run_tools", return_value=PROSE_THEN_JSON),
            patch.object(research_agent, "completion_text", side_effect=fake_completion_text),
        ):
            research_agent.run_research_agent(
                skill_text="s",
                phase_inputs={},
                shared_context={},
                output_model=_Out,
                model="openrouter/deepseek/deepseek-chat",
                tools=[{"type": "function", "function": {"name": "get_macro_series"}}],
                execute_tool=lambda n, a: "{}",
                max_retries=1,
            )
        messages = seen["messages"]
        assert isinstance(messages, list)
        assert any(
            m.get("role") == "assistant" and m.get("content") == PROSE_THEN_JSON for m in messages
        )

    @pytest.mark.unit
    def test_provider_error_on_the_enforced_retry_reraises_the_original_parse_error(self) -> None:
        """Never-worse-than-today: the enforced retry's own failure must not become a NEW
        failure class for the research/portfolio fail-soft handlers keyed on the parse error."""
        with (
            patch.object(research_agent, "run_tools", return_value="prose, no json"),
            patch.object(
                research_agent,
                "completion_text",
                side_effect=RuntimeError("provider down"),
            ) as ct,
        ):
            with pytest.raises(json.JSONDecodeError):
                research_agent.run_research_agent(
                    skill_text="s",
                    phase_inputs={},
                    shared_context={},
                    output_model=_Out,
                    model="openrouter/deepseek/deepseek-chat",
                    tools=[{"type": "function", "function": {"name": "get_macro_series"}}],
                    execute_tool=lambda n, a: "{}",
                    max_retries=1,
                )
        # The enforced retry must actually have been attempted — otherwise this test would
        # pass trivially against the pre-#1739 tool-loop retry, which never calls the
        # enforced path at all.
        assert ct.call_count == 1

    @pytest.mark.unit
    def test_first_attempt_provider_error_still_propagates_on_the_tool_free_path(self) -> None:
        """The never-worse-than-today guard must not swallow a first-attempt provider error
        on the no-tools path, where there is no prior parse failure to degrade to."""
        with (
            patch.object(
                research_agent, "completion_text", side_effect=RuntimeError("provider down")
            ),
            pytest.raises(RuntimeError, match="provider down"),
        ):
            research_agent.run_research_agent(
                skill_text="s",
                phase_inputs={},
                shared_context={},
                output_model=_Out,
                model="openrouter/deepseek/deepseek-chat",
                max_retries=1,
            )

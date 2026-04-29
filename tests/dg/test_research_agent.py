"""Unit tests for the generic research-agent node."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from pydantic import BaseModel, Field, ValidationError

from digigraph.graph.research_agent import (
    ANALYST_SYSTEM,
    _format_scope_block,
    run_research_agent,
)


class _SampleOutput(BaseModel):
    """Minimal target model for tests."""

    regime: str = Field(description="regime label")
    confidence: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


@pytest.mark.unit
class TestFormatScopeBlock:
    def test_parts_have_cache_control_on_stable_blocks(self) -> None:
        parts = _format_scope_block(
            skill_text="research the macro regime",
            phase_inputs={"data": 1},
            shared_context={"config": "x"},
            output_schema={"type": "object"},
            schema_name="Foo",
        )
        # Shared context, skill, and schema are cache-controlled.
        assert parts[0]["text"].startswith("SHARED_CONTEXT:")
        assert parts[0]["cache_control"] == {"type": "ephemeral"}
        assert parts[1]["text"].startswith("RESEARCH_SCOPE")
        assert parts[1]["cache_control"] == {"type": "ephemeral"}
        # Phase inputs are volatile — no cache marker.
        assert parts[2]["text"].startswith("PHASE_INPUTS")
        assert "cache_control" not in parts[2]
        # Schema block stable per segment.
        assert parts[3]["text"].startswith("OUTPUT_SCHEMA")
        assert parts[3]["cache_control"] == {"type": "ephemeral"}

    def test_shared_context_serialized_stably(self) -> None:
        """Sorted keys matter for cache hits — same ctx must produce same text."""
        a = _format_scope_block(
            skill_text="s",
            phase_inputs={},
            shared_context={"b": 2, "a": 1},
            output_schema={},
            schema_name="X",
        )
        b = _format_scope_block(
            skill_text="s",
            phase_inputs={},
            shared_context={"a": 1, "b": 2},
            output_schema={},
            schema_name="X",
        )
        assert a[0]["text"] == b[0]["text"]


@pytest.mark.unit
class TestRunResearchAgent:
    def _fake_response(self, **fields: object) -> str:
        return json.dumps(fields)

    def test_successful_first_try(self) -> None:
        payload = self._fake_response(regime="growth", confidence=0.8, notes=["ok"])
        with patch("digigraph.graph.research_agent.chat_completion", return_value=payload) as mock:
            out = run_research_agent(
                skill_text="x",
                phase_inputs={"d": 1},
                shared_context={"c": 2},
                output_model=_SampleOutput,
                model="test-model",
            )
        assert out.regime == "growth"
        assert out.confidence == 0.8
        assert mock.call_count == 1
        # System prompt in messages; user content is a list of cache-aware parts.
        _args, kwargs = mock.call_args
        messages = mock.call_args.args[1] if mock.call_args.args else kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == ANALYST_SYSTEM
        assert isinstance(messages[1]["content"], list)

    def test_strips_markdown_code_fence(self) -> None:
        fenced = "```json\n" + json.dumps({"regime": "r", "confidence": 0.5}) + "\n```"
        with patch("digigraph.graph.research_agent.chat_completion", return_value=fenced):
            out = run_research_agent(
                skill_text="x",
                phase_inputs={},
                shared_context={},
                output_model=_SampleOutput,
                model="test-model",
            )
        assert out.regime == "r"

    def test_retry_once_on_validation_error_then_succeed(self) -> None:
        bad = json.dumps({"regime": "x"})  # missing confidence
        good = json.dumps({"regime": "x", "confidence": 0.4})
        with patch(
            "digigraph.graph.research_agent.chat_completion",
            side_effect=[bad, good],
        ) as mock:
            out = run_research_agent(
                skill_text="x",
                phase_inputs={},
                shared_context={},
                output_model=_SampleOutput,
                model="test-model",
                max_retries=1,
            )
        assert out.confidence == 0.4
        assert mock.call_count == 2
        # Second call must append assistant + corrective user message.
        second_messages = mock.call_args_list[1].args[1]
        assert second_messages[-2]["role"] == "assistant"
        assert second_messages[-1]["role"] == "user"
        assert "did not validate" in second_messages[-1]["content"]

    def test_raises_validation_error_after_exhausting_retries(self) -> None:
        bad = json.dumps({"regime": "x"})
        with patch(
            "digigraph.graph.research_agent.chat_completion",
            side_effect=[bad, bad],
        ):
            with pytest.raises(ValidationError):
                run_research_agent(
                    skill_text="x",
                    phase_inputs={},
                    shared_context={},
                    output_model=_SampleOutput,
                    model="test-model",
                    max_retries=1,
                )

    def test_handles_tuple_response_from_chat_completion(self) -> None:
        """chat_completion returns (content, tool_calls) when tools are passed;
        research_agent never passes tools, but be defensive."""
        payload = json.dumps({"regime": "r", "confidence": 0.1})
        with patch(
            "digigraph.graph.research_agent.chat_completion",
            return_value=(payload, None),
        ):
            out = run_research_agent(
                skill_text="x",
                phase_inputs={},
                shared_context={},
                output_model=_SampleOutput,
                model="test-model",
            )
        assert out.regime == "r"

    def test_passes_response_format_to_chat_completion(self) -> None:
        """run_research_agent must pass response_format derived from output_model to chat_completion."""
        payload = json.dumps({"regime": "growth", "confidence": 0.9})
        with patch("digigraph.graph.research_agent.chat_completion", return_value=payload) as mock:
            run_research_agent(
                skill_text="x",
                phase_inputs={},
                shared_context={},
                output_model=_SampleOutput,
                model="test-model",
            )
        _, kwargs = mock.call_args
        rf = kwargs.get("response_format")
        assert rf is not None, "response_format must be passed to chat_completion"
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["name"] == "_SampleOutput"
        assert "properties" in rf["json_schema"]["schema"]

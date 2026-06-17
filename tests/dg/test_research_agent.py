"""Unit tests for the generic research-agent node."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from pydantic import BaseModel, Field, ValidationError

from digigraph.graph.research_agent import (
    ANALYST_SYSTEM,
    _format_scope_block,
    _strictify_json_schema,
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
class TestStrictifyJsonSchema:
    """The strictify transform must produce OpenRouter/OpenAI strict-mode-legal schemas."""

    def test_object_gets_additional_properties_false_and_all_required(self) -> None:
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
        }
        out = _strictify_json_schema(schema)
        assert out["additionalProperties"] is False
        assert out["required"] == ["a", "b"]

    def test_unsupported_keywords_stripped(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "score": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.5,
                },
                "when": {"type": "string", "format": "date"},
                "tag": {"type": "string", "pattern": "^[a-z]+$", "maxLength": 8},
            },
        }
        out = _strictify_json_schema(schema)
        score = out["properties"]["score"]
        assert "minimum" not in score
        assert "maximum" not in score
        assert "default" not in score
        assert "format" not in out["properties"]["when"]
        assert "pattern" not in out["properties"]["tag"]
        assert "maxLength" not in out["properties"]["tag"]
        # type/description-class keywords survive.
        assert score["type"] == "number"

    def test_recurses_into_defs_and_anyof_and_items(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/Leg"},
                    "maxItems": 5,
                },
                "maybe": {"anyOf": [{"$ref": "#/$defs/Leg"}, {"type": "null"}]},
            },
            "$defs": {
                "Leg": {
                    "type": "object",
                    "properties": {"qty": {"type": "integer", "minimum": 1}},
                }
            },
        }
        out = _strictify_json_schema(schema)
        # Array bound stripped, items recursed (no-op here), $defs object strictified.
        assert "maxItems" not in out["properties"]["items"]
        leg = out["$defs"]["Leg"]
        assert leg["additionalProperties"] is False
        assert leg["required"] == ["qty"]
        assert "minimum" not in leg["properties"]["qty"]
        # anyOf members recursed (null branch left intact).
        assert {"type": "null"} in out["properties"]["maybe"]["anyOf"]

    def test_recurses_into_additionalproperties_schema(self) -> None:
        # Pydantic emits dict[str, X] map fields as an object with a schema-valued
        # additionalProperties and NO properties — the value schema must still be strictified.
        schema = {
            "type": "object",
            "properties": {
                "weights": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {"pct": {"type": "number", "minimum": 0, "maximum": 1}},
                    },
                }
            },
        }
        out = _strictify_json_schema(schema)
        weights = out["properties"]["weights"]
        # The map object has no named properties → not forced to additionalProperties:false,
        # but its value schema is recursed: nested object strictified + bounds stripped.
        value_schema = weights["additionalProperties"]
        assert value_schema["additionalProperties"] is False
        assert value_schema["required"] == ["pct"]
        assert "minimum" not in value_schema["properties"]["pct"]
        assert "maximum" not in value_schema["properties"]["pct"]

    def test_boolean_additionalproperties_preserved(self) -> None:
        # A bool additionalProperties (e.g. extra="forbid" → false) is passed through unchanged.
        out = _strictify_json_schema(
            {
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "additionalProperties": False,
            }
        )
        assert out["additionalProperties"] is False

    def test_input_not_mutated(self) -> None:
        schema = {
            "type": "object",
            "properties": {"a": {"type": "number", "minimum": 0}},
        }
        before = json.dumps(schema, sort_keys=True)
        _strictify_json_schema(schema)
        assert json.dumps(schema, sort_keys=True) == before

    def test_pydantic_model_schema_is_strictified(self) -> None:
        """End-to-end on a real Pydantic schema: Field(ge/le) bounds → stripped, all required."""
        out = _strictify_json_schema(_SampleOutput.model_json_schema())
        assert out["additionalProperties"] is False
        assert set(out["required"]) == {"regime", "confidence", "notes"}
        conf = out["properties"]["confidence"]
        assert "minimum" not in conf and "maximum" not in conf


@pytest.mark.unit
class TestRunResearchAgent:
    def _fake_response(self, **fields: object) -> str:
        return json.dumps(fields)

    def test_successful_first_try(self) -> None:
        payload = self._fake_response(regime="growth", confidence=0.8, notes=["ok"])
        with patch("digigraph.graph.research_agent.completion_text", return_value=payload) as mock:
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
        with patch("digigraph.graph.research_agent.completion_text", return_value=fenced):
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
            "digigraph.graph.research_agent.completion_text",
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
            "digigraph.graph.research_agent.completion_text",
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

    def test_passes_response_format_to_completion(self) -> None:
        """run_research_agent must pass response_format derived from output_model to completion_text."""
        payload = json.dumps({"regime": "growth", "confidence": 0.9})
        with patch("digigraph.graph.research_agent.completion_text", return_value=payload) as mock:
            run_research_agent(
                skill_text="x",
                phase_inputs={},
                shared_context={},
                output_model=_SampleOutput,
                model="test-model",
            )
        _, kwargs = mock.call_args
        rf = kwargs.get("response_format")
        assert rf is not None, "response_format must be passed to completion_text"
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["name"] == "_SampleOutput"
        # Strict structured outputs: OpenRouter "Always set strict:true" + a strict-legal schema.
        assert rf["json_schema"]["strict"] is True
        strict_schema = rf["json_schema"]["schema"]
        assert "properties" in strict_schema
        assert strict_schema["additionalProperties"] is False
        assert set(strict_schema["required"]) == {"regime", "confidence", "notes"}

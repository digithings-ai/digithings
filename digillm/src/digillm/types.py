"""Typed request and tool payload shapes shared by digillm modules."""

from __future__ import annotations

from typing import Any, TypedDict


class ToolCallFunction(TypedDict, total=False):
    """Function block on an assistant ``tool_call``."""

    name: str
    arguments: str


class ToolCallDict(TypedDict, total=False):
    """OpenAI assistant ``tool_call`` entry."""

    id: str
    type: str
    function: ToolCallFunction


class ChatCompletionMessage(TypedDict, total=False):
    """OpenAI chat message shape for ``chat.completions.create``."""

    role: str
    content: str | list[dict[str, Any]] | None
    name: str
    tool_call_id: str
    tool_calls: list[ToolCallDict]


class ToolFunctionSpec(TypedDict, total=False):
    """Function spec inside a :class:`ToolDefinition`."""

    name: str
    description: str
    parameters: dict[str, Any]


class ToolDefinition(TypedDict, total=False):
    """A single tool exposed to the model."""

    type: str
    function: ToolFunctionSpec


class JsonSchemaResponseFormat(TypedDict, total=False):
    """OpenAI ``response_format`` descriptor for json_schema structured output."""

    type: str
    json_schema: dict[str, Any]


ToolArguments = dict[str, Any]

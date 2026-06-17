"""OpenAI-style orchestrator tool definitions for DigiVault.

Hubs (e.g. DigiGraph) fetch these via ``POST /v1/orchestrator_tools`` and execute
via ``POST /v1/orchestrator_invoke`` so vault tooling is owned by this service.
"""

from __future__ import annotations

from typing import Any, TypedDict  # noqa: ANN401 — OpenAI tool JSON-schema property maps


class FunctionParametersSchema(TypedDict, total=False):
    type: str
    properties: dict[str, Any]
    required: list[str]


class FunctionToolSchema(TypedDict):
    name: str
    description: str
    parameters: FunctionParametersSchema


class OpenAIToolDict(TypedDict):
    type: str
    function: FunctionToolSchema


TOOL_VAULT_SEARCH_TAG = "digivault_search_tag"
TOOL_VAULT_BACKLINKS = "digivault_backlinks"
TOOL_VAULT_LINT = "digivault_lint"
TOOL_VAULT_CREATE_NOTE = "digivault_create_note"

ORCHESTRATOR_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_VAULT_SEARCH_TAG,
        TOOL_VAULT_BACKLINKS,
        TOOL_VAULT_LINT,
        TOOL_VAULT_CREATE_NOTE,
    }
)


def _fn(name: str, description: str, params: FunctionParametersSchema) -> OpenAIToolDict:
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": params},
    }


def build_orchestrator_tool_manifest() -> list[OpenAIToolDict]:
    """Return the OpenAI function-tool definitions owned by DigiVault."""
    return [
        _fn(
            TOOL_VAULT_SEARCH_TAG,
            "Find vault notes carrying a given tag. Use to locate documentation by topic.",
            {
                "type": "object",
                "properties": {"tag": {"type": "string", "description": "Tag without '#'"}},
                "required": ["tag"],
            },
        ),
        _fn(
            TOOL_VAULT_BACKLINKS,
            "List notes that link to a given note (its backlinks).",
            {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Note name (stem)"}},
                "required": ["name"],
            },
        ),
        _fn(
            TOOL_VAULT_LINT,
            "Validate the vault: unresolved wikilinks, missing frontmatter, orphans.",
            {"type": "object", "properties": {}},
        ),
        _fn(
            TOOL_VAULT_CREATE_NOTE,
            "Create a new markdown note in the vault with optional frontmatter and body.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "New note name (stem)"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
    ]

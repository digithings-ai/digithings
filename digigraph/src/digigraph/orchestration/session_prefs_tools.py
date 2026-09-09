"""Session preference tools — the model asks, the client applies (#3736).

Handlers echo the requested change. They do not hold React state; digichat
applies the same EmbedChatPrefsApi mutators as slash commands.
"""

from __future__ import annotations

from typing import Any  # score:allow untyped any — MCP tool JSON args / results

from digigraph.orchestration.registry import ToolContext

SESSION_SET_LANGUAGE = "session_set_language"
SESSION_SET_MODEL = "session_set_model"
SESSION_SET_EFFORT = "session_set_effort"
SESSION_SET_THINKING = "session_set_thinking"
SESSION_TOGGLE_TOOL = "session_toggle_tool"
SESSION_UPSERT_MCP = "session_upsert_mcp"
SESSION_REMOVE_MCP = "session_remove_mcp"

SESSION_TOOL_NAMES = frozenset(
    {
        SESSION_SET_LANGUAGE,
        SESSION_SET_MODEL,
        SESSION_SET_EFFORT,
        SESSION_SET_THINKING,
        SESSION_TOGGLE_TOOL,
        SESSION_UPSERT_MCP,
        SESSION_REMOVE_MCP,
    }
)


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


SESSION_SET_LANGUAGE_TOOL = _fn(
    SESSION_SET_LANGUAGE,
    "Set the user's reply language for this chat session. "
    "Use when they ask to switch language (ISO code or name, e.g. nl, Dutch).",
    {"code": {"type": "string", "description": "ISO 639-1 code or language name."}},
    ["code"],
)
SESSION_SET_MODEL_TOOL = _fn(
    SESSION_SET_MODEL,
    "Set the chat model id for this session (must be on the deployment allowlist).",
    {"model": {"type": "string", "description": "Model id, e.g. openai/gpt-oss-20b:free."}},
    ["model"],
)
SESSION_SET_EFFORT_TOOL = _fn(
    SESSION_SET_EFFORT,
    "Set reasoning effort for this session: low, medium, or high.",
    {"effort": {"type": "string", "enum": ["low", "medium", "high"]}},
    ["effort"],
)
SESSION_SET_THINKING_TOOL = _fn(
    SESSION_SET_THINKING,
    "Show or hide thinking/reasoning in the transcript (display only).",
    {"enabled": {"type": "boolean"}},
    ["enabled"],
)
SESSION_TOGGLE_TOOL_TOOL = _fn(
    SESSION_TOGGLE_TOOL,
    "Enable or disable a catalog or MCP tool for this session "
    "(digisearch, digivault, websearch, or an extra/MCP id).",
    {
        "id": {"type": "string", "description": "Tool or MCP id."},
        "enabled": {"type": "boolean"},
    },
    ["id", "enabled"],
)
SESSION_UPSERT_MCP_TOOL = _fn(
    SESSION_UPSERT_MCP,
    "Add or update a session MCP server (id, url, auth, token). "
    "A new URL may require the user to confirm in /mcp edit.",
    {
        "id": {"type": "string"},
        "label": {"type": "string"},
        "url": {"type": "string"},
        "auth": {"type": "string", "enum": ["none", "bearer", "oauth"]},
        "token": {"type": "string"},
    },
    ["id"],
)
SESSION_REMOVE_MCP_TOOL = _fn(
    SESSION_REMOVE_MCP,
    "Remove a session-added MCP server (not operator YAML).",
    {"id": {"type": "string"}},
    ["id"],
)

SESSION_TOOL_SCHEMAS: list[tuple[str, dict[str, Any]]] = [
    (SESSION_SET_LANGUAGE, SESSION_SET_LANGUAGE_TOOL),
    (SESSION_SET_MODEL, SESSION_SET_MODEL_TOOL),
    (SESSION_SET_EFFORT, SESSION_SET_EFFORT_TOOL),
    (SESSION_SET_THINKING, SESSION_SET_THINKING_TOOL),
    (SESSION_TOGGLE_TOOL, SESSION_TOGGLE_TOOL_TOOL),
    (SESSION_UPSERT_MCP, SESSION_UPSERT_MCP_TOOL),
    (SESSION_REMOVE_MCP, SESSION_REMOVE_MCP_TOOL),
]


def _handle_session_tool(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Echo the requested prefs change for the client applicator."""
    del context
    clean = {k: v for k, v in (args or {}).items() if v is not None}
    return {"ok": True, "session_prefs": clean}

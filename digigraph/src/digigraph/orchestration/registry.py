"""Tool registry and execution context for the research node.

Orchestrator tools have: name, OpenAI schema, handler(args, context) -> result, optional tags.
Skills are named bundles of tool names with optional when(context) -> bool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# Handler: (args, context) -> str | dict. Dict may include dataset_ref for stored_datasets merge.
ToolHandler = Callable[[dict[str, Any], "ToolContext"], str | dict[str, Any]]
# When predicate for a skill: context -> bool
WhenPredicate = Callable[["ToolContext"], bool]
# Optional schema factory for tools whose schema depends on context (e.g. digisearch).
SchemaFactory = Callable[["ToolContext"], dict[str, Any]]


@dataclass
class ToolContext:
    """Execution context passed to every orchestrator tool handler."""

    session_id: str | None
    run_data_dir: str | None
    index_name: str
    index_config: dict[str, Any]
    state: dict[str, Any]

    @property
    def has_run_data_dir(self) -> bool:
        return bool(self.run_data_dir and self.run_data_dir.strip())


# Tool descriptor: name -> (schema | None, schema_factory | None, handler, tags)
_tools: dict[str, tuple[dict | None, SchemaFactory | None, ToolHandler, set[str]]] = {}
# Skill: skill_id -> (tool_names, when | None)
_skills: dict[str, tuple[list[str], WhenPredicate | None]] = {}


def register_tool(
    name: str,
    schema: dict[str, Any] | None,
    handler: ToolHandler,
    tags: set[str] | None = None,
    schema_factory: SchemaFactory | None = None,
) -> None:
    """Register an orchestrator tool. Schema must be OpenAI function tool format.
    If schema_factory is provided, get_tools uses schema_factory(context) instead of schema.
    """
    _tools[name] = (dict(schema) if schema else None, schema_factory, handler, set(tags or []))


def register_skill(
    skill_id: str,
    tool_names: list[str],
    when: WhenPredicate | None = None,
) -> None:
    """Register a skill: bundle of tool names, optionally gated by when(context)."""
    _skills[skill_id] = (list(tool_names), when)


def get_tools(skill_ids: list[str], context: ToolContext) -> list[dict[str, Any]]:
    """Return OpenAI tool dicts for the given skills and context. Only includes tools
    from skills whose when predicate passes (or has no when). Deduplicates by tool name.
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for skill_id in skill_ids:
        if skill_id not in _skills:
            continue
        tool_names, when = _skills[skill_id]
        if when is not None and not when(context):
            continue
        for name in tool_names:
            if name in seen or name not in _tools:
                continue
            seen.add(name)
            schema, schema_factory, _, _ = _tools[name]
            if schema_factory is not None:
                out.append(schema_factory(context))
            else:
                out.append(schema)
    return out


def execute(name: str, args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """Dispatch to the handler for the given tool name. Returns handler result (str or dict)."""
    if name not in _tools:
        return f"Unknown tool: {name}"
    _, _, handler, _ = _tools[name]
    return handler(args, context)


def list_tool_names(tag: str | None = None) -> list[str]:
    """List registered tool names, optionally filtered by tag (e.g. 'delegate')."""
    if tag is None:
        return list(_tools.keys())
    return [n for n, (_, _, _, tags) in _tools.items() if tag in tags]


def has_tool(name: str) -> bool:
    """Return True if a tool is registered with this name."""
    return name in _tools

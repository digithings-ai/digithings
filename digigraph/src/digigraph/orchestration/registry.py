"""Tool registry and execution context for the research node.

Orchestrator tools have: name, OpenAI schema, handler(args, context) -> result, optional tags.
Skills are named bundles of tool names with optional when(context) -> bool.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class ToolExposureMode(Enum):
    """Controls how tools are serialised for injection into the agent context.

    SUMMARY:  one-line ``tool_name: description`` strings — minimises context window usage.
    DETAILED: full OpenAI function-tool dicts — backwards-compatible default.
    """

    SUMMARY = "summary"
    DETAILED = "detailed"


class _ProviderConfig(BaseModel):
    """A single provider entry (free or premium) from mcp_servers.yaml."""

    name: str
    enabled: bool = True
    api_key_env: str | None = None
    optional: bool = False
    enabled_if_env: str | None = None


class _MCPServerConfig(BaseModel):
    """Per-server block from mcp_servers.yaml."""

    description: str = ""
    enabled: bool = True
    tool_exposure_mode: ToolExposureMode = ToolExposureMode.SUMMARY
    free_providers: list[_ProviderConfig] = Field(default_factory=list)
    premium_providers: list[_ProviderConfig] = Field(default_factory=list)


# Handler: (args, context) -> str | dict. Dict may include dataset_ref for stored_datasets merge.
ToolHandler = Callable[[dict[str, Any], "ToolContext"], str | dict[str, Any]]
# When predicate for a skill: context -> bool
WhenPredicate = Callable[["ToolContext"], bool]
# Optional schema factory for tools whose schema depends on context (e.g. digisearch).
SchemaFactory = Callable[["ToolContext"], dict[str, Any]]

def _tool_schema_name(tool_dict: dict[str, Any]) -> str | None:
    fn = tool_dict.get("function")
    if isinstance(fn, dict):
        name = fn.get("name")
        return str(name) if name else None
    return None


@dataclass
class ToolContext:
    """Execution context passed to every orchestrator tool handler."""

    session_id: str | None
    run_data_dir: str | None
    index_name: str
    index_config: dict[str, Any]
    state: dict[str, Any]
    # When set, only these tool names may be executed and exposed via get_tools.
    allowed_tool_names: frozenset[str] | None = None
    request_id: str | None = None
    workflow_id: str | None = None

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
    if name in _tools:
        raise ValueError(f"Orchestrator tool {name!r} is already registered")
    _tools[name] = (dict(schema) if schema else None, schema_factory, handler, set(tags or []))


def register_skill(
    skill_id: str,
    tool_names: list[str],
    when: WhenPredicate | None = None,
) -> None:
    """Register a skill: bundle of tool names, optionally gated by when(context)."""
    _skills[skill_id] = (list(tool_names), when)


def get_tools(
    skill_ids: list[str],
    context: ToolContext,
    mode: ToolExposureMode = ToolExposureMode.DETAILED,
) -> list[dict[str, Any]] | list[str]:
    """Return tool descriptors for the given skills and context.

    Only includes tools from skills whose when predicate passes (or has no when).
    Deduplicates by tool name.

    Args:
        skill_ids: Skill identifiers to collect tools from.
        context:   Execution context (allowlists, session, etc.).
        mode:      Exposure mode.
                   ``DETAILED`` (default) — returns a list of OpenAI function-tool dicts
                   (full JSON schema); backwards-compatible.
                   ``SUMMARY`` — returns a list of ``"tool_name: description"`` strings,
                   one per tool, for injecting a compact tool manifest into a system prompt.
    """
    seen: set[str] = set()
    out_detailed: list[dict[str, Any]] = []
    out_summary: list[str] = []

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
                td = schema_factory(context)
            else:
                td = schema
            tname = _tool_schema_name(td) if isinstance(td, dict) else None
            if context.allowed_tool_names is not None:
                if not tname or tname not in context.allowed_tool_names:
                    continue
            if mode is ToolExposureMode.SUMMARY:
                description = ""
                if isinstance(td, dict):
                    fn = td.get("function") or {}
                    description = fn.get("description") or ""
                tool_name = tname or name
                out_summary.append(f"{tool_name}: {description}" if description else tool_name)
            else:
                out_detailed.append(td)

    return out_summary if mode is ToolExposureMode.SUMMARY else out_detailed


def execute(name: str, args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """Dispatch to the handler for the given tool name. Returns handler result (str or dict)."""
    if name not in _tools:
        return f"Unknown tool: {name}"
    if context.allowed_tool_names is not None and name not in context.allowed_tool_names:
        from digigraph.audit import audit_log

        allow = context.allowed_tool_names
        sig = hashlib.sha256(",".join(sorted(allow)).encode()).hexdigest()[:16]
        audit_log(
            "tool_denied",
            agent_id="digigraph",
            payload={
                "tool": name,
                "allowlist_count": len(allow),
                "allowlist_sha256_16": sig,
                "request_id": context.request_id or "",
                "workflow_id": context.workflow_id or "",
            },
        )
        return {
            "error": "tool_not_allowed",
            "tool": name,
            "message": (
                f"Tool {name!r} is not in the allowed tool list for this session. "
                "Adjust agents.allowed_tools, DIGI_ALLOWED_TOOLS, or the request allowed_tools field."
            ),
        }
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


def list_registered_tools_detailed() -> list[dict[str, Any]]:
    """Return manifest entries: tool name, tags, and whether schema is dynamic (schema_factory)."""
    out: list[dict[str, Any]] = []
    for name, (_schema, schema_factory, _handler, tags) in sorted(_tools.items(), key=lambda x: x[0]):
        out.append({
            "name": name,
            "tags": sorted(tags),
            "dynamic_schema": schema_factory is not None,
        })
    return out


def _resolve_mcp_config_path(config_path: str) -> Path:
    """Resolve mcp_servers.yaml path.

    Tries the given path as-is (absolute or relative to cwd), then relative to
    the repository root (two levels up from this file: src/digigraph/orchestration/).
    """
    p = Path(config_path)
    if p.is_absolute():
        return p
    if p.exists():
        return p.resolve()
    # Fallback: resolve relative to repo root (this file is digigraph/src/digigraph/orchestration/)
    repo_root = Path(__file__).parent.parent.parent.parent.parent
    candidate = repo_root / config_path
    if candidate.exists():
        return candidate.resolve()
    return p.resolve()


def register_mcp_server(
    name: str,
    config_path: str = "config/mcp_servers.yaml",
    mode: ToolExposureMode = ToolExposureMode.SUMMARY,
) -> list[dict[str, Any]]:
    """Load an MCP server entry from config and return tool descriptors for active providers.

    Free providers are always included (if ``enabled: true``).  Premium providers are
    included only when their ``enabled_if_env`` environment variable is set.

    Note: this function returns descriptors only — wiring descriptors into
    ``register_tool()`` happens in a follow-up unit once the OpenBB MCP client is
    integrated.

    Args:
        name: Key under ``mcp_servers:`` in the config file (e.g. ``"openbb"``).
        config_path: Path to ``mcp_servers.yaml`` (absolute or relative to repo root).
        mode: ``SUMMARY`` (default) returns compact descriptors to save context tokens;
            ``DETAILED`` returns full OpenAI function-tool schema stubs.

    Returns:
        List of tool descriptor dicts, one per active provider.  Each dict has at
        minimum ``name`` and ``description``; ``DETAILED`` mode additionally has
        ``type`` and ``function`` keys matching the OpenAI function-call schema.
    """
    resolved = _resolve_mcp_config_path(config_path)
    if not resolved.exists():
        log.warning("register_mcp_server: config not found at %s — returning empty list", resolved)
        return []

    raw: dict[str, Any] = yaml.safe_load(resolved.read_text()) or {}
    servers_raw: dict[str, Any] = raw.get("mcp_servers", {})
    server_raw: dict[str, Any] | None = servers_raw.get(name)
    if server_raw is None:
        log.warning("register_mcp_server: server %r not found in %s", name, resolved)
        return []

    server_cfg = _MCPServerConfig.model_validate(server_raw)
    if not server_cfg.enabled:
        log.info("register_mcp_server: server %r is disabled — skipping", name)
        return []

    descriptors: list[dict[str, Any]] = []

    # Free providers — included unconditionally when enabled.
    for provider in server_cfg.free_providers:
        if not provider.enabled:
            continue
        descriptors.append(_make_descriptor(name, provider, mode))

    # Premium providers — included only if their env var is set.
    for provider in server_cfg.premium_providers:
        env_var = provider.enabled_if_env
        if env_var and not os.environ.get(env_var):
            log.info(
                "register_mcp_server: skipping premium provider %r — %s not set",
                provider.name,
                env_var,
            )
            continue
        descriptors.append(_make_descriptor(name, provider, mode))

    return descriptors


def _make_descriptor(
    server_name: str,
    provider: _ProviderConfig,
    mode: ToolExposureMode,
) -> dict[str, Any]:
    """Build a tool descriptor for a provider in the requested exposure mode."""
    tool_name = f"{server_name}__{provider.name}"
    short_description = f"Financial data via {provider.name} (OpenBB/{server_name})"

    if mode is ToolExposureMode.SUMMARY:
        return {
            "name": tool_name,
            "description": short_description,
            "provider": provider.name,
            "server": server_name,
        }

    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": short_description,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Ticker symbol or identifier (provider-specific).",
                    },
                },
                "required": [],
            },
        },
    }

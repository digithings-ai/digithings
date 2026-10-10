"""Tool registry and execution context for the research node.

Orchestrator tools have: name, OpenAI schema, handler(args, context) -> result, optional tags.
Skills are named bundles of tool names with optional when(context) -> bool.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import threading
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
    # Optional digivault path prefix for multi-tenant corpus isolation.
    vault_path_prefix: str | None = None
    # Operator MCP servers for this turn (BFF). Not globally registered.
    extra_mcp_servers: list[dict[str, str]] | None = None

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
            log.warning(
                "skill id %r not registered (renamed or removed?) -- no tools contributed from it",
                skill_id,
            )
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

    extra_servers = context.extra_mcp_servers or []
    if extra_servers:
        from digigraph.orchestration.mcp_client import openai_tools_for_servers

        for td in openai_tools_for_servers(extra_servers):
            tname = _tool_schema_name(td) if isinstance(td, dict) else None
            if not tname or tname in seen:
                continue
            if context.allowed_tool_names is not None and tname not in context.allowed_tool_names:
                continue
            seen.add(tname)
            if mode is ToolExposureMode.SUMMARY:
                fn = td.get("function") or {}
                description = fn.get("description") or ""
                out_summary.append(f"{tname}: {description}" if description else tname)
            else:
                out_detailed.append(td)

    return out_summary if mode is ToolExposureMode.SUMMARY else out_detailed


# --- 284.4: a mutating MCP call stops and asks ---------------------------------
#
# 284.3 refuses to OFFER a tool the operator did not allow. That stops a
# well-behaved model, because the model only ever sees the offered set. It does
# not stop a write: an allowed tool whose operation changes remote state is
# offered happily and then executed unattended on the next round. This gate sits
# at the one point where a name becomes an action, and it is downstream of
# 284.3's allowlist refusal on purpose -- the refusal must not depend on a human
# saying yes.
#
# Where the recorded call lives. NOT in the LangGraph state:
# graph/mcp_checkpoint_redact.py redacts the ``mcp_servers`` channel only, so
# every other state key is written to the durable checkpoint verbatim and
# archived. ``WorkflowState["pending_mcp_decision"]`` therefore carries a lean
# event -- pending id, server, tool -- and never the arguments. The payload lives
# here, in process memory, beside the credential the ToolContext already holds.


class MetaToolConfirmationRefused(RuntimeError):
    """A meta tool was handed to the confirm path.

    ``discover`` / ``executeRead`` / ``executeWrite`` / ``executeDestructive``
    decide for themselves what to call next, so a consent box naming one asks a
    human to approve an unknown call. 284.3 refuses them before they are
    offered, which is why this is unreachable in production and only a test can
    hold it.
    """


@dataclass(frozen=True)
class PendingMcpCall:
    """One recorded call that is waiting for a human decision.

    ``offered_name`` and ``args`` are the call, stored as they were offered and
    as the model wrote them. A decision carries only approve-or-deny: the
    consuming function below has no parameter for a tool name or for arguments,
    so a substituted payload cannot be spelled, let alone executed.
    """

    pending_id: str
    session_id: str | None
    server_id: str
    remote_tool: str
    offered_name: str
    args: dict[str, Any]

    @property
    def target_arguments(self) -> list[str]:
        """Which argument carries the target. Values may be client data."""
        return sorted(str(key) for key in self.args)

    def as_public_event(self) -> dict[str, Any]:
        """The lean event safe to surface, checkpoint, and render."""
        return {
            "pending_id": self.pending_id,
            "server_id": self.server_id,
            "tool": self.remote_tool,
            "target_arguments": self.target_arguments,
            "decided": False,
        }


_pending_mcp_calls: dict[tuple[str | None, str], PendingMcpCall] = {}
_pending_mcp_lock = threading.Lock()


def _remote_operation(
    name: str, servers: list[dict[str, Any]]
) -> tuple[str, str, dict[str, Any]] | None:
    """Resolve ``name`` to the remote operation ``call_prefixed_tool`` would run.

    Mirrors that function's resolution exactly -- including the whole prefixed
    name it passes to ``resolve_remote_tool_name`` (DIG-507) and the tail it uses
    when no list-time snapshot exists -- so the gate decides on the same string
    the transport will be handed. Returns ``None`` when the name resolves to no
    unique advertised tool; ``call_prefixed_tool`` refuses there, so there is no
    execution to gate.
    """
    from digigraph.orchestration.mcp_client import (
        raw_tool_names_for_server,
        resolve_remote_tool_name,
        split_prefixed_tool_name,
    )

    split = split_prefixed_tool_name(name)
    if not split:
        return None
    server_id, offered = split
    row = next(
        (s for s in servers if isinstance(s, dict) and s.get("id") == server_id),
        None,
    )
    if row is None:
        return None
    raw_names = raw_tool_names_for_server(row)
    if raw_names is None:
        return server_id, offered, row
    remote = resolve_remote_tool_name(server_id, name, raw_names)
    if remote is None:
        return None
    return server_id, remote, row


def _requires_human_approval(
    name: str, servers: list[dict[str, Any]]
) -> tuple[str, str, dict[str, Any]] | None:
    """Return the remote operation when this call must not run unattended.

    ``mutatingTools`` is the operator's own row (284.1), never a server-supplied
    annotation: rule 5 makes an absent list mean every allowed tool mutates.
    """
    from digigraph.orchestration.mcp_client import _refused_meta_tool, mcp_server_mutating_tools

    resolved = _remote_operation(name, servers)
    if resolved is None:
        return None
    server_id, remote, row = resolved
    if _refused_meta_tool(remote):
        raise MetaToolConfirmationRefused(
            f"Refusing to ask for approval of meta tool {remote!r} on server {server_id!r}: "
            "it selects its own operation, so no consent box can describe what it will call."
        )
    if remote not in mcp_server_mutating_tools(row):
        return None
    return server_id, remote, row


def _refuse_for_human_approval(
    name: str, args: dict[str, Any], context: ToolContext, server_id: str, remote: str
) -> dict[str, Any]:
    """Record the call once, audit it once, and refuse it without executing it."""
    from digigraph.audit import audit_log

    record = PendingMcpCall(
        pending_id=secrets.token_hex(16),
        session_id=context.session_id,
        server_id=server_id,
        remote_tool=remote,
        offered_name=name,
        args=dict(args),
    )
    key = (record.session_id, record.pending_id)
    with _pending_mcp_lock:
        _pending_mcp_calls[key] = record

    audit_log(
        "mcp_call_pending_human_approval",
        agent_id="digigraph",
        payload={
            "tool": remote,
            "offered_tool": name,
            "server_id": server_id,
            "pending_id": record.pending_id,
            "target_arguments": record.target_arguments,
            "request_id": context.request_id or "",
            "workflow_id": context.workflow_id or "",
        },
        redact=["args", "body", "text", "comment"],
    )
    if isinstance(context.state, dict):
        context.state["pending_mcp_decision"] = record.as_public_event()

    targets = ", ".join(record.target_arguments) or "none"
    return {
        "error": "mcp_call_requires_human_approval",
        "pending_id": record.pending_id,
        "server_id": record.server_id,
        "tool": record.remote_tool,
        "target_arguments": record.target_arguments,
        "message": (
            f"Tool {record.remote_tool!r} on server {record.server_id!r} changes remote state, "
            f"so it was not called. It was called as {record.offered_name!r} with the target "
            f"argument(s) {targets}; no argument value was evaluated. A human must decide "
            f"pending decision {record.pending_id!r} before anything runs. Stop this turn and "
            "report that decision as pending."
        ),
    }


def pending_mcp_decision(
    pending_id: str, *, session_id: str | None = None
) -> PendingMcpCall | None:
    """The recorded call behind a pending id, or ``None``.

    Session-scoped on purpose: a pending id is a handle inside one session, and
    a decision route must not be able to read another session's recorded call.
    """
    with _pending_mcp_lock:
        return _pending_mcp_calls.get((session_id, pending_id))


def decide_mcp_call(
    pending_id: str,
    approve: bool,
    *,
    session_id: str | None = None,
    servers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Consume a pending decision. The only path that can execute a recorded call.

    There is no parameter for a tool name or for arguments, and none may be
    added: what runs is ``record.offered_name`` and ``record.args`` as they were
    recorded. The record is consumed before the call leaves, so an approval
    replays as unknown rather than running twice -- at-most-once is the correct
    bias for a brake on unattended writes.

    ``servers`` carries the transport only. The row that executes must be the one
    the call was recorded against; a different row is refused rather than
    substituted. Nothing is consumed unless the call is actually dispatched.
    """
    with _pending_mcp_lock:
        record = _pending_mcp_calls.pop((session_id, pending_id), None)
    if record is None:
        return {"error": "unknown_pending_mcp_decision", "pending_id": pending_id}

    from digigraph.audit import audit_log

    if not approve:
        audit_log(
            "mcp_call_denied_by_human",
            agent_id="digigraph",
            payload={
                "tool": record.remote_tool,
                "server_id": record.server_id,
                "pending_id": record.pending_id,
            },
        )
        return {
            "status": "denied",
            "pending_id": record.pending_id,
            "tool": record.remote_tool,
            "server_id": record.server_id,
        }

    if not servers:
        return {"error": "mcp_call_requires_servers", "pending_id": record.pending_id}
    if not any(
        isinstance(s, dict) and s.get("id") == record.server_id and s.get("url") for s in servers
    ):
        return {"error": "mcp_server_not_available", "pending_id": record.pending_id}

    from digigraph.orchestration.mcp_client import call_prefixed_tool

    return call_prefixed_tool(record.offered_name, record.args, servers)


def execute(name: str, args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """Dispatch to the handler for the given tool name. Returns handler result (str or dict)."""
    from digigraph.orchestration.mcp_client import call_prefixed_tool, split_prefixed_tool_name
    from digigraph.tool_policy import is_proxied_web_search_tool

    split = split_prefixed_tool_name(name)
    is_extra = bool(
        split
        and any(
            isinstance(s, dict) and s.get("id") == split[0]
            for s in (context.extra_mcp_servers or [])
        )
    )
    if not has_tool(name) and not is_extra:
        return f"Unknown tool: {name}"
    # Execute-level opt-out gate (#4246 review). The concrete allowlist that
    # strips proxied web-search tools is discovery-dependent — an MCP list
    # failure caches [] for 60s, so an unrestricted session stays at None and
    # a model-guessed {id}_web_search would otherwise reach the remote tool,
    # which has no handler-side availability check. Native ``web_search``
    # keeps its own handler gate, so only the proxied suffix is denied here.
    if is_proxied_web_search_tool(name) and not context.state.get("enable_web_search"):
        from digigraph.orchestration.web_search_tools import web_search_disabled_payload

        return web_search_disabled_payload(name)
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
    if is_extra and not has_tool(name):
        extra_servers = context.extra_mcp_servers or []
        gated = _requires_human_approval(name, extra_servers)
        if gated is not None:
            server_id, remote, _row = gated
            return _refuse_for_human_approval(name, args, context, server_id, remote)
        return call_prefixed_tool(name, args, extra_servers)
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
    for name, (_schema, schema_factory, _handler, tags) in sorted(
        _tools.items(), key=lambda x: x[0]
    ):
        out.append(
            {
                "name": name,
                "tags": sorted(tags),
                "dynamic_schema": schema_factory is not None,
            }
        )
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

    SIMP-004 (done): returns descriptors only until MCP wire-up (#401); production tools
    register via ``register_tool`` from builtin skills. ``has_tool`` guards ``execute``.

    Free providers are always included (if ``enabled: true``).  Premium providers are
    included only when their ``enabled_if_env`` environment variable is set.

    Returns descriptors only (issue #401): does not call ``register_tool()`` yet.

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

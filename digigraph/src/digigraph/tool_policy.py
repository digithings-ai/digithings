"""Resolve which orchestrator tools may run for a workflow (env, project config, request override)."""

from __future__ import annotations

import os

from digigraph.boundaries import PROJECT_CONFIG_ERRORS
from digigraph.models import WorkflowRequest
from digigraph.policy import _env_truthy
from digigraph.project_config import DigiProjectConfig

# Opt-in digichat/digigraph web search (#3420). Never in the default corpus allowlist;
# only unioned when the request explicitly enables it.
WEB_SEARCH_TOOL_NAME = "web_search"

# Remote MCP tools are registered as ``{server_id}_{tool}``
# (``mcp_client.prefixed_tool_name``), so a digisearch MCP server exposes its
# web-search tool as ``digisearch_web_search``. It is the same capability as
# the native tool and must obey the same request opt-in (#4223 review).
_WEB_SEARCH_MCP_SUFFIX = f"_{WEB_SEARCH_TOOL_NAME}"


def is_web_search_tool(name: str) -> bool:
    """True for ``web_search`` and its MCP-proxied form ``{server_id}_web_search``."""
    return name == WEB_SEARCH_TOOL_NAME or name.endswith(_WEB_SEARCH_MCP_SUFFIX)


def is_proxied_web_search_tool(name: str) -> bool:
    """True only for the MCP-proxied form ``{server_id}_web_search`` (native excluded).

    The execute-level opt-out gate uses this: the native ``web_search`` handler
    already checks ``state["enable_web_search"]`` itself, while the MCP proxy
    forwards to a remote tool with no such handler-side check (#4246 review).
    """
    return name.endswith(_WEB_SEARCH_MCP_SUFFIX)


def strip_web_search_tools(names: frozenset[str]) -> frozenset[str]:
    """Drop ``web_search`` and every MCP-proxied ``{id}_web_search`` from an allowlist."""
    return frozenset(n for n in names if not is_web_search_tool(n))


# Catalog ids / slash aliases → orchestrator tools to strip (#3733).
_DISABLE_TOOL_ALIASES: dict[str, frozenset[str]] = {
    "digisearch": frozenset({"digisearch", "digisearch_fetch_all"}),
    "search": frozenset({"digisearch", "digisearch_fetch_all"}),
    "digivault": frozenset({"digivault_search_notes", "digivault_get_note"}),
    "vault": frozenset({"digivault_search_notes", "digivault_get_note"}),
    "docs": frozenset({"digivault_search_notes", "digivault_get_note"}),
    "digivault_search_notes": frozenset({"digivault_search_notes", "digivault_get_note"}),
}


def expand_disabled_tool_tokens(tokens: list[str] | tuple[str, ...] | None) -> frozenset[str]:
    """Map client catalog ids onto registered tool names. Unknown tokens ignored."""
    if not tokens:
        return frozenset()
    out: set[str] = set()
    for raw in tokens:
        key = str(raw).strip().lower()
        mapped = _DISABLE_TOOL_ALIASES.get(key)
        if mapped:
            out |= mapped
    return frozenset(out)


def apply_disabled_tools(
    names: frozenset[str] | None,
    disabled: frozenset[str],
) -> frozenset[str] | None:
    """Subtract *disabled* from an allowlist. Unrestricted (None) becomes the registry minus disabled."""
    if not disabled:
        return names
    if names is None:
        from digigraph.orchestration.registry import list_tool_names

        names = frozenset(list_tool_names())
    return frozenset(n for n in names if n not in disabled)


def apply_web_search_opt_in(
    names: frozenset[str] | None,
    *,
    enable_web_search: bool,
) -> frozenset[str] | None:
    """Activate or strip web search within an already-authoritative allowlist.

    Request opt-in must **never** escalate past the operator/project allowlist
    (#3420 review): if web search is not already permitted, enabling the
    header/body flag does nothing. When the allowlist includes ``web_search``
    or an MCP-proxied ``{id}_web_search`` and the request opts out (default),
    strip both so the model cannot reach the public web through either path.
    Unrestricted sessions (``None``) stay unrestricted — the ``web`` skill
    ``when`` predicate and tool handler still require ``enable_web_search``;
    the MCP-proxied tool has no such handler gate, so
    :func:`apply_mcp_extra_tools` materializes the allowlist instead.
    """
    if names is None:
        return None
    if enable_web_search:
        # Do not union — only activate a tool the operator already allowlisted.
        return names
    return strip_web_search_tools(names)


def apply_mcp_extra_tools(
    names: frozenset[str] | None,
    extra_names: frozenset[str],
    disabled_extra: frozenset[str],
    *,
    enable_web_search: bool,
) -> frozenset[str] | None:
    """Fold discovered remote-MCP tool names into an allowlist, web-search gated.

    Single policy point for ``research_node``'s MCP-extra union: subtract the
    disabled MCP tokens, then drop MCP-proxied web-search tools unless the
    request opted in.
    Unrestricted sessions (``None``) stay unrestricted **unless** a gate forces
    a concrete allowlist — the existing disabled-token fallback, or a
    discovered ``{id}_web_search`` with no opt-in, which would otherwise be
    admitted by the unrestricted ``None`` because the MCP proxy has no
    handler-side availability check. The concrete fallback is
    ``list_tool_names() | live``, the same shape the disabled-token path uses.
    """
    live = frozenset(n for n in extra_names if n not in disabled_extra)
    gated = False
    if not enable_web_search:
        stripped = strip_web_search_tools(live)
        gated = stripped != live
        live = stripped
        # The base allowlist normally arrives already stripped by
        # apply_web_search_opt_in; strip again so this function is safe to call
        # with either input order (and never re-admits a proxied tool).
        if names is not None:
            names = strip_web_search_tools(names)
    if names is not None:
        return names | live if live else names
    if disabled_extra or gated:
        from digigraph.orchestration.registry import list_tool_names

        return frozenset(list_tool_names()) | live
    return None


def allowed_tool_names_for_workflow(
    req: WorkflowRequest,
    cfg: DigiProjectConfig | None = None,
) -> frozenset[str] | None:
    """Return allowed tool names, or None if unrestricted.

    * If *req.allowed_tools* is set (including empty list), only that set applies — empty means no tools.
    * Otherwise: project ``agents.allowed_tools``, then env ``DIGI_ALLOWED_TOOLS`` (comma-separated).
    * If none of the above apply, returns ``None`` (all registered tools allowed).
    * ``enable_web_search`` then unions or strips ``web_search`` (#3420).
    """
    if req.allowed_tools is not None:
        base = frozenset(t.strip() for t in req.allowed_tools if t and str(t).strip())
    else:
        if cfg is None:
            try:
                cfg = DigiProjectConfig.load()
            except PROJECT_CONFIG_ERRORS:
                cfg = None
        from_cfg = cfg.get_allowed_tools() if cfg is not None else []
        if from_cfg:
            base = frozenset(str(t).strip() for t in from_cfg if str(t).strip())
        else:
            raw_env = os.environ.get("DIGI_ALLOWED_TOOLS", "").strip()
            if raw_env:
                parts = [p.strip() for p in raw_env.split(",") if p.strip()]
                base = frozenset(parts) if parts else None
            else:
                base = None

    with_web = apply_web_search_opt_in(base, enable_web_search=bool(req.enable_web_search))
    disabled = expand_disabled_tool_tokens(req.disabled_tools)
    result = apply_disabled_tools(with_web, disabled)
    if req.force_tool:
        from digigraph.retrieval import resolve_force_tool

        forced_name = resolve_force_tool(req.force_tool)
        if forced_name and result is not None:
            # Re-add only the locate tool — not fetch_all / get_note siblings.
            result = result | {forced_name}
    return result


def require_tool_calls_for_workflow(
    req: WorkflowRequest,
    cfg: DigiProjectConfig | None = None,
) -> bool:
    """Whether this workflow must force tool_choice='required'.

    Resolved as a FLOOR, not an override (deliberately unlike
    allowed_tool_names_for_workflow's most-specific-wins precedence): a
    request-level True can only ADD the requirement, never remove one the
    deployment already mandates via project config or env. allowed_tools is
    safe to fully override per-request because the resolved set is still
    bounded by the tool registry (a caller can't invoke what was never
    wired); require_tool_calls has no such ceiling — it's a bare bool that
    directly controls tool_choice, and digigraph's own /v1/chat/completions
    is reachable by callers outside digichat's control (Open WebUI-compatible
    clients), so a full override would let any caller defeat an operator's
    mandatory tool-forcing policy with one field/header.
    """
    if cfg is None:
        try:
            cfg = DigiProjectConfig.load()
        except PROJECT_CONFIG_ERRORS:
            cfg = None
    if cfg is not None and bool(cfg.get_require_tool_calls()):
        return True
    if _env_truthy("DIGI_REQUIRE_TOOL_CALLS"):
        return True
    return bool(req.require_tool_calls)


def state_list_from_frozen(names: frozenset[str] | None) -> list[str] | None:
    """Serialize allowlist for :class:`WorkflowState` (sorted for stable checkpoints)."""
    if names is None:
        return None
    return sorted(names)


def frozen_from_state_list(names: list[str] | None) -> frozenset[str] | None:
    """Deserialize allowlist from :class:`WorkflowState`.

    ``None`` means unrestricted; ``[]`` means deny-all. Must not use a falsy
    check — ``frozenset([]) if [] else None`` wrongly yields ``None``.
    """
    if names is None:
        return None
    return frozenset(names)

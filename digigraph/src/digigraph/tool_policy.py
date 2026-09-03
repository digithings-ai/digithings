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


def apply_web_search_opt_in(
    names: frozenset[str] | None,
    *,
    enable_web_search: bool,
) -> frozenset[str] | None:
    """Union or strip ``web_search`` from a resolved allowlist.

    Default is off. A concrete project allowlist never gains ``web_search``
    unless the request opts in. Unrestricted sessions (``None``) stay
    unrestricted either way — exposure is gated by the ``web`` skill's
    ``when`` predicate and the tool handler's enable check, so digillm web
    calls never mix into corpus RAG silently (#3420).
    """
    if names is None:
        return None
    if enable_web_search:
        return names | {WEB_SEARCH_TOOL_NAME}
    return frozenset(n for n in names if n != WEB_SEARCH_TOOL_NAME)


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

    return apply_web_search_opt_in(base, enable_web_search=bool(req.enable_web_search))


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

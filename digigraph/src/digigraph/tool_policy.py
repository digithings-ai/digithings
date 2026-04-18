"""Resolve which orchestrator tools may run for a workflow (env, project config, request override)."""

from __future__ import annotations

import os

from digigraph.models import WorkflowRequest
from digigraph.project_config import DigiProjectConfig


def allowed_tool_names_for_workflow(
    req: WorkflowRequest,
    cfg: DigiProjectConfig | None = None,
) -> frozenset[str] | None:
    """Return allowed tool names, or None if unrestricted.

    * If *req.allowed_tools* is set (including empty list), only that set applies — empty means no tools.
    * Otherwise: project ``agents.allowed_tools``, then env ``DIGI_ALLOWED_TOOLS`` (comma-separated).
    * If none of the above apply, returns ``None`` (all registered tools allowed).
    """
    if req.allowed_tools is not None:
        return frozenset(t.strip() for t in req.allowed_tools if t and str(t).strip())

    cfg = cfg or DigiProjectConfig.load()
    from_cfg = cfg.get_allowed_tools()
    if from_cfg:
        return frozenset(str(t).strip() for t in from_cfg if str(t).strip())

    raw_env = os.environ.get("DIGI_ALLOWED_TOOLS", "").strip()
    if raw_env:
        parts = [p.strip() for p in raw_env.split(",") if p.strip()]
        if parts:
            return frozenset(parts)

    return None


def state_list_from_frozen(names: frozenset[str] | None) -> list[str] | None:
    """Serialize allowlist for :class:`WorkflowState` (sorted for stable checkpoints)."""
    if names is None:
        return None
    return sorted(names)

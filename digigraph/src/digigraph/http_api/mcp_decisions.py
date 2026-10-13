"""The route that consumes one recorded MCP decision (DIG-284 leaf 284.6).

This is the digigraph side of the contract DIG-414 already built. The client
route (``apps/digichat/src/app/api/chat/approve/route.ts``) posts to
``/v1/mcp/decisions`` with ``{pending_id, approve}`` and ``X-Session-Id``, and
answers 502 unless the reply carries ``status`` "approved" or "denied".

Three rules make that request safe, and all three are the point of the route.

* The body is an ALLOWLIST of exactly two keys. Every other key is refused by
  name. The client already refuses ``url``, ``auth``, ``token``,
  ``authHeader``, ``allowedTools`` and ``mutatingTools`` on its own side; this
  route refuses them independently, because a client-side refusal is not a
  control on what the upstream is asked to do.
* The session comes from the ``X-Session-Id`` header alone, never the body,
  because the recorded call is stored under ``(session_id, pending_id)`` and a
  body-supplied session would let a caller reach another session's recorded
  call.
* The transport is resolved HERE, at decide time, and never taken from the
  request. It comes from the session's own checkpointed ``mcp_servers`` --
  written each turn from the operator's own header, where the operator URL
  already wins -- plus the operator env fallback. That is CTO decision (2) on
  DIG-284 (comment 98e32de0). A row captured at refusal time was rejected
  there: it would defeat operator rotation between refuse and decide, and it
  would park a credential-bearing row in the pending map.

The decision itself is applied by ``orchestration.registry.decide_mcp_call``,
which re-applies the full gate against the row resolved here. This module
resolves the transport and forwards; it decides nothing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

ALLOWED_KEYS = frozenset({"pending_id", "approve"})

router = APIRouter()


def decision_from_request(
    body: object, *, session_id: str | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a decision request into its two fields, or say why it is refused.

    Returns ``(fields, {})`` or ``({}, error)``. Never raises on a bad body: a
    refusal names the offending key so the caller can be told what was wrong
    with its own request rather than that something was wrong.
    """
    if not isinstance(body, dict):
        return {}, {"error": "decision_body_rejected", "key": "body"}
    for key in sorted(body):
        if key not in ALLOWED_KEYS:
            return {}, {"error": "decision_body_rejected", "key": key}
    pending_id = body.get("pending_id")
    approve = body.get("approve")
    if not isinstance(pending_id, str) or not pending_id:
        return {}, {"error": "decision_body_rejected", "key": "pending_id"}
    if not isinstance(approve, bool):
        return {}, {"error": "decision_body_rejected", "key": "approve"}
    if not session_id:
        return {}, {"error": "mcp_decision_requires_session"}
    return {"pending_id": pending_id, "approve": approve}, {}


def resolve_session_transport(http_request: Request, session_id: str) -> list[dict[str, Any]]:
    """The live operator transport for this session, or nothing.

    Reads the ``mcp_servers`` the turn already checkpointed for this thread and
    falls back to the operator env. Never reads the request body: that is the
    whole point of decision (2). A session with no checkpoint, an unreadable
    checkpoint, or an unreadable graph all answer "no transport", which the
    consumer turns into a refusal rather than a write.
    """
    from digigraph.graph import build_workflow_graph
    from digigraph.http_api.context import _thread_config
    from digigraph.orchestration.mcp_client import merge_mcp_servers, parse_mcp_servers_env

    try:
        config = _thread_config(http_request, session_id)
    except Exception:
        return []
    try:
        snapshot = build_workflow_graph().get_state(config)
    except Exception:
        return []
    values = getattr(snapshot, "values", None) or {}
    stored = values.get("mcp_servers") or []

    rows: list[dict[str, Any]] = []
    for ref in stored:
        # The checkpoint holds McpServerRef models; call_prefixed_tool wants a
        # flat camelCase row. by_alias gives authHeader / allowedTools /
        # mutatingTools back, and exclude_none keeps absent auth out.
        row = (
            ref.model_dump(by_alias=True, exclude_none=True)
            if hasattr(ref, "model_dump")
            else dict(ref)
        )
        if row.get("id") and row.get("url"):
            rows.append(row)
    return merge_mcp_servers(rows, parse_mcp_servers_env())


@router.post("/v1/mcp/decisions")
async def post_mcp_decision(request: Request) -> dict[str, Any]:
    """Apply one human decision to one recorded call, at most once."""
    try:
        body = await request.json()
    except Exception:  # a body that is not JSON at all
        return {"error": "decision_body_rejected", "key": "body"}

    session_id = request.headers.get("x-session-id")
    fields, error = decision_from_request(body, session_id=session_id)
    if error:
        return error

    from digigraph.orchestration.registry import decide_mcp_call

    servers = resolve_session_transport(request, session_id)
    return decide_mcp_call(
        fields["pending_id"],
        fields["approve"],
        session_id=session_id,
        servers=servers,
    )

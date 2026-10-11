"""The route that consumes one recorded MCP decision (DIG-284 leaf 284.6).

This is the digigraph side of the contract DIG-414 already built. The client
route (``apps/digichat/src/app/api/chat/approve/route.ts``) posts to
``/v1/mcp/decisions`` with ``{pending_id, approve}`` and ``X-Session-Id``, and
answers 502 unless the reply carries ``status`` "approved" or "denied".

Two rules make that request safe, and both are the point of the route:

* The body is an ALLOWLIST of exactly two keys. Every other key is refused by
  name. The client already refuses ``url``, ``auth``, ``token``,
  ``authHeader``, ``allowedTools`` and ``mutatingTools`` on its own side; this
  route refuses them independently, because a client-side refusal is not a
  control on what the upstream is asked to do. In particular the deciding
  request cannot re-supply an MCP transport: the row that executes was captured
  at refusal time beside the recorded arguments, so an attacker-chosen ``url``
  would point those arguments at an arbitrary endpoint. That is the gate turned
  into a suggestion with a network hop in it.
* The session comes from the ``X-Session-Id`` header alone, never the body,
  because the recorded call is stored under ``(session_id, pending_id)`` and a
  body-supplied session would let a caller read another session's recorded
  call.

The decision itself is applied by ``orchestration.registry.decide_mcp_call``.
This module validates the request shape and forwards; it decides nothing.
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

    return decide_mcp_call(fields["pending_id"], fields["approve"], session_id=session_id)

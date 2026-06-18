"""DigiQuant orchestrator manifest + invoke (tools owned by DigiQuant HTTP API)."""

from __future__ import annotations

from typing import Any

from digibase.http import outbound_service_headers
from digibase.http_client import sync_client

from digigraph.vertical_orchestrator._common import HUB_CLIENT_ERRORS, log_manifest_fetch_failure

_MANIFEST_CACHE: dict[str, list[dict[str, Any]]] = {}


def fetch_digiquant_tool_dicts(
    base_url: str,
    bearer_token: str | None,
    request_id: str | None,
) -> dict[str, dict[str, Any]]:
    """Return tool name -> OpenAI tool dict from ``POST /v1/orchestrator_tools``."""
    base = base_url.strip().rstrip("/")
    if base not in _MANIFEST_CACHE:
        url = f"{base}/v1/orchestrator_tools"
        headers = outbound_service_headers(request_id, bearer_token)
        headers["Content-Type"] = "application/json"
        try:
            with sync_client(timeout=30.0) as client:
                r = client.post(url, json={}, headers=headers)
                r.raise_for_status()
                body = r.json()
        except HUB_CLIENT_ERRORS as e:
            log_manifest_fetch_failure("DigiQuant", e)
            raise
        tools = body.get("tools") or []
        if not isinstance(tools, list):
            tools = []
        _MANIFEST_CACHE[base] = tools
    by_name: dict[str, dict[str, Any]] = {}
    for t in _MANIFEST_CACHE[base]:
        fn = t.get("function") if isinstance(t, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            by_name[str(fn["name"])] = t
    return by_name


def invoke_digiquant_tool(
    base_url: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    bearer_token: str | None,
    request_id: str | None,
) -> dict[str, Any]:
    """POST ``/v1/orchestrator_invoke`` on DigiQuant."""
    url = f"{base_url.strip().rstrip('/')}/v1/orchestrator_invoke"
    headers = outbound_service_headers(request_id, bearer_token)
    headers["Content-Type"] = "application/json"
    payload = {"tool": tool, "arguments": arguments}
    with sync_client(timeout=600.0) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
    body = r.json()
    if not isinstance(body, dict):
        return {"ok": False, "error": "invalid_response"}
    return body

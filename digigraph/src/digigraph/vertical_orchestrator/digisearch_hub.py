"""DigiSearch orchestrator manifest + invoke (tools owned by DigiSearch HTTP API)."""

from __future__ import annotations

import json
import logging
from typing import Any

from digibase.http import outbound_service_headers
from digibase.http_client import sync_client

logger = logging.getLogger(__name__)

_MANIFEST_CACHE: dict[str, list[dict[str, Any]]] = {}


def _cache_key(base_url: str, index_config: dict[str, Any] | None) -> str:
    return json.dumps({"b": base_url.rstrip("/"), "i": index_config or {}}, sort_keys=True)


def fetch_digisearch_tool_dicts(
    base_url: str,
    index_config: dict[str, Any] | None,
    bearer_token: str | None,
    request_id: str | None,
) -> dict[str, dict[str, Any]]:
    """Return tool name -> OpenAI tool dict from ``POST /v1/orchestrator_tools``."""
    base = base_url.strip().rstrip("/")
    key = _cache_key(base, index_config)
    if key not in _MANIFEST_CACHE:
        url = f"{base}/v1/orchestrator_tools"
        headers = outbound_service_headers(request_id, bearer_token)
        headers["Content-Type"] = "application/json"
        try:
            with sync_client(timeout=30.0) as client:
                r = client.post(url, json={"index_config": index_config or {}}, headers=headers)
                r.raise_for_status()
                body = r.json()
        except Exception as e:
            logger.warning("DigiSearch orchestrator_tools fetch failed: %s", e)
            raise
        tools = body.get("tools") or []
        if not isinstance(tools, list):
            tools = []
        _MANIFEST_CACHE[key] = tools
    by_name: dict[str, dict[str, Any]] = {}
    for t in _MANIFEST_CACHE[key]:
        fn = t.get("function") if isinstance(t, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            by_name[str(fn["name"])] = t
    return by_name


def invoke_digisearch_tool(
    base_url: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    default_index_name: str,
    bearer_token: str | None,
    request_id: str | None,
) -> dict[str, Any]:
    """POST ``/v1/orchestrator_invoke`` on DigiSearch."""
    url = f"{base_url.strip().rstrip('/')}/v1/orchestrator_invoke"
    headers = outbound_service_headers(request_id, bearer_token)
    headers["Content-Type"] = "application/json"
    payload: dict[str, Any] = {
        "tool": tool,
        "arguments": arguments,
        "default_index_name": default_index_name,
    }
    with sync_client(timeout=120.0) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
    body = r.json()
    if not isinstance(body, dict):
        return {"ok": False, "error": "invalid_response"}
    return body

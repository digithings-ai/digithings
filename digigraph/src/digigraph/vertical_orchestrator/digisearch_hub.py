"""digisearch orchestrator manifest + invoke (tools owned by digisearch HTTP API)."""

from __future__ import annotations

import json
from typing import Any

from digibase.http import outbound_service_headers
from digibase.http_client import sync_client

from digigraph.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from digigraph.vertical_orchestrator._common import HUB_CLIENT_ERRORS, log_manifest_fetch_failure

_MANIFEST_CACHE: dict[str, list[dict[str, Any]]] = {}
_cb = CircuitBreaker("digisearch_hub", failure_threshold=5, recovery_timeout=30.0)


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
        except HUB_CLIENT_ERRORS as e:
            log_manifest_fetch_failure("digisearch", e)
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
    """POST ``/v1/orchestrator_invoke`` on digisearch."""
    url = f"{base_url.strip().rstrip('/')}/v1/orchestrator_invoke"
    headers = outbound_service_headers(request_id, bearer_token)
    headers["Content-Type"] = "application/json"
    payload: dict[str, Any] = {
        "tool": tool,
        "arguments": arguments,
        "default_index_name": default_index_name,
    }
    try:
        # Only the network call itself is inside `with _cb:` -- a genuine transport
        # failure (httpx.RequestError: connection refused, timeout, DNS failure) is
        # what should count against the breaker. `raise_for_status()`/`.json()` run
        # OUTSIDE it deliberately: a 4xx/5xx response or a malformed body is a real
        # rejection from a live, reachable service (RetryPolicy's own reasoning in
        # graph/graph.py: "never httpx.HTTPStatusError -- a 4xx/5xx is a real
        # rejection, not a blip"), not evidence the service is down, so it must not
        # trip the process-wide circuit for every other caller.
        with _cb:
            with sync_client(timeout=120.0) as client:
                r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        body = r.json()
    except CircuitBreakerOpen:
        return {"ok": False, "error": "digisearch circuit open; downstream unavailable"}
    except HUB_CLIENT_ERRORS as e:
        # A genuine transport failure (httpx.RequestError, raised inside `with _cb:`
        # above) also counts as a breaker failure -- CircuitBreaker.__exit__ already
        # recorded it -- but must still surface as this function's normal ok:False
        # contract rather than raise, matching every other failure path here (see
        # "invalid_response"). A 4xx/5xx or malformed-JSON response reaches this
        # same except clause but was raised AFTER `with _cb:` already exited
        # cleanly, so it does not count toward opening the circuit.
        return {"ok": False, "error": f"digisearch invoke failed: {e}"}
    if not isinstance(body, dict):
        return {"ok": False, "error": "invalid_response"}
    return body

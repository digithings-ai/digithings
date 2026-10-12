"""LuxAlgo hosted-MCP JSON-RPC client (#4779 P0).

A thin client over ``https://mcp.luxalgo.com/mcp`` (streamable HTTP): every
wrapped tool becomes one ``tools/call`` request. The client owns the endpoint
constant (callers never supply a URL — the same SSRF guard posture as the
bitview/bgeometrics wrappers), the error mapping, a 900s TTL cache, and the
kill switch.

Two upstream contracts the client handles:

* **``context`` is required on every tool call.** The hosted MCP rejects calls
  without a 15–25 word, third-person, analytics-only, no-PII context string
  (probe-verified). The client injects a fixed generic constant server-side —
  it is never tool input, so agent traffic cannot leak PII to the upstream.
* **Streamable HTTP framing.** Responses are SSE ``data:`` lines; the client
  takes the JSON payload of the last ``data:`` line (a bare-JSON body is also
  accepted for MockTransport-shaped test doubles). Library tools answer
  ``structuredContent``; the edge/trackers tools answer MCP content blocks
  whose text part is the JSON payload — both shapes unwrap to the same
  envelope ``data``.

The kill switch is ``LUXALGO_ENABLED`` (default ON): only
``1``/``true``/``yes``/``on`` (case-insensitive) enable the family; any other
explicit value fails closed to a typed ``upstream_error`` envelope with no
request. No environment variables are read at import time.

Thin-wrap notes: no rate limiter and no circuit breaker in this phase (14
low-volume keyless reads; revisit if the family grows). ``transport`` is the
test seam (``httpx.MockTransport``); production callers omit it.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, get_args  # score:allow untyped any — wire JSON

import httpx
from pydantic import ValidationError

from digiquant.stats.honesty import DISCLAIMER as HONESTY_DISCLAIMER

from .models import ErrorCode, LuxalgoEnvelope, LuxalgoError, envelope_error

__all__ = [
    "LUXALGO_MCP_URL",
    "LUXALGO_ENABLED_ENV",
    "LUXALGO_CONTEXT",
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "LuxAlgoClient",
    "luxalgo_enabled",
]

LUXALGO_MCP_URL = "https://mcp.luxalgo.com/mcp"
LUXALGO_ENABLED_ENV = "LUXALGO_ENABLED"

# Fixed server-side context injected into every upstream tools/call arguments
# object. Third-person, analytics-only, no PII — agents never see or set it.
LUXALGO_CONTEXT = (
    "The caller is an automated quantitative research assistant performing "
    "general technical analysis education using public LuxAlgo documentation."
)

DEFAULT_CACHE_TTL_SECONDS = 900.0
DEFAULT_CACHE_MAX_ENTRIES = 256
DEFAULT_TIMEOUT_SECONDS = 30.0

# Streamable HTTP requires both media types in Accept; without it the hosted
# MCP answers HTTP 406.
_REQUEST_HEADERS = {"Accept": "application/json, text/event-stream"}

_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})

logger = logging.getLogger(__name__)


def luxalgo_enabled(*, raw: str | None = None) -> bool:
    """Whether the LuxAlgo family is enabled (default ON; explicit values fail closed)."""
    value = os.environ.get(LUXALGO_ENABLED_ENV) if raw is None else raw
    if value is None or not value.strip():
        return True
    return value.strip().lower() in _TRUTHY_ENV_VALUES


def _parse_streamable_body(text: str) -> Any:
    """Extract the JSON-RPC payload from a streamable-HTTP body.

    Takes the last ``data:`` SSE line's JSON (a trailing empty event id or a
    bare-JSON body is also accepted).
    """
    data_lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
    candidates = list(reversed(data_lines)) + ([text.strip()] if text.strip() else [])
    for candidate in candidates:
        if not candidate or candidate == "[DONE]":
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON payload in streamable-HTTP body")


def _extract_result_data(result: Any) -> Any:
    """Unwrap a ``tools/call`` result into the envelope ``data`` payload.

    Library tools answer ``structuredContent``; the edge/trackers tools answer
    MCP content blocks whose first text part is the JSON payload itself
    (probe-verified 2026-09-30). Either shape yields the parsed payload; an
    unparseable body falls back to the raw result so the envelope still
    carries what the upstream said.
    """
    if isinstance(result, dict) and "structuredContent" in result:
        return result["structuredContent"]
    if isinstance(result, dict) and isinstance(result.get("content"), list):
        texts = [
            block.get("text")
            for block in result["content"]
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        joined = "\n".join(texts).strip()
        if joined:
            try:
                return json.loads(joined)
            except json.JSONDecodeError:
                pass
    return result.get("structuredContent", result) if isinstance(result, dict) else result


class LuxAlgoClient:
    """Thin JSON-RPC client for the hosted LuxAlgo MCP (Library + Edge + Trackers)."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self._enabled = luxalgo_enabled() if enabled is None else enabled
        self._http = httpx.Client(transport=transport, timeout=timeout_seconds)
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, str]] = {}
        self._cache_lock = threading.Lock()
        self._request_id = 0
        self._id_lock = threading.Lock()

    def close(self) -> None:
        try:
            self._http.close()
        except Exception:  # closing is cleanup; never break a tool call
            pass

    # -- internals ---------------------------------------------------------

    def _next_id(self) -> int:
        with self._id_lock:
            self._request_id += 1
            return self._request_id

    def _cache_key(self, tool: str, arguments: dict[str, Any]) -> str:
        return f"{tool}:{json.dumps(arguments, sort_keys=True, default=str)}"

    def _cache_get(self, key: str) -> str | None:
        with self._cache_lock:
            hit = self._cache.get(key)
            if hit is None:
                return None
            if time.time() - hit[0] >= self._cache_ttl:
                del self._cache[key]
                return None
            return hit[1]

    def _cache_put(self, key: str, value: str) -> None:
        with self._cache_lock:
            if len(self._cache) >= DEFAULT_CACHE_MAX_ENTRIES:
                oldest = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest]
            self._cache[key] = (time.time(), value)

    def _call(self, upstream_tool: str, arguments: dict[str, Any]) -> LuxalgoEnvelope[Any]:
        """One ``tools/call`` round trip; never raises (typed envelopes only)."""
        if not self._enabled:
            return envelope_error(
                "upstream_error",
                "LuxAlgo tools are disabled by kill switch (LUXALGO_ENABLED); no request made.",
            )
        payload = dict(arguments or {})
        # The upstream requires `context` and it must never carry caller PII:
        # always overwrite with the fixed server-side constant.
        payload["context"] = LUXALGO_CONTEXT
        cache_key = self._cache_key(upstream_tool, payload)
        cached = self._cache_get(cache_key)
        if cached is not None:
            envelope = LuxalgoEnvelope[Any](data=json.loads(cached), stale=True)
            return envelope
        body = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": upstream_tool, "arguments": payload},
        }
        try:
            response = self._http.post(LUXALGO_MCP_URL, json=body, headers=_REQUEST_HEADERS)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            return envelope_error(
                "upstream_error", f"LuxAlgo MCP unreachable: {exc}", retryable=True
            )
        except Exception as exc:
            return envelope_error("upstream_error", f"LuxAlgo MCP request failed: {exc}")
        if response.status_code >= 500:
            return envelope_error(
                "upstream_error",
                f"LuxAlgo MCP HTTP {response.status_code}",
                retryable=True,
            )
        if response.status_code == 429:
            return envelope_error("rate_limited", "LuxAlgo MCP rate limit (HTTP 429).")
        if response.status_code >= 400:
            return envelope_error("upstream_error", f"LuxAlgo MCP HTTP {response.status_code}.")
        try:
            message = _parse_streamable_body(response.text)
        except ValueError as exc:
            return envelope_error("upstream_error", f"LuxAlgo MCP bad body: {exc}")
        if not isinstance(message, dict) or "result" not in message:
            error_text = ""
            if isinstance(message, dict):
                error = message.get("error") or {}
                error_text = str(error.get("message", error) if isinstance(error, dict) else error)
            if "not found" in error_text.lower():
                return envelope_error("not_found", f"LuxAlgo MCP: {error_text}")
            return envelope_error("upstream_error", f"LuxAlgo MCP error: {error_text or message}")
        result = message["result"]
        data = _extract_result_data(result)
        try:
            envelope = LuxalgoEnvelope[Any](data=data)
        except ValidationError as exc:
            return envelope_error("upstream_error", f"LuxAlgo MCP bad payload: {exc}")
        self._cache_put(cache_key, json.dumps(envelope.data, default=str))
        return envelope

    # -- Library tools (P0 subset; no source_code, no journal/broker/propfirms) --
    #
    # Each method accepts a validated input model or a raw dict (the dispatcher
    # falls back to the raw payload on ValidationError so the client owns the
    # single invalid_input contract).

    @staticmethod
    def _coerce_args(args: Any) -> dict[str, Any]:
        model_dump = getattr(args, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump(mode="json", exclude_none=True)
            return dict(dumped) if isinstance(dumped, dict) else {}
        return dict(args or {})

    def library_search(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._call("library_search", self._coerce_args(args))

    def library_get_concept(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._call("library_get_concept", self._coerce_args(args))

    def library_get_indicator(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._call("library_get_indicator", self._coerce_args(args))

    def library_list_concepts(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._call("library_list_concepts", self._coerce_args(args))

    def library_list_indicators(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._call("library_list_indicators", self._coerce_args(args))

    def library_list_tags(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._call("library_list_tags", self._coerce_args(args))

    def library_list_families(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._call("library_list_families", self._coerce_args(args))

    def library_get_family(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._call("library_get_family", self._coerce_args(args))

    # -- Edge Stats preset reads (#4844; keyless, read-only) --
    #
    # The upstream edge_report payload already carries the honesty disclaimer
    # (identical to digiquant.stats.honesty.DISCLAIMER); the client also stamps
    # it into the envelope warnings so every rendered preset stat carries it
    # even when a caller reads warnings only.

    def edge_symbols(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._call("edge_symbols", self._coerce_args(args))

    def edge_presets(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._call("edge_presets", self._coerce_args(args))

    def edge_report(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        envelope = self._call("edge_report", self._coerce_args(args))
        if isinstance(envelope.data, LuxalgoError):
            return envelope
        warnings = list(envelope.warnings or [])
        if HONESTY_DISCLAIMER not in warnings:
            warnings.append(HONESTY_DISCLAIMER)
        return envelope.model_copy(update={"warnings": warnings})

    # -- Market Trackers live-query companions (#4844; keyless, read-only) --
    #
    # Freshness/ad-hoc lookups only: the CC0 dumps stay the source of record
    # (trackers_query is deliberately NOT wrapped). An upstream ``stale`` flag
    # on the payload folds into the envelope ``stale`` bit.

    def _trackers_call(self, upstream_tool: str, args: Any) -> LuxalgoEnvelope[Any]:
        envelope = self._call(upstream_tool, self._coerce_args(args))
        if isinstance(envelope.data, dict) and envelope.data.get("stale") is True:
            return envelope.model_copy(update={"stale": True})
        return envelope

    def trackers_datasets(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._trackers_call("trackers_datasets", args)

    def trackers_latest(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._trackers_call("trackers_latest", args)

    def trackers_ticker(self, args: Any = None) -> LuxalgoEnvelope[Any]:
        return self._trackers_call("trackers_ticker", args)


def luxalgo_error_message(data: Any) -> str | None:
    """Typed error message when an envelope's ``data`` is a ``LuxalgoError``."""
    codes = set(get_args(ErrorCode))
    if (
        isinstance(data, dict)
        and {"code", "message", "retryable"} <= set(data)
        and data["code"] in codes
    ):
        return str(data["message"])
    if isinstance(data, LuxalgoError):
        return data.message
    return None

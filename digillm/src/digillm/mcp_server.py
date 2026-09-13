"""digillm MCP server — exposes generic LLM completion as MCP tools.

Run: ``python -m digillm.mcp_server`` (streamable HTTP, default 127.0.0.1:8768).

digillm is a generic provider router (model string + key + base URL) with no
vendor tooling. This server exposes the serializable slice of that surface:

- ``complete`` — single chat completion, optional ``max_tokens`` and an
  optional JSON-schema response contract.

``run_tools`` and ``structured_completion`` stay library-only: they need a
caller-side ``execute_tool`` callable / Pydantic model class, neither of which
crosses the MCP boundary — compose them client-side around ``complete``.

Routing follows the process environment (house Cheaper Inference when
``CHEAPERINFERENCE_API_KEY`` is set, else OpenRouter rewrite / LiteLLM proxy /
vendor clients). Per-request BYOK / proxy-key contextvars do not cross the
MCP boundary. Provider errors surface as MCP errors (fail-fast, no fallback).

Trust model (same as the other component servers): streamable-http binds
loopback by default — treat any wider bind (``--host`` / ``DIGILLM_MCP_HOST``)
like a network API with gateway auth, since callers spend the operator key.
stdio suits trusted local clients.
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP

    _MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the [mcp] extra
    FastMCP = None  # type: ignore[assignment,misc]
    _MCP_AVAILABLE = False

if not _MCP_AVAILABLE:
    logger.warning(
        "digillm MCP server requires the 'mcp' package. Install it with: pip install mcp"
    )

mcp = FastMCP("digillm", json_response=True) if _MCP_AVAILABLE else None

_VALID_ROLES = frozenset({"system", "user", "assistant", "developer", "tool"})


def _coerce_messages(messages: Any) -> list[dict[str, str]]:
    """Validate the MCP message list into chat message dicts."""
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list of {role, content} objects")
    coerced: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            raise ValueError("each message must be a {role, content} object")
        role, content = item.get("role"), item.get("content")
        if role not in _VALID_ROLES or not isinstance(content, str) or not content.strip():
            raise ValueError(
                f"each message needs a valid role ({sorted(_VALID_ROLES)}) and non-empty content"
            )
        coerced.append({"role": role, "content": content})
    return coerced


def _register_tools(server: Any) -> None:
    """Register digillm tools on a FastMCP server (deferred so import stays light)."""

    @server.tool()
    def complete(
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run one chat completion on any routed model.

        Args:
            model: Model string (``provider/model`` routes to that vendor client;
                otherwise the ``OPENAI_API_BASE`` default client serves it).
            messages: Non-empty list of ``{role, content}`` objects.
            temperature: Sampling temperature.
            max_tokens: Optional output cap (omit for provider default).
            json_schema: Optional ``{"name": ..., "schema": {...}}`` contract —
                sent as a strict OpenAI json_schema response_format.

        Returns:
            ``{"content": str, "model": str}`` — the served model id plus text.
        """
        from digillm import completion as _completion

        chat_messages = _coerce_messages(messages)
        response_format: dict[str, Any] | None = None
        if json_schema is not None:
            if not isinstance(json_schema, dict) or "schema" not in json_schema:
                raise ValueError("json_schema must be a {name, schema} object")
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": json_schema.get("name", "response"),
                    "strict": True,
                    "schema": json_schema["schema"],
                },
            }
        resp = _completion(
            model,
            chat_messages,  # type: ignore[arg-type]
            temperature=temperature,
            response_format=response_format,  # type: ignore[arg-type]
            max_tokens=max_tokens,
        )
        if not resp.choices:
            raise RuntimeError(f"model {model!r} returned no choices")
        return {
            "content": (resp.choices[0].message.content or "").strip(),
            "model": getattr(resp, "model", None) or model,
        }


if _MCP_AVAILABLE and mcp is not None:
    _register_tools(mcp)


def run_mcp(
    transport: str = "streamable-http",
    host: str | None = None,
    port: int = 8768,
) -> None:
    """Run the MCP server. Default: streamable HTTP on 127.0.0.1:8768."""
    if not _MCP_AVAILABLE or mcp is None:
        raise RuntimeError("the 'mcp' package is not installed (pip install 'digillm[mcp]')")
    bind = host or os.environ.get("DIGILLM_MCP_HOST", "127.0.0.1")
    mcp.settings.host = bind
    mcp.settings.port = port
    mcp.run(transport=transport)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: ``python -m digillm.mcp_server [--stdio]``."""
    parser = argparse.ArgumentParser(description="digillm MCP server (generic LLM completion)")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport (Claude Desktop)")
    parser.add_argument("--host", default=None, help="Bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("DIGILLM_MCP_PORT", "8768")))
    args = parser.parse_args(argv)
    if args.stdio:
        run_mcp(transport="stdio")
    else:
        run_mcp(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover
    main()

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

# No `from __future__ import annotations`: the stack image ships FastMCP 1.9.3,
# which calls issubclass() on raw annotations — PEP 563 string annotations crash
# every @mcp.tool() at import (Dockerfile.digithings-stack-cloudflare marker v8).

import argparse
import logging
import os
from dataclasses import asdict, is_dataclass
from types import MappingProxyType, SimpleNamespace
from typing import Any, Mapping

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


# --- Art. 9 surface registry (DIG-1083 leaf 10) -----------------------------
#
# digibase's registry (digibase.art9) is keyed by HTTP path templates, so it
# structurally cannot see this server: a streamable-HTTP MCP tool call has no
# path. digillm has no FastAPI app and no route table, so the path-keyed floor
# would pass every call here through unscreened.
#
# This registry is deliberately local and self-contained:
#
#   * digillm must NOT import digibase as a dependency (see egress_record.py
#     and its package rules), so the detector is imported lazily and a missing
#     digibase FAILS CLOSED with art9:screening_unavailable rather than
#     letting content through unscanned.
#   * digillm must NOT import fastapi anywhere, so this is plain Python: no
#     ASGI middleware, no Request objects.
#
# Surface ids are explicit, not derived from a path: an unregistered surface is
# refused, which is what makes a *missing* registration detectable instead of
# silent.
SURFACE_KIND_MCP = "mcp"
SURFACE_MCP = "mcp"
SURFACE_UNREGISTERED = "art9:surface_unregistered"
SURFACE_SCREENING_UNAVAILABLE = "art9:screening_unavailable"

_surfaces: dict[str, str] = {SURFACE_MCP: SURFACE_KIND_MCP}

#: Read-only view of the digillm Art. 9 surface registry (surface id -> kind).
ART9_SURFACES: Mapping[str, str] = MappingProxyType(_surfaces)


def declare_art9_surface(surface: str, kind: str) -> None:
    """Register ``surface`` as an Art. 9-screened entry point."""
    _surfaces[surface] = kind


def art9_surface_kind(surface: str) -> str | None:
    """Return the registered kind for ``surface``, or ``None`` if unregistered."""
    return _surfaces.get(surface)


class Art9SurfaceRefusal(RuntimeError):
    """Raised when a declared surface carries Art. 9 special-category content."""

    def __init__(self, surface: str, reason: str, categories: tuple[str, ...]) -> None:
        super().__init__(f"{surface}: {reason}")
        self.surface = surface
        self.reason = reason
        self.categories = categories


def _refusal_result(reason: str, categories: tuple[str, ...] = ()) -> Any:
    """Build a ScreenResult-shaped object for refusals raised without digibase.

    Duplicated here on purpose: digillm must not import digibase, and a refusal
    that cannot be rendered as a ScreenResult is a refusal that callers cannot
    assert on. The attributes below are the entire ScreenResult surface this
    module reads.
    """
    return SimpleNamespace(
        categories=categories,
        redacted=None,
        decision="refuse",
        reason=reason,
        exception_ref=None,
    )


def screen_art9_surface(surface: str, payload: Any, *, exception_ref: str | None = None) -> Any:
    """Screen ``payload`` for Art. 9 special-category content on ``surface``.

    Fails closed in two ways: an unregistered surface is refused outright, and
    an unavailable detector is refused rather than skipped.
    """
    if surface not in _surfaces:
        return _refusal_result(f"{SURFACE_UNREGISTERED}:{surface}")
    try:
        from digibase.art9 import screen_request
    except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
        logger.error("digibase.art9 unavailable; refusing %s rather than screening", surface)
        return _refusal_result(SURFACE_SCREENING_UNAVAILABLE)
    return screen_request(payload, exception_ref=exception_ref)


def require_art9_clear(surface: str, payload: Any, *, exception_ref: str | None = None) -> None:
    """Raise ``Art9SurfaceRefusal`` unless ``payload`` screens clean on ``surface``."""
    result = screen_art9_surface(surface, payload, exception_ref=exception_ref)
    if result.decision == "refuse":
        raise Art9SurfaceRefusal(surface, result.reason, tuple(result.categories))


def _tool_payload(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Build the screenable payload for one MCP tool call."""
    if len(args) == 1 and not kwargs:
        return args[0]
    if not args:
        return dict(kwargs)
    return {"args": list(args), "kwargs": dict(kwargs)}


def _as_screenable(value: Any) -> Any:
    """Convert dataclass payloads (pydantic models included) into plain data."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


def _screened_tool_fn(tool_name: str, fn: Any, is_async: bool) -> Any:
    """Return ``fn`` wrapped so every call is screened before it runs."""
    # Capture the original FIRST: closing over `tool.fn` after reassigning it
    # makes the wrapper call itself (RecursionError -> ToolError).
    original = fn

    if is_async:

        async def screened(*args: Any, **kwargs: Any) -> Any:
            require_art9_clear(SURFACE_MCP, _as_screenable(_tool_payload(args, kwargs)))
            return await original(*args, **kwargs)

    else:

        def screened(*args: Any, **kwargs: Any) -> Any:
            require_art9_clear(SURFACE_MCP, _as_screenable(_tool_payload(args, kwargs)))
            return original(*args, **kwargs)

    screened.__name__ = getattr(original, "__name__", tool_name)
    screened.__doc__ = original.__doc__
    screened.__art9_screened__ = True
    return screened


def install_art9_surface_screen(server: Any = None) -> int:
    """Screen every registered MCP tool on ``server``; return how many were wrapped.

    FastMCP 1.9.3 exposes no middleware hook, and its public ``call_tool`` is
    the client-facing path, so wrapping it would guard nothing. The real
    dispatch is ToolManager.call_tool -> Tool.run -> fn, and ``Tool.fn`` is a
    plain attribute: reassigning it intercepts genuine server-side dispatch.

    Raises if the tool manager is missing, or if the server serves no tools at
    all — a screen covering a server with nothing on it is a guard that passes
    without testing anything. Re-installing over already-screened tools is a
    no-op that returns 0 rather than raising: that is idempotence, not absence.
    """
    srv = server if server is not None else mcp
    manager = getattr(srv, "_tool_manager", None)
    if manager is None:
        raise RuntimeError("digillm MCP server has no tool manager to screen")
    tools = list(manager.list_tools())
    if not tools:
        raise RuntimeError("art9 surface screen installed on 0 digillm MCP tools")
    wrapped = 0
    for tool in tools:
        if getattr(tool, "__art9_screened__", False) or getattr(
            tool.fn, "__art9_screened__", False
        ):
            continue
        tool.fn = _screened_tool_fn(tool.name, tool.fn, bool(tool.is_async))
        wrapped += 1
    if wrapped:
        logger.info("art9 screen installed on %d digillm MCP tool(s)", wrapped)
    return wrapped


ART9_SCREENED_TOOLS = install_art9_surface_screen() if _MCP_AVAILABLE and mcp is not None else 0


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

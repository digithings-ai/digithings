"""digigraph MCP server. Exposes workflow, chat, thread state, and tool discovery as MCP tools.

Install::

    pip install -e "digigraph[mcp]"

Run standalone::

    python -m digigraph.mcp_server             # streamable-http on port 8766
    python -m digigraph.mcp_server --stdio     # stdio transport (Claude Desktop)

**Trust model:** Treat streamable-http like any network API: bind to loopback, use a firewall, or terminate TLS with auth at a gateway. stdio is appropriate for trusted local clients (e.g. Claude Desktop). With ``DIGI_MCP_REQUIRE_AUTH=1``, every tool verifies a digikey-issued RS256 bearer token (signature via ``DIGIKEY_JWKS_URL`` / ``DIGIKEY_PUBLIC_KEY_PEM``, plus issuer/audience/exp) and requires the tool's scope; the server fails closed if no verifier is configured. Without that flag the server is unauthenticated, so combine it with network policy when the stack is reachable beyond localhost.

**Graphiti / graph memory:** Not exposed via MCP yet; see ``digigraph/ARCHITECTURE.md`` Phase 2 roadmap.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from collections.abc import Mapping
from typing import Any

_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# Required digikey scope per MCP tool. Mirrors digigraph_path_scopes for the
# HTTP routes the chat/thread_state tools call in-process.
SCOPE_WORKFLOW = "digigraph:workflow"
SCOPE_CHAT = "digigraph:chat"
SCOPE_MCP = "digigraph:mcp"


def _validate_thread_id(thread_id: str | None) -> str | None:
    if thread_id is None:
        return None
    tid = thread_id.strip()
    if not tid or not _THREAD_ID_RE.match(tid):
        raise ValueError("thread_id must be 1-128 alphanumeric characters (._- allowed)")
    return tid


logger = logging.getLogger(__name__)

_MCP_WORKFLOW_ERRORS = (
    ValueError,
    OSError,
    RuntimeError,
    ImportError,
    TypeError,
    KeyError,
    AttributeError,
)

_MCP_CLIENT_ERRORS = (
    ImportError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


def _has_digikey_verifier_config() -> bool:
    return bool(
        (os.environ.get("DIGIKEY_JWKS_URL") or "").strip()
        or (os.environ.get("DIGIKEY_PUBLIC_KEY_PEM") or "").strip()
    )


class McpAuthDenied(Exception):
    """An MCP tool call was refused by the auth gate (missing/invalid token or scope)."""


def _mcp_auth_required() -> bool:
    return (os.environ.get("DIGI_MCP_REQUIRE_AUTH") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _bearer_from_headers(headers: Mapping[str, str] | None) -> str | None:
    if not headers:
        return None
    raw = ""
    for key, value in headers.items():
        if key.lower() == "authorization":
            raw = value or ""
            break
    if raw[:7].lower() != "bearer ":
        return None
    token = raw[7:].strip()
    return token or None


def _authorize_mcp_headers(headers: Mapping[str, str] | None, required_scope: str) -> str | None:
    """Verify a digikey RS256 bearer token for an MCP call, or raise ``McpAuthDenied``.

    Reuses the same digikey verification path as ``DigiAuthMiddleware``:
    ``decode_token`` validates signature, issuer, audience and exp;
    ``blocklist`` applies the same fail-closed revocation policy (including
    ``DIGIKEY_REQUIRE_BLOCKLIST=1``); scope matching uses the shared
    wildcard-aware ``scope_grants_required``. Fails closed: when auth is
    required and no verifier is configured, every call is refused rather than
    silently allowed.

    Returns the caller's bearer token so a caller can forward it to internal
    same-process HTTP calls (which re-verify it via ``DigiAuthMiddleware``).
    When auth is not required the token is returned unverified (or ``None``).
    """
    token = _bearer_from_headers(headers)
    if not _mcp_auth_required():
        return token
    if not _has_digikey_verifier_config():
        raise McpAuthDenied(
            "MCP auth required but no digikey verifier configured "
            "(set DIGIKEY_JWKS_URL or DIGIKEY_PUBLIC_KEY_PEM)"
        )
    if not token:
        raise McpAuthDenied("Bearer token required")

    import jwt
    from digikey import blocklist
    from digikey.jwt_verify import JwtVerificationError, decode_token
    from digikey.scopes import scope_grants_required

    try:
        claims = decode_token(token)
    except (jwt.PyJWTError, JwtVerificationError) as exc:
        raise McpAuthDenied("Invalid or expired bearer token") from exc
    # Post-signature revocation check, mirroring DigiAuthMiddleware: fail closed
    # when the blocklist policy is unmet or the backend is unreachable.
    if claims.jti:
        try:
            blocklist.assert_blocklist_ready()
        except blocklist.BlocklistUnavailable as exc:
            raise McpAuthDenied("Auth backend temporarily unavailable") from exc
    if claims.jti and blocklist.is_configured():
        try:
            if blocklist.is_blocked(claims.jti):
                raise McpAuthDenied("Token has been revoked")
        except blocklist.BlocklistUnavailable as exc:
            raise McpAuthDenied("Auth backend temporarily unavailable") from exc
    if not scope_grants_required(claims.scopes, [required_scope]):
        raise McpAuthDenied(f"Insufficient scope: {required_scope} required")
    return token


def _headers_from_context(ctx: Any) -> Mapping[str, str] | None:
    """Best-effort extraction of HTTP headers from a FastMCP request Context.

    Returns ``None`` for transports without HTTP headers (stdio), so auth stays
    fail-closed there when required.
    """
    try:
        request = ctx.request_context.request
    except (AttributeError, ValueError):
        return None
    if request is None:
        return None
    return getattr(request, "headers", None)


def _authorize_mcp_ctx(ctx: Any, required_scope: str) -> str | None:
    return _authorize_mcp_headers(_headers_from_context(ctx), required_scope)


def _internal_auth_headers(token: str | None) -> dict[str, str]:
    """Forward the caller's verified bearer to an in-process HTTP call.

    The ``chat`` / ``thread_state`` tools call the digraph FastAPI app via
    TestClient; without the header ``DigiAuthMiddleware`` 401s even a valid
    caller. The token is re-verified by that middleware, so this is a
    pass-through, not a bypass.
    """
    return {"Authorization": f"Bearer {token}"} if token else {}


def _mcp_denied_json(exc: McpAuthDenied) -> str:
    logger.warning("MCP tool call denied: %s", exc)
    return json.dumps(
        {
            "success": False,
            "error": "unauthorized",
            "message": f"Unauthorized: {exc}",
            "backtest_result": None,
        }
    )


try:
    from mcp.server.fastmcp import Context, FastMCP

    _MCP_AVAILABLE = True
except ImportError:
    Context = None  # type: ignore[assignment,misc]
    FastMCP = None  # type: ignore[assignment,misc]
    _MCP_AVAILABLE = False

if not _MCP_AVAILABLE:
    logger.warning(
        "digigraph MCP server requires the 'mcp' package. Install it with: pip install mcp"
    )


def _require_mcp() -> "FastMCP":
    if not _MCP_AVAILABLE:
        raise ImportError(
            "digigraph MCP server requires the 'mcp' package. Install: pip install mcp"
        )
    return FastMCP  # type: ignore[return-value]


def create_mcp_server() -> Any:
    """Build and return a FastMCP server exposing digigraph capabilities.

    Tools:
    - ``workflow(prompt, thread_id)`` — run the full research+backtest graph
    - ``chat(message, thread_id)`` — single-turn OpenAI-compatible chat
    - ``thread_state(thread_id)`` — return the current LangGraph checkpoint state
    - ``list_orchestrator_tools()`` — registered orchestrator tool names (skills/registry)
    - ``list_orchestrator_tools_detailed()`` — manifest (name, tags, dynamic_schema)
    """
    _require_mcp()

    # MCP uses in-process HTTP (TestClient) for chat/thread routes; enable thread API in this process.
    os.environ.setdefault("DIGI_ENABLE_THREAD_API", "1")

    mcp = FastMCP("digigraph")

    @mcp.tool()
    def list_orchestrator_tools(ctx: Context = None) -> str:  # type: ignore[assignment]
        """List registered orchestrator tool names (MCP / OpenAI function names)."""
        try:
            _authorize_mcp_ctx(ctx, SCOPE_MCP)
        except McpAuthDenied as exc:
            return _mcp_denied_json(exc)
        from digigraph.orchestration import list_tool_names

        return json.dumps(sorted(list_tool_names()), indent=2)

    @mcp.tool()
    def list_orchestrator_tools_detailed(ctx: Context = None) -> str:  # type: ignore[assignment]
        """List orchestrator tools with tags and whether schema is context-dependent."""
        try:
            _authorize_mcp_ctx(ctx, SCOPE_MCP)
        except McpAuthDenied as exc:
            return _mcp_denied_json(exc)
        from digigraph.orchestration import list_registered_tools_detailed

        return json.dumps(list_registered_tools_detailed(), indent=2)

    @mcp.tool()
    def workflow(
        prompt: str,
        thread_id: str | None = None,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Run the digigraph research + backtest workflow.

        Accepts a natural-language investment idea (e.g. 'test a mean-reversion
        strategy on AAPL using the last 3 years of data') and returns a structured
        JSON result containing the research response and backtest metrics.

        Args:
            prompt: The investment idea or analysis request.
            thread_id: Optional session ID for conversation continuity.
        """
        from digigraph.models import WorkflowRequest
        from digigraph.workflow import run_digigraph_workflow

        try:
            _authorize_mcp_ctx(ctx, SCOPE_WORKFLOW)
        except McpAuthDenied as exc:
            return _mcp_denied_json(exc)
        try:
            session_id = _validate_thread_id(thread_id)
        except ValueError as exc:
            return json.dumps({"success": False, "message": str(exc), "backtest_result": None})
        req = WorkflowRequest(
            prompt=prompt,
            session_id=session_id,
            request_id=str(uuid.uuid4()),
        )
        try:
            result = run_digigraph_workflow(req)
            return json.dumps(
                {
                    "success": result.success,
                    "message": result.message,
                    "backtest_result": result.backtest_result,
                    "research_brief": result.research_brief,
                    "rag_sources": result.rag_sources,
                    "profiling_questions": result.profiling_questions,
                },
                indent=2,
            )
        except _MCP_WORKFLOW_ERRORS as e:
            logger.error("digigraph workflow MCP tool failed: %s", e)
            return json.dumps({"success": False, "message": str(e), "backtest_result": None})

    @mcp.tool()
    def chat(
        message: str,
        thread_id: str | None = None,
        model: str = "digigraph-rag",
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Send a single chat message to digigraph and get a response.

        Uses the full tool-calling loop (digisearch RAG, digiquant backtest, analytics)
        as needed. Maintains conversation history across calls when *thread_id* is reused.

        Args:
            message: The user message.
            thread_id: Optional session ID for multi-turn conversations.
            model: Model identifier (passed through to LiteLLM router; default: digigraph-rag).
        """
        try:
            token = _authorize_mcp_ctx(ctx, SCOPE_CHAT)
        except McpAuthDenied as exc:
            logger.warning("digigraph chat MCP tool denied: %s", exc)
            return "[digigraph chat error: unauthorized]"
        try:
            session_id = _validate_thread_id(thread_id)
        except ValueError as exc:
            return f"[digigraph chat error: {exc}]"
        try:
            from fastapi.testclient import TestClient

            from digigraph.server import app as dg_app

            client = TestClient(dg_app, raise_server_exceptions=False)
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": message}],
                "stream": False,
                "session_id": session_id,
            }
            r = client.post(
                "/v1/chat/completions",
                json=payload,
                headers=_internal_auth_headers(token),
            )
            if r.status_code == 200:
                data = r.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
            return f"[digigraph chat error: HTTP {r.status_code}]"
        except _MCP_CLIENT_ERRORS as e:
            logger.error("digigraph chat MCP tool failed: %s", e)
            return f"[digigraph chat error: {e}]"

    @mcp.tool()
    def thread_state(thread_id: str, ctx: Context = None) -> str:  # type: ignore[assignment]
        """Return the current LangGraph checkpoint state for a thread.

        Useful for inspecting what a prior workflow run produced — research notes,
        backtest results, stored datasets — without re-running the workflow.

        Args:
            thread_id: The session/thread ID to look up.
        """
        try:
            token = _authorize_mcp_ctx(ctx, SCOPE_MCP)
        except McpAuthDenied as exc:
            return _mcp_denied_json(exc)
        try:
            tid = _validate_thread_id(thread_id)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        if tid is None:
            return json.dumps({"error": "thread_id is required"})
        try:
            from fastapi.testclient import TestClient

            from digigraph.server import app as dg_app

            client = TestClient(dg_app, raise_server_exceptions=False)
            r = client.get(f"/threads/{tid}/state", headers=_internal_auth_headers(token))
            if r.status_code == 200:
                return json.dumps(r.json(), indent=2)
            return json.dumps({"error": f"HTTP {r.status_code}", "detail": r.text})
        except _MCP_CLIENT_ERRORS as e:
            logger.error("digigraph thread_state MCP tool failed: %s", e)
            return json.dumps({"error": str(e)})

    return mcp


_mcp_instance: Any | None = None


def get_mcp_server() -> Any:
    """Return a module-level singleton MCP server (lazy init)."""
    global _mcp_instance
    if _mcp_instance is None:
        _mcp_instance = create_mcp_server()
    return _mcp_instance


def run_mcp(
    transport: str = "streamable-http",
    host: str | None = None,
    port: int = 8766,
) -> None:
    """Start the MCP server. Defaults: streamable-http on 127.0.0.1:8766."""
    bind = host or os.environ.get("DIGIGRAPH_MCP_HOST", "127.0.0.1")
    mcp = get_mcp_server()
    logger.info("Starting digigraph MCP server on %s:%d (transport=%s)", bind, port, transport)
    mcp.settings.host = bind
    mcp.settings.port = port
    mcp.run(transport=transport)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="digigraph MCP server")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport (Claude Desktop)")
    parser.add_argument("--host", default=os.environ.get("DIGIGRAPH_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    transport = "stdio" if args.stdio else "streamable-http"
    run_mcp(transport=transport, host=args.host, port=args.port)

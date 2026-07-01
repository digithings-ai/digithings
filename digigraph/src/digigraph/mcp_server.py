"""DigiGraph MCP server. Exposes workflow, chat, thread state, and tool discovery as MCP tools.

Install::

    pip install -e "digigraph[mcp]"

Run standalone::

    python -m digigraph.mcp_server             # streamable-http on port 8766
    python -m digigraph.mcp_server --stdio     # stdio transport (Claude Desktop)

**Trust model:** Treat streamable-http like any network API: bind to loopback, use a firewall, or terminate TLS with auth at a gateway. stdio is appropriate for trusted local clients (e.g. Claude Desktop). MCP does not add its own API-key layer; combine with ``DIGI_API_KEY`` on the DigiGraph HTTP app and network policy when the stack is reachable beyond localhost.

**Graphiti / graph memory:** Not exposed via MCP yet; see ``digigraph/ARCHITECTURE.md`` Phase 2 roadmap.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any

_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


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


try:
    from mcp.server.fastmcp import FastMCP

    _MCP_AVAILABLE = True
except ImportError:
    FastMCP = None  # type: ignore[assignment,misc]
    _MCP_AVAILABLE = False

if not _MCP_AVAILABLE:
    logger.warning(
        "DigiGraph MCP server requires the 'mcp' package. Install it with: pip install mcp"
    )


def _require_mcp() -> "FastMCP":
    if not _MCP_AVAILABLE:
        raise ImportError(
            "DigiGraph MCP server requires the 'mcp' package. Install: pip install mcp"
        )
    return FastMCP  # type: ignore[return-value]


def create_mcp_server() -> Any:
    """Build and return a FastMCP server exposing DigiGraph capabilities.

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

    mcp = FastMCP("DigiGraph")

    @mcp.tool()
    def list_orchestrator_tools() -> str:
        """List registered orchestrator tool names (MCP / OpenAI function names)."""
        from digigraph.orchestration import list_tool_names

        return json.dumps(sorted(list_tool_names()), indent=2)

    @mcp.tool()
    def list_orchestrator_tools_detailed() -> str:
        """List orchestrator tools with tags and whether schema is context-dependent."""
        from digigraph.orchestration import list_registered_tools_detailed

        return json.dumps(list_registered_tools_detailed(), indent=2)

    @mcp.tool()
    def workflow(
        prompt: str,
        thread_id: str | None = None,
    ) -> str:
        """Run the DigiGraph research + backtest workflow.

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
            session_id = _validate_thread_id(thread_id)
        except ValueError as exc:
            return json.dumps({"success": False, "message": str(exc), "backtest_result": None})
        req = WorkflowRequest(
            prompt=prompt,
            session_id=session_id,
            request_id=str(uuid.uuid4()),
        )
        if (
            os.environ.get("DIGI_MCP_REQUIRE_AUTH", "").strip().lower() in ("1", "true", "yes")
            and not _has_digikey_verifier_config()
        ):
            return json.dumps(
                {
                    "success": False,
                    "message": "MCP workflow disabled: set DIGIKEY_JWKS_URL or DIGIKEY_PUBLIC_KEY_PEM, or unset DIGI_MCP_REQUIRE_AUTH",
                    "backtest_result": None,
                }
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
            logger.error("DigiGraph workflow MCP tool failed: %s", e)
            return json.dumps({"success": False, "message": str(e), "backtest_result": None})

    @mcp.tool()
    def chat(
        message: str,
        thread_id: str | None = None,
        model: str = "sitaas-rag",
    ) -> str:
        """Send a single chat message to DigiGraph and get a response.

        Uses the full tool-calling loop (DigiSearch RAG, DigiQuant backtest, analytics)
        as needed. Maintains conversation history across calls when *thread_id* is reused.

        Args:
            message: The user message.
            thread_id: Optional session ID for multi-turn conversations.
            model: Model identifier (passed through to LiteLLM router; default: sitaas-rag).
        """

        try:
            session_id = _validate_thread_id(thread_id)
        except ValueError as exc:
            return f"[DigiGraph chat error: {exc}]"
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
            r = client.post("/v1/chat/completions", json=payload)
            if r.status_code == 200:
                data = r.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
            return f"[DigiGraph chat error: HTTP {r.status_code}]"
        except _MCP_CLIENT_ERRORS as e:
            logger.error("DigiGraph chat MCP tool failed: %s", e)
            return f"[DigiGraph chat error: {e}]"

    @mcp.tool()
    def thread_state(thread_id: str) -> str:
        """Return the current LangGraph checkpoint state for a thread.

        Useful for inspecting what a prior workflow run produced — research notes,
        backtest results, stored datasets — without re-running the workflow.

        Args:
            thread_id: The session/thread ID to look up.
        """
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
            r = client.get(f"/threads/{tid}/state")
            if r.status_code == 200:
                return json.dumps(r.json(), indent=2)
            return json.dumps({"error": f"HTTP {r.status_code}", "detail": r.text})
        except _MCP_CLIENT_ERRORS as e:
            logger.error("DigiGraph thread_state MCP tool failed: %s", e)
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
    logger.info("Starting DigiGraph MCP server on %s:%d (transport=%s)", bind, port, transport)
    mcp.run(transport=transport, host=bind, port=port)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="DigiGraph MCP server")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport (Claude Desktop)")
    parser.add_argument("--host", default=os.environ.get("DIGIGRAPH_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    transport = "stdio" if args.stdio else "streamable-http"
    run_mcp(transport=transport, host=args.host, port=args.port)

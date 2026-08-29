"""digivault MCP server — exposes vault management as MCP tools for digigraph.

Run: ``python -m digivault.mcp_server`` (streamable HTTP, default 127.0.0.1:8766).
Operates on the vault directory named by ``DIGIVAULT_ROOT``.

Tool registration is owned by :mod:`digivault.tool_dispatch` — this module only
opens the vault and starts the transport. Do not add ``@mcp.tool`` handlers here.
"""

from __future__ import annotations

import logging
import os

from mcp.server.fastmcp import FastMCP

from digivault.tool_dispatch import register_mcp_tools
from digivault.vault import Vault, VaultError

logger = logging.getLogger(__name__)

mcp = FastMCP("digivault", json_response=True)


def _open_vault() -> Vault:
    root = (os.environ.get("DIGIVAULT_ROOT") or "").strip()
    if not root:
        raise VaultError("DIGIVAULT_ROOT is not configured")
    return Vault(root)


# Single registration path — discovery names == VAULT_HANDLERS keys.
register_mcp_tools(mcp, _open_vault)


def run_mcp(
    transport: str = "streamable-http",
    host: str | None = None,
    port: int = 8766,
) -> None:
    """Run the MCP server. Default: streamable HTTP on 127.0.0.1:8766."""
    bind = host or os.environ.get("DIGIVAULT_MCP_HOST", "127.0.0.1")
    mcp.run(transport=transport, host=bind, port=port)


if __name__ == "__main__":  # pragma: no cover
    run_mcp()

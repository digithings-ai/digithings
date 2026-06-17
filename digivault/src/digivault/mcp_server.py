"""DigiVault MCP server — exposes vault management as MCP tools for DigiGraph.

Run: ``python -m digivault.mcp_server`` (streamable HTTP, default 127.0.0.1:8766).
Operates on the vault directory named by ``DIGIVAULT_ROOT``.
"""

from __future__ import annotations

import json as _json
import logging
import os

from mcp.server.fastmcp import FastMCP

from digivault.vault import Vault, VaultError

logger = logging.getLogger(__name__)

mcp = FastMCP("DigiVault", json_response=True)


def _open_vault() -> Vault:
    root = (os.environ.get("DIGIVAULT_ROOT") or "").strip()
    if not root:
        raise VaultError("DIGIVAULT_ROOT is not configured")
    return Vault(root)


@mcp.tool()
def digivault_search_tag(tag: str) -> str:
    """Find vault notes carrying a given tag (without '#'). Use to locate docs by topic."""
    try:
        notes = _open_vault().search_by_tag(tag)
    except VaultError as e:
        return f"[DigiVault error: {e}]"
    return _json.dumps([{"name": n.name, "title": n.title, "rel_path": n.rel_path} for n in notes])


@mcp.tool()
def digivault_backlinks(name: str) -> str:
    """List notes that link to a given note (its backlinks)."""
    try:
        vault = _open_vault()
    except VaultError as e:
        return f"[DigiVault error: {e}]"
    if vault.get_note(name) is None:
        return f"[DigiVault: no such note {name!r}]"
    return _json.dumps({"name": name, "backlinks": list(vault.backlinks(name))})


@mcp.tool()
def digivault_lint() -> str:
    """Validate the vault: unresolved wikilinks, missing frontmatter, orphans, tags."""
    try:
        report = _open_vault().lint()
    except VaultError as e:
        return f"[DigiVault error: {e}]"
    return report.model_dump_json(indent=2)


@mcp.tool()
def digivault_create_note(name: str, title: str | None = None, body: str = "") -> str:
    """Create a new markdown note in the vault with optional title and body."""
    try:
        fm = {"title": title} if title else {}
        note = _open_vault().create_note(name, frontmatter=fm, body=body)
    except VaultError as e:
        return f"[DigiVault error: {e}]"
    return note.model_dump_json()


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

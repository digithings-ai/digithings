"""The MCP manifest must not over-claim.

`_mcp-tools.json` is the tool list digiquant.io renders, so every name in it has
to be a tool the server really registers. The 2026-10-11 audit found 42 of the
127 committed names were never registered at all: refused by
`digiquant.tool_refusals`, or gated behind the Gloomberb session entitlement.
`scripts/gen_mcp_manifest.py` now drops them, and these two checks keep the
committed file honest.

Check 1 needs no MCP install: the generator reads `mcp_server.py` with `ast`, so
a name the server stops defining -- or starts defining and the manifest has not
caught up with -- fails here. Check 2 asks the live server, and skips when the
`mcp` extra is absent rather than silently passing.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "apps" / "digiquant-web" / "scripts" / "gen_mcp_manifest.py"
MANIFEST = ROOT / "apps" / "digiquant-web" / "app" / "_mcp-tools.json"


def _manifest_names() -> list[str]:
    tools = json.loads(MANIFEST.read_text(encoding="utf-8"))
    names = [t["name"] for t in tools]
    # A non-empty set is the control: without it every subset assertion below
    # would pass on an empty manifest.
    assert names, "manifest is empty; the checks below would be vacuous"
    assert len(names) == len(set(names)), "manifest repeats a tool name"
    return names


def test_committed_manifest_matches_the_generator():
    """`--check` exits non-zero when the committed file differs from generated."""
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"gen_mcp_manifest.py --check failed (rc={proc.returncode}); "
        f"re-run it. stdout: {proc.stdout.strip()} stderr: {proc.stderr.strip()}"
    )


def test_every_manifest_tool_is_registered_by_the_live_server():
    """The subset check that matters: manifest ⊆ registered."""
    pytest.importorskip("mcp", reason="the digiquant lane installs no mcp extra")

    names = set(_manifest_names())

    async def _registered() -> set[str]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = {**os.environ, "PYTHONPATH": str(ROOT / "digiquant" / "src")}
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "digiquant.mcp_server", "--stdio", "--scope", "full"],
            cwd=str(ROOT),
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                return {t.name for t in listed.tools}

    # The generator reads READ_SCOPE_TOOLS with ast; the live server applies it.
    registered = asyncio.run(_registered())
    assert registered, "live server registered no tools; the subset check would be vacuous"

    unrouted = sorted(names - registered)
    assert not unrouted, (
        f"{len(unrouted)} manifest tool(s) are not registered by the server: {unrouted}"
    )

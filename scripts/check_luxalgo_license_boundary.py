#!/usr/bin/env python3
"""Fail when LuxAlgo indicator Pine source can reach a paid surface (#4845).

The 9th hosted LuxAlgo MCP tool serves indicator source that is CC BY-NC-SA:
no source payload may be persisted (Chroma / Supabase / documents rows) or
rendered into paid digiquant surfaces (tearsheets, briefs, chat answers)
without a commercial Library license (``LUXALGO_COMMERCIAL_LICENSE``,
default OFF).

This is the CI-adjacent half of the guard (the other half is the unit test
``tests/dq/test_luxalgo_license_guard.py``). Both halves call
``digiquant.data.luxalgo.license_guard.run_boundary_checks``: exposure
violations across the live MCP / manifest / dispatcher surfaces plus the
repo-wide code-reference scan. Exit 0 when clean, 1 with violations listed.

The MCP surfaces are best-effort: without the ``mcp`` extra installed they
are skipped with a warning (the unit test pins them where the extra exists).
Everything else is strict.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.data.luxalgo.license_guard import (  # noqa: E402
    LUXALGO_COMMERCIAL_LICENSE_ENV,
    luxalgo_commercial_license_enabled,
    run_boundary_checks,
)


def _live_surfaces() -> dict[str, set[str]]:
    from digiquant.data.luxalgo.agent_tools import LUXALGO_DISPATCH, LUXALGO_TOOLS, RESEARCH_TOOLS
    from digiquant.data.luxalgo.entitlements import TOOL_ENTITLEMENTS
    from digiquant.orchestrator_tools import build_orchestrator_tool_manifest

    surfaces: dict[str, set[str]] = {
        "manifest": {tool["function"]["name"] for tool in build_orchestrator_tool_manifest()},
        "entitlements": set(TOOL_ENTITLEMENTS),
        "agent_schemas": {tool["function"]["name"] for tool in LUXALGO_TOOLS},
        "research_subset": set(RESEARCH_TOOLS),
        "dispatcher": set(LUXALGO_DISPATCH),
    }
    try:
        from digiquant.mcp_server import READ_SCOPE_TOOLS, create_mcp_server

        surfaces["mcp_full"] = {
            tool.name for tool in create_mcp_server(scope="full")._tool_manager.list_tools()
        }
        surfaces["mcp_read"] = {
            tool.name for tool in create_mcp_server(scope="read")._tool_manager.list_tools()
        }
        surfaces["read_scope"] = set(READ_SCOPE_TOOLS)
    except ImportError as exc:
        print(f"warning: MCP surfaces skipped ({exc})", file=sys.stderr)
    return surfaces


def main() -> int:
    commercial = luxalgo_commercial_license_enabled()
    print(
        f"commercial license flag ({LUXALGO_COMMERCIAL_LICENSE_ENV}): "
        f"{'ON' if commercial else 'OFF (default)'}"
    )
    violations = run_boundary_checks(ROOT, _live_surfaces(), commercial=commercial)
    if violations:
        print("luxalgo license boundary violations:")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("luxalgo license boundary OK")
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    raise SystemExit(main())

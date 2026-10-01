#!/usr/bin/env python3
"""Write the per-module endpoint, MCP-tool and version facts the landing prints.

The module mosaic sizes each tile by lines of code and states two more numbers
beside it: how many public HTTP endpoints the module serves, and how many MCP
tools it exposes. Neither existed as data before this script — `modules.ts`
carries a hand-authored sample of three or four paths, not a count — so the
tiles would have had to print nothing, or print a number someone typed.

Both are derivable from committed sources, so they are derived here and written
to `apps/digithings-web/lib/module-counts.json`, which is committed. The same
shape as `scripts/fetch_repo_activity.py` / `lib/repo-activity.json`: a
generated snapshot the app reads at build time, with a test that recomputes it
and fails on drift.

Sources:
  * endpoints — `docs/openapi/<service>.json`, the committed specs produced by
    `scripts/export_openapi.py` (`make openapi-export`). Counted as the number
    of entries under `paths`. A service with no spec has no count, not a zero.
  * mcp tools — the decorator sites in each module's server. Counted by regex
    over the source, so adding a tool with `@mcp.tool` moves the number without
    anyone remembering to edit a table.
  * versions — the version each module declares for itself: `version` in its
    `pyproject.toml`, or `version` in `apps/digichat/package.json`. This is the
    only honest per-module version source. The changelog in
    `packages/design/releases.json` tracks releases, and release-please only
    cuts them for digichat and digiskills, so a ledger built from it would list
    two modules and silently omit the rest.

Run from the repo root:

    python3 scripts/fetch_module_counts.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "apps" / "digithings-web" / "lib" / "module-counts.json"

# module id -> the file whose decorators are its MCP surface. The pattern is
# per-file because the two servers spell the decorator differently:
# `@mcp.tool()` on a plain FastMCP server, and `@_maybe_tool(...)` where the
# server builds its registry through a helper.
MCP_SOURCES: dict[str, tuple[str, str]] = {
    "digigraph": ("digigraph/src/digigraph/mcp_server.py", r"^\s*@mcp\.tool"),
    "digiquant": ("digiquant/src/digiquant/mcp_server.py", r"^\s*@_maybe_tool"),
    "digisearch": ("digisearch/src/digisearch/mcp_server.py", r"^\s*@mcp\.tool"),
    "digivault": ("digivault/src/digivault/tool_dispatch.py", r"^\s*@mcp\.tool"),
}

# module id -> the file that declares the module's own version. digichat is the
# one Node package (its version is bumped by release-please, so it runs ahead of
# the changelog tag); every other shipped module is Python and declares its
# version in pyproject.toml. digistore and digilink are roadmap and have no
# directory, so they have no version and are simply absent from the map.
VERSION_SOURCES: dict[str, str] = {
    "digigraph": "digigraph/pyproject.toml",
    "digiquant": "digiquant/pyproject.toml",
    "digisearch": "digisearch/pyproject.toml",
    "digichat": "apps/digichat/package.json",
    "digikey": "digikey/pyproject.toml",
    "digismith": "digismith/pyproject.toml",
    "digiclaw": "digiclaw/pyproject.toml",
    "digibase": "digibase/pyproject.toml",
    "digivault": "digivault/pyproject.toml",
    "digiskills": "digiskills/pyproject.toml",
}

# module id -> the OpenAPI spec stem under docs/openapi/. Only the services that
# publish a spec; digiclaw is a CLI, digibase is a library, and digistore and
# digilink are roadmap, so none of the four has one (docs/openapi/README.md).
SPEC_SOURCES: dict[str, str] = {
    "digigraph": "digigraph",
    "digiquant": "digiquant",
    "digisearch": "digisearch",
    "digichat": "digichat",
    "digikey": "digikey",
    "digismith": "digismith",
    "digivault": "digivault",
}


def endpoint_count(service: str) -> int | None:
    spec = REPO / "docs" / "openapi" / f"{service}.json"
    if not spec.is_file():
        return None
    with spec.open(encoding="utf-8") as fh:
        return len(json.load(fh).get("paths", {}))


def mcp_tool_count(module: str) -> int | None:
    entry = MCP_SOURCES.get(module)
    if entry is None:
        return None
    rel, pattern = entry
    path = REPO / rel
    if not path.is_file():
        return None
    matcher = re.compile(pattern)
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if matcher.match(line))


def module_version(module: str) -> str | None:
    rel = VERSION_SOURCES.get(module)
    if rel is None:
        return None
    path = REPO / rel
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if path.name == "package.json":
        return json.loads(text).get("version")
    match = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return match.group(1) if match else None


def main() -> int:
    modules: dict[str, dict[str, int]] = {}
    for module in sorted(set(SPEC_SOURCES) | set(MCP_SOURCES)):
        facts: dict[str, int] = {}
        service = SPEC_SOURCES.get(module)
        if service is not None:
            endpoints = endpoint_count(service)
            if endpoints is not None:
                facts["endpoints"] = endpoints
        tools = mcp_tool_count(module)
        if tools is not None:
            facts["mcpTools"] = tools
        if facts:
            modules[module] = facts

    versions: dict[str, str] = {}
    for module in sorted(VERSION_SOURCES):
        version = module_version(module)
        if version:
            versions[module] = version

    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpointSource": "docs/openapi/*.json (paths)",
        "mcpSource": "module MCP server decorator sites",
        "versionSource": "pyproject.toml / package.json declared version",
        "modules": modules,
        "versions": versions,
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} ({len(modules)} modules)")
    for module, facts in modules.items():
        print(f"  {module}: {facts}")
    for module, version in versions.items():
        print(f"  {module}: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

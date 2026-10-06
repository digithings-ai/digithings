# Design Note: MCP 2.x Migration Decision

**Issue:** DIG-1514  
**Author:** Architect  
**Date:** 2026-10-06  
**Status:** Decision recorded — stay on MCP 1.x with explicit documentation

---

## Summary

We pin `mcp<2` in four packages (`digigraph`, `digillm`, `digisearch`, `digivault`) because MCP 2.0 removed `mcp.server.fastmcp`, which our three live MCP servers import at module scope. Lifting the bound without migration causes a hard `ImportError` (see issues #1705, #1711).

**Decision:** Stay on MCP 1.x (currently 1.29.0) and document this explicitly. Do not migrate this week. Track migration as a separate spike.

---

## Evidence (Research Ladder — High Confidence)

| Source | Finding |
|--------|---------|
| Upstream releases (`modelcontextprotocol/python-sdk`) | v2.3.0 (2026-10-02), v2.2.0 (2026-09-07), v1.30.0 (2026-09-07), v2.0.0 (2026-07-28) |
| PyPI / `uv.lock` (develop `8de942f`) | We resolve to **mcp 1.29.0** — one release behind the 1.x tail |
| Official migration guide (`py.sdk.modelcontextprotocol.io/migration/`) | Rename-and-adjust, not a rewrite: `FastMCP` → `MCPServer` (import from `mcp.server`), `@mcp.tool()` unchanged, `McpError` → `MCPError`, new top-level `Client` |

**Interpretation (Medium confidence):** The 1.x line has had no release since 2026-09-07 while 2.x shipped v2.2.0 and v2.3.0. No upstream policy statement confirms 1.x maintenance; only the release record suggests a tail.

---

## Where We Are Exposed

| Package | Constraint | MCP Server | Import Location |
|---------|------------|------------|-----------------|
| `digigraph` | `mcp>=1.2,<2` (extra) | — | — |
| `digillm` | `mcp>=1.2,<2` (extra) | `digillm.mcp_server` | `from mcp.server.fastmcp import FastMCP` |
| `digisearch` | `mcp>=1.0,<2` (server extra) | `digisearch.mcp_server` | `from mcp.server.fastmcp import FastMCP` |
| `digivault` | `mcp>=1.0,<2` (service extra) | `digivault.mcp_server` | `from mcp.server.fastmcp import FastMCP` |

The `scripts/zammad_mcp` referenced in the issue does not exist in the repo.

---

## Migration Scope (If We Decide Later)

Per the official guide, the migration is a rename-and-adjust:

1. **Import change:** `from mcp.server.fastmcp import FastMCP` → `from mcp.server import MCPServer`
2. **Class rename:** `FastMCP` → `MCPServer` (decorator surface `@mcp.tool()`, `@mcp.resource()` unchanged)
3. **Error rename:** `McpError` → `MCPError`
4. **Client side:** New top-level `Client` from `mcp` (not used by our servers today)

Estimated breakage: 3 files (the three MCP servers), each a single import + class rename. No decorator or tool signature changes.

---

## Options Considered

| Option | Description | Cost | Recommendation |
|--------|-------------|------|----------------|
| **1. Stay on 1.x, document explicitly** | Record that we are deliberately on the 1.x tail with the verification date. Next reader does not rediscover this. | ~1 hour writing | ✅ **Chosen** — Cheap, buys time, no risk |
| 2. Spike migration on `rnd/` | Time-boxed spike to measure actual break count, then decide with data. | One focused session | Deferred — File a separate spike issue if needed |
| 3. Ignore it | Let it surface during an unrelated upgrade. | $0 now, high risk later | ❌ Not recommended — Failure mode is ImportError at worst moment |

---

## Decision

**We stay on MCP 1.x (`mcp>=1.2,<2` / `mcp>=1.0,<2`) with explicit documentation.**

- The upper bound remains in the four `pyproject.toml` files.
- This design note serves as the "say so out loud" record.
- Verification date: **2026-10-06** — confirmed on `uv.lock` at develop `8de942f` (mcp 1.29.0).
- When 1.x stops receiving fixes (or we need a 2.x feature), the migration path is documented above and is a rename-only change on three files.

---

## Follow-Up

- [ ] No immediate code changes required.
- [ ] If a future need arises (security fix only in 2.x, or new 2.x feature required), file a migration task referencing this note.
- [ ] The separate spike issue (if filed) should measure actual break count and verify the rename-only assumption.

---

## Confidence Labels

- **High:** Release facts, current version, migration guide content, our import locations.
- **Medium:** "1.x is in maintenance tail" — inferred from release cadence only; no upstream policy statement found.
- **Low:** Exact effort to migrate — not measured (that's what the spike is for).
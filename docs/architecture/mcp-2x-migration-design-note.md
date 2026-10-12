# Design Note: MCP 2.x Migration Decision

**Issue:** DIG-1514
**Author:** Architect
**First written:** 2026-10-06
**Revised:** 2026-10-07 (revision 2 — exposure counts corrected, see [Revision history](#revision-history))
**Status:** Decision recorded — stay on MCP 1.x with explicit documentation

---

## Summary

We pin `mcp<2` in **five** packages (`digigraph`, `digillm`, `digiquant`, `digisearch`, `digivault`) because MCP 2.0 removed `mcp.server.fastmcp`, which **six** tracked call sites import. Lifting the bound without a port fails — but not uniformly. Three sites are guarded and degrade; three are unguarded module-scope imports and hard-crash. See [Failure modes](#failure-modes-under-a-2x-upgrade).

**Decision:** Stay on MCP 1.x (currently 1.29.0) and document this explicitly. Do not migrate now. The migration path is written down below so a future decision is a rename, not an investigation.

The decision is unchanged from revision 1. Only the measured facts underneath it were wrong, and they were wrong **against** the decision — the real exposure is larger than revision 1 recorded, which strengthens the case for keeping the bound.

---

## Evidence

### Release record (Research Ladder — High confidence)

| Source | Finding |
|--------|---------|
| Upstream releases (`modelcontextprotocol/python-sdk`) | v2.3.0 (2026-10-02), v2.2.0 (2026-09-07), v1.30.0 (2026-09-07), v2.0.0 (2026-07-28) |
| PyPI / `uv.lock` | We resolve to **mcp 1.29.0** (`uv.lock` `name = "mcp"` / `version = "1.29.0"`) — one release behind the 1.x tail |
| Official migration guide (`py.sdk.modelcontextprotocol.io/migration/`) | Rename-and-adjust, not a rewrite: `FastMCP` → `MCPServer` (import from `mcp.server`), `@mcp.tool()` unchanged, `McpError` → `MCPError`, new top-level `Client` |

**Interpretation (Medium confidence):** the 1.x line has had no release since 2026-09-07 while 2.x shipped v2.2.0 and v2.3.0. No upstream policy statement confirms 1.x maintenance; only the release record suggests a tail. This is the one claim in this note that rests on inference.

---

## Where we are exposed

Every pin, verified by `git grep` on tracked files:

| Package | Pin | Location |
|---------|-----|----------|
| `digigraph` | `mcp>=1.2,<2` | `digigraph/pyproject.toml:39` |
| `digillm` | `mcp>=1.2,<2` | `digillm/pyproject.toml:26` |
| `digiquant` | `mcp>=1.2,<2` | `digiquant/pyproject.toml:98` |
| `digisearch` | `mcp>=1.0,<2` | `digisearch/pyproject.toml:38` |
| `digivault` | `mcp>=1.0,<2` | `digivault/pyproject.toml:29` |

Every import of the removed module, verified by `git grep` on tracked files:

| Call site | Guarded? | Behavior if `mcp 2.x` is installed |
|-----------|----------|------------------------------------|
| `digigraph/src/digigraph/mcp_server.py:198` | yes — `try:` / `except ImportError` → `_MCP_AVAILABLE = False` | degrades; MCP tools vanish, process stays up |
| `digillm/src/digillm/mcp_server.py:38` | yes — same shape | degrades |
| `digiquant/src/digiquant/mcp_server.py:469` | yes — same shape | degrades |
| `digisearch/src/digisearch/mcp_server.py:15` | **no** — module scope | **hard ImportError on import** |
| `digivault/src/digivault/mcp_server.py:16` | **no** — module scope | **hard ImportError on import** |
| `scripts/zammad_mcp/server.py:15` | **no** — module scope | **hard ImportError on import** |

---

## Failure modes under a 2.x upgrade

This is the part revision 1 got wrong, and it is the part that matters for planning.

The original issue argued the bound "is a hard ImportError without a migration." That is true of **three** of the six sites and false of the other three:

- **Guarded (digigraph, digillm, digiquant).** The `try/except ImportError` already exists, so a 2.x install turns `_MCP_AVAILABLE` to `False` and the module keeps importing. The failure is **silent capability loss** — MCP tools disappear and callers see an empty tool list, not a traceback. This is the worse failure mode in practice: it does not page anyone.
- **Unguarded (digisearch, digivault, scripts/zammad_mcp).** Module-scope import, so the process fails at import with a traceback. Loud, immediate, obvious in the logs.

Consequence for sequencing: a botched migration does not fail all-or-nothing. Half the surface degrades quietly and half crashes loudly. A migration that only fixes the crashing three would look successful in the deploy log while three services had quietly lost their MCP tools. Any port must assert `_MCP_AVAILABLE is True` per service, not just "the process starts."

---

## Migration scope (if we decide later)

Per the official guide this is a rename-and-adjust, not a rewrite:

1. **Import:** `from mcp.server.fastmcp import FastMCP` → `from mcp.server import MCPServer`
2. **Class:** `FastMCP` → `MCPServer`. The decorator surface (`@mcp.tool()`, `@mcp.resource()`) is unchanged.
3. **Error:** `McpError` → `MCPError`
4. **Client:** new top-level `Client` from `mcp` (unused by our servers today)

**Scope: six files, not three.** The decorator surface is untouched, so no tool signature changes. The one thing to plan for beyond the rename is the assertion in the previous section — the guarded sites will not tell you they broke.

---

## Options considered

| Option | Description | Cost | Verdict |
|--------|-------------|------|---------|
| **1. Stay on 1.x, document explicitly** | Record that we are deliberately on the 1.x tail with the verification date. | ~1 hour | **Chosen** — cheap, reversible, no risk |
| 2. Spike migration on `rnd/` | Time-boxed spike to measure break count, then decide with data. | One focused session | Deferred — the count is now measured; a spike would re-measure what this note records |
| 3. Ignore it | Let it surface during an unrelated upgrade. | $0 now, high risk later | Rejected — the failure mode is a silent capability loss in three services, which is worse than the loud ImportError the original issue predicted |

---

## Decision

**We stay on MCP 1.x with explicit documentation.**

- The upper bounds remain in the five `pyproject.toml` files.
- This note is the "say so out loud" record, so the next reader does not rediscover the cap as a surprise.
- **Re-verified 2026-10-07** at `uv.lock` `version = "1.29.0"`.
- Trigger to revisit: 1.x stops receiving fixes, or we need a 2.x-only feature. Either way the port is a six-file rename plus a per-service availability assertion.

---

## Known-wrong comments this decision now contradicts

Three places in the repo already describe this bound inaccurately. They are recorded here rather than fixed, because this note does not own code changes:

1. `renovate.json:51` — "which four packages import (digigraph, digiquant, digisearch, digivault)". Five packages pin the bound (`digillm` is missing) and six files import the module (`digillm` and `scripts/zammad_mcp` both missing). Tracked as a follow-up.
2. `digigraph/pyproject.toml:37` and `digiquant/pyproject.toml:93` — "which **both** MCP servers import". Neither package has two MCP servers; each has one, and the count that matters is six across the repo.
3. The wording "hard ImportError" — true of three sites, silent degradation of the other three. See [Failure modes](#failure-modes-under-a-2x-upgrade).

---

## Revision history

**Revision 2 (2026-10-07).** Revision 1 was written 2026-10-06 and reported: four pinned packages, three import sites, `scripts/zammad_mcp` "does not exist in the repo", and a uniform hard ImportError. Every one of those was checked against the tree and is wrong. Corrected counts: **five** pins, **six** import sites, `scripts/zammad_mcp` exists and is unguarded. Added the guarded/unguarded split, which changes the migration plan. Decision unchanged.

**Revision 1 (2026-10-06).** Initial note. Decision and migration path correct; exposure counts wrong.

---

## Confidence labels

- **High:** release facts; resolved version 1.29.0; the five pins; the six import sites; guarded/unguarded split; migration-guide content.
- **Medium:** "1.x is in maintenance tail" — inferred from release cadence only. No upstream policy statement found.
- **Low:** exact effort to migrate. The call-site count is measured; the work per call site is not.
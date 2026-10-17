import tools from "./_mcp-tools.json";
import type { McpTool } from "@/lib/mcp-demo";

/** Data for the MCP band. The tool list is the real registry, not a sample:
 *  `_mcp-tools.json` is generated from digiquant/src/digiquant/mcp_server.py by
 *  scripts/gen_mcp_manifest.py, and tests/dq/test_mcp_manifest_parity.py fails if it
 *  drifts from the server (one check against the generator, one against the live
 *  `tools/list`).
 *
 *  - The generator drops a tool in two independent ways. First, it never emits a name
 *    the server cannot register: refused by `digiquant.tool_refusals`, or held behind
 *    the Gloomberb session entitlement. That dropped 42 names on 2026-10-11. Second, it
 *    keeps only the tools an audit found to answer a real call, so the band never
 *    advertises a tool that refuses.
 *  - The audited list is a point-in-time snapshot taken 2026-10-11 with the network up.
 *    Re-run `gen_mcp_manifest.py --why` to refresh it; every drop reason is printed.
 *  - `--stdio` runs the server locally; `--scope read` registers only READ_SCOPE_TOOLS (the
 *    dashboard chat's list), `--scope full` (the default) registers every tool.
 *  - There is no hosted endpoint. Optimize results are in-sample; export writes a local
 *    file. Nothing trades. */

export const MCP_TOOLS = tools as McpTool[];

export const MCP_INSTALL_COMMAND = 'pip install "digiquant[nautilus,mcp]"';

export const MCP_COMMAND = "python -m digiquant.mcp_server --stdio --scope full";

export const MCP_READ_COUNT = MCP_TOOLS.filter((t) => t.scope === "read").length;

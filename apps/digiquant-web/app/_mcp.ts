import tools from "./_mcp-tools.json";
import type { McpTool } from "@/lib/mcp-demo";

/** Data for the MCP band. The tool list is the real registry, not a sample:
 *  `_mcp-tools.json` is generated from digiquant/src/digiquant/mcp_server.py by
 *  scripts/gen_mcp_manifest.py (and a test fails if it drifts from the server).
 *
 *  - `--stdio` runs the server locally; `--scope read` registers only READ_SCOPE_TOOLS (the
 *    dashboard chat's list), `--scope full` (the default) registers every tool.
 *  - There is no hosted endpoint. Optimize results are in-sample; export writes a local
 *    file. Nothing trades. */

export const MCP_TOOLS = tools as McpTool[];

export const MCP_INSTALL_COMMAND = 'pip install "digiquant[nautilus,mcp]"';

export const MCP_COMMAND = "python -m digiquant.mcp_server --stdio --scope full";

export const MCP_READ_COUNT = MCP_TOOLS.filter((t) => t.scope === "read").length;

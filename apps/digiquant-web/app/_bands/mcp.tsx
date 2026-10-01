import { McpCli } from "@/components/mcp/McpCli";
import { Band } from "../_chrome/Band";
import { MCP_TOOLS } from "../_mcp";

/** MCP tooling in digiquant, drawn as the terminal you would use it from: the server
 *  command and the full tool registry. Text only; nothing here is a live connection. */
export function McpBand() {
  return (
    <Band
      id="mcp"
      status="from the repo"
      title="The tools are MCP tools"
      takeaway={`Every capability in digiquant is a tool on one MCP server you run yourself: ${MCP_TOOLS.length} of them. The dashboard chat calls the read-scope tools; your own client can call all of them.`}
    >
      <McpCli />
    </Band>
  );
}

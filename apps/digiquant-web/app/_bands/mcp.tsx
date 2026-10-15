import { McpCli } from "@/components/mcp/McpCli";
import { Band } from "../_chrome/Band";
import { MCP_TOOLS } from "../_mcp";

/** MCP tooling in digiquant. One list of the audited registry. Execute calls the
 *  local gateway, which runs the tool on the digiquant MCP server. */
export function McpBand() {
  return (
    <Band
      id="mcp"
      fill
      title="The tools are MCP tools"
      takeaway={`Every capability in digiquant is a tool on one MCP server you run yourself: ${MCP_TOOLS.length} of them, in one list. Execute runs that call on the local gateway.`}
    >
      <McpCli />
    </Band>
  );
}

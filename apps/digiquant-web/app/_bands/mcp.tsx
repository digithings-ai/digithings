import { McpManifest } from "@/components/mcp/McpManifest";
import { Band } from "../_chrome/Band";
import { MCP_LEDGER, MCP_ROWS } from "../_mcp";

/** MCP tooling in digiquant: the tool groups the local server exposes, and what
 *  it does and does not expose. Text only; nothing here is a live connection. */
export function McpBand() {
  return (
    <Band
      id="mcp"
      status="from the repo"
      title="The tools are MCP tools"
      takeaway="Every capability in digiquant is a tool on one MCP server. The dashboard chat calls the read-scope tools; your own client can call all of them."
    >
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <McpManifest rows={MCP_ROWS} />
        <dl className="m-0 border border-hair text-left font-mono text-[0.72rem] leading-[1.55]">
          {MCP_LEDGER.map((row) => (
            <div key={row.key} className="border-b border-hair px-3 py-2 last:border-b-0">
              <dt className="text-ink-mute">[ {row.key} ]</dt>
              <dd className="m-0 mt-1 font-sans text-[0.8125rem] text-ink-soft">{row.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </Band>
  );
}

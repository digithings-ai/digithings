import type { ReactNode } from "react";
import { CopyCommand } from "@digithings/ui";
import { PricingStrip } from "../../components/start/pricing-strip";
import { Band } from "../_chrome/Band";

const REPO = "https://github.com/digithings-ai/digithings";
// Exact command from app/_mcp-transcript.json; flags verified against
// digiquant/src/digiquant/mcp_server.py (--stdio, --scope full|read).
const MCP_COMMAND = "python -m digiquant.mcp_server --stdio --scope read";

function Step({ n, label, children }: { n: string; label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-[0.7rem] border-b border-hair p-[1.3rem] text-left last:border-b-0 lg:border-b-0 lg:border-e lg:last:border-e-0">
      <p className="m-0 font-mono text-[0.68rem] leading-[1.5] text-ink-mute">
        [ {n} ] {label}
      </p>
      {children}
    </div>
  );
}

export function StartBand() {
  return (
    <Band id="start" title="Run it yourself" takeaway="digiquant is open core. Self-host it free, or have it run for you." status="open core">
      <>
        <div className="grid grid-cols-[minmax(0,1fr)] border border-hair lg:grid-cols-2">
          <Step n="01" label="clone">
            <CopyCommand
              samples={[{ label: "clone", protocol: "git clone", code: `git clone ${REPO}.git` }]}
              ariaLabel="Clone command"
              className="max-w-none"
            />
          </Step>
          <Step n="02" label="run the local MCP server (read scope)">
            <CopyCommand
              samples={[{ label: "stdio", protocol: "python -m", code: MCP_COMMAND }]}
              ariaLabel="Local MCP run command"
              className="max-w-none"
            />
          </Step>
        </div>
        <div className="mt-4">
          <PricingStrip />
        </div>
      </>
    </Band>
  );
}

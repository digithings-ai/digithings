import type { ReactNode } from "react";
import { CopyCommand } from "@digithings/ui";
import { PricingStrip } from "../../components/start/pricing-strip";
import { Band } from "../_chrome/Band";
import { MCP_COMMAND, MCP_INSTALL_COMMAND } from "../_mcp";

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
          <Step n="01" label="install digiquant">
            <CopyCommand
              samples={[{ label: "install", protocol: "pip", code: MCP_INSTALL_COMMAND }]}
              ariaLabel="Install command"
              className="max-w-none"
            />
          </Step>
          <Step n="02" label="then run the local MCP server">
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

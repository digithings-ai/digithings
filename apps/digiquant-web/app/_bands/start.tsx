import type { ReactNode } from "react";
import { CopyCommand } from "@digithings/ui";
import { PricingStrip } from "../../components/start/pricing-strip";
import { Band } from "../_chrome/Band";
import { MCP_COMMAND, MCP_INSTALL_COMMAND } from "../_mcp";

function Step({ n, label, children }: { n: string; label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col border-b border-hair text-left last:border-b-0 lg:border-b-0 lg:border-e lg:last:border-e-0">
      <p className="m-0 flex h-7 items-center border-b border-hair px-2.5 font-mono text-[0.6875rem] leading-none tracking-[0.04em] text-ink-mute">
        [ {n} ] {label}
      </p>
      <div className="p-2">{children}</div>
    </div>
  );
}

const COMMAND =
  "max-w-none [&_[role=tab]]:pb-1 [&_[role=tab]]:text-[0.68rem] [&_[role=tablist]]:gap-x-4 [&_.copy-cmd]:gap-3 [&_.copy-cmd]:px-3 [&_.copy-cmd]:py-2 [&_.copy-cmd]:text-[0.72rem]";

export function StartBand() {
  return (
    <Band id="start" title="Run it yourself" takeaway="digiquant is open core. Self-host it free, or have it run for you." status="open core">
      <>
        <div className="grid grid-cols-[minmax(0,1fr)] border border-hair lg:grid-cols-2">
          <Step n="01" label="install digiquant">
            <CopyCommand
              samples={[{ label: "install", protocol: "pip", code: MCP_INSTALL_COMMAND }]}
              ariaLabel="Install command"
              className={COMMAND}
            />
          </Step>
          <Step n="02" label="then run the local MCP server">
            <CopyCommand
              samples={[{ label: "stdio", protocol: "python -m", code: MCP_COMMAND }]}
              ariaLabel="Local MCP run command"
              className={COMMAND}
            />
          </Step>
        </div>
        <div className="mt-2">
          <PricingStrip />
        </div>
      </>
    </Band>
  );
}

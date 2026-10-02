import type { Metadata } from "next";
import { DeskFrame } from "@/components/desk/desk-frame";
import { GloomberbTerminal } from "@/components/desk/gloomberb-terminal";

export const metadata: Metadata = {
  title: "Terminal — digiquant",
  description: "The browser page for the terminal slot. No official read is registered for it.",
};

export default function ToolsTerminalPage() {
  return (
    <main id="main" className="h-[100svh]">
      <DeskFrame current="/tools/terminal">
        <GloomberbTerminal />
      </DeskFrame>
    </main>
  );
}

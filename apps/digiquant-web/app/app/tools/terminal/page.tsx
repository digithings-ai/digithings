import type { Metadata } from "next";
import { DeskFrame } from "@/components/desk/desk-frame";
import { EmptySlot } from "@/components/desk/empty-slot";

export const metadata: Metadata = {
  title: "Terminal — digiquant",
  description: "The browser page for the terminal slot. No official read is registered for it.",
};

export default function ToolsTerminalPage() {
  return (
    <main id="main" className="h-[100svh]">
      <DeskFrame current="/tools/terminal">
        <EmptySlot title="Terminal" />
      </DeskFrame>
    </main>
  );
}

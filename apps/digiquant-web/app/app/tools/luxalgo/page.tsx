import type { Metadata } from "next";
import { DeskFrame } from "@/components/desk/desk-frame";
import { EmptySlot } from "@/components/desk/empty-slot";

export const metadata: Metadata = {
  title: "LuxAlgo — digiquant",
  description: "The LuxAlgo slot. No official read is registered for it.",
};

export default function ToolsLuxAlgoPage() {
  return (
    <main id="main" className="h-[100svh]">
      <DeskFrame current="/tools/luxalgo">
        <EmptySlot title="LuxAlgo" />
      </DeskFrame>
    </main>
  );
}

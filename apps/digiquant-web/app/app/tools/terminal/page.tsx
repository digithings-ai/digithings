import type { Metadata } from "next";
import { GloomberbTerminal } from "@/components/desk/gloomberb-terminal";

export const metadata: Metadata = {
  title: "Terminal — digiquant",
  description: "The browser page for the terminal slot. No official read is registered for it.",
};

export default function ToolsTerminalPage() {
  return <GloomberbTerminal />;
}

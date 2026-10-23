import type { Metadata } from "next";
import { MCP_TOOLS } from "@/app/_mcp";
import { GloomberbTools } from "@/components/desk/gloomberb-tools";

export const metadata: Metadata = {
  title: "Gloomberb",
  description: "Gloomberb tools from the digiquant MCP registry. They are Gloomberb extensions.",
};

const GLOOMBERB_TOOLS = MCP_TOOLS.filter((tool) => tool.name.startsWith("gloomberb_")).map((tool) => tool.name);

export default function ToolsGloomberbPage() {
  return <GloomberbTools tools={GLOOMBERB_TOOLS} />;
}

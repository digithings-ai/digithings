import type { Metadata } from "next";
import { GloomberbTools } from "@/components/desk/gloomberb-tools";

export const metadata: Metadata = {
  title: "Gloomberb",
  description: "Gloomberb tools. They appear here when the Gloomberb migration is mounted.",
};

export default function ToolsGloomberbPage() {
  return <GloomberbTools />;
}

import type { Metadata } from "next";
import { VelaPane } from "@/components/desk/vela-pane";

export const metadata: Metadata = {
  title: "Vela — digiquant",
  description: "LuxAlgo Vela workspace. House bars at 15 minutes.",
};

export default function ToolsVelaPage() {
  return <VelaPane />;
}

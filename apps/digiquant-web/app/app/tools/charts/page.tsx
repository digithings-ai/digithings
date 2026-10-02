import type { Metadata } from "next";
import { DeskFrame } from "@/components/desk/desk-frame";
import { VelaPane } from "@/components/desk/vela-pane";

export const metadata: Metadata = {
  title: "LuxAlgo charts — digiquant",
  description: "LuxAlgo Vela workspace. Binance BTCUSDT at 15 minutes, with Coinbase registered.",
};

export default function ToolsChartsPage() {
  return (
    <main id="main" className="h-[100svh]">
      <DeskFrame current="/tools/charts">
        <VelaPane />
      </DeskFrame>
    </main>
  );
}

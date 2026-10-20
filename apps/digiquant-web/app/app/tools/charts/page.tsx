import type { Metadata } from "next";
import { VelaPane } from "@/components/desk/vela-pane";

export const metadata: Metadata = {
  title: "LuxAlgo charts — digiquant",
  description: "LuxAlgo Vela workspace. Binance BTCUSDT at 15 minutes, with Coinbase registered.",
};

export default function ToolsChartsPage() {
  return <VelaPane />;
}

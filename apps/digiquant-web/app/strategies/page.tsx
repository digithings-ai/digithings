import type { Metadata } from "next";
import { SiteNav } from "@/components/landing/SiteNav";
import { SiteFooter } from "@/components/landing/SiteFooter";
import { AmbientMesh } from "@/components/landing/AmbientMesh";
import { StrategyLibraryLive } from "@/components/tearsheet/strategy-library-live";

export const metadata: Metadata = {
  title: "Strategies — digiquant",
  description: "Backtest tearsheets for published digiquant strategies.",
};

export default function StrategiesPage() {
  return (
    <>
      <SiteNav />
      <main className="dq-subpage pb-[clamp(4.5rem,10vw,7rem)]">
        <AmbientMesh />
        <div className="wrap pb-[1.5rem]">
          <header className="dq-sechead">
            <div className="kicker">{"// strategies"}</div>
            <h1 className="dq-title">Strategy library</h1>
            <p className="dq-sub">
              Full tearsheets — equity, drawdown, trade log, and risk metrics. Each run is a
              Nautilus backtest on Coinbase daily OHLCV, refreshed when new bars land.
            </p>
          </header>

          <StrategyLibraryLive />
        </div>
      </main>
      <SiteFooter />
    </>
  );
}

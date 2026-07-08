import type { Metadata } from "next";
import { Footer } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "../_nav";
import { SiteNav } from "@/components/landing/SiteNav";
import { AmbientMesh } from "@/components/landing/AmbientMesh";
import { StrategyLibrary } from "@/components/tearsheet/strategy-library";
import { type StrategyIndexEntry } from "@/components/tearsheet/types";
import index from "@/public/strategies/index.json";

export const metadata: Metadata = {
  title: "Strategies — digiquant",
  description: "Backtest tearsheets for published digiquant strategies.",
};

const strategies = index as StrategyIndexEntry[];

export default function StrategiesPage() {
  return (
    <>
      <SiteNav />
      <main className="dq-subpage dq-subpage-library">
        <AmbientMesh />
        <div className="wrap">
          <header className="dq-sechead">
            <div className="dq-eyebrow">{"// strategies"}</div>
            <h1 className="dq-title">Strategy library</h1>
            <p className="dq-sub">
              Full tearsheets — equity, drawdown, trade log, and risk metrics. Each run is a
              Nautilus backtest on Coinbase daily OHLCV, refreshed when new bars land.
            </p>
          </header>

          <StrategyLibrary strategies={strategies} />
        </div>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}

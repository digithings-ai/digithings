import type { Metadata } from "next";
import { Footer } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "../_nav";
import { DqNav } from "@/components/landing/DqNav";
import { AmbientMesh } from "@/components/landing/AmbientMesh";
import { StrategyCard } from "@/components/tearsheet/strategy-card";
import { type StrategyIndexEntry } from "@/components/tearsheet/types";
import index from "@/public/strategies/index.json";

export const metadata: Metadata = {
  title: "Strategy Library — digiquant",
  description:
    "Backtest tearsheets for each registered digiquant strategy — equity, drawdown, and the full trade log.",
};

const strategies = index as StrategyIndexEntry[];

export default function StrategiesPage() {
  return (
    <>
      <DqNav />
      <main className="dq-subpage">
        <AmbientMesh />
        <div className="wrap">
          <header className="dq-sechead">
            <div className="dq-eyebrow">{"// strategy library"}</div>
            <h1 className="dq-title">Three base strategies, fully validated</h1>
            <p className="dq-sub">
              digiquant ships with three reference crypto strategies — one per major asset
              (BTC, ETH, SOL) — as starting points you can fork, re-optimize, and extend. Each is
              run through the backtest engine and rendered as an interactive
              tearsheet: equity, drawdown, the per-trade ledger, and the full trade log. These are
              <strong> in-sample validation</strong> runs from the 2018 optimization window; high
              single-run profit factors are an overfitting signal, not a forward guarantee.
              Walk-forward is the next step.
            </p>
          </header>

          <section className="ts-lib-grid" aria-label="Published strategies">
            {strategies.length === 0 ? (
              <p className="ts-status">No published strategies yet.</p>
            ) : (
              strategies.map((e) => <StrategyCard key={e.strategy} e={e} />)
            )}
          </section>
        </div>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}

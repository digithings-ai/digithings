import type { Metadata } from "next";
import { Nav, Footer } from "@digithings/web";
import { Brand, DQ_NAV, DQ_FOOTER, DQ_FOOTER_META } from "../_nav";
import { StrategyCard } from "@/components/tearsheet/strategy-card";
import { type StrategyIndexEntry } from "@/components/tearsheet/types";
import index from "@/public/strategies/index.json";

export const metadata: Metadata = {
  title: "Strategy Library — DigiQuant",
  description:
    "Pine-faithful validation tearsheets for each registered DigiQuant strategy — equity, drawdown, and the full trade log.",
};

const strategies = index as StrategyIndexEntry[];

export default function StrategiesPage() {
  return (
    <>
      <Nav brand={<Brand />} links={DQ_NAV} />
      <main className="ts-page">
        <div className="wrap">
          <header className="ts-lib-head">
            <span className="kicker">// strategy library</span>
            <h1 className="ts-h1">Three base strategies, fully validated</h1>
            <p className="ts-lib-lede">
              DigiQuant ships with three reference crypto strategies — one per major asset
              (BTC, ETH, SOL) — as starting points you can fork, re-optimize, and extend. Each is
              run through the Pine-faithful validation backtester and rendered as an interactive
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

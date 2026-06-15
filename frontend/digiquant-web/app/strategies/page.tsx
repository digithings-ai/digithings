import type { Metadata } from "next";
import { Nav, Footer, type NavLink } from "@digithings/web";
import { StrategyCard } from "@/components/tearsheet/strategy-card";
import { type StrategyIndexEntry } from "@/components/tearsheet/types";
import index from "@/public/strategies/index.json";

export const metadata: Metadata = {
  title: "Strategy Library — DigiQuant",
  description:
    "Pine-faithful validation tearsheets for each registered DigiQuant strategy — equity, drawdown, and the full trade log.",
};

const NAV: NavLink[] = [
  { label: "Pipeline", href: "/pipeline" },
  { label: "Strategies", href: "/strategies" },
  { label: "Atlas", href: "/subsystems/atlas" },
  { label: "Pricing", href: "/#pricing" },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
  { label: "Open Olympus", href: "/olympus/", cta: true },
];
const Brand = () => (<><span className="dq-glyph" aria-hidden="true" /><span className="brand-word">digiquant</span></>);

const strategies = index as StrategyIndexEntry[];

export default function StrategiesPage() {
  return (
    <>
      <Nav brand={<Brand />} links={NAV} />
      <main className="ts-page">
        <div className="wrap">
          <header className="ts-lib-head">
            <span className="kicker">// strategy library</span>
            <h1 className="ts-h1">Validation tearsheets</h1>
            <p className="ts-lib-lede">
              Each strategy in the DigiQuant registry, run through the Pine-faithful validation
              backtester and rendered as an interactive tearsheet — equity, drawdown, and the full
              trade log. These are <strong>in-sample validation</strong> runs from the 2018
              optimization window; high single-run profit factors are an overfitting signal, not a
              forward guarantee. Walk-forward is the next step.
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
      <Footer
        links={[
          { label: "Pipeline", href: "/pipeline" },
          { label: "Olympus", href: "/olympus/" },
          { label: "digithings.ai", href: "https://digithings.ai", external: true },
          { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
        ]}
        meta="© 2026 digithings AI · open core"
      />
    </>
  );
}

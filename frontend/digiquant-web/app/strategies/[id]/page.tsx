import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Nav, Footer } from "@digithings/web";
import { Brand, DQ_NAV } from "../../_nav";
import { TearsheetView } from "@/components/tearsheet/tearsheet-view";
import { type StrategyIndexEntry } from "@/components/tearsheet/types";
import index from "@/public/strategies/index.json";

const strategies = index as StrategyIndexEntry[];

export const dynamicParams = false;
export function generateStaticParams() {
  return strategies.map((s) => ({ id: s.strategy }));
}
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const s = strategies.find((e) => e.strategy === id);
  return s
    ? { title: `${s.strategy} · ${s.symbol} — DigiQuant tearsheet`, description: `Pine-faithful validation tearsheet for ${s.strategy} (${s.symbol}) — equity, drawdown, and per-trade analytics.` }
    : { title: "Strategy Tearsheet — DigiQuant" };
}

export default async function TearsheetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!strategies.some((e) => e.strategy === id)) notFound();

  return (
    <>
      <Nav brand={<Brand />} links={DQ_NAV} />
      <main className="ts-page">
        <div className="wrap">
          <TearsheetView slug={id} />
        </div>
      </main>
      <Footer
        links={[
          { label: "Strategies", href: "/strategies" },
          { label: "Pipeline", href: "/pipeline" },
          { label: "Olympus", href: "/olympus/" },
          { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
        ]}
        meta="© 2026 digithings AI · validation tearsheet · illustrative, in-sample"
      />
    </>
  );
}

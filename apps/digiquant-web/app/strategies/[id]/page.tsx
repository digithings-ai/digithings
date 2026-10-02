import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { strategyDisplayName } from "@/components/tearsheet/strategy-names";
import { TearsheetView } from "@/components/tearsheet/tearsheet-view";
import { PUBLISHED_STRATEGIES } from "@/components/tearsheet/published";

const PUBLISHED = Object.fromEntries(PUBLISHED_STRATEGIES.map((s) => [s.id, s]));

export const dynamicParams = false;
export function generateStaticParams() {
  return PUBLISHED_STRATEGIES.map((s) => ({ id: s.id }));
}
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const s = PUBLISHED[id];
  const name = s ? strategyDisplayName(id, s.label) : id;
  if (!s) return { title: "Strategy Tearsheet — digiquant" };
  const dca = id.includes("sdca");
  return {
    title: `${name} · ${s.symbol} — digiquant tearsheet`,
    description: dca
      ? `Backtest tearsheet for ${name} (${s.symbol}) — remaining-book SDCA on a composite valuation index. Illustrative backtest; not a live strategy.`
      : `Backtest tearsheet for ${name} (${s.symbol}) — equity, drawdown, and per-trade analytics.`,
  };
}

export default async function TearsheetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!(id in PUBLISHED)) notFound();
  return (
    <main id="main" tabIndex={-1}>
      <TearsheetView slug={id} />
    </main>
  );
}

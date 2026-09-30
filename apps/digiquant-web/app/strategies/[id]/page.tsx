import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DocumentFrame, PageTitle } from "@digithings/ui";
import { strategyDisplayName } from "@/components/tearsheet/strategy-names";

// Static export needs the route list (and per-route metadata) at build time,
// while the tearsheet DATA is read live from Supabase (#1069). The published set
// is the three Slappers plus btc_sdca (DCA). Slugs stay code ids; public names
// are asset-then-type.
const PUBLISHED: Record<string, { label: string; symbol: string }> = {
  btc_slapper: { label: "BTC L/S", symbol: "BTC-USD" },
  eth_slapper: { label: "ETH L/S", symbol: "ETH-USD" },
  sol_slapper: { label: "SOL L/S", symbol: "SOL-USD" },
  btc_sdca: { label: "BTC-SDCA", symbol: "BTC-USD" },
};

export const dynamicParams = false;
export function generateStaticParams() {
  return Object.keys(PUBLISHED).map((id) => ({ id }));
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
      ? `Backtest tearsheet for ${name} (${s.symbol}) — remaining-book SDCA on a composite valuation index. Illustrative Nautilus backtest; not a live strategy.`
      : `Backtest tearsheet for ${name} (${s.symbol}) — equity, drawdown, and per-trade analytics.`,
  };
}

export default async function TearsheetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!(id in PUBLISHED)) notFound();

  return (
    <main id="main" tabIndex={-1}>
      <DocumentFrame>
        <PageTitle title={strategyDisplayName(id, PUBLISHED[id].label)}>placeholder</PageTitle>
      </DocumentFrame>
    </main>
  );
}

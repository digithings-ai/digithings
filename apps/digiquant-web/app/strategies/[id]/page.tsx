import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Footer } from "@digithings/ui";
import { DQ_FOOTER } from "../../_nav";
import { SiteNav } from "@/components/landing/SiteNav";
import { TearsheetView } from "@/components/tearsheet/tearsheet-view";
import { strategyDisplayName } from "@/components/tearsheet/strategy-names";

// Static export needs the route list (and per-route metadata) at build time,
// while the tearsheet DATA is read live from Supabase inside <TearsheetView/>.
// The published set is the three Slappers plus btc_sdca (DCA). Keep the
// slug→label/symbol map here so the build never depends on the live store (#1069).
// Route slugs stay code ids (`btc_sdca`, `*_slapper`); public names are asset-then-type.
const PUBLISHED: Record<string, { label: string; symbol: string }> = {
  btc_slapper: { label: "BTC L/S", symbol: "BTC-USD" },
  eth_slapper: { label: "ETH L/S", symbol: "ETH-USD" },
  sol_slapper: { label: "SOL L/S", symbol: "SOL-USD" },
  btc_sdca: { label: "BTC-SDCA", symbol: "BTC-USD" },
  // TEMPORARY local-preview only (gold v3 proof tearsheet, #4804). REVERT BEFORE ANY MERGE.
  gold_sdca: { label: "GLD-SDCA (v3 proof)", symbol: "GLD-USD" },
  // TEMPORARY local-preview only (gold v4 no-trend diagnostic, #4804). REVERT BEFORE ANY MERGE.
  gold_sdca_v4: { label: "GLD-SDCA (v4 diagnostic)", symbol: "GLD-USD" },
  // TEMPORARY local-preview only (gold v5 secular diagnostic, #4804). REVERT BEFORE ANY MERGE.
  gold_sdca_v5: { label: "GLD-SDCA (v5 diagnostic)", symbol: "GLD-USD" },
  // TEMPORARY local-preview only (gold reselect diagnostic, #4804 Plan 16). REVERT BEFORE ANY MERGE.
  gold_sdca_v6_reselect: { label: "GLD-SDCA (reselect diagnostic)", symbol: "GLD-USD" },
  // TEMPORARY local-preview only (gold reselect LIVE-PROOF Nautilus run, #4804 Plan 17 Ruling 6). REVERT BEFORE ANY MERGE.
  gold_sdca_reselect_live: { label: "GLD-SDCA (reselect live proof)", symbol: "GLD-USD" },
  // TEMPORARY local-preview only (gold Plan-19 indicator-fit pass list — anchor only, #4804). REVERT BEFORE ANY MERGE.
  gold_sdca_indicator_fit: { label: "GLD-SDCA (indicator-fit pass list)", symbol: "GLD-USD" },
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
    <>
      <SiteNav />
      <main className="ts-page dq-subpage">
        <div className="wrap">
          <TearsheetView key={id} slug={id} />
        </div>
      </main>
      {/* Shared links so the footer can't drift from the rest of the site;
          tearsheet-specific meta is the one intentional per-page override. */}
      <Footer links={DQ_FOOTER} meta="© 2026 digithings AI · backtest · illustrative, in-sample" />
    </>
  );
}

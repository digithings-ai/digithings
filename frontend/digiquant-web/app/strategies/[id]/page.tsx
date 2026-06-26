import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Footer } from "@digithings/web";
import { DQ_FOOTER } from "../../_nav";
import { DqNav } from "@/components/landing/DqNav";
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
    ? { title: `${s.strategy} · ${s.symbol} — digiquant tearsheet`, description: `Backtest tearsheet for ${s.strategy} (${s.symbol}) — equity, drawdown, and per-trade analytics.` }
    : { title: "Strategy Tearsheet — digiquant" };
}

export default async function TearsheetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!strategies.some((e) => e.strategy === id)) notFound();

  return (
    <>
      <DqNav />
      <main className="ts-page dq-subpage">
        <div className="wrap">
          <TearsheetView slug={id} />
        </div>
      </main>
      {/* Shared links so the footer can't drift from the rest of the site;
          tearsheet-specific meta is the one intentional per-page override. */}
      <Footer links={DQ_FOOTER} meta="© 2026 digithings AI · backtest · illustrative, in-sample" />
    </>
  );
}

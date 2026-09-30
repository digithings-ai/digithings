"use client";
/** Live research-book island for the home page. Reads the same public seam the
 *  dashboard uses (useLivePortfolio) and hands it to BookView, which renders it
 *  with kit parts on the instrument-panel frame. With no feed configured, or
 *  before the first fetch settles, BookView shows framed axes and a labelled
 *  empty state and no numbers. Static export prerenders that state, so server
 *  HTML and the first client render agree. */
import { useMemo } from "react";
import { BookView } from "@/components/dashboard/book-view";
import { currentNavRun } from "@/lib/live/nav-seam";
import { useLivePortfolio } from "@/lib/live/useLivePortfolio";

export function PortfolioIsland() {
  const live = useLivePortfolio();
  const series = useMemo(
    () => currentNavRun(live.nav).map((n) => ({ time: n.date, value: n.nav })),
    [live.nav],
  );

  if (live.loading) return <BookView state="loading" />;
  if (!live.configured || series.length === 0 || !live.kpis) return <BookView state="empty" />;

  const k = live.kpis;
  return (
    <BookView
      state="live"
      asOf={live.metricsAsOf}
      windowStart={k.sinceInceptionStartDate}
      windowEnd={k.priceAsOfDate ?? k.bookNavDate}
      benchmark={k.benchmarkReturnPct != null ? k.benchmarkTicker : null}
      sinceInceptionPct={k.portfolioReturnPct ?? k.sinceInceptionPct}
      benchmarkPct={k.benchmarkReturnPct}
      excessPct={k.excessReturnPct}
      dayPct={k.dayReturnPct}
      positions={live.positions.length}
      series={series}
    />
  );
}

"use client";
/** Live research-book island for the home page. Reads the same public seam the
 *  dashboard uses (useLivePortfolio) and renders it with kit parts only. With
 *  no feed configured, or before the first fetch settles, it shows a labeled
 *  empty state and no numbers — static export prerenders the loading state so
 *  server HTML and the first client render agree. */
import { useMemo } from "react";
import { EquityCurve, Kpi, KpiStrip, LiveBadge, fmtNum, fmtPct } from "@digithings/ui";
import { currentNavRun } from "@/lib/live/nav-seam";
import { useLivePortfolio } from "@/lib/live/useLivePortfolio";

export function PortfolioIsland() {
  const live = useLivePortfolio();
  const series = useMemo(
    () => currentNavRun(live.nav).map((n) => ({ time: n.date, value: n.nav })),
    [live.nav],
  );

  if (live.loading) {
    return <p className="m-0 text-ink-mute">Loading the research book…</p>;
  }
  if (!live.configured || series.length === 0) {
    return (
      <p className="m-0 text-ink-mute">
        Live feed not connected in this build — no figures shown rather than placeholder ones.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-[1.2rem]">
      <div className="flex flex-wrap items-center gap-[0.8rem]">
        <LiveBadge label="research book" ariaLabel="Live research book, paper portfolio" />
        {live.metricsAsOf ? <span className="text-ink-mute">as of {live.metricsAsOf}</span> : null}
      </div>
      <KpiStrip ariaLabel="Research book summary">
        <Kpi label="NAV" value={fmtNum(live.liveTotalValue, 2)} />
        <Kpi label="vs mark" value={fmtPct(live.liveVsMarkPct)} />
        <Kpi label="Positions" value={fmtNum(live.positions.length)} />
      </KpiStrip>
      <div className="h-[18rem]">
        <EquityCurve data={series} label="Research book NAV" />
      </div>
    </div>
  );
}

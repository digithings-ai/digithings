"use client";
/** The paper book as an instrument panel: a hairline frame with a bracketed
 *  header row, a KPI strip, and the NAV curve on a framed plot. Purely
 *  presentational; PortfolioIsland feeds it from the live seam.
 *
 *  Three states, one frame:
 *   - loading  the feed is configured and the first read has not settled
 *   - empty    no feed in this build, or it returned no NAV: framed axes with
 *              no data and a plain label, never a placeholder figure
 *   - live     real NAV series and the KPIs computed from it
 *
 *  Every return figure names its benchmark, its window and "paper". */
import { EquityCurve, EASE, Kpi, KpiStrip, LiveBadge, fmtNum, fmtPct, m, toneClass, useMotionSafe } from "@digithings/ui";
import { Badge } from "@digithings/ui/ui";
import { CountUp } from "./count-up";

export type BookSeriesPoint = { time: string; value: number };

export type BookViewProps = {
  state: "loading" | "empty" | "live";
  asOf?: string | null;
  windowStart?: string | null;
  windowEnd?: string | null;
  benchmark?: string | null;
  sinceInceptionPct?: number | null;
  benchmarkPct?: number | null;
  excessPct?: number | null;
  dayPct?: number | null;
  positions?: number;
  series?: BookSeriesPoint[];
};

const signedPct = (n: number) => `${n > 0 ? "+" : ""}${fmtPct(n)}`;

function Figure({ value, format }: { value: number | null | undefined; format: (n: number) => string }) {
  if (value == null) return <span className="text-ink-mute">n/a</span>;
  return <CountUp value={value} format={format} className={toneClass(value)} />;
}

/** The plot frame: corner ticks, a hairline grid, and the axes' own labels. */
function PlotFrame({ children, startLabel, endLabel }: { children: React.ReactNode; startLabel: string; endLabel: string }) {
  return (
    <div className="border border-hair bg-surface-2">
      <div className="relative h-[16rem] sm:h-[18rem]">
        <div
          aria-hidden="true"
          className="absolute inset-0 opacity-40 [background-image:linear-gradient(var(--hair)_1px,transparent_1px),linear-gradient(90deg,var(--hair)_1px,transparent_1px)] [background-size:3rem_3rem]"
        />
        {children}
      </div>
      <div className="flex justify-between border-t border-hair px-3 py-1.5 text-[0.62rem] tracking-[0.06em] text-ink-mute">
        <span>{startLabel}</span>
        <span>{endLabel}</span>
      </div>
    </div>
  );
}

function EmptyPlot({ loading }: { loading: boolean }) {
  const safe = useMotionSafe();
  return (
    <PlotFrame startLabel="start: --" endLabel="as of: --">
      <div aria-hidden="true" className="absolute inset-y-3 start-2 flex flex-col justify-between text-[0.6rem] text-ink-mute">
        <span>--</span>
        <span>--</span>
        <span>--</span>
      </div>
      <m.div
        aria-hidden="true"
        className="absolute inset-x-10 top-[72%] origin-left border-t border-dashed border-ink-soft"
        initial={safe ? { scaleX: 0 } : false}
        whileInView={{ scaleX: 1 }}
        viewport={{ once: true, amount: 0.5 }}
        transition={{ duration: 1.2, ease: EASE }}
      />
      <div className="absolute inset-0 grid place-content-center justify-items-center gap-2 px-4 text-center">
        <span className="border border-hair bg-surface px-3 py-1 text-[0.72rem] tracking-[0.06em] text-ink-soft">
          {loading ? "[ reading the paper book ]" : "[ live feed not connected in this build ]"}
        </span>
        <span className="max-w-[34ch] text-[0.68rem] leading-[1.5] text-ink-mute">
          {loading ? "no figures until the first read settles" : "no figures shown rather than placeholder ones"}
          <span aria-hidden="true" className="ms-1 motion-safe:animate-pulse">
            ▌
          </span>
        </span>
      </div>
    </PlotFrame>
  );
}

function LivePlot({ series, startLabel, endLabel }: { series: BookSeriesPoint[]; startLabel: string; endLabel: string }) {
  const safe = useMotionSafe();
  return (
    <PlotFrame startLabel={startLabel} endLabel={endLabel}>
      <div className="absolute inset-0 px-1 py-2">
        <EquityCurve data={series} label="Paper book NAV index over the window, not money" />
      </div>
      {safe ? (
        <m.div
          aria-hidden="true"
          className="absolute inset-0 origin-right bg-surface-2"
          initial={{ scaleX: 1 }}
          whileInView={{ scaleX: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 1.5, ease: EASE, delay: 0.15 }}
        />
      ) : null}
    </PlotFrame>
  );
}

export function BookView(p: BookViewProps) {
  const live = p.state === "live";
  const bench = p.benchmark ?? null;
  const window =
    p.windowStart && p.windowEnd ? `${p.windowStart} to ${p.windowEnd}` : p.windowStart ? `since ${p.windowStart}` : null;
  const paperWindow = window ? `paper · ${window}` : "paper";
  const against = bench ? `vs ${bench}` : "benchmark n/a";

  return (
    <div className="border border-hair bg-surface font-mono text-left" data-state={p.state}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-hair px-3 py-2 text-[0.68rem] tracking-[0.04em] text-ink-mute">
        <span>~/digiquant/book</span>
        <Badge variant="neutral">paper, not money</Badge>
        {live ? <LiveBadge label="research book" ariaLabel="Live research book, paper portfolio" /> : null}
        {live ? <span>{fmtNum(p.positions ?? 0)} positions</span> : null}
        <span className="ms-auto text-ink-soft">
          {live ? (p.asOf ? `as of ${p.asOf}` : "as-of date not reported") : "as of: no data"}
        </span>
      </div>

      <div className="px-3 pt-3">
        <KpiStrip
          ariaLabel="Paper book summary"
          className="[grid-template-columns:repeat(2,minmax(0,1fr))] min-[900px]:[grid-template-columns:repeat(4,minmax(0,1fr))]"
        >
          <Kpi
            label="Since inception"
            value={live ? <Figure value={p.sinceInceptionPct} format={signedPct} /> : <span className="text-ink-mute">--</span>}
            sub={live ? `${against} · ${paperWindow}` : "paper · no window yet"}
          />
          <Kpi
            label={bench ? `${bench}, same window` : "Benchmark"}
            value={live ? <Figure value={p.benchmarkPct} format={signedPct} /> : <span className="text-ink-mute">--</span>}
            sub={live ? (bench ? `buy and hold · ${window ?? "window n/a"}` : "benchmark feed not connected") : "no benchmark yet"}
          />
          <Kpi
            label="Excess return"
            value={live ? <Figure value={p.excessPct} format={signedPct} /> : <span className="text-ink-mute">--</span>}
            sub={live ? `book minus ${bench ?? "benchmark"} · ${paperWindow}` : "book minus benchmark"}
          />
          <Kpi
            label="Day return"
            value={live ? <Figure value={p.dayPct} format={signedPct} /> : <span className="text-ink-mute">--</span>}
            sub={live ? "1 day · paper · vs prior NAV" : "1 day · paper"}
          />
        </KpiStrip>
      </div>

      <div className="px-3 pb-3">
        {live && p.series && p.series.length > 0 ? (
          <LivePlot
            series={p.series}
            startLabel={`start: ${p.windowStart ?? p.series[0].time}`}
            endLabel={`as of: ${p.asOf ?? p.series[p.series.length - 1].time}`}
          />
        ) : (
          <EmptyPlot loading={p.state === "loading"} />
        )}
      </div>

      <div className="border-t border-hair px-3 py-2 text-[0.66rem] leading-[1.5] text-ink-mute">
        {live
          ? `Paper NAV index${bench ? `, benchmark ${bench}` : ""}${window ? `, window ${window}` : ""}. A research portfolio with no real money in it; not a performance claim.`
          : "A research portfolio, not money. The live feed is not connected in this build."}
      </div>
    </div>
  );
}

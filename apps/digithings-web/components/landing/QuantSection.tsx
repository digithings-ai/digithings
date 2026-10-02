"use client";

import { useState } from "react";
import {
  CardRail,
  LOOKBACK_OPTIONS,
  MultiTimeSeries,
  SegToggle,
  TearsheetCard,
  TearsheetCardKpi,
  TearsheetCardKpis,
  fmtCompact,
  matchLookbackPreset,
  sliceByView,
  viewWindowForPreset,
  type LookbackPreset,
  type OverlaySeries,
  type TearsheetSeriesPoint,
  type ViewWindow,
} from "@digithings/ui";
import { cagrPct } from "@/lib/live/portfolio";
import { useOfficialBand, type OfficialBandRead } from "@/lib/live/useOfficialBand";
import type { NavPoint, PricePoint, TearsheetCardRead } from "@/lib/live/officialBand";
import { GROUPED_LABEL } from "./label";
import { windowAlpha, windowBeta } from "@/lib/bookMath";
import { QuantWordmark } from "./QuantWordmark";
import { PIPELINE_ENGINES } from "@/lib/digiquantPipeline";

/**
 * The digiquant band (v15 point 9, #4429; reworked across rounds 3–5).
 *
 * The owner's round-5 direction, which this composition follows: "the finance
 * section, the start at the very top we have the ticker tape and then below the
 * next one we show that we have the performance, portfolio at a glance, we show
 * ... just the performance metrics with the chart of the portfolio nav or the
 * portfolio percent return" with "time controls to show the last week the last
 * month the last three months year to date one year five year full history",
 * and "i wouldn't show the positions here ... you'd have to visit digiquant";
 * and on the pipeline: "i actually prefer the pipeline from variant A, keep it
 * simple" — the six dashboard stages as one thin row rather than the kit's
 * detail-panel flow; and on the cards: "use the library cards for each of the
 * strategies don't put the live indicator though just show the library cards and
 * put them all in a horizontal scrollable pane" — the kit's `CardRail`, promoted
 * from the design reference's changelog rail.
 *
 * So the band reads, top to bottom: the digiquant.io brand header with the two
 * ways into the product (the dashboard and the tearsheets); the title with the
 * strategy library rail beside it and the MCP tooling line under it; the
 * pipeline as one horizontal rail of the real phase-folder cards; the book
 * (portfolio against benchmark, with the lookback controls, the chart
 * compressed and the window's three reads beside it). No positions blotter — that surface belongs to digiquant.io — and no lead
 * paragraph or closing footnote: the owner asked for the title on its own,
 * "simple and clean".
 *
 * Round 6 changed the order and dropped the market tape. The owner: "i'd remove
 * markets latest close at the top ... i'd show digiquant.io at the very top with
 * the digiquant colors and branding ... put the pipeline above the chart ...
 * i'd put the metrics to the right or the left side of the chart, compress the
 * chart to show the metrics ... keep it at three metrics ... we need to show the
 * relative performance over the period selected in the chart". So the tape is
 * gone and the three reads are the window's own returns.
 *
 * Round 7 took the section apart again. The owner: "I removed that DigiQuant bar
 * logo. I don't want to maintain that. I don't want any logos for any sections."
 * — so the brand header row is gone, and with it the "research tooling · 78 MCP
 * tools" line ("Remove what you put below it. Research tooling, the MCP count.").
 * The space beside the title now carries the two ways into the product instead:
 * "Put the buttons there to open the dashboard with the DigiQuant dashboard logo.
 * And then tier sheets as another button below it. That's what could fill up that
 * space and it could be aligned properly." The strategy-library kicker is gone
 * ("Remove the strategy library title. Just have the slide in menu."), the
 * metrics column lost its panel ("The performance metrics shouldn't have a
 * background ... a cleaner way of showing these with no background and more
 * simplistic styling"), the chart is pinned to the metrics' height, and the
 * section's own watermark is the *dashboard* mark, animated — "the cool effect
 * would be if we place the DigiQuant dashboard logo behind this DigiQuant section
 * and have it animated. A bit faded and animated."
 *
 * Brand (#4900, digiquant.io's solid-black craft). The band wears no livery of
 * its own: no teal accent scope, no tinted gradient, no animated dashboard-mark
 * watermark. It sits on the page's own canvas between hairline rails like every
 * other band, in the page's Inter + JetBrains Mono, with ink as the only accent
 * (the chart's "accent" tone resolves to ink here). The one brand element is the
 * digiquant pixel wordmark from digiquant.io, which is also the link to it.
 *
 * HONESTY (binding). Figures come from the official digiquant API
 * (`GET /performance`, `GET /benchmarks`, `GET /strategies`,
 * `GET /strategies/default/performance`). A stub envelope, a withheld read, or
 * a missing field renders an em dash. This band does not draw an example book.
 */

const DIGIQUANT_URL = "https://digiquant.io";

/**
 * The pipeline, in the dashboard's own phase folders.
 *
 * Real phase-folder cards from `apps/digiquant-web/.../PipelineScene.tsx`
 * (via the `digiquantPipeline.ts` copy): research preflight → publish (10) and
 * portfolio thesis review → commit run (9), with execution honestly marked "in
 * development" — routing is off by default and no live venue is wired, so the
 * band shows the stage and says so rather than drawing folders that do not
 * exist. Same card grammar as the digiquant site's `dqp-step`: mono folder id,
 * phase name, one-line mechanism; hairline border on the page surface; ink
 * only, no module livery. One horizontal rail with engine divider chips, so
 * the band stays at a readable height instead of growing a detail panel.
 */
function PipelineRail() {
  return (
    <div
      className="flex min-w-0 snap-x snap-proximity gap-[0.5rem] overflow-x-auto pb-[0.2rem]"
      role="list"
      aria-label="digiquant pipeline phases"
      /* The rail is far wider than the viewport, so it is the only way through
         the phases. Focusable, or keyboard readers lose 16 of the 19. Same
         contract as the kit CardRail track. */
      tabIndex={0}
    >
      {PIPELINE_ENGINES.map((engine) => (
        <div
          key={engine.id}
          role="listitem"
          aria-label={engine.label}
          className="flex shrink-0 items-stretch gap-[0.5rem]"
        >
          <span
            aria-hidden="true"
            className="flex items-center font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
          >
            {engine.label}
          </span>
          {engine.phases.map((phase) => (
            <div
              key={phase.id}
              title={`Phase folder ${phase.id}`}
              className="flex w-[10.5rem] shrink-0 snap-start flex-col gap-[0.2rem] border border-hair bg-surface p-[0.6rem]"
            >
              <span className="font-mono text-[0.6rem] tracking-[0.06em] text-ink-mute">
                {phase.id}
              </span>
              <span className="font-mono text-[0.78rem] text-ink">{phase.name}</span>
              <span className="text-[0.7rem] leading-[1.45] text-ink-mute">{phase.detail}</span>
            </div>
          ))}
          {engine.phases.length === 0 ? (
            <div
              className="flex w-[10.5rem] shrink-0 snap-start flex-col gap-[0.2rem] border border-dashed border-hair bg-surface p-[0.6rem]"
            >
              <span className="font-mono text-[0.6rem] uppercase tracking-[0.06em] text-ink-mute">
                in development
              </span>
              <span className="text-[0.7rem] leading-[1.45] text-ink-mute">
                Research and portfolio run today. Live execution is next.
              </span>
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

/** The card shape the rail renders. Every value is an API field or an em dash. */
type StrategyCardData = {
  slug: string;
  name: string;
  symbol: string;
  kind: string;
  kpis: { label: string; value: string }[];
};

function fmtPctValue(value: number | null): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(1)}%`;
}

function isDcaCard(read: TearsheetCardRead): boolean {
  if (read.kind && /accumul|dca/i.test(read.kind)) return true;
  return /sdca|dca/.test(read.id);
}

/**
 * The six reads a card shows, from the stored tearsheet payload.
 *
 * A DCA strategy carries different headline fields than a long/short one (it has
 * no win rate or profit factor), so the card shows the DCA set — the same split
 * digiquant.io's own library card makes. A missing field stays an em dash.
 */
function liveStrategyCard(read: TearsheetCardRead): StrategyCardData {
  const dca = isDcaCard(read);
  const cagr =
    read.netProfitPct !== null && read.periodStart && read.periodEnd
      ? cagrPct(read.netProfitPct, read.periodStart, read.periodEnd)
      : null;
  const trades = read.totalTrades === null ? "—" : read.totalTrades.toLocaleString("en-US");
  const since = read.periodStart ? read.periodStart.slice(0, 7) : "—";
  const kpis = dca
    ? [
        { label: "Total return", value: fmtPctValue(read.netProfitPct) },
        { label: "Max DD", value: fmtPctValue(read.maxDrawdownPct) },
        { label: "Vs buy & hold", value: fmtPctValue(read.vsLumpPct) },
        {
          label: "Allocated",
          value: read.allocatedPct === null ? "—" : `${read.allocatedPct.toFixed(1)}%`,
        },
        { label: "Trades", value: trades },
        { label: "Since", value: since },
      ]
    : [
        { label: "CAGR", value: fmtPctValue(cagr) },
        { label: "Max DD", value: fmtPctValue(read.maxDrawdownPct) },
        {
          label: "Profit factor",
          value: read.profitFactor === null ? "—" : read.profitFactor.toFixed(2),
        },
        { label: "Win rate", value: fmtPctValue(read.winRatePct) },
        { label: "Trades", value: trades },
        { label: "Since", value: since },
      ];
  return {
    slug: read.id,
    name: read.name,
    symbol: (read.symbol ?? "—").replace(/-USD$/, ""),
    kind: read.kind ?? (dca ? "accumulation" : "long / short"),
    kpis,
  };
}

/** A live pair, each leg indexed to 100 at its own first point. `Book` rebases
 * the drawn window to 0% at its left date edge before it reaches the chart. */
function indexLive(
  nav: NavPoint[],
  benchmark: PricePoint[],
): { series: OverlaySeries[]; fullSpan: [string, string] } | null {
  if (nav.length < 2) return null;
  const baseNav = nav[0].nav;
  if (!baseNav) return null;
  const start = nav[0].date;
  const portfolio: TearsheetSeriesPoint[] = nav.map((point) => ({
    t: point.date,
    v: (point.nav / baseNav) * 100,
  }));
  const prices = benchmark.filter((point) => point.date >= start);
  const basePrice = prices[0]?.price ?? 0;
  const benchmarkPoints: TearsheetSeriesPoint[] =
    basePrice > 0
      ? prices.map((point) => ({ t: point.date, v: (point.price / basePrice) * 100 }))
      : [];
  const series: OverlaySeries[] = [
    { id: "portfolio", label: "digiquant portfolio", points: portfolio, tone: "accent", fill: true },
  ];
  if (benchmarkPoints.length > 1) {
    series.push({
      id: "benchmark",
      label: "benchmark",
      points: benchmarkPoints,
      tone: "mute",
      dotted: true,
    });
  }
  return { series, fullSpan: [portfolio[0].t, portfolio[portfolio.length - 1].t] };
}

/**
 * Rebase every leg to percent return from the *visible* window's start.
 *
 * The legs arrive indexed to 100 at the full series' start (`indexLive`, or
 * the example pair) — the right stored shape but the wrong drawn one. On a 1M
 * window the curves would otherwise start at whatever index level the book
 * had drifted to, and the axis would read in index points. Rebasing maps each
 * leg to `(v / v0 - 1) * 100`, where `v0` is the leg's value at the window's
 * left date edge, so the visible chart always starts at 0% and the axis reads
 * in percent. The base is found by date (the same edge the chart slices on),
 * not by index fraction, so the drawn first point is exactly zero. Values
 * outside the window are rebased too but never drawn — the chart still slices
 * by date itself — and the window reads beside the chart are the last drawn
 * values of these same rebased legs, so the numbers and the curves cannot
 * disagree.
 */
function rebaseToWindow(
  series: OverlaySeries[],
  window: ViewWindow,
  fullSpan: [string, string],
): OverlaySeries[] {
  const t0 = new Date(fullSpan[0]).getTime();
  const t1 = new Date(fullSpan[1]).getTime();
  const span = t1 - t0;
  if (!Number.isFinite(span) || span <= 0) return series;
  const loT = t0 + window.lo * span;
  return series.map((leg) => {
    const base = leg.points.find((point) => new Date(point.t).getTime() >= loT)?.v ?? 0;
    if (!base) return leg;
    return {
      ...leg,
      points: leg.points.map((point) => ({ t: point.t, v: (point.v / base - 1) * 100 })),
    };
  });
}

/** A signed percent, or an em dash when the window cannot be measured. */
function fmtSignedPct(value: number | null): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(1)}%`;
}

/** An alpha read, or an em dash when the window cannot be measured. */
function fmtAlpha(alpha: number | null): string {
  if (alpha === null) return "—";
  return `${alpha >= 0 ? "+" : "−"}${Math.abs(alpha).toFixed(1)} pts`;
}

/** One block of the book's window reads: plain label/value rows, no background. */
function ReadRows({ rows }: { rows: { label: string; value: string; title?: string }[] }) {
  return (
    <>
      {rows.map((row) => (
        <div
          key={row.label}
          className="flex items-baseline justify-between gap-[0.8rem] border-b border-hair/60 pb-[0.55rem] last:border-b-0 last:pb-0"
        >
          <span className="font-mono text-[0.68rem] uppercase tracking-[0.06em] text-ink-mute">
            {row.label}
          </span>
          <span
            className="font-mono text-[1.05rem] tabular-nums text-ink"
            {...(row.title ? { title: row.title } : {})}
          >
            {row.value}
          </span>
        </div>
      ))}
    </>
  );
}

/**
 * Portfolio against benchmark, compressed, with the window's reads beside
 * it and the lookback controls the owner asked for.
 *
 * The preset drives the view, so the buttons are the control; a drag on the
 * chart writes a view back through `onView` and the active button follows the
 * window rather than the click that started it. The reads are three rows —
 * net return and annualized CAGR for the book on its own, then alpha against
 * the dotted benchmark leg (beta in its hover title) — all computed from the
 * SAME window the chart is drawing, so change the preset and the numbers move
 * with it.
 *
 * The chart itself draws percent return rebased to zero at the window's left
 * edge (`rebaseToWindow`), not the stored index levels: switching from 1Y to
 * 1M re-anchors the curves at 0% and the axis reads in percent, with the area
 * filled to the zero line. The y-domain stays the chart's own tight auto fit,
 * so the whole progression of the period fills the pane.
 *
 * Values are deliberately untinted: the up/down money classes are reserved for
 * figures that are somebody's result.
 */
function Book({
  series,
  fullSpan,
}: {
  series: OverlaySeries[] | null;
  fullSpan: [string, string] | null;
}) {
  const [view, setView] = useState<ViewWindow | null>(null);
  if (!series || !fullSpan) {
    return (
      <div className="flex min-w-0 flex-col gap-[0.8rem]">
        <span className={GROUPED_LABEL}>the book</span>
        <p className="m-0 font-mono text-[0.78rem] text-ink-mute">
          The official API has not published the baseline portfolio.
        </p>
        <ReadRows
          rows={[
            { label: "net return", value: "—" },
            { label: "CAGR (ann.)", value: "—" },
            { label: "alpha", value: "—" },
          ]}
        />
      </div>
    );
  }
  const active: LookbackPreset = (view && matchLookbackPreset(view, fullSpan)) || "1y";
  const window: ViewWindow = view ?? viewWindowForPreset("1y", fullSpan);
  /* Percent from the window's own start, so the drawn curves always begin at
     0% no matter which preset (or drag) set the window. No useMemo: a few
     hundred points per render is trivial, and the React Compiler memoizes the
     component itself. */
  const drawn = rebaseToWindow(series, window, fullSpan);
  /* The reads are the last drawn values of the rebased legs — sliced by the
     chart's own `sliceByView`, so the numbers and the curves are the same
     window and can never disagree — plus alpha, the window's portfolio return
     minus beta times the benchmark's, with beta from the in-window daily
     returns paired by date (beta shows in alpha's hover title). An empty leg
     renders an em dash rather than a fabricated zero, the same rule the rest
     of the band follows. */
  const drawnPortfolio = sliceByView(
    drawn.find((entry) => entry.id === "portfolio")?.points ?? [],
    window,
    fullSpan,
  );
  const drawnBenchmark = sliceByView(
    drawn.find((entry) => entry.id === "benchmark")?.points ?? [],
    window,
    fullSpan,
  );
  const portfolioReturn =
    drawnPortfolio.length > 0 ? drawnPortfolio[drawnPortfolio.length - 1].v : null;
  const benchmarkReturn =
    drawnBenchmark.length > 0 ? drawnBenchmark[drawnBenchmark.length - 1].v : null;
  const beta = windowBeta(drawnPortfolio, drawnBenchmark);
  const alpha = windowAlpha(portfolioReturn, benchmarkReturn, beta);
  const betaTitle = beta === null ? undefined : `Beta ${beta.toFixed(2)} vs benchmark, this window`;
  /* CAGR annualizes the window's own return over the actual calendar span,
     and is withheld under ~2 months — annualizing a 1M window is noise. */
  const windowEnd = drawnPortfolio.length > 0 ? drawnPortfolio[drawnPortfolio.length - 1].t : null;
  const windowDays =
    drawnPortfolio.length > 1 && windowEnd
      ? (Date.parse(windowEnd) - Date.parse(drawnPortfolio[0].t)) / 86_400_000
      : 0;
  const cagr =
    windowDays >= 60 && portfolioReturn !== null && windowEnd
      ? cagrPct(portfolioReturn, drawnPortfolio[0].t, windowEnd)
      : null;

  return (
    <div className="flex min-w-0 flex-col gap-[0.8rem]">
      <span className={GROUPED_LABEL}>the book</span>
      {/* Single column at the base for the same reason as the block above: an
          SVG chart measures its own pane, so an implicit `auto` track would size
          from that min-content and push the page wider than the viewport. */}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-[1rem] min-[980px]:grid-cols-[minmax(0,1.55fr)_minmax(0,0.45fr)] min-[980px]:items-stretch min-[980px]:gap-[1.4rem]">
        <div className="h-[240px] overflow-hidden border border-hair">
          <MultiTimeSeries
            series={drawn}
            height={240}
            interactive
            zeroBaseline
            fmt={(v) => `${fmtCompact(v)}%`}
            view={view ?? undefined}
            onView={setView}
            fullSpan={fullSpan}
            ariaLabel="digiquant portfolio percent return against a benchmark, rebased to zero at the start of the visible window"
          />
        </div>

        {/* The window's own reads: three rows, no background. Round 7: "The
            performance metrics shouldn't have a background ... a cleaner way
            of showing these with no background and more simplistic styling",
            and "the chart should be the same height as the performance
            metrics" — so the reads are plain label/value rows pinned to the
            pane's own 240px, under the timeframe selector that drives them.
            An empty leg renders an em dash rather than a fabricated zero,
            the same rule the rest of the band follows. */}
        <div className="flex min-w-0 flex-col justify-center gap-[0.6rem] min-[980px]:h-[240px]">
          <SegToggle
            value={active}
            options={LOOKBACK_OPTIONS}
            onChange={(preset) => setView(viewWindowForPreset(preset, fullSpan))}
            label="Lookback window"
          />
          <ReadRows
            rows={[
              { label: "net return", value: fmtSignedPct(portfolioReturn) },
              { label: "CAGR (ann.)", value: fmtSignedPct(cagr) },
              { label: "alpha", value: fmtAlpha(alpha), title: betaTitle },
            ]}
          />
        </div>
      </div>
    </div>
  );
}

export function QuantSection({ className }: { className?: string }) {
  const live: OfficialBandRead = useOfficialBand();
  const book = live.nav.length > 1 ? indexLive(live.nav, live.benchmark) : null;
  const cards: StrategyCardData[] = live.cards.map(liveStrategyCard);

  return (
    <div className={`relative ${className ?? ""}`}>
      <div className="relative px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2rem]">
          {/* Title on the left, the strategy library rail beside it. The rail
              takes the wider column because it scrolls and needs the room.
              Explicit single column at the base: an SVG chart measures its own
              pane, so below 980px an implicit `auto` track would size itself
              from that min-content and push the page wider than the viewport.
              `minmax(0,1fr)` + `min-w-0` pin the track to the container. */}
          <div className="grid grid-cols-[minmax(0,1fr)] gap-[2rem] min-[980px]:grid-cols-[minmax(0,0.72fr)_minmax(0,1.28fr)] min-[980px]:gap-[2.4rem]">
            {/* Left: the digiquant pixel wordmark and its domain as one link to
                digiquant.io, with the claim below. The wordmark is the same mark
                digiquant.io draws, in ink; the visible domain stays under it
                because the owner asked for the text to be visible. */}
            <div className="flex min-w-0 flex-col justify-center gap-[1rem]">
              {/* `h2`, not `h3`: this band has no other heading, so an `h3` left
                  the document outline skipping a level between `#open-source`
                  and `#pricing`. The band's heading is its product name; the
                  slogan under it carries the claim. */}
              <h2 className="m-0">
                <a
                  href={DIGIQUANT_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex w-full max-w-[22rem] flex-col gap-[0.7rem] text-ink no-underline"
                >
                  <QuantWordmark className="block h-auto w-full" />
                  <span className="font-mono text-[0.78rem] tracking-[0.04em] text-ink-mute underline decoration-hair decoration-1 underline-offset-[0.2em] transition-colors group-hover:text-ink group-focus-visible:text-ink">
                    digiquant.io
                  </span>
                </a>
              </h2>
              <p className="m-0 max-w-[var(--measure-prose)] text-[0.92rem] leading-[1.6] text-ink-soft">
                A quant research desk in a glass box you own.
              </p>
            </div>

            {/* Right: the library, in the kit's horizontal rail — the element
                promoted from the design reference's changelog rail. */}
            <div className="flex min-w-0 flex-col justify-center gap-[0.5rem]">
              <span className={GROUPED_LABEL}>
                {showExampleBadge ? "flagship strategies · example" : "flagship strategies"}
              </span>
              <CardRail ariaLabel="Flagship digiquant strategies">
                {cards.length === 0 ? (
                  <p className="m-0 px-6 py-4 font-mono text-[0.78rem] text-ink-mute">
                    {live.loading
                      ? "Reading published tearsheets."
                      : "The official API has not published these tearsheets."}
                  </p>
                ) : null}
                {cards.map((strategy) => (
                  <div key={strategy.slug} role="listitem" className="flex-[0_0_17rem] snap-start">
                    <TearsheetCard href={`${DIGIQUANT_URL}/strategies/${strategy.slug}`}>
                      <div className="ts-card-head">
                        <div className="ts-card-title">
                          <div className="ts-card-title-text">
                            <span className="ts-card-name">{strategy.name}</span>
                            <span className="ts-card-period">
                              {strategy.symbol} · {strategy.kind}
                              {showExampleBadge ? " · example" : ""}
                            </span>
                          </div>
                        </div>
                      </div>
                      <TearsheetCardKpis>
                        {strategy.kpis.map((kpi) => (
                          <TearsheetCardKpi key={kpi.label} label={kpi.label} value={kpi.value} />
                        ))}
                      </TearsheetCardKpis>
                    </TearsheetCard>
                  </div>
                ))}
              </CardRail>
            </div>
          </div>

          <div className="flex min-w-0 flex-col gap-[0.7rem]">
            <span className={GROUPED_LABEL}>the pipeline · 19 phase folders</span>
            <PipelineRail />
          </div>

          <Book series={book?.series ?? null} fullSpan={book?.fullSpan ?? null} />
        </div>
      </div>
    </div>
  );
}

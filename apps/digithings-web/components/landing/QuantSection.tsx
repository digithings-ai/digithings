"use client";

import { useState } from "react";
import {
  CardRail,
  CtaLink,
  DigiquantMark,
  LOOKBACK_OPTIONS,
  MultiTimeSeries,
  SegToggle,
  TearsheetCard,
  TearsheetCardKpi,
  TearsheetCardKpis,
  matchLookbackPreset,
  viewWindowForPreset,
  type LookbackPreset,
  type OverlaySeries,
  type TearsheetSeriesPoint,
  type ViewWindow,
} from "@digithings/ui";
import { GROUPED_LABEL } from "./label";

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
 * pipeline as one thin row; the book (portfolio against benchmark, with the
 * lookback controls, the chart compressed and the window's three reads beside
 * it). No positions blotter — that surface belongs to digiquant.io — and no lead
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
 * The band is full-bleed — the section in LandingPage carries no horizontal
 * padding, so this component paints digiquant's own livery and tinted background
 * (`accent-digiquant` + `.quant-band`) edge to edge while the content stays on
 * the page's frame.
 *
 * HONESTY (binding). With the market tape gone, EVERY figure on this band is
 * synthetic and badged as such — the performance pair, the three window reads
 * and the strategy cards. No figure here is a digiquant result, and the two
 * series are a deterministic example, not a reported return.
 *
 * LIVE WIRING (approved, in progress). The owner authorised wiring these to the
 * dashboard's own backend: "we need to do the same architecture as we have for
 * the DigiQuant website. We'll just duplicate it from there, so copy it over. We
 * will copy all the secrets and all the permissions. And they should share the
 * same canonical backend for getting all that data." The real series live in
 * digiquant's Supabase tables (`public_accounting_nav_history`,
 * `public_portfolio_positions`, `strategy_tearsheets`) — there is no public
 * no-auth endpoint — so this means a Supabase client here plus
 * `NEXT_PUBLIC_SUPABASE_URL`/`ANON_KEY` at build and a CSP `connect-src` entry.
 * That is a new external service dependency: flagged for the owner, not merged
 * autonomously. Until the env is set the band keeps the badged example series.
 */

const DIGIQUANT_URL = "https://digiquant.io";

/** Years of weekly closes in the example pair. */
const SERIES_WEEKS = 156;

/**
 * The example performance pair: portfolio against benchmark, both indexed to 100
 * at the start.
 *
 * Synthetic and deterministic — two drifting walks with fixed periodic terms and
 * no random source, so the drawn chart is identical on every build and nobody can
 * read a change into a redeploy. This is the one figure on the page whose absence
 * of a real source is worth stating plainly: the real portfolio series lives in
 * digiquant's own tearsheet store, and reading it from here would mean giving
 * this static-export site a second service dependency. When that trade is worth
 * making, this function is the seam: it returns the shape the chart already
 * takes.
 */
function performance(): { portfolio: TearsheetSeriesPoint[]; benchmark: TearsheetSeriesPoint[] } {
  const start = Date.UTC(2023, 0, 6);
  const week = 7 * 24 * 60 * 60 * 1000;
  const portfolio: TearsheetSeriesPoint[] = [];
  const benchmark: TearsheetSeriesPoint[] = [];
  let p = 100;
  let b = 100;
  for (let i = 0; i < SERIES_WEEKS; i += 1) {
    const t = new Date(start + i * week).toISOString().slice(0, 10);
    p *= 1 + 0.0018 + 0.014 * Math.sin(i / 7.3);
    b *= 1 + 0.0009 + 0.011 * Math.sin(i / 5.1 + 1.2);
    portfolio.push({ t, v: p });
    benchmark.push({ t, v: b });
  }
  return { portfolio, benchmark };
}

const EXAMPLE = performance();

const PERFORMANCE_SERIES: OverlaySeries[] = [
  { id: "portfolio", label: "digiquant portfolio", points: EXAMPLE.portfolio, tone: "accent", fill: true },
  { id: "benchmark", label: "benchmark", points: EXAMPLE.benchmark, tone: "mute", dashed: true },
];

const FULL_SPAN: [string, string] = [
  EXAMPLE.portfolio[0].t,
  EXAMPLE.portfolio[EXAMPLE.portfolio.length - 1].t,
];

/**
 * The pipeline, in the dashboard's own categories.
 *
 * The owner asked for the simple presentation version rather than every folder:
 * the six stages the dashboard's pipeline page shows — inputs → research →
 * synthesis → selection → decision → learning — as one thin row, with each
 * stage's one-line mechanism under its name. No diagnostics: this is the
 * pipeline as a *definition*, not a completed run, so there is no wall time or
 * token count to report.
 */
const STAGES: { id: string; label: string; detail: string; steps: string[] }[] = [
  {
    id: "inputs",
    label: "Inputs",
    detail: "Market and reference data validated before any research runs.",
    steps: ["preflight", "attention plan"],
  },
  {
    id: "research",
    label: "Research",
    detail: "Independent specialist reads, before any of them are combined.",
    steps: ["alt-data", "institutional", "macro", "asset classes", "sectors"],
  },
  {
    id: "synthesis",
    label: "Synthesis",
    detail: "The reads reconciled into one directional call and a narrative.",
    steps: ["consolidate", "digest"],
  },
  {
    id: "selection",
    label: "Selection",
    detail: "Challenged, screened and risk-sized portfolio candidates.",
    steps: ["thesis", "screener", "analysts", "deliberation", "PM direction", "risk sizing"],
  },
  {
    id: "decision",
    label: "Decision",
    detail: "The recommendation, with the evidence chain that produced it.",
    steps: ["commit"],
  },
  {
    id: "learning",
    label: "Learning",
    detail: "Resolved outcomes folded back in on the next run.",
    steps: ["beliefs"],
  },
];

/**
 * The six stages as one thin row — the simple version the owner asked for over
 * the kit's `Pipeline` panel. It stays readable at band height and never adds a
 * detail panel's worth of vertical space.
 */
function StageStrip() {
  return (
    <ol
      className="m-0 flex list-none flex-wrap items-stretch gap-[0.4rem] p-0"
      aria-label="digiquant pipeline stages"
    >
      {STAGES.map((stage, index) => (
        <li key={stage.id} className="flex min-w-[9rem] flex-1 items-stretch gap-[0.4rem]">
          <div className="flex flex-1 flex-col gap-[0.25rem] border border-hair bg-surface p-[0.6rem]">
            <span className="font-mono text-[0.6rem] tracking-[0.06em] text-ink-mute">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="font-mono text-[0.8rem] text-ink">{stage.label}</span>
            <span className="text-[0.72rem] leading-[1.45] text-ink-mute">{stage.detail}</span>
          </div>
          {index < STAGES.length - 1 ? (
            <span aria-hidden="true" className="self-center font-mono text-[0.8rem] text-ink-mute">
              →
            </span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

/**
 * The strategies the library shipped, as the *library* card — the same
 * composition digiquant.io/strategies renders.
 *
 * `slug` is the real public slug, so the card links to that strategy's own
 * tearsheet, where the figures are the real ones. The reads here are examples:
 * the owner asked for the library cards without the live badge, and a live mark
 * over figures that are not live would be the one dishonest pixel on the page.
 * Values are also deliberately untinted — the up/down money classes are reserved
 * for figures that are somebody's result, and none of these is.
 */
const STRATEGIES: {
  slug: string;
  name: string;
  symbol: string;
  kind: string;
  kpis: { label: string; value: string }[];
}[] = [
  {
    slug: "btc_slapper",
    name: "BTC L/S",
    symbol: "BTC",
    kind: "long / short",
    kpis: [
      { label: "CAGR", value: "+24.6%" },
      { label: "Max DD", value: "−18.2%" },
      { label: "Profit factor", value: "1.72" },
      { label: "Win rate", value: "56.0%" },
      { label: "Avg trade", value: "+0.31%" },
      { label: "Trades", value: "1,204" },
    ],
  },
  {
    slug: "eth_slapper",
    name: "ETH L/S",
    symbol: "ETH",
    kind: "long / short",
    kpis: [
      { label: "CAGR", value: "+19.4%" },
      { label: "Max DD", value: "−22.6%" },
      { label: "Profit factor", value: "1.48" },
      { label: "Win rate", value: "53.1%" },
      { label: "Avg trade", value: "+0.27%" },
      { label: "Trades", value: "986" },
    ],
  },
  {
    slug: "sol_slapper",
    name: "SOL L/S",
    symbol: "SOL",
    kind: "long / short",
    kpis: [
      { label: "CAGR", value: "+31.2%" },
      { label: "Max DD", value: "−29.8%" },
      { label: "Profit factor", value: "1.61" },
      { label: "Win rate", value: "51.7%" },
      { label: "Avg trade", value: "+0.38%" },
      { label: "Trades", value: "842" },
    ],
  },
  {
    slug: "btc_sdca",
    name: "BTC-SDCA",
    symbol: "BTC",
    kind: "accumulation",
    kpis: [
      { label: "Total return", value: "+41.8%" },
      { label: "Max DD", value: "−15.4%" },
      { label: "Vs buy & hold", value: "+6.2%" },
      { label: "Allocated", value: "62.0%" },
      { label: "Deployed", value: "88.0%" },
      { label: "Fills", value: "214" },
    ],
  },
];

/**
 * The percent change across the *visible* window of an indexed series.
 *
 * `ViewWindow` is a normalized `[lo, hi]` slice of the full date span, so the
 * window maps onto point indices by fraction. Returns `null` when the window is
 * too narrow to hold two points — the caller renders an em dash rather than a
 * fabricated zero, the same rule the rest of the band follows.
 */
function windowReturn(points: TearsheetSeriesPoint[], view: ViewWindow): number | null {
  const last = points.length - 1;
  if (last < 1) return null;
  const from = Math.max(0, Math.min(last, Math.round(view.lo * last)));
  const to = Math.max(0, Math.min(last, Math.round(view.hi * last)));
  if (to <= from) return null;
  const start = points[from].v;
  if (!start) return null;
  return (points[to].v / start - 1) * 100;
}

/** A signed percent, or an em dash when the window cannot be measured. */
function fmtSignedPct(value: number | null): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(1)}%`;
}

/** The portfolio's excess over the benchmark, in percentage points. */
function fmtRelative(portfolio: number | null, benchmark: number | null): string {
  if (portfolio === null || benchmark === null) return "—";
  const diff = portfolio - benchmark;
  return `${diff >= 0 ? "+" : "−"}${Math.abs(diff).toFixed(1)} pts`;
}

/**
 * Portfolio against benchmark, compressed, with the window's three reads beside
 * it and the lookback controls the owner asked for.
 *
 * The preset drives the view, so the buttons are the control; a drag on the
 * chart writes a view back through `onView` and the active button follows the
 * window rather than the click that started it. The three reads are computed
 * from the SAME window the chart is drawing, so "relative performance over the
 * period selected in the chart" is literally what the middle figure reports —
 * change the preset and the numbers move with it.
 *
 * Values are deliberately untinted: the up/down money classes are reserved for
 * figures that are somebody's result, and none of these is.
 */
function Book() {
  const [view, setView] = useState<ViewWindow | null>(null);
  const active: LookbackPreset = (view && matchLookbackPreset(view, FULL_SPAN)) || "1y";
  const window: ViewWindow = view ?? viewWindowForPreset("1y", FULL_SPAN);
  const portfolioReturn = windowReturn(EXAMPLE.portfolio, window);
  const benchmarkReturn = windowReturn(EXAMPLE.benchmark, window);

  return (
    <div className="flex min-w-0 flex-col gap-[0.8rem]">
      <span className={GROUPED_LABEL}>the book · example</span>
      {/* Single column at the base for the same reason as the block above: an
          SVG chart measures its own pane, so an implicit `auto` track would size
          from that min-content and push the page wider than the viewport. */}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-[1rem] min-[980px]:grid-cols-[minmax(0,1.55fr)_minmax(0,0.45fr)] min-[980px]:items-stretch min-[980px]:gap-[1.4rem]">
        <div className="h-[240px] overflow-hidden border border-hair">
          <MultiTimeSeries
            series={PERFORMANCE_SERIES}
            height={240}
            interactive
            view={view ?? undefined}
            onView={setView}
            fullSpan={FULL_SPAN}
            ariaLabel="Example performance, digiquant portfolio against a benchmark, indexed to 100 at the start (synthetic series)"
          />
        </div>

        {/* The window's own reads. Three, as the owner asked — the dashboard
            shows more, but here the point is the shape of the period, not a
            blotter. Round 7: "The performance metrics shouldn't have a
            background ... a cleaner way of showing these with no background and
            more simplistic styling", and "the chart should be the same height as
            the performance metrics" — so the reads are plain label/value rows
            pinned to the pane's own 240px. */}
        <div className="flex min-w-0 flex-col justify-center gap-[0.6rem] min-[980px]:h-[240px]">
          <span className="font-mono text-[0.6rem] uppercase tracking-[0.06em] text-ink-mute">
            over the window
          </span>
          {[
            { label: "portfolio", value: fmtSignedPct(portfolioReturn) },
            { label: "benchmark", value: fmtSignedPct(benchmarkReturn) },
            { label: "relative", value: fmtRelative(portfolioReturn, benchmarkReturn) },
          ].map((row) => (
            <div
              key={row.label}
              className="flex items-baseline justify-between gap-[0.8rem] border-b border-hair/60 pb-[0.55rem] last:border-b-0 last:pb-0"
            >
              <span className="font-mono text-[0.68rem] uppercase tracking-[0.06em] text-ink-mute">
                {row.label}
              </span>
              <span className="font-mono text-[1.05rem] tabular-nums text-ink">{row.value}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-[0.6rem]">
        <p className="m-0 font-mono text-[0.68rem] text-ink-mute">
          indexed to 100 · portfolio (solid) vs benchmark (dashed) · synthetic series
        </p>
        <SegToggle
          value={active}
          options={LOOKBACK_OPTIONS}
          onChange={(preset) => setView(viewWindowForPreset(preset, FULL_SPAN))}
          label="Lookback window"
        />
      </div>
    </div>
  );
}

export function QuantSection({ className }: { className?: string }) {
  return (
    <div className={`accent-digiquant quant-band relative overflow-hidden ${className ?? ""}`}>
      {/* The dashboard mark, behind everything, faded and animated — the
          section's branding without a bar the owner has to maintain. */}
      <span
        aria-hidden="true"
        className="quant-mark pointer-events-none absolute -top-[6%] end-[-4%] w-[58%] max-w-[46rem] select-none text-accent"
      >
        <DigiquantMark size={720} className="h-auto w-full" />
      </span>

      {/* Full width is the band's, not the content's: the background bleeds to
          the viewport edges and the frame below keeps the page grid. */}
      <div className="relative px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2rem]">
          {/* Title on the left, the strategy library rail beside it. The rail
              takes the wider column because it scrolls and needs the room.
              Explicit single column at the base: an SVG chart measures its own
              pane, so below 980px an implicit `auto` track would size itself
              from that min-content and push the page wider than the viewport.
              `minmax(0,1fr)` + `min-w-0` pin the track to the container. */}
          <div className="grid grid-cols-[minmax(0,1fr)] gap-[2rem] min-[980px]:grid-cols-[minmax(0,0.72fr)_minmax(0,1.28fr)] min-[980px]:gap-[2.4rem]">
            {/* Left: the claim and the two ways into the product. The owner
                wanted the space beside the title filled — "Put the buttons there
                to open the dashboard with the DigiQuant dashboard logo. And then
                tier sheets as another button below it ... aligned properly." */}
            <div className="flex min-w-0 flex-col justify-center gap-[1.4rem]">
              {/* `h2`, not `h3`: this band has no other heading, so an `h3` left
                  the document outline skipping a level between `#open-source`
                  and `#pricing`. Every other band's `h2` is its claim rather than
                  its product name, so the claim is the band's heading. */}
              <h2 className="m-0 font-mono text-[clamp(1.4rem,2.6vw,2rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink">
                A hedge fund in a glass box you own.
              </h2>
              <div className="flex flex-col items-start gap-[0.6rem]">
                <CtaLink
                  href={`${DIGIQUANT_URL}/dashboard`}
                  external
                  icon={<DigiquantMark size={16} />}
                >
                  Open the dashboard
                </CtaLink>
                <CtaLink href={`${DIGIQUANT_URL}/strategies`} external variant="ghost">
                  Tearsheets
                </CtaLink>
              </div>
            </div>

            {/* Right: the library, in the kit's horizontal rail — the element
                promoted from the design reference's changelog rail. */}
            <div className="flex min-w-0 flex-col justify-center">
              <CardRail ariaLabel="Flagship digiquant strategies">
                {STRATEGIES.map((strategy) => (
                  <div key={strategy.slug} role="listitem" className="flex-[0_0_17rem] snap-start">
                    <TearsheetCard href={`${DIGIQUANT_URL}/strategies/${strategy.slug}`}>
                      <div className="ts-card-head">
                        <div className="ts-card-title">
                          <div className="ts-card-title-text">
                            <span className="ts-card-name">{strategy.name}</span>
                            <span className="ts-card-period">
                              {strategy.symbol} · {strategy.kind}
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
            <span className={GROUPED_LABEL}>the pipeline</span>
            <StageStrip />
          </div>

          <Book />
        </div>
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import {
  CardRail,
  Kpi,
  KpiStrip,
  LOOKBACK_OPTIONS,
  MultiTimeSeries,
  SegToggle,
  StockTicker,
  TearsheetCard,
  TearsheetCardKpi,
  TearsheetCardKpis,
  matchLookbackPreset,
  viewWindowForPreset,
  type LookbackPreset,
  type OverlaySeries,
  type TearsheetSeriesPoint,
} from "@digithings/ui";
import { usePriceTape } from "@/lib/priceTape";
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
 * So the band reads, top to bottom: the market tape; the title with the strategy
 * library rail beside it; the book (portfolio against benchmark, with the
 * lookback controls and the headline metrics under the chart); the pipeline. No
 * positions blotter — that surface belongs to digiquant.io — and no lead
 * paragraph, call-to-action buttons or closing footnote: the owner asked for the
 * title on its own, "simple and clean".
 *
 * The band is full-bleed — the section in LandingPage carries no horizontal
 * padding, so this component paints digiquant's own livery and tinted background
 * (`accent-digiquant` + `.quant-band`) edge to edge while the content stays on
 * the page's frame.
 *
 * HONESTY (binding). The market tape is REAL: the latest daily close and the
 * real prior-session change for the majors, read from the public market-data
 * archive, labelled `markets · latest close` rather than anything implying a
 * stream. Everything else on this band is synthetic and badged as such — the
 * performance pair, the tearsheet readout and the strategy cards. No figure here
 * is a digiquant result, and the two series are a deterministic example, not a
 * reported return.
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
 * The example tearsheet, in the tearsheet's own element. The values are neutral
 * on purpose: the up/down money classes are reserved for figures that are
 * somebody's result, and none of these is.
 */
const TEARSHEET_KPIS: { label: string; value: string; sub: string }[] = [
  { label: "CAGR", value: "24.6%", sub: "example" },
  { label: "Sharpe", value: "1.34", sub: "example" },
  { label: "Sortino", value: "1.88", sub: "example" },
  { label: "Max drawdown", value: "-18.2%", sub: "example" },
  { label: "Win rate", value: "56.0%", sub: "example" },
  { label: "Profit factor", value: "1.72", sub: "example" },
];

/**
 * The market tape. Empty until the read lands, and muted rather than blank when
 * it cannot — a strip that flashes an error would make decoration look
 * load-bearing.
 */
function Tape() {
  const { items } = usePriceTape();

  return (
    <div className="flex min-w-0 flex-col gap-[0.45rem]">
      <span className={GROUPED_LABEL}>markets · latest close</span>
      <div className="border-y border-hair">
        {items.length === 0 ? (
          <p className="m-0 px-[0.2rem] py-[0.75rem] font-mono text-[0.78rem] text-ink-mute">
            connecting to the market feed…
          </p>
        ) : (
          <StockTicker items={items} />
        )}
      </div>
    </div>
  );
}

/**
 * Portfolio against benchmark, with the lookback controls the owner asked for.
 *
 * The preset drives the view, so the buttons are the control; a drag on the
 * chart writes a view back through `onView` and the active button follows the
 * window rather than the click that started it.
 */
function Book() {
  const [view, setView] = useState<ReturnType<typeof viewWindowForPreset> | null>(null);
  const active: LookbackPreset = (view && matchLookbackPreset(view, FULL_SPAN)) || "1y";

  return (
    <div className="flex min-w-0 flex-col gap-[0.8rem]">
      <span className={GROUPED_LABEL}>the book · example</span>
      <figure className="m-0 flex min-w-0 flex-col gap-[0.6rem]">
        <div className="h-[clamp(190px,26vh,260px)] overflow-hidden border border-hair">
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
        <div className="flex flex-wrap items-center justify-between gap-[0.6rem]">
          <figcaption className="m-0 font-mono text-[0.68rem] text-ink-mute">
            indexed to 100 · portfolio (solid) vs benchmark (dashed) · synthetic series
          </figcaption>
          <SegToggle
            value={active}
            options={LOOKBACK_OPTIONS}
            onChange={(preset) => setView(viewWindowForPreset(preset, FULL_SPAN))}
            label="Lookback window"
          />
        </div>
      </figure>
      <KpiStrip primary ariaLabel="Example tearsheet, synthetic series">
        {TEARSHEET_KPIS.map((kpi) => (
          <Kpi key={kpi.label} label={kpi.label} value={kpi.value} sub={kpi.sub} />
        ))}
      </KpiStrip>
    </div>
  );
}

export function QuantSection({ className }: { className?: string }) {
  return (
    <div className={`accent-digiquant quant-band ${className ?? ""}`}>
      {/* Full width is the band's, not the content's: the background bleeds to
          the viewport edges and the frame below keeps the page grid. */}
      <div className="px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2rem]">
          <Tape />

          {/* Title on the left, the strategy library rail beside it. The rail
              takes the wider column because it scrolls and needs the room.
              Explicit single column at the base: an SVG chart measures its own
              pane, so below 980px an implicit `auto` track would size itself
              from that min-content and push the page wider than the viewport.
              `minmax(0,1fr)` + `min-w-0` pin the track to the container. */}
          <div className="grid grid-cols-[minmax(0,1fr)] gap-[2rem] min-[980px]:grid-cols-[minmax(0,0.72fr)_minmax(0,1.28fr)] min-[980px]:gap-[2.4rem]">
            {/* Left: the claim and nothing else. The owner asked for the title
                on its own — "just keep the title, the hedge fund in the glass
                box you own, keep it simple and clean" — so no lead paragraph
                and no call-to-action buttons. */}
            <div className="flex min-w-0 flex-col gap-[1.2rem]">
              {/* `h2`, not `h3`: this band has no other heading, so an `h3` left
                  the document outline skipping a level between `#open-source`
                  and `#pricing`. Every other band's `h2` is its claim rather than
                  its product name, so the claim is the band's heading. */}
              <h2 className="m-0 font-mono text-[clamp(1.4rem,2.6vw,2rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink">
                A hedge fund in a glass box you own.
              </h2>
            </div>

            {/* Right: the library, in the kit's horizontal rail — the element
                promoted from the design reference's changelog rail. */}
            <div className="flex min-w-0 flex-col gap-[0.5rem]">
              <span className={GROUPED_LABEL}>the strategy library</span>
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

          <Book />

          <div className="flex min-w-0 flex-col gap-[0.7rem]">
            <span className={GROUPED_LABEL}>the pipeline</span>
            <StageStrip />
          </div>
        </div>
      </div>
    </div>
  );
}

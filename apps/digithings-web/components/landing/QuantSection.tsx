"use client";

import {
  CtaLink,
  Kpi,
  KpiStrip,
  MultiTimeSeries,
  Pipeline,
  StockTicker,
  type OverlaySeries,
  type PipelineColumn,
  type PipelineSummaryItem,
  type TearsheetSeriesPoint,
} from "@digithings/ui";
import { PIPELINE_ENGINES, PIPELINE_PHASES } from "@/lib/digiquantPipeline";
import { usePriceTape } from "@/lib/priceTape";
import { GROUPED_LABEL } from "./label";

/**
 * The digiquant band (v15 point 9, #4429; reworked in rounds 3 and 4).
 *
 * The owner's direction: "I'd build out the digiquant section properly… a
 * different background to stand out… If you took the digiquant website and
 * compressed it in the same way… that's what I want to see", then: "make the
 * background of the digiquant section expand the full width… it could be its own
 * section with its own background", and in round 4: "use the proper flow digiweb
 * element to describe the pipeline… by the pipeline I meant the actual digiquant
 * pipeline, the one used in the dashboard, for research and then portfolio
 * management decision making and then execution framework… we could show some
 * strategies in a horizontal scrollable card… it'd be nice to also connect the
 * performance of the digiquant dashboard and we could show the portfolio
 * performance versus a benchmark with a line chart… and then the tearsheet of
 * all the performance metrics as they appear in the digiquant tearsheet
 * elements."
 *
 * So the band is full-bleed — the section in LandingPage carries no horizontal
 * padding, and this component paints digiquant's own livery and its own tinted
 * background (`accent-digiquant` + `.quant-band`) edge to edge while the content
 * stays on the page's frame.
 *
 * ROUND 4 CHANGES, and why:
 *  - the pipeline is now the kit's `<Pipeline>` — the element the dashboard's
 *    workflow view was promoted from — fed with digiquant's real phase list
 *    (`research` 00–09, `portfolio` h1–h9 + the coverage director, `execution`
 *    with no folders yet). It was a bespoke four-tab rail before; the real
 *    pipeline has twenty stages across three engines, and the honest thing is to
 *    draw the one that runs, not a summary of it. The stage list is a guarded
 *    copy of the digiquant site's own source (see `lib/digiquantPipeline.ts`).
 *  - the strategy block is a horizontal snap rail (`.h-scroll`, the marketing
 *    site's own row primitive) instead of a wrapping grid.
 *  - the candle chart is replaced by the performance line chart: portfolio
 *    against a benchmark. The band already carries the market tape at the top,
 *    so the second chart earns its place by comparing something rather than
 *    repeating an instrument.
 *  - the tearsheet metrics use the tearsheet's own `KpiStrip`/`Kpi` grammar.
 *
 * HONESTY (binding). The market tape is REAL: the latest daily close and the real
 * prior-session change for the majors, read from the public market-data archive,
 * labelled `markets · latest close` rather than anything implying a stream.
 * Everything else on this band is synthetic and badged as such — the performance
 * pair, the KPI strip and the strategy cards. No figure here is a digiquant
 * result, and the two series are a deterministic example, not a reported return.
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

/**
 * The pipeline, in the dashboard's own terms.
 *
 * One column per engine, in run order, with every shipped phase as a node. The
 * node's `note` is the phase's own one-line mechanism (`detail` in the source)
 * prefixed with its real folder id, so the detail panel answers "what does this
 * step do" rather than restating the name. No diagnostics are passed — this is
 * the pipeline as a *definition*, not as a completed run, so there is no wall
 * time or token count to report, and `Pipeline` omits the block rather than
 * printing an em dash for each.
 */
const PIPELINE_COLUMNS: PipelineColumn[] = PIPELINE_ENGINES.map((engine) => ({
  id: engine.id,
  kind: "step" as const,
  label: engine.phases.length > 0 ? `${engine.label} · ${engine.phases.length} phases` : engine.label,
  nodes:
    engine.phases.length > 0
      ? engine.phases.map((phase) => ({
          id: `${engine.id}-${phase.id}`,
          label: phase.name,
          status: "done" as const,
          note: `${phase.id} · ${phase.detail}`,
        }))
      : [
          {
            id: "execution-pending",
            label: "Not built",
            status: "queued" as const,
            note: engine.summary,
          },
        ],
}));

const PIPELINE_SUMMARY: PipelineSummaryItem[] = [
  { label: "phases shipped", value: String(PIPELINE_PHASES.length) },
  { label: "execution engine", value: "in development" },
  { label: "live orders", value: "0" },
];

/**
 * The first four strategies the library shipped. `slug` is the real public slug,
 * so the link lands on that strategy's own tearsheet — the figures live there,
 * where they are the real ones.
 */
const FLAGSHIP: { slug: string; label: string; symbol: string; kind: string }[] = [
  { slug: "btc_slapper", label: "BTC Slapper", symbol: "BTC", kind: "long / short" },
  { slug: "eth_slapper", label: "ETH Slapper", symbol: "ETH", kind: "long / short" },
  { slug: "sol_slapper", label: "SOL Slapper", symbol: "SOL", kind: "long / short" },
  { slug: "btc_sdca", label: "BTC DCA", symbol: "BTC", kind: "accumulation" },
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

export function QuantSection({ className }: { className?: string }) {
  return (
    <div className={`accent-digiquant quant-band ${className ?? ""}`}>
      {/* Full width is the band's, not the content's: the background bleeds to
          the viewport edges and the frame below keeps the page grid. */}
      <div className="px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2rem]">
          <Tape />

          {/* Explicit single column at the base: an SVG chart measures its own
              pane, so below 980px an implicit `auto` track would size itself from
              that min-content and push the page wider than the viewport.
              `minmax(0,1fr)` + `min-w-0` pin the track to the container. */}
          <div className="grid grid-cols-[minmax(0,1fr)] gap-[2rem] min-[980px]:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] min-[980px]:gap-[2.4rem]">
            {/* Left: the claim, in digiquant's own voice. */}
            <div className="flex min-w-0 flex-col gap-[1.2rem]">
              {/* `h2`, not `h3`: this band has no other heading, so an `h3` left
                  the document outline skipping a level between `#open-source`
                  and `#pricing`. Every other band's `h2` is its claim rather than
                  its product name, so the claim is the band's heading. */}
              <h2 className="m-0 font-mono text-[clamp(1.4rem,2.6vw,2rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink">
                A hedge fund in a glass box you own.
              </h2>
              <p className="m-0 max-w-[var(--measure-prose)] text-[0.92rem] leading-[1.75] text-ink-soft">
                digiquant is the module that shows what the rest of the stack is for. Ideas are
                proposed against public data, every one is backtested before it is seen, and the
                survivor is sized into target weights. It is the same glass box as the rest of
                digithings — your hosts, data and keys — pointed at the finance work.
              </p>

              <div className="flex flex-wrap items-center gap-[0.8rem] pt-[0.4rem]">
                <CtaLink href={DIGIQUANT_URL} external>
                  digiquant.io
                </CtaLink>
                <CtaLink href="/docs" variant="ghost">
                  Read the docs
                </CtaLink>
              </div>
            </div>

            {/* Right: the operator surface — performance over time, then the
                tearsheet readout in the tearsheet's own grammar. */}
            <div className="flex min-w-0 flex-col gap-[1rem]">
              <figure className="m-0 flex min-w-0 flex-col gap-[0.5rem]">
                <div className="h-[clamp(190px,26vh,260px)] overflow-hidden border border-hair">
                  <MultiTimeSeries
                    series={PERFORMANCE_SERIES}
                    height={240}
                    interactive
                    ariaLabel="Example performance, digiquant portfolio against a benchmark, indexed to 100 at the start (synthetic series)"
                  />
                </div>
                <figcaption className="font-mono text-[0.68rem] text-ink-mute">
                  example · indexed to 100 · digiquant portfolio (solid) vs benchmark (dashed) ·
                  synthetic series
                </figcaption>
              </figure>

              <div className="flex flex-col gap-[0.8rem]">
                <span className={GROUPED_LABEL}>example tearsheet · synthetic</span>
                <KpiStrip primary ariaLabel="Example tearsheet, synthetic series">
                  {TEARSHEET_KPIS.map((kpi) => (
                    <Kpi key={kpi.label} label={kpi.label} value={kpi.value} sub={kpi.sub} />
                  ))}
                </KpiStrip>
              </div>
            </div>
          </div>

          <div className="flex min-w-0 flex-col gap-[1rem]">
            <span className={GROUPED_LABEL}>the pipeline</span>
            <Pipeline
              columns={PIPELINE_COLUMNS}
              summary={PIPELINE_SUMMARY}
              defaultSelectedId="research-00"
            />
          </div>

          <div className="flex min-w-0 flex-col gap-[1rem]">
            <span className={GROUPED_LABEL}>the strategy library</span>
            {/* The marketing site's own snap row: it masks its edges, scrolls
                with the keyboard because the track is a focusable scroll
                container, and stacks in flow under prefers-reduced-motion. */}
            <div className="h-scroll">
              <div
                className="h-scroll__track"
                role="list"
                aria-label="flagship digiquant strategies"
                tabIndex={0}
              >
                {FLAGSHIP.map((strategy) => (
                  /* Wider than the primitive's 262px default so four cards
                     overflow the frame and the row actually scrolls — the point
                     of the element is the gesture, and four cards that happen to
                     fit would just be a grid with an edge fade. */
                  <a
                    key={strategy.slug}
                    role="listitem"
                    href={`${DIGIQUANT_URL}/strategies/${strategy.slug}`}
                    target="_blank"
                    rel="noreferrer"
                    className="h-scroll__card min-w-[19rem] max-w-[19rem] no-underline"
                  >
                    <span className="flex flex-wrap items-baseline justify-between gap-[0.5rem]">
                      <span className="font-mono text-[0.88rem] text-ink">{strategy.label}</span>
                      <span className="font-mono text-[0.68rem] text-ink-mute">
                        {strategy.symbol}
                      </span>
                    </span>
                    <span className="font-mono text-[0.68rem] text-ink-mute">{strategy.kind}</span>
                    <span className="mt-[0.2rem] font-mono text-[0.72rem] text-accent">
                      full tearsheet ↗
                    </span>
                  </a>
                ))}
              </div>
            </div>
          </div>

          <p className="m-0 font-mono text-[0.72rem] leading-[1.6] text-ink-mute">
            Market prices above are the latest daily close from the public market-data archive —
            figures for real instruments, not a live stream. The performance pair, the tearsheet
            readout and the strategy cards are drawn from a badged synthetic series: none of those
            figures is a digiquant result, and this page states no return, no Sharpe and no P&amp;L
            for the product. Live trading is guarded by a human review gate, not a runtime
            interlock.
          </p>
        </div>
      </div>
    </div>
  );
}

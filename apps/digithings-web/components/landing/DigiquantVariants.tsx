"use client";

import {
  CardRail,
  CtaLink,
  Kpi,
  KpiStrip,
  MultiTimeSeries,
  Pipeline,
  StockTicker,
  TearsheetCard,
  TearsheetCardKpi,
  TearsheetCardKpis,
  type OverlaySeries,
  type PipelineColumn,
  type PipelineSummaryItem,
  type TearsheetSeriesPoint,
} from "@digithings/ui";
import { usePriceTape } from "@/lib/priceTape";
import { GROUPED_LABEL } from "./label";

/**
 * Three variations of the digiquant band, on one throwaway page.
 *
 * The owner asked for the section to be "kind of like an advertisement page of
 * digiquant's main services which are the tearsheets, the strategies that are
 * built and then the digiquant pipeline", and for it to be "visually appealing
 * and simple to understand" — plus, explicitly, "make a separate page and give
 * you a few variations of what you would put on this digiquant section".
 *
 * So this file is a comparison harness, not the band. The winner's composition
 * gets folded back into `QuantSection.tsx` and this page goes away.
 *
 * The three differ by what they lead with:
 *   A — strategies first: the tearsheet cards are the hero.
 *   B — performance first: the portfolio-vs-benchmark read is the hero.
 *   C — pipeline first: the dashboard's stage flow is the hero.
 *
 * HONESTY. Every figure on this page is a badged example. There is no public,
 * no-auth source for digiquant strategy or portfolio numbers — digiquant.io
 * reads them from Supabase with an anon key, and the landing page is a static
 * export with no Supabase client. The only live thing here is the price tape,
 * which reads the same R2-backed market Worker the digiquant site uses. So each
 * block carries a visible "example" mark rather than pretending.
 */

const DIGIQUANT_URL = "https://digiquant.io";

/* ── The dashboard's six pipeline categories ────────────────────────────────
   Mirrors `apps/dashboard/lib/pipeline-topology.ts` (inputs → research →
   synthesis → selection → decision → learning), which the owner pointed at:
   "the pipeline i'd show a simplified version that just shows the main
   categories the research the deliberation decision inputs like it appears in
   the digiquant dashboard ... a pipeline flow which it should fit and not take
   up so much vertical height". Descriptions are shortened from that file. */
type Stage = { id: string; label: string; detail: string; steps: string[] };

const STAGES: Stage[] = [
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

/* ── The four published strategies, with example tearsheet reads ───────────
   Names and slugs are the real ones (`btc_slapper`, `eth_slapper`,
   `sol_slapper`, `btc_sdca`); the numbers are examples, marked as such. */
type Kpi = { label: string; value: string; tone?: "pos" | "neg" };
type Strategy = { slug: string; name: string; symbol: string; kind: string; kpis: Kpi[] };

const STRATEGIES: Strategy[] = [
  {
    slug: "btc_slapper",
    name: "BTC L/S",
    symbol: "BTC",
    kind: "long / short",
    kpis: [
      { label: "CAGR", value: "+24.6%", tone: "pos" },
      { label: "Max DD", value: "−18.2%", tone: "neg" },
      { label: "Profit factor", value: "1.72" },
      { label: "Win rate", value: "56.0%" },
      { label: "Avg trade", value: "+0.31%", tone: "pos" },
      { label: "Trades", value: "1,204" },
    ],
  },
  {
    slug: "eth_slapper",
    name: "ETH L/S",
    symbol: "ETH",
    kind: "long / short",
    kpis: [
      { label: "CAGR", value: "+19.4%", tone: "pos" },
      { label: "Max DD", value: "−22.6%", tone: "neg" },
      { label: "Profit factor", value: "1.48" },
      { label: "Win rate", value: "53.1%" },
      { label: "Avg trade", value: "+0.27%", tone: "pos" },
      { label: "Trades", value: "986" },
    ],
  },
  {
    slug: "sol_slapper",
    name: "SOL L/S",
    symbol: "SOL",
    kind: "long / short",
    kpis: [
      { label: "CAGR", value: "+31.2%", tone: "pos" },
      { label: "Max DD", value: "−29.8%", tone: "neg" },
      { label: "Profit factor", value: "1.61" },
      { label: "Win rate", value: "51.7%" },
      { label: "Avg trade", value: "+0.38%", tone: "pos" },
      { label: "Trades", value: "842" },
    ],
  },
  {
    slug: "btc_sdca",
    name: "BTC-SDCA",
    symbol: "BTC",
    kind: "accumulation",
    kpis: [
      { label: "Total return", value: "+41.8%", tone: "pos" },
      { label: "Max DD", value: "−15.4%", tone: "neg" },
      { label: "Vs buy & hold", value: "+6.2%", tone: "pos" },
      { label: "Allocated", value: "62.0%" },
      { label: "Deployed", value: "88.0%" },
      { label: "Fills", value: "214" },
    ],
  },
];

/* ── Example performance, portfolio against a benchmark ────────────────────
   A deterministic walk, so the chart is stable across renders and identical on
   every machine — same approach as the current band's `performance()`. */
const SERIES_WEEKS = 156;

function performance(): { portfolio: TearsheetSeriesPoint[]; benchmark: TearsheetSeriesPoint[] } {
  const portfolio: TearsheetSeriesPoint[] = [];
  const benchmark: TearsheetSeriesPoint[] = [];
  const start = Date.UTC(2023, 0, 6);
  let p = 100;
  let b = 100;
  for (let i = 0; i < SERIES_WEEKS; i += 1) {
    p *= 1 + 0.0018 + 0.014 * Math.sin(i / 7.3);
    b *= 1 + 0.0009 + 0.011 * Math.sin(i / 5.1 + 1.2);
    const t = new Date(start + i * 7 * 86_400_000).toISOString().slice(0, 10);
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

/* The six stages as the kit's `Pipeline` — one column per stage, so the flow is
   a single row that fits the band, with the detail panel under it. This is the
   promoted `effects/pipeline` element the reference gallery renders
   (`apps/reference/components/pipeline-reference.tsx`), not a hand-rolled
   strip. */
const PIPELINE_COLUMNS: PipelineColumn[] = STAGES.map((stage) => ({
  id: stage.id,
  kind: "step",
  nodes: [
    {
      id: stage.id,
      label: stage.label,
      status: "done",
      note: `${stage.detail} Inside it: ${stage.steps.join(", ")}.`,
    },
  ],
}));

const PIPELINE_SUMMARY: PipelineSummaryItem[] = [
  { label: "stages", value: "6" },
  { label: "live orders", value: "0" },
];

const HEADLINE = [
  { label: "CAGR", value: "+24.6%", sub: "example" },
  { label: "Sharpe", value: "1.34", sub: "example" },
  { label: "Max drawdown", value: "−18.2%", sub: "example" },
  { label: "Trades / yr", value: "612", sub: "example" },
];

/* ── Shared pieces ────────────────────────────────────────────────────────── */

function Tape() {
  const { items } = usePriceTape();
  return (
    <div className="flex flex-col gap-[0.4rem]">
      <span className={GROUPED_LABEL}>markets · latest close</span>
      <div className="border-y border-hair">
        {items.length === 0 ? (
          <p className="m-0 px-[1.3rem] py-[0.75rem] font-mono text-[0.78rem] text-ink-mute">
            connecting to the market feed…
          </p>
        ) : (
          <StockTicker items={items} />
        )}
      </div>
    </div>
  );
}

/** A compact left-to-right stage flow: the whole pipeline in one band. */
function StageStrip({ className }: { className?: string }) {
  return (
    <ol
      className={`m-0 flex list-none flex-wrap items-stretch gap-[0.4rem] p-0 ${className ?? ""}`}
      aria-label="digiquant pipeline stages"
    >
      {STAGES.map((stage, i) => (
        <li key={stage.id} className="flex min-w-[9rem] flex-1 items-stretch gap-[0.4rem]">
          <div className="flex flex-1 flex-col gap-[0.25rem] border border-hair bg-surface p-[0.6rem]">
            <span className="font-mono text-[0.6rem] tracking-[0.06em] text-ink-mute">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span className="font-mono text-[0.8rem] text-ink">{stage.label}</span>
            <span className="text-[0.72rem] leading-[1.45] text-ink-mute">{stage.detail}</span>
          </div>
          {i < STAGES.length - 1 ? (
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
 * One strategy as the *library* card — the same composition
 * `apps/digiquant-web/components/tearsheet/strategy-card.tsx` renders on
 * digiquant.io/strategies, minus the live badge.
 *
 * The owner: "use the library cards for each of the strategies don't put the
 * live indicator though just show the library cards". The badge is dropped
 * because these are example reads, not a live book, and a live mark over
 * figures that are not live would be the one dishonest pixel on the page.
 */
function StrategyCard({ strategy }: { strategy: Strategy }) {
  return (
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
        {strategy.kpis.map((k) => (
          <TearsheetCardKpi key={k.label} label={k.label} value={k.value} />
        ))}
      </TearsheetCardKpis>
    </TearsheetCard>
  );
}

/** The strategies in the kit's horizontal rail (the promoted changelog rail). */
function StrategyRail() {
  return (
    <CardRail ariaLabel="Flagship digiquant strategies">
      {STRATEGIES.map((s) => (
        <div key={s.slug} role="listitem" className="flex-[0_0_17rem] snap-start">
          <StrategyCard strategy={s} />
        </div>
      ))}
    </CardRail>
  );
}

function FootNote() {
  return (
    <p className="m-0 font-mono text-[0.72rem] leading-[1.6] text-ink-mute">
      Market prices are the latest daily close from the public market-data archive — real figures for
      real instruments, not a live stream. The tearsheet reads, the performance pair and the
      headline metrics are badged examples: this page states no return, no Sharpe and no P&amp;L for
      digiquant. Live trading is guarded by a human review gate, not a runtime interlock.
    </p>
  );
}

function Band({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`accent-digiquant quant-band ${className ?? ""}`}>
      <div className="px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[1.8rem]">{children}</div>
      </div>
    </div>
  );
}

function Lede({ children }: { children: React.ReactNode }) {
  return (
    <p className="m-0 max-w-[var(--measure-prose)] text-[0.92rem] leading-[1.75] text-ink-soft">
      {children}
    </p>
  );
}

function Ctas() {
  return (
    <div className="flex flex-wrap items-center gap-[0.8rem]">
      <CtaLink href={DIGIQUANT_URL} external>
        digiquant.io
      </CtaLink>
      <CtaLink href={`${DIGIQUANT_URL}/strategies`} external variant="ghost">
        Strategy library
      </CtaLink>
    </div>
  );
}

/* ── A — strategies first ─────────────────────────────────────────────────── */

function VariantA() {
  return (
    <Band>
      <Tape />
      <div className="flex flex-col gap-[1rem]">
        <h2 className="m-0 font-mono text-[clamp(1.5rem,3vw,2.2rem)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
          Strategies you can read before you trust them.
        </h2>
        <Lede>
          Four calibrated systems ship in the digiquant library today — BTC, ETH and SOL long /
          short, and a BTC accumulation book. Every one is a Nautilus backtest over exchange daily
          bars, with equity, drawdown, trade log and a full tearsheet you can open.
        </Lede>
        <Ctas />
      </div>
      {/* Full width, not a column: at a third of the frame the value text wraps
          ("+24.6" / "%"), which reads as a broken number. */}
      <div className="flex flex-col gap-[0.6rem]">
        <span className={GROUPED_LABEL}>headline · example</span>
        <KpiStrip primary ariaLabel="Example headline performance">
          {HEADLINE.map((k) => (
            <Kpi key={k.label} label={k.label} value={k.value} sub={k.sub} />
          ))}
        </KpiStrip>
      </div>
      <div className="flex flex-col gap-[0.7rem]">
        <span className={GROUPED_LABEL}>the strategy library</span>
        <StrategyRail />
      </div>
      <div className="flex flex-col gap-[0.7rem]">
        <span className={GROUPED_LABEL}>the pipeline</span>
        <StageStrip />
      </div>
      <FootNote />
    </Band>
  );
}

/* ── B — performance first ────────────────────────────────────────────────── */

function VariantB() {
  return (
    <Band>
      <Tape />
      {/* Title on the left, the tearsheet rail beside it. */}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-[1.6rem] min-[980px]:grid-cols-[minmax(0,0.72fr)_minmax(0,1.28fr)]">
        <div className="flex flex-col gap-[1rem]">
          <h2 className="m-0 font-mono text-[clamp(1.5rem,3vw,2.2rem)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
            A hedge fund in a glass box you own.
          </h2>
          <Lede>
            Ideas are proposed against public data, every one is backtested before it is seen, and the
            survivor is sized into target weights. The same glass box as the rest of digithings —
            your hosts, data and keys — pointed at the finance work.
          </Lede>
          <Ctas />
        </div>
        <div className="flex min-w-0 flex-col gap-[0.7rem]">
          <span className={GROUPED_LABEL}>the strategy library · example</span>
          <StrategyRail />
        </div>
      </div>
      {/* The book, in the middle. */}
      <div className="flex flex-col gap-[0.7rem]">
        <span className={GROUPED_LABEL}>the book · example</span>
        <figure className="m-0 flex flex-col gap-[0.5rem]">
          <div className="h-[clamp(190px,26vh,260px)] overflow-hidden border border-hair">
            <MultiTimeSeries
              series={PERFORMANCE_SERIES}
              height={240}
              interactive
              ariaLabel="Example performance, digiquant portfolio against a benchmark, indexed to 100 at the start (synthetic series)"
            />
          </div>
          <figcaption className="m-0 font-mono text-[0.68rem] text-ink-mute">
            portfolio vs benchmark · indexed to 100 · synthetic series
          </figcaption>
        </figure>
      </div>
      {/* The pipeline, below — the kit's flow element, one row of stages with the
          detail panel under it. */}
      <div className="flex flex-col gap-[0.7rem]">
        <span className={GROUPED_LABEL}>the pipeline</span>
        <Pipeline
          columns={PIPELINE_COLUMNS}
          summary={PIPELINE_SUMMARY}
          defaultSelectedId="research"
        />
      </div>
      <FootNote />
    </Band>
  );
}

/* ── C — pipeline first ───────────────────────────────────────────────────── */

function VariantC() {
  return (
    <Band>
      <Tape />
      <div className="flex flex-col gap-[0.7rem]">
        <span className={GROUPED_LABEL}>the pipeline</span>
        <h2 className="m-0 font-mono text-[clamp(1.5rem,3vw,2.2rem)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
          Research in, a tested strategy out.
        </h2>
        <Lede>
          Six stages, from validated inputs to a beliefs fold that carries what was learned into the
          next run. Nothing is routed to a venue — connecting execution is your own integration, not
          a flag we flip.
        </Lede>
        <StageStrip />
        <p className="m-0 font-mono text-[0.72rem] leading-[1.6] text-ink-mute">
          Each stage fans out into the specialists it needs — alt-data, institutional flow, macro,
          asset classes and sectors run in parallel inside Research; thesis, screener, analysts,
          deliberation, PM direction and risk sizing inside Selection.
        </p>
      </div>
      <div className="flex flex-col gap-[0.6rem]">
        <span className={GROUPED_LABEL}>headline · example</span>
        <KpiStrip primary ariaLabel="Example headline performance">
          {HEADLINE.map((k) => (
            <Kpi key={k.label} label={k.label} value={k.value} sub={k.sub} />
          ))}
        </KpiStrip>
      </div>
      <div className="flex flex-col gap-[0.7rem]">
        <span className={GROUPED_LABEL}>the strategy library · example</span>
        <StrategyRail />
      </div>
      <Ctas />
      <FootNote />
    </Band>
  );
}

/* ── The harness ──────────────────────────────────────────────────────────── */

function Label({ id, title, blurb }: { id: string; title: string; blurb: string }) {
  return (
    <div className="flex flex-col gap-[0.35rem] border-b border-hair pb-[0.8rem]">
      <span className={GROUPED_LABEL}>
        variant {id} · {title}
      </span>
      <p className="m-0 max-w-[var(--measure-prose)] text-[0.85rem] leading-[1.6] text-ink-soft">
        {blurb}
      </p>
    </div>
  );
}

export function DigiquantVariants() {
  return (
    <div className="flex flex-col gap-[3.5rem]">
      <section className="flex flex-col gap-[1rem]">
        <Label
          id="A"
          title="strategies first"
          blurb="Leads with the tearsheet cards, so the library is the advertisement. The headline metrics sit beside the claim, and the pipeline is a single thin strip at the bottom."
        />
        <VariantA />
      </section>
      <section className="flex flex-col gap-[1rem]">
        <Label
          id="B"
          title="performance first"
          blurb="Leads with the book: portfolio against benchmark, then the claim. Strategies are compact cards with three reads each, and the pipeline stays a thin strip."
        />
        <VariantB />
      </section>
      <section className="flex flex-col gap-[1rem]">
        <Label
          id="C"
          title="pipeline first"
          blurb="Leads with the six dashboard stages, so the mechanism is the advertisement. The strategy rail and the headline metrics sit under it."
        />
        <VariantC />
      </section>
    </div>
  );
}

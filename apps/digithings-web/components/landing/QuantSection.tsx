"use client";

import { Fragment, useState } from "react";
import {
  CtaLink,
  PRICE_CHART_DEMO,
  PerfMetrics,
  PriceChart,
  StockTicker,
  type PerfMetric,
} from "@digithings/ui";
import { usePriceTape } from "@/lib/priceTape";
import { GROUPED_LABEL } from "./label";

/**
 * The digiquant band (v15 point 9, #4429; reworked in round 3).
 *
 * The owner's direction: "I'd build out the digiquant section properly… a
 * different background to stand out… If you took the digiquant website and
 * compressed it in the same way… that's what I want to see", and in round 3:
 * "make the background of the digiquant section expand the full width… it could
 * be its own section with its own background… I'd keep it simple, sweet, just as
 * a little view into the flagship product… And then if you click through every
 * step, you see what it does… we don't have to explain how strategies are built
 * in detail. We could just show a few of the flagship strategy metrics and
 * tearsheets, and links to the strategy page."
 *
 * So the band is full-bleed — the section in LandingPage carries no horizontal
 * padding, and this component paints digiquant's own livery and its own tinted
 * background (`accent-digiquant` + `.quant-band`) edge to edge while the content
 * stays on the page's frame.
 *
 * ROUND 3 CHANGES, and why:
 *  - the header bar is gone. It was a chrome strip naming the module, and the
 *    claim below it already says what the band is; a banner that only labels the
 *    card is one more thing between the reader and the product.
 *  - the pipeline is a click-through flow, not a node graph with node
 *    diagnostics. Selecting a stage shows what it actually does, plus its inputs
 *    and outputs, in the product's own vocabulary — and the stage ids are now
 *    described mechanics rather than internal component names.
 *  - the strategy block is a small library row with links out to the real
 *    tearsheets, instead of prose explaining how strategies are built.
 *
 * HONESTY (binding). The market tape is REAL: the latest daily close and the
 * real prior-session change for the majors, read from the public market-data
 * archive, labelled `markets · latest close` rather than anything that would
 * imply streaming. Everything else is illustrative — the candle chart, the
 * example tearsheet and the strategy cards — and the band's footnote says so
 * without hedging. Nothing here is a digiquant result: no return, no Sharpe and
 * no P&L is stated for the product.
 */

const DIGIQUANT_URL = "https://digiquant.io";

/** A tearsheet's grade block, from the shared demo walk — labelled as example. */
const TEARSHEET: PerfMetric[] = [
  { label: "CAGR", value: "24.6%", tone: "up" },
  { label: "Sharpe", value: "1.34" },
  { label: "Sortino", value: "1.88" },
  { label: "Max drawdown", value: "-18.2%", tone: "down" },
  { label: "Win rate", value: "56.0%" },
  { label: "Profit factor", value: "1.72" },
];

/**
 * The pipeline as four stages a reader can walk. `note` is what the stage does,
 * `inputs`/`outputs` are what it consumes and hands on — the whole point being
 * that clicking a stage tells you something you could not guess from its name.
 * No internal component name appears here.
 */
const FLOW: { id: string; label: string; note: string; inputs: string; outputs: string }[] = [
  {
    id: "propose",
    label: "propose",
    note: "An idea is formed against public macro and market data. No private order flow and no broker feed goes in, so the direction is explainable from sources anyone can point at.",
    inputs: "public macro + market data",
    outputs: "candidate directions",
  },
  {
    id: "backtest",
    label: "backtest",
    note: "The candidate is run over history before a number is shown to anyone. A result that only exists in the sample it was fitted to is not treated as a result.",
    inputs: "candidate + price history",
    outputs: "fills",
  },
  {
    id: "optimize",
    label: "optimize",
    note: "Parameters are searched over a declared space rather than hand-tuned, so the fit is reproducible and anyone can re-run it against the same window.",
    inputs: "candidate + parameter space",
    outputs: "chosen parameters",
  },
  {
    id: "size",
    label: "size",
    note: "The survivor becomes target weights, held until the rules fire. Nothing is routed to a venue — connecting execution is a separate, deliberate step, not a flag.",
    inputs: "validated signal",
    outputs: "target weights",
  },
];

/**
 * The first four strategies the library shipped. `slug` is the real public
 * slug, so the link lands on that strategy's own tearsheet rather than the
 * catalog — the figures live there, where they are the real ones.
 */
const FLAGSHIP: { slug: string; label: string; symbol: string; kind: string }[] = [
  { slug: "btc_slapper", label: "BTC Slapper", symbol: "BTC", kind: "long / short" },
  { slug: "eth_slapper", label: "ETH Slapper", symbol: "ETH", kind: "long / short" },
  { slug: "sol_slapper", label: "SOL Slapper", symbol: "SOL", kind: "long / short" },
  { slug: "btc_sdca", label: "BTC DCA", symbol: "BTC", kind: "accumulation" },
];

/**
 * The market tape. Empty until the read lands, and muted rather than blank when
 * it cannot — a strip that flashes an error would make decoration look load-bearing.
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

/** The four-stage flow: a rail you click, and a panel that answers. */
function Flow() {
  const [selected, setSelected] = useState<string>(FLOW[0].id);
  const stage = FLOW.find((entry) => entry.id === selected) ?? FLOW[0];

  return (
    <div className="flex min-w-0 flex-col gap-[1rem]">
      <div
        role="tablist"
        aria-label="digiquant pipeline stages"
        className="flex flex-wrap items-center gap-[0.5rem]"
      >
        {FLOW.map((entry, i) => (
          <Fragment key={entry.id}>
            {i > 0 ? (
              <span aria-hidden className="font-mono text-[0.8rem] text-ink-mute">
                →
              </span>
            ) : null}
            <button
              type="button"
              role="tab"
              id={`flow-tab-${entry.id}`}
              aria-selected={selected === entry.id}
              aria-controls="flow-panel"
              onClick={() => setSelected(entry.id)}
              className={`border px-[0.7rem] py-[0.35rem] font-mono text-[0.78rem] transition-colors duration-200 ${
                selected === entry.id
                  ? "border-accent bg-surface-2 text-ink"
                  : "border-hair text-ink-soft hover:border-ink-mute hover:text-ink"
              }`}
            >
              <span className="mr-[0.4rem] text-ink-mute">
                {String(i + 1).padStart(2, "0")}
              </span>
              {entry.label}
            </button>
          </Fragment>
        ))}
      </div>

      <div
        role="tabpanel"
        id="flow-panel"
        aria-labelledby={`flow-tab-${stage.id}`}
        className="grid gap-[1rem] border border-hair bg-surface p-[1rem] min-[760px]:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]"
      >
        <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
          {stage.note}
        </p>
        <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] content-start gap-x-[1rem] gap-y-[0.5rem] font-mono text-[0.74rem]">
          <dt className="text-ink-mute">in</dt>
          <dd className="m-0 text-ink-soft">{stage.inputs}</dd>
          <dt className="text-ink-mute">out</dt>
          <dd className="m-0 text-ink-soft">{stage.outputs}</dd>
        </dl>
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

          {/* Explicit single column at the base, exactly like the Boot band: the
              chart bakes the pane's pixel width into its own canvases at first
              measurement, so below 980px an implicit `auto` track would size
              itself from that min-content and blow the page wider than the
              viewport. minmax(0,1fr) + min-w-0 on each column pins the track to
              the container, and the chart's autoSize re-measures to fit. */}
          <div className="grid grid-cols-[minmax(0,1fr)] gap-[2rem] min-[980px]:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] min-[980px]:gap-[2.4rem]">
            {/* Left: the claim, in digiquant's own voice. */}
            <div className="flex min-w-0 flex-col gap-[1.2rem]">
              {/* `h2`, not `h3`: this band has no other heading, so an `h3` left
                  the document outline skipping a level between `#open-source`
                  and `#pricing`. Every other band's `h2` is its claim rather than
                  its product name, so the claim is the band's heading. The
                  bespoke size is kept: this is a product band, deliberately below
                  the page's section stand. */}
              <h2 className="m-0 font-mono text-[clamp(1.4rem,2.6vw,2rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink">
                A hedge fund in a glass box you own.
              </h2>
              <p className="m-0 max-w-[var(--measure-prose)] text-[0.92rem] leading-[1.75] text-ink-soft">
                digiquant is the module that shows what the rest of the stack is for. Ideas are
                proposed against public data, every one is backtested before it is seen, and the
                survivor is sized into target weights. It is the same glass box as the rest of
                digithings — your hosts, your data, your keys — pointed at the finance work.
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

            {/* Right: the operator surface — chart and tearsheet. */}
            <div className="flex min-w-0 flex-col gap-[1.2rem]">
              {/* PriceChart's host is `h-full w-full` and its pane auto-sizes, so
                  it needs a definite-height parent or it collapses to a sliver.
                  The pane also clips: the chart's baked canvases must never be
                  allowed to push this figure's min-content past the track. */}
              <figure className="m-0 flex min-w-0 flex-col gap-[0.5rem]">
                <div className="h-[clamp(170px,22vh,230px)] overflow-hidden border border-hair">
                  <PriceChart
                    candles={PRICE_CHART_DEMO.candles}
                    volume={PRICE_CHART_DEMO.volume}
                    label="Example instrument — daily candles and volume (synthetic series)"
                  />
                </div>
                <figcaption className="font-mono text-[0.68rem] text-ink-mute">
                  example instrument · daily candles + volume · synthetic series
                </figcaption>
              </figure>

              <div className="flex flex-col gap-[0.8rem]">
                <span className={GROUPED_LABEL}>example tearsheet</span>
                {/*
                  Three columns, not the primitive's default four. There are six
                  metrics, so four columns filled the first row and left the
                  second two-thirds empty — two 145x97 panels of the container's
                  own background sitting under SORTINO and MAX DRAWDOWN, which
                  reads as an unfinished grid. Three columns give two even rows of
                  three. The alternative, padding the set to eight metrics, would
                  mean inventing figures to fill space, which is the thing this
                  band's own footnote disavows.
                */}
                <PerfMetrics metrics={TEARSHEET} columns={3} />
              </div>
            </div>
          </div>

          <div className="flex min-w-0 flex-col gap-[1rem]">
            <span className={GROUPED_LABEL}>the pipeline</span>
            <Flow />
          </div>

          <div className="flex min-w-0 flex-col gap-[1rem]">
            <span className={GROUPED_LABEL}>the strategy library</span>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-[0.7rem]">
              {FLAGSHIP.map((strategy) => (
                <a
                  key={strategy.slug}
                  href={`${DIGIQUANT_URL}/strategies/${strategy.slug}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex min-w-0 flex-col gap-[0.4rem] border border-hair bg-surface p-[0.9rem] no-underline transition-colors duration-200 hover:border-ink-mute"
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

          <p className="m-0 font-mono text-[0.72rem] leading-[1.6] text-ink-mute">
            Market prices above are the latest daily close from the public market-data archive —
            real figures for real instruments, not a live stream. The candle chart, the example
            tearsheet and the strategy cards are illustrative: this page states no return, no Sharpe
            and no P&amp;L for digiquant. Live trading is guarded by a human review gate, not a
            runtime interlock.
          </p>
        </div>
      </div>
    </div>
  );
}

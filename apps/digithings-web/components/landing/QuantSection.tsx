"use client";

import {
  CtaLink,
  Emblem,
  LiveBadge,
  PRICE_CHART_DEMO,
  PerfMetrics,
  Pipeline,
  PriceChart,
  StockTicker,
  type PerfMetric,
  type PipelineColumn,
  type TickerItem,
} from "@digithings/ui";
import { GROUPED_LABEL } from "./label";

/**
 * The digiquant band (v15 point 9, #4429).
 *
 * The owner's direction (v15): "I'd build out the digiquant section properly…
 * a different background to stand out, an animated candle chart or banner with
 * prices, tear-sheet data, the pipeline, some live metrics — even just a light
 * form. If you took the digiquant website and compressed it in the same way…
 * that's what I want to see."
 *
 * So this is deliberately a *foreign* band: it wears digiquant's own livery
 * (`.accent-digiquant`, phosphor cyan) and a tinted background no other section
 * has, and it shows the operator surface — a market tape, a candle chart, a
 * tearsheet grade block and the research → portfolio pipeline.
 *
 * HONESTY (binding). Every price and metric below is a *synthetic demo series*
 * from the shared primitives (`PRICE_CHART_DEMO`, and a demo tearsheet walk) —
 * not a real quote and not a real strategy result. The badge and the footnote
 * say so without hedging, and the pipeline diagnostics are all em dashes. There
 * is no real return, Sharpe or P&L anywhere in this file.
 */

const DIGIQUANT_URL = "https://digiquant.io";

/** Market tape — demo quotes only. Carries the honesty badge below the strip. */
const TAPE: TickerItem[] = [
  { symbol: "BTC-PERP", last: "63,410", change: "1.24%", up: true },
  { symbol: "ETH-PERP", last: "3,088", change: "0.62%", up: true },
  { symbol: "SOL-PERP", last: "142.60", change: "2.10%", up: false },
  { symbol: "SPY", last: "548.21", change: "0.31%", up: true },
  { symbol: "NVDA", last: "121.44", change: "3.44%", up: true },
  { symbol: "AAPL", last: "229.87", change: "0.18%", up: false },
  { symbol: "GOLD", last: "2,410.5", change: "0.22%", up: true },
  { symbol: "US10Y", last: "4.281%", change: "0.05%", up: false },
];

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
 * The research → portfolio flow, as stage names. Every diagnostic string is a
 * dash by design; nothing here is a measured figure.
 */
const QUANT_PIPELINE: PipelineColumn[] = [
  {
    id: "research",
    kind: "step",
    nodes: [
      {
        id: "propose",
        label: "propose",
        status: "done",
        ms: "—",
        tokens: "—",
        model: "digigraph",
        inputs: "public macro + market data",
        outputs: "candidate directions",
        cost: "—",
      },
    ],
  },
  {
    id: "validate",
    kind: "parallel",
    label: "parallel · 2",
    nodes: [
      {
        id: "backtest",
        label: "backtest",
        status: "done",
        ms: "—",
        tokens: "—",
        model: "nautilus",
        inputs: "candidate + dataset",
        outputs: "fills",
        cost: "—",
      },
      {
        id: "optimize",
        label: "optimize",
        status: "done",
        ms: "—",
        tokens: "—",
        model: "optuna",
        inputs: "candidate + space",
        outputs: "parameters",
        cost: "—",
      },
    ],
  },
  {
    id: "portfolio",
    kind: "step",
    nodes: [
      {
        id: "size",
        label: "size",
        status: "done",
        ms: "—",
        tokens: "—",
        model: "digiquant",
        inputs: "validated signal",
        outputs: "target weights",
        cost: "—",
      },
    ],
  },
];

/** The four steps, in the product's own vocabulary. */
const STEPS: [string, string][] = [
  ["propose", "an idea is formed against public macro and market data"],
  ["backtest", "NautilusTrader runs it on history before you see a number"],
  ["optimize", "parameters are searched over the space, not hand-tuned"],
  ["size", "the survivor becomes target weights, held until the rules fire"],
];

export function QuantSection({ className }: { className?: string }) {
  return (
    <div className={`accent-digiquant quant-band ${className ?? ""}`}>
      <div className="mx-auto max-w-[var(--frame-w)] border border-hair bg-surface">
        {/* Header bar — digiquant's own chrome, like a terminal pane. */}
        <div className="flex flex-wrap items-center justify-between gap-[0.8rem] border-b border-hair px-[1rem] py-[0.6rem]">
          <span className={`flex items-center gap-[0.5rem] ${GROUPED_LABEL}`}>
            <Emblem id="digiquant" size={14} />
            digiquant
          </span>
          <span className="flex items-center gap-[0.6rem]">
            <LiveBadge label="example" ariaLabel="Example data, not live" />
            <span className={`${GROUPED_LABEL} text-ink-mute normal-case`}>
              demo series · no real figures
            </span>
          </span>
        </div>

        {/* Market tape — the strip that makes the band read as a trading surface. */}
        <div className="border-b border-hair">
          <StockTicker items={TAPE} />
        </div>

        {/* Explicit single column at the base, exactly like the Boot band: the
            chart bakes the pane's pixel width into its own canvases at first
            measurement, so below 980px an implicit `auto` track would size
            itself from that min-content and blow the page wider than the
            viewport. minmax(0,1fr) + min-w-0 on each column pins the track to
            the container, and the chart's autoSize re-measures to fit. */}
        <div className="grid grid-cols-[minmax(0,1fr)] gap-[2rem] p-[1.4rem] min-[980px]:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] min-[980px]:gap-[2.4rem]">
          {/* Left: the claim, in digiquant's own voice. */}
          <div className="flex min-w-0 flex-col gap-[1.2rem]">
            {/* `h2`, not `h3`: this band has no other heading, so an `h3` left
                the document outline skipping a level between `#open-source`
                and `#pricing`. Every other band's `h2` is its claim rather than
                its product name, so the claim is the band's heading and the
                brand chip in the header bar stays a span — it labels the card's
                chrome, not the document section. The bespoke size is kept: this
                is a framed product card, deliberately below the page's section
                stand. */}
            <h2 className="m-0 font-mono text-[clamp(1.4rem,2.6vw,2rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink">
              A hedge fund in a glass box you own.
            </h2>
            <p className="m-0 max-w-[var(--measure-prose)] text-[0.92rem] leading-[1.75] text-ink-soft">
              digiquant is the module that shows what the rest of the stack is for. Ideas are
              proposed against public data, every one is backtested through NautilusTrader before it
              is seen, and the survivor is sized into target weights. It is the same glass box as the
              rest of digithings — your hosts, your data, your keys — pointed at the finance work.
            </p>

            <ol className="m-0 grid list-none gap-[0.7rem] p-0">
              {STEPS.map(([name, note], i) => (
                <li key={name} className="flex gap-[0.8rem] border-t border-hair pt-[0.7rem]">
                  <span className="font-mono text-[0.72rem] text-ink-mute">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="min-w-0">
                    <span className="font-mono text-[0.85rem] text-ink">{name}</span>
                    <span className="mt-[0.2rem] block text-[0.82rem] leading-[1.6] text-ink-soft">
                      {note}
                    </span>
                  </span>
                </li>
              ))}
            </ol>

            <div className="flex flex-wrap items-center gap-[0.8rem] pt-[0.4rem]">
              <CtaLink href={DIGIQUANT_URL} external>
                digiquant.io
              </CtaLink>
              <CtaLink href="/docs" variant="ghost">
                Read the docs
              </CtaLink>
            </div>
            <p className="m-0 font-mono text-[0.72rem] leading-[1.6] text-ink-mute">
              Every quote and metric shown here is a synthetic example series, not a real result —
              this page states no return, no Sharpe and no P&amp;L for digiquant. Live trading is
              guarded by a human review gate, not a runtime interlock.
            </p>
          </div>

          {/* Right: the operator surface — chart, tearsheet, pipeline. */}
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

            <div className="flex min-w-0 flex-col gap-[1rem]">
              <span className={GROUPED_LABEL}>the flow</span>
              <Pipeline columns={QUANT_PIPELINE} defaultSelectedId="backtest" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

"use client";

/**
 * Spark specimens — Sparkline, StatusDot, StatusStrip, CompositionBar and Donut from
 * @digithings/ui, live. All SVG/CSS, presentational: data comes in by props.
 * Health uses accent/warn/ink-mute; up/down stay reserved for P&L.
 */
import { useState } from "react";

import {
  CompositionBar,
  Donut,
  Sparkline,
  StatusDot,
  StatusStrip,
} from "@digithings/ui/ui";

const SERIES = [4, 5, 4.5, 6, 7, 6.5, 8, 9, 8.5, 10];
const GAPPED = [4, 5, null, null, 6, 7, 6.5, 8, null, 9];
const RUNS = Array.from({ length: 24 }, (_, i) => ({
  key: `run-${i}`,
  label: `run ${i + 1}`,
  tone: i === 7 ? ("warn" as const) : i > 20 ? ("off" as const) : ("ok" as const),
}));
const MIX = [
  { label: "Equity", value: 52 },
  { label: "Credit", value: 21 },
  { label: "Gold", value: 9 },
  { label: "Cash", value: 18, cash: true },
];

export function SparkReference() {
  const [picked, setPicked] = useState("none");

  return (
    <section className="section-block" id="spark">
      <p className="kicker">{"// spark"}</p>
      <h2 className="title">Small marks that carry state.</h2>
      <p className="section-copy">
        <code>Sparkline</code>, <code>StatusDot</code>, <code>StatusStrip</code> and{" "}
        <code>CompositionBar</code> — inline SVG/CSS, no canvas, no fetching. Null values break the
        line into gaps; health tones are accent, warn and mute, never the P&amp;L pair.
      </p>

      <div className="mt-[1.2rem] grid gap-[1.2rem] border border-hair p-4 font-mono text-[0.78rem] text-ink-soft">
        <div className="flex flex-wrap items-center gap-6">
          <Sparkline values={SERIES} />
          <Sparkline values={SERIES} area tone="up" />
          <Sparkline values={GAPPED} tone="ink" />
          <Sparkline values={[]} />
          <span className="inline-flex items-center gap-2">
            <StatusDot label="live" /> live
            <StatusDot tone="warn" label="degraded" /> degraded
            <StatusDot tone="off" label="off" /> off
            <StatusDot tone="idle" label="idle" /> idle
          </span>
        </div>
        <div>
          <p className="mb-1.5">run strip (hover a cell, or click)</p>
          <StatusStrip cells={RUNS} onSelect={(c) => setPicked(c.label)} />
          <p className="mt-1 text-ink-mute">selected: {picked}</p>
        </div>
        <div>
          <p className="mb-1.5">composition (share) with cash</p>
          <CompositionBar segments={MIX} legend onSelect={(s) => setPicked(s.label)} />
        </div>
        <div>
          <p className="mb-1.5">donut with ranked legend (hover an arc or row)</p>
          <Donut segments={MIX}>
            <span className="text-lg font-semibold text-ink">82%</span>
            <span className="text-[10px] uppercase tracking-widest text-ink-mute">invested</span>
          </Donut>
        </div>
      </div>
    </section>
  );
}

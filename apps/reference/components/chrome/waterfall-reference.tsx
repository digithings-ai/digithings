"use client";

/**
 * Waterfall specimen — the attribution bridge (signed steps, P&L colours) and
 * the call trace (start + duration rows, health colours), from
 * @digithings/ui/ui.
 */
import { useState } from "react";

import { WaterfallBridge, WaterfallTrace } from "@digithings/ui/ui";

export function WaterfallReference() {
  const [sel, setSel] = useState<string | null>("score");
  return (
    <section className="section-block">
      <p className="kicker">{"// waterfall"}</p>
      <h2 className="title">Bridges and call traces.</h2>
      <p className="section-copy">
        <code>WaterfallBridge</code> walks signed steps between totals; sign colour is P&amp;L by
        default. <code>WaterfallTrace</code> draws spans by start and duration and uses health
        tones (accent, warn, ink-mute) only.
      </p>
      <WaterfallBridge
        steps={[
          { label: "Start", value: 100, kind: "total" },
          { label: "Equity", value: 6.4 },
          { label: "Rates", value: -2.1 },
          { label: "FX", value: 1.3 },
          { label: "Fees", value: -0.8 },
          { label: "End", value: 104.8, kind: "total" },
        ]}
        label="Attribution bridge"
      />
      <WaterfallTrace
        selectedId={sel}
        onSelect={setSel}
        rows={[
          { id: "run", label: "pipeline.run", start: 0, duration: 940 },
          { id: "load", label: "load_prices", start: 10, duration: 180, depth: 1 },
          { id: "score", label: "score_models", start: 200, duration: 520, depth: 1, status: "warn" },
          { id: "cache", label: "cache_hit", start: 210, duration: 40, depth: 2, status: "mute" },
          { id: "write", label: "write_book", start: 730, duration: 200, depth: 1 },
        ]}
        formatDuration={(n) => `${n}ms`}
        label="Pipeline call trace"
      />
    </section>
  );
}

"use client";

import { useState } from "react";
import { MarketBar, type MarketBarCell, type MarketBarStatus } from "@digithings/ui";
import { Button } from "@digithings/ui/ui";

/**
 * Market bar — the specimen for the shared <MarketBar/> (@digithings/ui,
 * finance-composites): the terminal status line built on the Marquee. The badge
 * reads "live" only for status live; the other states show a muted bracketed
 * word; with no cells the bar says `connecting…` and invents nothing. The strip
 * is aria-hidden with a plain-text sr summary and aria-live off; a pause control
 * stops the loop; a tick flashes a cell by opacity alone; only the signed change
 * wears the money colors. Cells here are obviously synthetic sample values, not
 * a feed — every real consumer supplies its own labelled data.
 */
const SAMPLE: MarketBarCell[] = [
  { symbol: "AAA", value: "1,000.00", changePct: 0.5 },
  { symbol: "BBB", value: "250.00", changePct: -0.25 },
  { symbol: "CCC", value: "12.50", changePct: 0 },
  { symbol: "DDD", value: "80.00", changePct: 1.2, asOf: "as of 01-01", source: "sample close" },
  { symbol: "EEE", value: null },
];

const STATUSES: MarketBarStatus[] = ["connecting", "live", "stale", "offline"];

export function MarketBarReference() {
  const [status, setStatus] = useState<MarketBarStatus>("live");
  const [empty, setEmpty] = useState(false);
  const [tick, setTick] = useState(0);

  const cells = empty
    ? []
    : SAMPLE.map((c) => (c.symbol === "AAA" ? { ...c, flashKey: tick } : c));

  return (
    <section className="section-block" id="market-bar">
      <p className="kicker">{"// market bar"}</p>
      <h2 className="title">A status line that never invents a price.</h2>
      <p className="section-copy">
        The terminal strip for a live market tool: feed status on the left, the tape in the
        middle, an optional clock and a pause control on the right. Switch the feed state to see
        the badge stay honest, empty the tape to see the empty state, or send a tick to see the
        opacity flash. Sample values are placeholders.
      </p>

      <div className="mt-[1.2rem] border border-hair px-3">
        <MarketBar
          cells={cells}
          status={status}
          trailing="00:00Z"
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {STATUSES.map((s) => (
          <Button
            key={s}
            size="sm"
            variant={status === s ? "default" : "outline"}
            aria-pressed={status === s}
            onClick={() => setStatus(s)}
          >
            {s}
          </Button>
        ))}
        <Button size="sm" variant="outline" aria-pressed={empty} onClick={() => setEmpty((e) => !e)}>
          {empty ? "restore tape" : "empty tape"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => setTick((t) => t + 1)} disabled={empty}>
          send tick
        </Button>
      </div>
    </section>
  );
}

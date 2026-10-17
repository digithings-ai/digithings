"use client";

import { MarketBar, type MarketBarCell } from "@digithings/ui";
import { displaySymbol, useMarketBar, type MarketCell } from "@/lib/live/market-bar";

/** Price strip at the top of the tearsheets band. Only symbols with a quote
 *  scroll. The tape is treated as live, so it never prints an as-of date. */
function toCell(c: MarketCell): MarketBarCell {
  const quoted = Number.isFinite(c.price) && c.price > 0;
  return {
    symbol: displaySymbol(c.symbol),
    value: quoted ? c.value : null,
    changePct: quoted ? c.changePct : null,
    source: !quoted ? undefined : c.kind === "crypto" ? "exchange ticker" : "daily close archive",
  };
}

export function MarketBarShell() {
  const { cells, status } = useMarketBar();
  return (
    <div className="min-w-0 border-b border-hair">
      <MarketBar
        className="w-full px-3"
        cells={cells.map((c) => toCell(c))}
        status={status}
      />
    </div>
  );
}

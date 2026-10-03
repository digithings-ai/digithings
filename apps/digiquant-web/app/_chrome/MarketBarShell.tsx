"use client";

import { MarketBar, type MarketBarCell } from "@digithings/ui";
import { displaySymbol, useMarketBar, type MarketCell } from "@/lib/live/market-bar";

/** Price strip at the top of the tearsheets band. Renders the baseline universe.
 *  A symbol with no quote is an em dash for the price and the percent. Crypto
 *  spots that are ticking omit the as-of stamp; dated closes keep theirs. */
function toCell(c: MarketCell, live: boolean): MarketBarCell {
  const crypto = c.kind === "crypto";
  const quoted = Number.isFinite(c.price) && c.price > 0;
  return {
    symbol: displaySymbol(c.symbol),
    value: quoted ? c.value : null,
    changePct: quoted ? c.changePct : null,
    asOf: !quoted || !c.stamp || (crypto && live) ? undefined : c.stamp,
    source: !quoted ? undefined : crypto ? "exchange ticker" : "daily close archive",
  };
}

export function MarketBarShell() {
  const { cells, status } = useMarketBar();
  return (
    <div className="min-w-0 border border-hair">
      <MarketBar
        className="w-full px-3"
        cells={cells.map((c) => toCell(c, status === "live"))}
        status={status}
      />
    </div>
  );
}

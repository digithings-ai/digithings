"use client";

import { MarketBar, type MarketBarCell } from "@digithings/ui";
import { displaySymbol, useMarketBar, type MarketCell } from "@/lib/live/market-bar";

/** Chrome price strip under the nav. Renders only what useMarketBar returns:
 *  SSR and the first client render are empty (`connecting…`), so no price ever
 *  appears before a real feed delivers one. Crypto is the Coinbase public
 *  websocket; SPY/QQQ are dated closes and always carry their as-of stamp.
 *  Crypto cells add a stamp only once the feed is no longer live. */
function toCell(c: MarketCell, live: boolean): MarketBarCell {
  const crypto = c.kind === "crypto";
  return {
    symbol: displaySymbol(c.symbol),
    value: c.value,
    changePct: c.changePct,
    asOf: crypto && live ? undefined : c.stamp,
    source: crypto ? "Coinbase Exchange, live ticker" : "daily close archive",
    flashKey: crypto ? c.asOf : undefined,
  };
}

export function MarketBarShell() {
  const { cells, status } = useMarketBar();
  return (
    <div className="relative z-10 border-b border-hair">
      <MarketBar
        className="mx-auto w-full max-w-[var(--frame-w)] px-[var(--page-pad)]"
        cells={cells.map((c) => toCell(c, status === "live"))}
        status={status}
      />
    </div>
  );
}

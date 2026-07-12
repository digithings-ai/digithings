"use client";
/**
 * LiveTickerRow (#1461/#1462) — the market-pulse strip under the hero. A thin
 * client island that feeds live quotes into ONE shared @digithings/web
 * <StockTicker/> tape (finance-composites, tk-*): a single scrolling row
 * carrying crypto (Coinbase's keyless public WS, streams client-side regardless
 * of Supabase config) followed by the equity/ETF majors (seeded from the
 * daily-close view with its real prior-session change, live intraday during US
 * hours over the "prices:live" broadcast). One band, both asset classes — the
 * crypto ticks 24/7; the majors show their last daily move until the market
 * opens (user ruling 2026-07-12).
 *
 * The tape is the ONE marquee that legitimately wears the money colors: a
 * price change IS the up/down semantic (StockTicker colors from TickerItem.up
 * only — never a module accent).
 *
 * SSR/static-export safe: useLivePrices opens no sockets during render, so at
 * prerender (and before the first quote arrives) the tape is empty and the band
 * shows a single muted "connecting" line — never blank, never a crash. Crypto
 * lights up within a beat on the client; the majors seed as soon as the public
 * env vars are set.
 */
import { StockTicker, fmtNum, fmtPct, type TickerItem } from "@digithings/web";
import { useLivePrices, type LivePriceMap } from "@/lib/live";
import { symbolBase } from "@/components/tearsheet/strategy-names";

// Coinbase-streamable spot pairs (the keyless WS lane). The stored -USD
// universe (ticker_venues.py) also holds BNB/TRX/XMR/SUI20947-USD, which are
// NOT Coinbase products: they would be rejected on subscribe and could only
// ever seed a permanently-stale close, so a *live* tape drops them (a decision,
// not an omission — see the task summary). Order is the display order.
const CRYPTO_PRODUCTS: string[] = [
  "BTC-USD",
  "ETH-USD",
  "SOL-USD",
  "XRP-USD",
  "DOGE-USD",
  "ADA-USD",
  "AVAX-USD",
  "LINK-USD",
  "DOT-USD",
  "BCH-USD",
  "LTC-USD",
  "ATOM-USD",
  "NEAR-USD",
];

// Curated liquid majors spanning the macro book's lenses — broad cap, rates,
// the dollar, developed + EM, credit, gold. Seeded from public_price_latest;
// live during US market hours via the equity broadcast.
const EQUITY_MAJORS: string[] = [
  "SPY",
  "QQQ",
  "DIA",
  "IWM",
  "GLD",
  "TLT",
  "UUP",
  "EFA",
  "EEM",
  "HYG",
];

/** Adaptive precision so a $63k BTC and a $0.07 DOGE both read cleanly. */
function fmtTapePrice(price: number): string {
  const a = Math.abs(price);
  if (a >= 1000) return fmtNum(price, 0);
  if (a >= 1) return fmtNum(price, 2);
  return fmtNum(price, 4);
}

/** Map a symbol list → StockTicker rows, in order, skipping any with no quote. */
function toTickerItems(
  symbols: string[],
  quotes: LivePriceMap,
  display: (symbol: string) => string,
): TickerItem[] {
  const items: TickerItem[] = [];
  for (const symbol of symbols) {
    const q = quotes[symbol];
    if (!q) continue;
    items.push({
      symbol: display(symbol),
      last: fmtTapePrice(q.price),
      // Magnitude only — StockTicker draws the ▲/▼ and the color from `up`.
      change: fmtPct(Math.abs(q.changePct)),
      up: q.up,
    });
  }
  return items;
}

export function LiveTickerRow() {
  const quotes = useLivePrices({ symbols: EQUITY_MAJORS, cryptoProductIds: CRYPTO_PRODUCTS });
  // One tape: crypto first (always live), then the majors — a single scrolling
  // row across both asset classes.
  const items = [
    ...toTickerItems(CRYPTO_PRODUCTS, quotes, symbolBase),
    ...toTickerItems(EQUITY_MAJORS, quotes, (s) => s),
  ];

  return (
    <section aria-label="Live market prices" className="border-y border-hair">
      {items.length === 0 ? (
        <p className="m-0 px-[1.3rem] py-[0.75rem] font-mono text-[0.78rem] text-ink-mute">
          <span className="text-[0.6rem] uppercase tracking-[0.14em]">markets</span>
          <span className="px-3 text-hair" aria-hidden="true">
            |
          </span>
          connecting to the live feed…
        </p>
      ) : (
        <div className="flex items-stretch">
          <span className="flex items-center border-r border-hair bg-surface px-[1.1rem] font-mono text-[0.6rem] uppercase tracking-[0.14em] text-ink-mute">
            markets
          </span>
          <StockTicker items={items} className="flex-1" />
        </div>
      )}
    </section>
  );
}

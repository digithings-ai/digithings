"use client";
/**
 * LiveTickerRow (#1461/#1462) — the market-pulse strip under the hero. A thin
 * client island that feeds live quotes into the shared @digithings/web
 * <StockTicker/> tape (finance-composites, tk-*). Two labeled rows keep the
 * asset classes legible: a crypto tape (Coinbase's keyless public WS, streams
 * client-side regardless of Supabase config) and a markets tape (equity/ETF
 * majors — seeded from the daily-close view, live during US hours over the
 * "prices:live" broadcast).
 *
 * The tape is the ONE marquee that legitimately wears the money colors: a
 * price change IS the up/down semantic (StockTicker colors from TickerItem.up
 * only — never a module accent). No per-item "live" indicator: seeds are stale
 * (flat, source="seed") and must not masquerade as a live tick.
 *
 * SSR/static-export safe: useLivePrices opens no sockets during render, so at
 * prerender (and before the first tick / when the feed is dark) both tapes are
 * empty and the band shows a single muted "connecting" line — never blank,
 * never a crash. Crypto lights up within a beat on the client; equities follow
 * once the public env vars are set (a human deploy step).
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

function TapeRow({ label, items }: { label: string; items: TickerItem[] }) {
  return (
    <div className="flex items-stretch">
      <span className="flex items-center border-y border-r border-hair bg-surface px-[1.1rem] font-mono text-[0.6rem] uppercase tracking-[0.14em] text-ink-mute">
        {label}
      </span>
      <StockTicker items={items} className="flex-1" />
    </div>
  );
}

export function LiveTickerRow() {
  const quotes = useLivePrices({ symbols: EQUITY_MAJORS, cryptoProductIds: CRYPTO_PRODUCTS });
  const crypto = toTickerItems(CRYPTO_PRODUCTS, quotes, symbolBase);
  const equities = toTickerItems(EQUITY_MAJORS, quotes, (s) => s);
  const empty = crypto.length === 0 && equities.length === 0;

  return (
    <section aria-label="Live market prices">
      {empty ? (
        <p className="m-0 border-y border-hair px-[1.3rem] py-[0.75rem] font-mono text-[0.78rem] text-ink-mute">
          <span className="uppercase tracking-[0.14em] text-[0.6rem]">markets</span>
          <span className="px-3 text-hair" aria-hidden="true">
            |
          </span>
          connecting to the live feed…
        </p>
      ) : (
        <>
          {crypto.length > 0 ? <TapeRow label="crypto" items={crypto} /> : null}
          {equities.length > 0 ? <TapeRow label="markets" items={equities} /> : null}
        </>
      )}
    </section>
  );
}

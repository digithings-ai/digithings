/**
 * Order book — the exchange-grade depth ladder: asks descending into the spread,
 * a mid/spread divider, then bids below. Each row carries a depth bar scaled to
 * resting size and tinted by side. Sell side wears down, buy side up — the money
 * colors, never a livery. Mono tabular numerals so prices never jitter. Consumes
 * the shared <OrderBook/> primitive from @digithings/web. Static display
 * template.
 */
import { OrderBook, type OrderBookLevel } from "@digithings/web";

// Illustrative depth around a mid of ~92.40.
const ASKS: OrderBookLevel[] = [
  { price: 92.61, size: 12 },
  { price: 92.55, size: 34 },
  { price: 92.5, size: 21 },
  { price: 92.46, size: 58 },
  { price: 92.43, size: 40 },
];
const BIDS: OrderBookLevel[] = [
  { price: 92.38, size: 47 },
  { price: 92.35, size: 29 },
  { price: 92.31, size: 63 },
  { price: 92.26, size: 18 },
  { price: 92.2, size: 38 },
];

export function OrderbookReference() {
  return (
    <section className="section-block orderbook">
      <p className="kicker">{"// order book"}</p>
      <h2 className="title">Depth, ask over bid.</h2>
      <p className="section-copy">
        The exchange-grade ladder: asks descending into the spread, bids below, each row a depth
        bar scaled to resting size. Sell side wears <code>--down</code>, buy side{" "}
        <code>--up</code> — the money colors, never a livery. Mono numerals, tabular so prices
        never jitter.
      </p>

      <OrderBook asks={ASKS} bids={BIDS} mid="92.40" className="mt-[1.2rem] max-w-[380px]" />
    </section>
  );
}

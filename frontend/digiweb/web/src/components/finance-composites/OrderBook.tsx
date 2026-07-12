/**
 * OrderBook — the exchange-grade depth ladder promoted from the design
 * reference (finance/order-book): asks descending into the spread, a
 * mid/spread divider, bids below. Each row carries a depth bar scaled to the
 * largest resting size and tinted by side — sell side wears --down, buy side
 * --up: the money colors, never a livery. Mono tabular numerals so prices
 * never jitter. Server component — no state, no effects; token utilities
 * only, so it needs nothing from styles/finance-composites.css (still
 * `@source` this directory so the utilities are generated).
 *
 * Data convention (top to bottom, as rendered): `asks` descend INTO the
 * spread (last element = best ask); `bids` descend AWAY from it (first
 * element = best bid). `mid` and `spread` derive from that touch when
 * omitted. Width is the call site's business (e.g. `max-w-[380px]`).
 */
export type OrderBookLevel = {
  price: number;
  size: number;
};

export type OrderBookProps = {
  /** Sell side, rendered top-down toward the spread (last = best ask). */
  asks: OrderBookLevel[];
  /** Buy side, rendered top-down away from the spread (first = best bid). */
  bids: OrderBookLevel[];
  /** Preformatted mid read for the divider; midpoint of the touch when omitted. */
  mid?: string;
  /** Preformatted spread read; best ask − best bid when omitted. */
  spread?: string;
  /** Price formatter for derived reads and level prices. */
  formatPrice?: (price: number) => string;
  /** Mono micro-caps column headers. */
  priceLabel?: string;
  sizeLabel?: string;
  /** Label ahead of the spread read on the divider. */
  spreadLabel?: string;
  /** Extra classes on the board shell (margins, max-width …). */
  className?: string;
};

function Row({
  level,
  side,
  peak,
  formatPrice,
}: {
  level: OrderBookLevel;
  side: "ask" | "bid";
  peak: number;
  formatPrice: (price: number) => string;
}) {
  const depth = `${(level.size / peak) * 100}%`;
  const ask = side === "ask";
  return (
    <div className="relative flex justify-between overflow-hidden px-4 py-[0.28rem] text-[0.78rem]">
      {/* depth bar fills from the right, tinted by side (money colors) */}
      <span
        className={`absolute inset-y-0 right-0 z-0 ${ask ? "bg-down/[0.14]" : "bg-up/[0.14]"}`}
        style={{ width: depth }}
        aria-hidden="true"
      />
      <span className={`relative z-[1] ${ask ? "text-down" : "text-up"}`}>
        {formatPrice(level.price)}
      </span>
      <span className="relative z-[1] text-ink-soft">{level.size}</span>
    </div>
  );
}

export function OrderBook({
  asks,
  bids,
  mid,
  spread,
  formatPrice = (price) => price.toFixed(2),
  priceLabel = "price",
  sizeLabel = "size",
  spreadLabel = "spread",
  className,
}: OrderBookProps) {
  const bestAsk = asks[asks.length - 1]?.price ?? 0;
  const bestBid = bids[0]?.price ?? 0;
  const midText = mid ?? formatPrice((bestAsk + bestBid) / 2);
  const spreadText = spread ?? formatPrice(bestAsk - bestBid);
  const peak = Math.max(1, ...asks.map((l) => l.size), ...bids.map((l) => l.size));

  return (
    <div
      className={`rounded-[12px] border border-hair bg-surface py-2 font-mono [font-variant-numeric:tabular-nums]${
        className ? ` ${className}` : ""
      }`}
    >
      <div className="flex justify-between border-b border-hair px-4 pb-2 pt-[0.3rem] text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
        <span>{priceLabel}</span>
        <span>{sizeLabel}</span>
      </div>
      <div>
        {asks.map((l) => (
          <Row key={l.price} level={l} side="ask" peak={peak} formatPrice={formatPrice} />
        ))}
      </div>
      <div className="my-[0.2rem] flex items-baseline justify-between border-y border-hair px-4 py-2">
        <span className="text-base text-ink">{midText}</span>
        <span className="text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
          {spreadLabel} {spreadText}
        </span>
      </div>
      <div>
        {bids.map((l) => (
          <Row key={l.price} level={l} side="bid" peak={peak} formatPrice={formatPrice} />
        ))}
      </div>
    </div>
  );
}

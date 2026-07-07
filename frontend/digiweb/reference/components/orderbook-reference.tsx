/**
 * Order book — the exchange-grade depth ladder: asks descending into the spread,
 * a mid/spread divider, then bids below. Each row carries a depth bar scaled to
 * resting size and tinted by side. Sell side wears down, buy side up — the money
 * colors, never a livery. Mono tabular numerals so prices never jitter. Static
 * display template.
 */
type Level = { price: number; size: number };

// Illustrative depth around a mid of ~92.40.
const ASKS: Level[] = [
  { price: 92.61, size: 12 },
  { price: 92.55, size: 34 },
  { price: 92.5, size: 21 },
  { price: 92.46, size: 58 },
  { price: 92.43, size: 40 },
];
const BIDS: Level[] = [
  { price: 92.38, size: 47 },
  { price: 92.35, size: 29 },
  { price: 92.31, size: 63 },
  { price: 92.26, size: 18 },
  { price: 92.2, size: 38 },
];

const peak = Math.max(...[...ASKS, ...BIDS].map((l) => l.size));

function Row({ level, side }: { level: Level; side: "ask" | "bid" }) {
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
        {level.price.toFixed(2)}
      </span>
      <span className="relative z-[1] text-ink-soft">{level.size}</span>
    </div>
  );
}

export function OrderbookReference() {
  const spread = (ASKS[ASKS.length - 1].price - BIDS[0].price).toFixed(2);
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

      <div className="mt-[1.2rem] max-w-[380px] rounded-[12px] border border-hair bg-surface py-2 font-mono [font-variant-numeric:tabular-nums]">
        <div className="flex justify-between border-b border-hair px-4 pb-2 pt-[0.3rem] text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
          <span>price</span>
          <span>size</span>
        </div>
        <div>
          {ASKS.map((l) => (
            <Row key={l.price} level={l} side="ask" />
          ))}
        </div>
        <div className="my-[0.2rem] flex items-baseline justify-between border-y border-hair px-4 py-2">
          <span className="text-base text-ink">92.40</span>
          <span className="text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
            spread {spread}
          </span>
        </div>
        <div>
          {BIDS.map((l) => (
            <Row key={l.price} level={l} side="bid" />
          ))}
        </div>
      </div>
    </section>
  );
}

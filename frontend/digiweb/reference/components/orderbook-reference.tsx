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
  return (
    <div className={`ob-row ob-${side}`}>
      <span className="ob-depth" style={{ width: depth }} aria-hidden="true" />
      <span className="ob-price">{level.price.toFixed(2)}</span>
      <span className="ob-size">{level.size}</span>
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

      <div className="ob-shell">
        <div className="ob-head">
          <span>price</span>
          <span>size</span>
        </div>
        <div className="ob-side">
          {ASKS.map((l) => (
            <Row key={l.price} level={l} side="ask" />
          ))}
        </div>
        <div className="ob-spread">
          <span className="ob-mid">92.40</span>
          <span className="ob-spread-label">spread {spread}</span>
        </div>
        <div className="ob-side">
          {BIDS.map((l) => (
            <Row key={l.price} level={l} side="bid" />
          ))}
        </div>
      </div>
    </section>
  );
}

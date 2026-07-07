/**
 * Performance dashboard — the portfolio at a glance: a value/return headline,
 * a strip of aggregate ratios, and an allocation-by-strategy breakdown. Sits
 * above the single-strategy tearsheet metrics: this is the whole book. P&L
 * reads wear the money colors; ratios stay ink; the allocation bars take the
 * accent (teal on the digiquant-scoped Finance page). Static display template.
 */
const RATIOS = [
  { k: "sharpe", v: "2.31" },
  { k: "sortino", v: "3.10" },
  { k: "max drawdown", v: "−18.4%", tone: "down" },
  { k: "win rate", v: "58%" },
  { k: "profit factor", v: "2.31" },
  { k: "exposure", v: "0.62×" },
];

const ALLOC = [
  { name: "trend_xsec", pct: 42 },
  { name: "carry", pct: 28 },
  { name: "mean_rev", pct: 18 },
  { name: "pairs", pct: 12 },
];

export function PerformanceDashboardReference() {
  return (
    <section className="section-block" id="performance">
      <p className="kicker">{"// performance"}</p>
      <h2 className="title">The portfolio at a glance.</h2>
      <p className="section-copy">
        The book-level dashboard above the single-strategy tearsheet: headline value and return,
        the aggregate risk ratios, and where the capital actually sits. P&amp;L reads take the money
        colors; the allocation bars wear the accent.
      </p>

      <div className="pdash">
        <div className="pdash-head">
          <div className="pdash-hero">
            <span className="pdash-label">portfolio value</span>
            <span className="pdash-value">$1.284M</span>
            <span className="pdash-delta up">+$5.47K · +0.43% today</span>
          </div>
          <div className="pdash-hero pdash-hero--alt">
            <span className="pdash-label">total return</span>
            <span className="pdash-value up">+28.4%</span>
            <span className="pdash-sub">since inception · 2y</span>
          </div>
        </div>

        <div className="pdash-ratios">
          {RATIOS.map((r) => (
            <div key={r.k} className="pdash-ratio">
              <span className="pdash-ratio-k">{r.k}</span>
              <span className={`pdash-ratio-v${r.tone === "down" ? " down" : ""}`}>{r.v}</span>
            </div>
          ))}
        </div>

        <div className="pdash-alloc">
          <p className="pdash-alloc-label">allocation by strategy</p>
          {ALLOC.map((a) => (
            <div key={a.name} className="alloc-row">
              <span className="alloc-name">{a.name}</span>
              <span className="alloc-bar">
                <span className="alloc-fill" style={{ width: `${a.pct}%` }} />
              </span>
              <span className="alloc-pct">{a.pct}%</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

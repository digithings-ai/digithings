type Metric = { label: string; value: string; tone?: "up" | "down" };

// A tearsheet's metric block — the numbers that grade a strategy.
const METRICS: Metric[] = [
  { label: "CAGR", value: "+44.9%", tone: "up" },
  { label: "Sharpe", value: "1.82" },
  { label: "Sortino", value: "2.41" },
  { label: "Max drawdown", value: "-54.1%", tone: "down" },
  { label: "Win rate", value: "64.9%" },
  { label: "Profit factor", value: "2.31" },
  { label: "Volatility", value: "38.2%" },
  { label: "Exposure", value: "71.4%" },
];

export function PerfMetricsReference() {
  return (
    <section className="section-block perf-metrics">
      <p className="kicker">{"// performance metrics"}</p>
      <h2 className="title">The grade, at a glance.</h2>
      <p className="section-copy">
        A tearsheet&apos;s metric block: labels in mono micro-caps, values in large tabular
        numerals, and only the ones that carry money meaning — return and drawdown — take the
        <code> --up</code> / <code>--down</code> semantics. Everything else stays ink so the eye
        goes to what matters.
      </p>

      <div className="perf-grid">
        {METRICS.map((m) => (
          <div key={m.label} className="perf-metric">
            <span className="perf-metric-label">{m.label}</span>
            <span className={`perf-metric-value${m.tone ? ` ${m.tone}` : ""}`}>{m.value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * Performance metrics — a tearsheet's grade block: labels in mono micro-caps,
 * values in large tabular numerals, laid out on a four-up hairline grid. Only the
 * reads that carry money meaning — return and drawdown — take the up / down
 * money colors; everything else stays ink so the eye goes to what matters.
 * Static display template.
 */
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

      {/* Container + typography migrated to token-backed utilities; the .perf-metric
          base class stays so the :nth-child hairline-border grid (finance.css) still
          matches. Money colors (text-up/text-down) only on return + drawdown. */}
      <div className="mt-[1.2rem] grid grid-cols-4 overflow-hidden rounded-[12px] border border-hair bg-surface max-[720px]:grid-cols-2">
        {METRICS.map((m) => (
          <div key={m.label} className="perf-metric p-[1.2rem]">
            <span className="block font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
              {m.label}
            </span>
            <span
              className={`mt-[0.35rem] block font-mono text-[1.5rem] [font-variant-numeric:tabular-nums] ${
                m.tone === "up" ? "text-up" : m.tone === "down" ? "text-down" : "text-ink"
              }`}
            >
              {m.value}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

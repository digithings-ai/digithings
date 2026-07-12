/**
 * Performance metrics — a tearsheet's grade block: labels in mono micro-caps,
 * values in large tabular numerals, laid out on a four-up hairline grid. Only the
 * reads that carry money meaning — return and drawdown — take the up / down
 * money colors; everything else stays ink so the eye goes to what matters.
 * Consumes the shared <PerfMetrics/> primitive from @digithings/web.
 * Static display template.
 */
import { PerfMetrics, type PerfMetric } from "@digithings/web";

// A tearsheet's metric block — the numbers that grade a strategy.
const METRICS: PerfMetric[] = [
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
    <section className="section-block perf-metrics-section">
      <p className="kicker">{"// performance metrics"}</p>
      <h2 className="title">The grade, at a glance.</h2>
      <p className="section-copy">
        A tearsheet&apos;s metric block: labels in mono micro-caps, values in large tabular
        numerals, and only the ones that carry money meaning — return and drawdown — take the
        <code> --up</code> / <code>--down</code> semantics. Everything else stays ink so the eye
        goes to what matters.
      </p>

      <PerfMetrics metrics={METRICS} className="mt-[1.2rem]" />
    </section>
  );
}

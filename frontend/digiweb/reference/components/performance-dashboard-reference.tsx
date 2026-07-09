/**
 * Performance dashboard — the portfolio at a glance: a value/return headline,
 * a strip of aggregate ratios, and an allocation-by-strategy breakdown. Sits
 * above the single-strategy tearsheet metrics: this is the whole book. P&L
 * reads wear the money colors; ratios stay ink; the allocation bars take the
 * accent (teal on the digiquant-scoped Finance page). Consumes the shared
 * <PerformanceDashboard/> primitive from @digithings/web. Static display
 * template.
 */
import {
  PerformanceDashboard,
  type DashboardAllocation,
  type DashboardHeadline,
  type DashboardRatio,
} from "@digithings/web";

const HEADLINES: DashboardHeadline[] = [
  { label: "portfolio value", value: "$1.284M", note: "+$5.47K · +0.43% today", noteTone: "up" },
  { label: "total return", value: "+28.4%", tone: "up", note: "since inception · 2y" },
];

const RATIOS: DashboardRatio[] = [
  { label: "sharpe", value: "2.31" },
  { label: "sortino", value: "3.10" },
  { label: "max drawdown", value: "−18.4%", tone: "down" },
  { label: "win rate", value: "58%" },
  { label: "profit factor", value: "2.31" },
  { label: "exposure", value: "0.62×" },
];

const ALLOC: DashboardAllocation[] = [
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

      <PerformanceDashboard
        headlines={HEADLINES}
        ratios={RATIOS}
        allocations={ALLOC}
        className="mt-[1.2rem]"
      />
    </section>
  );
}

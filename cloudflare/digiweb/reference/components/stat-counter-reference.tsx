/**
 * Stat counter — a metric strip whose figures count up from zero the first time
 * the strip scrolls into view, the one place a number earns a little motion. The
 * running value is written straight to the DOM node (no per-frame re-render);
 * mono, tabular numerals keep the digits from reflowing. Fires once; reduced
 * motion and no-JS both show the final figure immediately. Consumes the shared
 * <StatCounter/> primitive from @digithings/web. Interactive display template.
 */
import { StatCounter, type CounterStat } from "@digithings/web";

const STATS: CounterStat[] = [
  { value: 8.72, decimals: 2, label: "profit factor" },
  { value: 75.9, decimals: 1, suffix: "%", label: "win rate" },
  { value: 3102, label: "backtests run" },
  { value: 12, label: "modules" },
];

export function StatCounterReference() {
  return (
    <section className="section-block stat-counter-section">
      <p className="kicker">{"// stat counter"}</p>
      <h2 className="title">Numbers that arrive.</h2>
      <p className="section-copy">
        A metric strip that counts up from zero once it scrolls into view — the one place a number
        earns a little motion. Mono numerals, hairline dividers, tabular so the digits never
        reflow. Fires once; reduced motion and no-JS both show the final figure immediately.
      </p>

      <StatCounter stats={STATS} className="mt-[1.2rem]" />
    </section>
  );
}

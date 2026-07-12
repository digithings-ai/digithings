/**
 * Odometer counter — the mechanical digit-roll (Revolut's sleek counters), the
 * companion to the count-up stat. Each digit is a 0–9 reel; on scroll-into-view
 * every reel rolls to its target with a staggered delay. Non-digit characters
 * ($ , . %) sit static between reels. The whole figure carries an aria-label so
 * screen readers read the value once; reels are decorative. Reduced motion and
 * no-JS both show the settled value (SSR ships the reels on their final digit).
 * Consumes the shared <OdometerStrip/> primitive from @digithings/web.
 * Interactive display template.
 */
import { OdometerStrip, type OdometerStat } from "@digithings/web";

const STATS: OdometerStat[] = [
  { label: "equity under test", value: "$1,284,000" },
  { label: "backtests run", value: "3,102" },
  { label: "profit factor", value: "2.31" },
  { label: "modules", value: "12" },
];

export function OdometerReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// odometer"}</p>
      <h2 className="title">Numbers that roll into place.</h2>
      <p className="section-copy">
        The mechanical counterpart to the count-up: each digit is a reel that rolls to its value
        when the figure scrolls into view, staggered left to right. Separators (<code>$ , .</code>)
        stay put; the value is announced once via <code>aria-label</code>. Reduced motion sets it
        without the roll.
      </p>

      <OdometerStrip stats={STATS} className="mt-[1.2rem]" />
    </section>
  );
}
